from __future__ import annotations

from base64 import b64encode
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from inspect import isawaitable
from typing import Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.application.policies.budget import BudgetGuard
from due_diligence_agent.application.policies.data_egress import (
    DataEgressDenied,
    DataEgressPolicy,
    DisclosureScope,
    EgressFragment,
)
from due_diligence_agent.application.policies.model_routing import ModelRoutingPolicy
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.ports.llm import (
    CodeInterpreterResult,
    LLMBudgetRequest,
    LLMRoutingContext,
    LLMUsage,
)
from due_diligence_agent.ports.repositories import ArtifactStore
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool, TraceContext, TraceSanitizer


class AsyncResponsesCreateClient(Protocol):
    async def create(self, **kwargs: object) -> object: ...


class GeneratedFileClient(Protocol):
    async def list_generated_files(self, container_id: str) -> tuple["GeneratedContainerFile", ...]: ...

    async def read_bytes(self, *, container_id: str | None, file_id: str) -> bytes: ...


class OpenAICodeInterpreterAuditError(RuntimeError):
    stable_error_code = "AUDIT_PERSISTENCE_ERROR"


class OpenAICodeInterpreterMetadataError(RuntimeError):
    stable_error_code = "METADATA_SANITIZATION_ERROR"


class OpenAICodeInterpreterGeneratedFileError(RuntimeError):
    stable_error_code = "GENERATED_FILE_PERSISTENCE_ERROR"


class CodeInterpreterArtifactInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    content: bytes
    media_type: str
    sensitivity: SensitivityClass
    redacted: bool
    minimized: bool
    redaction_policy_version: str


class OpenAICodeInterpreterAdapter:
    def __init__(
        self,
        *,
        responses_client: AsyncResponsesCreateClient,
        egress_policy: DataEgressPolicy,
        routing_policy: ModelRoutingPolicy,
        budget_guard: BudgetGuard,
        audit_spool: AuditSpool,
        artifact_store: ArtifactStore,
        container_file_client: GeneratedFileClient,
        destination: str = "openai.code_interpreter",
        sanitizer: TraceSanitizer | None = None,
    ) -> None:
        self._responses = responses_client
        self._egress_policy = egress_policy
        self._routing_policy = routing_policy
        self._budget_guard = budget_guard
        self._audit_spool = audit_spool
        self._artifact_store = artifact_store
        self._destination = destination
        self._sanitizer = sanitizer or StrictTraceSanitizer()
        self._container_file_client = container_file_client

    async def run_public_analysis(
        self,
        artifact: CodeInterpreterArtifactInput,
        *,
        code: str,
        budget_request: LLMBudgetRequest,
        routing_context: LLMRoutingContext,
        trace_context: TraceContext,
        disclosure_scope: DisclosureScope | None = None,
    ) -> CodeInterpreterResult:
        decision = self._egress_policy.evaluate(
            [
                EgressFragment(
                    id=artifact.id,
                    sensitivity=artifact.sensitivity,
                    redacted=artifact.redacted,
                    minimized=artifact.minimized,
                    redaction_policy_version=artifact.redaction_policy_version,
                )
            ],
            destination=self._destination,
            disclosure_scope=disclosure_scope,
        )
        if not decision.allowed:
            raise DataEgressDenied(decision)
        model = self._routing_policy.select(routing_context)
        reservation = self._budget_guard.reserve(budget_request, attempt="code_interpreter")
        try:
            metadata = self._metadata(trace_context, model.model)
        except ValueError as exc:
            self._budget_guard.release(reservation)
            raise OpenAICodeInterpreterMetadataError("METADATA_SANITIZATION_ERROR") from exc
        try:
            self._audit_spool.append(_disclosure_event(trace_context, model.model, metadata))
        except Exception as exc:
            self._budget_guard.release(reservation)
            raise OpenAICodeInterpreterAuditError("AUDIT_PERSISTENCE_ERROR") from exc

        source_hash = sha256(artifact.content).hexdigest()
        try:
            code_hash = sha256(code.encode("utf-8")).hexdigest()
            code_artifact = self._artifact_store.put_bytes(
                code.encode("utf-8"),
                media_type="text/x-python",
                source_snapshot_hash=source_hash,
                sensitivity=artifact.sensitivity,
            )
        except Exception:
            self._budget_guard.release(reservation)
            raise
        try:
            response = await self._responses.create(
                model=model.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Run the supplied code over the approved artifact. Return provisional analysis only.",
                            },
                            {
                                "type": "input_file",
                                "filename": f"{artifact.id}{_extension_for_media_type(artifact.media_type)}",
                                "file_data": _data_url(artifact),
                            },
                            {"type": "input_text", "text": code},
                        ],
                    }
                ],
                tools=[
                    {
                        "type": "code_interpreter",
                        "container": {"type": "auto", "network_policy": {"type": "disabled"}},
                    }
                ],
                tool_choice="required",
                store=False,
                include=["code_interpreter_call.outputs"],
                metadata=metadata,
            )
        except Exception:
            self._budget_guard.reconcile(reservation, usage=None)
            raise
        usage = _usage_from_response(response)
        self._budget_guard.reconcile(reservation, usage=usage)
        try:
            generated = await self._persist_generated_files(
                response,
                source_hash=source_hash,
                sensitivity=artifact.sensitivity,
            )
            output = _provisional_output_payload(response, generated)
            stored = self._artifact_store.put_bytes(
                output,
                media_type="text/plain",
                source_snapshot_hash=source_hash,
                sensitivity=artifact.sensitivity,
            )
        except Exception as exc:
            raise OpenAICodeInterpreterGeneratedFileError("GENERATED_FILE_PERSISTENCE_ERROR") from exc
        return CodeInterpreterResult(
            provisional=True,
            code_hash=code_hash,
            code_artifact_id=code_artifact.artifact_id,
            output_artifact_id=stored.artifact_id,
            output_hash=stored.content_hash,
            generated_artifact_ids=tuple(item.artifact_id for item in generated),
            canonical_calculation_ids=(),
        )

    def _metadata(self, trace_context: TraceContext, model: str) -> dict[str, str]:
        safe = self._sanitizer.sanitize_attributes(
            {
                "case_id": trace_context.case_id,
                "correlation_id": trace_context.correlation_id,
                "provider": "openai",
                "model": model,
                "status": "approved",
            }
        )
        return {key: str(value) for key, value in safe.items() if value is not None}

    async def _persist_generated_files(
        self,
        response: object,
        *,
        source_hash: str,
        sensitivity: SensitivityClass,
    ) -> tuple[StoredGeneratedArtifact, ...]:
        stored: list[StoredGeneratedArtifact] = []
        for generated_file in await _generated_files(response, self._container_file_client):
            payload = await self._container_file_client.read_bytes(
                container_id=generated_file.container_id,
                file_id=generated_file.file_id,
            )
            if sha256(payload).hexdigest() == source_hash:
                continue
            artifact = self._artifact_store.put_bytes(
                payload,
                media_type=generated_file.media_type,
                source_snapshot_hash=source_hash,
                sensitivity=sensitivity,
            )
            stored.append(
                StoredGeneratedArtifact(
                    artifact_id=artifact.artifact_id,
                    content_hash=artifact.content_hash,
                    byte_size=artifact.byte_size,
                    media_type=artifact.media_type,
                )
            )
        return tuple(stored)


class GeneratedContainerFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    container_id: str | None
    file_id: str
    filename: str
    media_type: str
    source: str = "assistant"


class StoredGeneratedArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    content_hash: str
    byte_size: int
    media_type: str


def _usage_from_response(response: object) -> LLMUsage | None:
    usage = getattr(response, "usage", None)
    if isinstance(usage, Mapping):
        return _usage_from_values(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    if usage is None:
        return None
    return _usage_from_values(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


def _usage_from_values(
    *,
    input_tokens: object,
    output_tokens: object,
    total_tokens: object,
) -> LLMUsage | None:
    try:
        if total_tokens is None:
            return None
        return LLMUsage(
            input_tokens=_token_int(input_tokens, default=0),
            output_tokens=_token_int(output_tokens, default=0),
            total_tokens=_token_int(total_tokens),
        )
    except (TypeError, ValueError):
        return None


def _token_int(value: object, *, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise TypeError("missing token value")
        return default
    if isinstance(value, str | bytes | bytearray):
        return int(value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value)
    raise TypeError("invalid token value")


def _data_url(artifact: CodeInterpreterArtifactInput) -> str:
    encoded = b64encode(artifact.content).decode("ascii")
    return f"data:{artifact.media_type};base64,{encoded}"


def _extension_for_media_type(media_type: str) -> str:
    normalized = media_type.split(";", 1)[0].strip().lower()
    return {
        "text/csv": ".csv",
        "application/csv": ".csv",
        "application/json": ".json",
        "application/pdf": ".pdf",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "text/x-python": ".py",
    }.get(normalized, ".bin")


class OpenAIContainerFileContentClient:
    def __init__(self, client: object) -> None:
        self._client = client

    async def list_generated_files(self, container_id: str) -> tuple[GeneratedContainerFile, ...]:
        containers = _field(self._client, "containers")
        container_files = _field(containers, "files")
        list_method = _field(container_files, "list")
        if not callable(list_method):
            raise TypeError("missing containers.files.list")
        page = list_method(container_id=container_id)
        page = await _maybe_await(page)
        files: list[GeneratedContainerFile] = []
        async for item in _async_iter_items(page):
            files.append(
                GeneratedContainerFile(
                    container_id=_string_field(item, "container_id") or container_id,
                    file_id=_string_field(item, "id") or _string_field(item, "file_id") or "",
                    filename=_generated_filename(item),
                    media_type=_string_field(item, "media_type")
                    or _string_field(item, "mime_type")
                    or _media_type_for_filename(_generated_filename(item)),
                    source=_string_field(item, "source") or "",
                )
            )
        return tuple(file for file in files if file.file_id)

    async def read_bytes(self, *, container_id: str | None, file_id: str) -> bytes:
        if container_id is not None:
            containers = _field(self._client, "containers")
            container_files = _field(containers, "files")
            content = _field(container_files, "content")
            retrieve = _field(content, "retrieve")
            if not callable(retrieve):
                raise TypeError("missing containers.files.content.retrieve")
            response = await _maybe_await(retrieve(container_id=container_id, file_id=file_id))
        else:
            files = _field(self._client, "files")
            content = _field(files, "content")
            if not callable(content):
                raise TypeError("missing files.content")
            response = await _maybe_await(content(file_id))
        read = _field(response, "read")
        if not callable(read):
            raise TypeError("missing binary response read")
        payload = await _maybe_await(read())
        if not isinstance(payload, bytes):
            raise TypeError("binary response read must return bytes")
        return payload


async def _generated_files(
    response: object,
    client: GeneratedFileClient,
) -> tuple[GeneratedContainerFile, ...]:
    by_file_id: dict[str, GeneratedContainerFile] = {}
    for container_id in _code_interpreter_container_ids(response):
        for listed in await client.list_generated_files(container_id):
            normalized = _normalize_generated_file(listed, default_container_id=container_id)
            if normalized.source != "assistant":
                continue
            by_file_id[normalized.file_id] = normalized
    for citation in _generated_file_refs(response):
        if citation.file_id in by_file_id:
            continue
        by_file_id[citation.file_id] = citation
    return tuple(by_file_id.values())


def _normalize_generated_file(
    value: object,
    *,
    default_container_id: str | None,
) -> GeneratedContainerFile:
    filename = _generated_filename(value)
    return GeneratedContainerFile(
        container_id=_string_field(value, "container_id") or default_container_id,
        file_id=_string_field(value, "file_id") or _string_field(value, "id") or "",
        filename=filename,
        media_type=_string_field(value, "media_type") or _string_field(value, "mime_type") or _media_type_for_filename(filename),
        source=_string_field(value, "source") or "assistant",
    )


def _code_interpreter_container_ids(response: object) -> tuple[str, ...]:
    container_ids: list[str] = []
    seen: set[str] = set()
    for output_item in _iter_items(_field(response, "output")):
        if _string_field(output_item, "type") not in {None, "code_interpreter_call"}:
            continue
        container_id = _string_field(output_item, "container_id")
        if container_id and container_id not in seen:
            seen.add(container_id)
            container_ids.append(container_id)
    return tuple(container_ids)


def _generated_file_refs(response: object) -> tuple[GeneratedContainerFile, ...]:
    citations: list[GeneratedContainerFile] = []
    for output_item in _iter_items(_field(response, "output")):
        for content_item in _iter_items(_field(output_item, "content")):
            for annotation in _iter_items(_field(content_item, "annotations")):
                annotation_type = _string_field(annotation, "type")
                if annotation_type not in {"container_file_citation", "file_path"}:
                    continue
                file_id = _string_field(annotation, "file_id") or _string_field(annotation, "container_file_id")
                container_id = _string_field(annotation, "container_id")
                if not file_id:
                    continue
                filename = _string_field(annotation, "filename") or f"{file_id}.bin"
                citations.append(
                    GeneratedContainerFile(
                        container_id=container_id,
                        file_id=file_id,
                        filename=filename,
                        media_type=_string_field(annotation, "media_type") or _media_type_for_filename(filename),
                    )
                )
    return tuple(citations)


def _generated_filename(value: object) -> str:
    path = _string_field(value, "path")
    if path:
        return _safe_path_basename(path)
    return _string_field(value, "filename") or _string_field(value, "name") or "generated.bin"


def _safe_path_basename(path: str) -> str:
    basename = path.replace("\\", "/").rsplit("/", 1)[-1]
    if basename in {"", ".", ".."}:
        return "generated.bin"
    return basename


async def _async_iter_items(value: object) -> AsyncIterator[object]:
    if hasattr(value, "__aiter__"):
        async for item in cast(AsyncIterator[object], value):
            yield item
        return
    data = _field(value, "data")
    if data is not None:
        for item in _iter_items(data):
            yield item
        return
    for item in _iter_items(value):
        yield item


async def _maybe_await(value: object) -> object:
    if isawaitable(value):
        return await value
    return value


def _provisional_output_payload(
    response: object,
    generated: tuple[StoredGeneratedArtifact, ...],
) -> bytes:
    statuses = sorted(
        {
            status
            for status in (_string_field(item, "status") for item in _iter_items(_field(response, "output")))
            if status
        }
    )
    lines = ["provisional=true"]
    for status in statuses:
        lines.append(f"status={status}")
    for log_item in _log_metadata(response):
        lines.append(
            "log="
            f"stream={log_item.stream};"
            f"hash:{log_item.content_hash};"
            f"bytes:{log_item.byte_size}"
        )
    for generated_item in generated:
        lines.append(
            "generated_file="
            f"artifact_id:{generated_item.artifact_id};"
            f"hash:{generated_item.content_hash};"
            f"bytes:{generated_item.byte_size};"
            f"media_type:{generated_item.media_type}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


class LogMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stream: str
    content_hash: str
    byte_size: int


def _log_metadata(response: object) -> tuple[LogMetadata, ...]:
    items: list[LogMetadata] = []
    for output_item in _iter_items(_field(response, "output")):
        for log_item in _iter_items(_field(output_item, "outputs")):
            raw_logs = _string_field(log_item, "logs") or _string_field(log_item, "text")
            if raw_logs is None:
                continue
            encoded = raw_logs.encode("utf-8")
            items.append(
                LogMetadata(
                    stream=_string_field(log_item, "stream") or "stdout",
                    content_hash=sha256(encoded).hexdigest(),
                    byte_size=len(encoded),
                )
            )
    return tuple(items)


def _media_type_for_filename(filename: str) -> str:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        ".csv": "text/csv",
        ".json": "application/json",
        ".pdf": "application/pdf",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".py": "text/x-python",
    }.get(suffix, "application/octet-stream")


def _iter_items(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, list | tuple):
        return tuple(value)
    return ()


def _field(value: object, key: str) -> object:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _string_field(value: object, key: str) -> str | None:
    item = _field(value, key)
    return item if isinstance(item, str) and item else None


def _disclosure_event(
    trace_context: TraceContext,
    model: str,
    metadata: Mapping[str, str],
) -> AuditEvent:
    return AuditEvent(
        schema_version="audit_event@1",
        event_id=f"event-{uuid4().hex}",
        timestamp_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        run_id=trace_context.run_id,
        correlation_id=trace_context.correlation_id,
        span_name="llm.call",
        event_type="disclosure",
        attributes={
            "case_id": metadata["case_id"],
            "correlation_id": metadata["correlation_id"],
            "provider": "openai",
            "model": model,
            "status": "approved",
        },
    )

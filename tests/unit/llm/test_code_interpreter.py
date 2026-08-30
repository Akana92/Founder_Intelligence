from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.adapters.openai.code_interpreter import (
    CodeInterpreterArtifactInput,
    OpenAIContainerFileContentClient,
    OpenAICodeInterpreterAuditError,
    OpenAICodeInterpreterGeneratedFileError,
    OpenAICodeInterpreterMetadataError,
    OpenAICodeInterpreterAdapter,
)
from due_diligence_agent.application.policies.budget import BudgetGuard
from due_diligence_agent.application.policies.data_egress import DataEgressDenied, DataEgressPolicy
from due_diligence_agent.application.policies.model_routing import ModelProfile, ModelRoutingPolicy
from due_diligence_agent.domain.artifacts.models import StoredArtifact
from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.llm import LLMBudgetRequest, LLMRoutingContext
from due_diligence_agent.ports.tracing import AuditEvent, TraceContext


class RecordingAuditSpool:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> str:
        self.events.append(event)
        return "memory://audit"

    def read_batch(self, limit: int = 100) -> list[AuditEvent]:
        return []

    def mark_flushed(self, event_ids: list[str]) -> None:
        return None


class FailingAuditSpool(RecordingAuditSpool):
    def append(self, event: AuditEvent) -> str:
        self.events.append(event)
        raise OSError("disk full secret prompt")


class FailingArtifactStore:
    def put_bytes(
        self,
        payload: bytes,
        *,
        media_type: str,
        artifact_id: UUID | None = None,
        source_snapshot_hash: str | None = None,
        sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> StoredArtifact:
        raise OSError("artifact store unavailable secret")

    def read_bytes(self, content_hash: str) -> bytes:
        return b""


@pytest.mark.asyncio
async def test_code_interpreter_rejects_restricted_or_unapproved_artifacts() -> None:
    adapter = _adapter(RecordingCreateResponses())

    with pytest.raises(DataEgressDenied):
        await adapter.run_public_analysis(
            _artifact(SensitivityClass.RESTRICTED),
            code="print('x')",
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.RESTRICTED),
            trace_context=_trace(),
        )

    with pytest.raises(DataEgressDenied):
        await adapter.run_public_analysis(
            _artifact(SensitivityClass.CONFIDENTIAL),
            code="print('x')",
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.CONFIDENTIAL),
            trace_context=_trace(),
        )


@pytest.mark.asyncio
async def test_code_interpreter_output_is_provisional_and_content_addressed() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithTemptingOutputText())
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert result.provisional is True
    assert result.code_hash
    assert result.output_artifact_id
    assert result.output_hash
    assert result.canonical_calculation_ids == ()
    assert result.code_artifact_id
    assert b"tempting provider prose" not in store.payloads[result.output_artifact_id]
    assert b"status=completed" in store.payloads[result.output_artifact_id]
    assert responses.calls[0]["tools"] == [
        {"type": "code_interpreter", "container": {"type": "auto", "network_policy": {"type": "disabled"}}}
    ]
    assert responses.calls[0]["tool_choice"] == "required"
    assert responses.calls[0]["store"] is False
    assert responses.calls[0]["include"] == ["code_interpreter_call.outputs"]
    serialized_input = repr(responses.calls[0]["input"])
    assert "data:text/csv;base64," in serialized_input
    assert "print('ratio')" in serialized_input
    assert "symbol,ratio" not in serialized_input


@pytest.mark.asyncio
async def test_code_interpreter_filename_extension_follows_media_type() -> None:
    responses = RecordingCreateResponses()
    adapter = _adapter(responses)
    artifact = _artifact(SensitivityClass.PUBLIC, media_type="application/vnd.ms-excel")

    await adapter.run_public_analysis(
        artifact,
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    serialized_input = repr(responses.calls[0]["input"])
    assert f"{artifact.id}.xls" in serialized_input
    assert f"{artifact.id}.csv" not in serialized_input


@pytest.mark.asyncio
async def test_code_interpreter_metadata_is_sanitized_and_fails_closed() -> None:
    responses = RecordingCreateResponses()
    adapter = _adapter(responses)

    with pytest.raises(OpenAICodeInterpreterMetadataError, match="METADATA_SANITIZATION_ERROR"):
        await adapter.run_public_analysis(
            _artifact(SensitivityClass.PUBLIC),
            code="print('ratio')",
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(case_id="john@example.com"),
        )

    assert responses.calls == []


@pytest.mark.asyncio
async def test_code_interpreter_audit_failure_releases_budget_and_skips_provider() -> None:
    responses = RecordingCreateResponses()
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    adapter = _adapter(responses, audit_spool=FailingAuditSpool(), budget_guard=budget_guard)

    with pytest.raises(OpenAICodeInterpreterAuditError, match="AUDIT_PERSISTENCE_ERROR"):
        await adapter.run_public_analysis(
            _artifact(SensitivityClass.PUBLIC),
            code="print('ratio')",
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )

    assert responses.calls == []
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0


@pytest.mark.asyncio
async def test_code_interpreter_artifact_store_failure_releases_budget_and_skips_provider() -> None:
    responses = RecordingCreateResponses()
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    adapter = _adapter(responses, budget_guard=budget_guard, artifact_store=FailingArtifactStore())

    with pytest.raises(OSError, match="artifact store unavailable"):
        await adapter.run_public_analysis(
            _artifact(SensitivityClass.PUBLIC),
            code="print('ratio')",
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )

    assert responses.calls == []
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0


@pytest.mark.asyncio
async def test_code_interpreter_output_sensitivity_inherits_approved_artifact() -> None:
    responses = RecordingCreateResponses()
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store)
    scope = _scope(SensitivityClass.CONFIDENTIAL)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.CONFIDENTIAL),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.CONFIDENTIAL),
        trace_context=_trace(),
        disclosure_scope=scope,
    )

    assert result.provisional is True
    assert store.by_id[result.output_artifact_id].sensitivity is SensitivityClass.CONFIDENTIAL
    assert store.by_id[result.code_artifact_id].sensitivity is SensitivityClass.CONFIDENTIAL


@pytest.mark.asyncio
async def test_code_interpreter_missing_usage_consumes_full_reservation() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithoutUsage())
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    adapter = _adapter(responses, budget_guard=budget_guard)

    await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    [record] = budget_guard.usage_for_case(_CASE_ID)
    assert record.tokens == 100
    assert record.usd_cost == Decimal("0.10")


@pytest.mark.asyncio
async def test_code_interpreter_object_usage_is_counted() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithObjectUsage())
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    adapter = _adapter(responses, budget_guard=budget_guard)

    await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    [record] = budget_guard.usage_for_case(_CASE_ID)
    assert record.tokens == 33


@pytest.mark.asyncio
async def test_code_interpreter_invalid_usage_consumes_full_reservation() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithInvalidUsage())
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    adapter = _adapter(responses, budget_guard=budget_guard)

    await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    [record] = budget_guard.usage_for_case(_CASE_ID)
    assert record.tokens == 100


@pytest.mark.asyncio
async def test_code_interpreter_persists_generated_file_citations_with_inherited_sensitivity() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithGeneratedFile())
    files = RecordingContainerFiles()
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store, container_file_client=files)
    scope = _scope(SensitivityClass.CONFIDENTIAL)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.CONFIDENTIAL),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.CONFIDENTIAL),
        trace_context=_trace(),
        disclosure_scope=scope,
    )

    assert files.listed == ["container-1"]
    assert files.fetched == [("container-1", "file-1")]
    assert len(result.generated_artifact_ids) == 1
    generated = store.by_id[result.generated_artifact_ids[0]]
    assert generated.media_type == "text/csv"
    assert generated.sensitivity is SensitivityClass.CONFIDENTIAL
    assert store.payloads[result.generated_artifact_ids[0]] == b"generated,csv\n"


@pytest.mark.asyncio
async def test_code_interpreter_persists_uncited_assistant_files_and_excludes_input_files() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithContainer())
    files = RecordingGeneratedFiles(
        listed={
            "container-1": [
                GeneratedFileRef("assistant-file", "container-1", "assistant.csv", "assistant", "text/csv"),
                GeneratedFileRef("input-file", "container-1", "input.csv", "user", "text/csv"),
            ]
        },
        payloads={("container-1", "assistant-file"): b"assistant,csv\n"},
    )
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store, container_file_client=files)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert files.listed == ["container-1"]
    assert files.fetched == [("container-1", "assistant-file")]
    assert len(result.generated_artifact_ids) == 1
    assert store.payloads[result.generated_artifact_ids[0]] == b"assistant,csv\n"


@pytest.mark.asyncio
async def test_code_interpreter_dedupes_listed_citation_and_file_path_refs() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithDuplicateRefs())
    files = RecordingGeneratedFiles(
        listed={"container-1": [GeneratedFileRef("file-1", "container-1", "generated.csv", "assistant", "text/csv")]},
        payloads={("container-1", "file-1"): b"deduped\n", (None, "loose-file"): b"loose\n"},
    )
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store, container_file_client=files)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert files.fetched == [("container-1", "file-1"), (None, "loose-file")]
    assert len(result.generated_artifact_ids) == 2
    assert {store.payloads[artifact_id] for artifact_id in result.generated_artifact_ids} == {b"deduped\n", b"loose\n"}


@pytest.mark.asyncio
async def test_code_interpreter_dedupes_globally_by_file_id_and_listed_ref_wins() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithListedAndFilePathSameFileId())
    files = RecordingGeneratedFiles(
        listed={"container-1": [GeneratedFileRef("same-file", "container-1", "listed.csv", "assistant", "text/csv")]},
        payloads={("container-1", "same-file"): b"listed wins\n"},
    )
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store, container_file_client=files)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert files.fetched == [("container-1", "same-file")]
    assert len(result.generated_artifact_ids) == 1
    assert store.payloads[result.generated_artifact_ids[0]] == b"listed wins\n"
    assert store.by_id[result.generated_artifact_ids[0]].media_type == "text/csv"


@pytest.mark.asyncio
async def test_code_interpreter_generated_file_failure_fails_closed() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithGeneratedFile())
    adapter = _adapter(responses, container_file_client=FailingGeneratedFiles())

    with pytest.raises(OpenAICodeInterpreterGeneratedFileError, match="GENERATED_FILE_PERSISTENCE_ERROR"):
        await adapter.run_public_analysis(
            _artifact(SensitivityClass.PUBLIC),
            code="print('ratio')",
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )


@pytest.mark.asyncio
async def test_code_interpreter_citation_only_input_bytes_are_not_generated() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithFilePathOnly("input-copy", "input.csv"))
    files = RecordingGeneratedFiles(
        listed={},
        payloads={(None, "input-copy"): b"symbol,ratio\nACME,1.23\n"},
    )
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store, container_file_client=files)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert files.fetched == [(None, "input-copy")]
    assert result.generated_artifact_ids == ()


@pytest.mark.asyncio
async def test_code_interpreter_file_path_assistant_payload_is_kept_when_hash_differs() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithFilePathOnly("assistant-output", "assistant.csv"))
    files = RecordingGeneratedFiles(
        listed={},
        payloads={(None, "assistant-output"): b"assistant output\n"},
    )
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store, container_file_client=files)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert files.fetched == [(None, "assistant-output")]
    assert len(result.generated_artifact_ids) == 1
    assert store.payloads[result.generated_artifact_ids[0]] == b"assistant output\n"


@pytest.mark.asyncio
async def test_code_interpreter_unresolved_container_citation_fails_closed() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithUnlistedContainerCitation())
    files = RecordingGeneratedFiles(listed={"container-1": []}, payloads={})
    adapter = _adapter(responses, container_file_client=files)

    with pytest.raises(OpenAICodeInterpreterGeneratedFileError, match="GENERATED_FILE_PERSISTENCE_ERROR"):
        await adapter.run_public_analysis(
            _artifact(SensitivityClass.PUBLIC),
            code="print('ratio')",
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )

    assert files.fetched == [("container-1", "missing-file")]


@pytest.mark.asyncio
async def test_code_interpreter_output_manifest_records_log_metadata_without_raw_logs() -> None:
    responses = RecordingCreateResponses(response=_CreatedWithLogs())
    store = InMemoryArtifactStore()
    adapter = _adapter(responses, artifact_store=store)

    result = await adapter.run_public_analysis(
        _artifact(SensitivityClass.PUBLIC),
        code="print('ratio')",
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    manifest = store.payloads[result.output_artifact_id]
    assert b"secret stdout" not in manifest
    assert b"stream=stdout" in manifest
    assert b"bytes:14" in manifest
    assert sha256(b"secret stdout\n").hexdigest().encode("ascii") in manifest


@pytest.mark.asyncio
async def test_openai_container_file_content_client_supports_sdk_shapes() -> None:
    sdk = RecordingSDKFileClient()
    client = OpenAIContainerFileContentClient(sdk)

    listed = await client.list_generated_files("container-1")
    container_payload = await client.read_bytes(container_id="container-1", file_id="assistant-file")
    loose_payload = await client.read_bytes(container_id=None, file_id="loose-file")

    assert [(item.file_id, item.container_id, item.filename, item.source) for item in listed] == [
        ("assistant-file", "container-1", "assistant.csv", "assistant")
    ]
    assert [item.media_type for item in listed] == ["text/csv"]
    assert container_payload == b"container-bytes"
    assert loose_payload == b"loose-bytes"
    assert sdk.container_content_reads == [("container-1", "assistant-file")]
    assert sdk.file_content_reads == ["loose-file"]


class RecordingCreateResponses:
    def __init__(self, response: object | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = response or _Created()

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class _Created:
    output_text = "ratio=1.23"
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class _CreatedWithoutUsage:
    output_text = "ratio=1.23"


class _UsageObject:
    input_tokens = 11
    output_tokens = 22
    total_tokens = 33


class _CreatedWithObjectUsage:
    output_text = "ratio=1.23"
    usage = _UsageObject()


class _CreatedWithInvalidUsage:
    output_text = "ratio=1.23"
    usage = {"total_tokens": "not-an-int"}


class _FileAnnotation:
    type = "container_file_citation"
    container_id = "container-1"
    file_id = "file-1"
    filename = "generated.csv"
    media_type = "text/csv"


class _OutputContent:
    annotations = [_FileAnnotation()]


class _OutputItem:
    content = [_OutputContent()]


class _CreatedWithGeneratedFile:
    output_text = "ratio=1.23"
    output = [{"type": "code_interpreter_call", "status": "completed", "container_id": "container-1"}, _OutputItem()]
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class _CreatedWithContainer:
    output_text = "ratio=1.23"
    output = [{"type": "code_interpreter_call", "status": "completed", "container_id": "container-1"}]
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class _ContainerFileCitationDict(dict[str, object]):
    def __init__(self) -> None:
        super().__init__(
            type="container_file_citation",
            container_id="container-1",
            file_id="file-1",
            filename="generated.csv",
        )


class _FilePathAnnotation:
    type = "file_path"
    file_id = "loose-file"
    filename = "loose.txt"


class _CreatedWithDuplicateRefs:
    output_text = "ratio=1.23"
    output = [
        {"type": "code_interpreter_call", "status": "completed", "container_id": "container-1"},
        {"content": [{"annotations": [_ContainerFileCitationDict(), _ContainerFileCitationDict(), _FilePathAnnotation()]}]},
    ]
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class _FilePathAnnotationFor:
    type = "file_path"

    def __init__(self, file_id: str, filename: str) -> None:
        self.file_id = file_id
        self.filename = filename


class _CreatedWithListedAndFilePathSameFileId:
    output_text = "ratio=1.23"
    output = [
        {"type": "code_interpreter_call", "status": "completed", "container_id": "container-1"},
        {"content": [{"annotations": [_FilePathAnnotationFor("same-file", "ignored.txt")]}]},
    ]
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class _CreatedWithFilePathOnly:
    output_text = "ratio=1.23"
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}

    def __init__(self, file_id: str, filename: str) -> None:
        self.output = [{"content": [{"annotations": [_FilePathAnnotationFor(file_id, filename)]}]}]


class _CreatedWithUnlistedContainerCitation:
    output_text = "ratio=1.23"
    output = [
        {"type": "code_interpreter_call", "status": "completed", "container_id": "container-1"},
        {
            "content": [
                {
                    "annotations": [
                        {
                            "type": "container_file_citation",
                            "container_id": "container-1",
                            "file_id": "missing-file",
                            "filename": "missing.csv",
                        }
                    ]
                }
            ]
        },
    ]
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class _CreatedWithTemptingOutputText:
    output_text = "tempting provider prose with raw answer"
    output = [{"type": "code_interpreter_call", "status": "completed"}]
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class _CreatedWithLogs:
    output_text = "tempting provider prose"
    output = [
        {
            "type": "code_interpreter_call",
            "status": "completed",
            "outputs": [{"type": "logs", "logs": "secret stdout\n", "stream": "stdout"}],
        }
    ]
    usage = {"total_tokens": 20, "input_tokens": 10, "output_tokens": 10}


class RecordingContainerFiles:
    def __init__(self) -> None:
        self.fetched: list[tuple[str, str]] = []
        self.listed: list[str] = []

    async def list_generated_files(self, container_id: str) -> tuple[object, ...]:
        self.listed.append(container_id)
        return ()

    async def read_bytes(self, *, container_id: str, file_id: str) -> bytes:
        self.fetched.append((container_id, file_id))
        return b"generated,csv\n"


class GeneratedFileRef:
    def __init__(
        self,
        file_id: str,
        container_id: str | None,
        filename: str,
        source: str,
        media_type: str,
    ) -> None:
        self.file_id = file_id
        self.container_id = container_id
        self.filename = filename
        self.source = source
        self.media_type = media_type


class NoGeneratedFiles:
    async def list_generated_files(self, container_id: str) -> tuple[object, ...]:
        return ()

    async def read_bytes(self, *, container_id: str | None, file_id: str) -> bytes:
        raise AssertionError("no generated files should be fetched")


class RecordingGeneratedFiles:
    def __init__(
        self,
        *,
        listed: dict[str, list[GeneratedFileRef]],
        payloads: dict[tuple[str | None, str], bytes],
    ) -> None:
        self._listed = listed
        self._payloads = payloads
        self.listed: list[str] = []
        self.fetched: list[tuple[str | None, str]] = []

    async def list_generated_files(self, container_id: str) -> tuple[GeneratedFileRef, ...]:
        self.listed.append(container_id)
        return tuple(self._listed.get(container_id, ()))

    async def read_bytes(self, *, container_id: str | None, file_id: str) -> bytes:
        self.fetched.append((container_id, file_id))
        return self._payloads[(container_id, file_id)]


class FailingGeneratedFiles:
    async def list_generated_files(self, container_id: str) -> tuple[object, ...]:
        raise OSError("sdk failure secret output")

    async def read_bytes(self, *, container_id: str | None, file_id: str) -> bytes:
        raise OSError("sdk failure secret output")


class _AsyncPage:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def __aiter__(self) -> "_AsyncPage":
        self._remaining = list(self._items)
        return self

    async def __anext__(self) -> object:
        if not self._remaining:
            raise StopAsyncIteration
        return self._remaining.pop(0)


class _SDKFile:
    id = "assistant-file"
    path = "reports/assistant.csv"
    source = "assistant"


class _SDKBinaryResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class _SDKContainerContent:
    def __init__(self, owner: "RecordingSDKFileClient") -> None:
        self._owner = owner

    async def retrieve(self, *, container_id: str, file_id: str) -> _SDKBinaryResponse:
        self._owner.container_content_reads.append((container_id, file_id))
        return _SDKBinaryResponse(b"container-bytes")


class _SDKContainerFiles:
    def __init__(self, owner: "RecordingSDKFileClient") -> None:
        self.content = _SDKContainerContent(owner)

    def list(self, *, container_id: str) -> _AsyncPage:
        return _AsyncPage([_SDKFile()])


class _SDKContainers:
    def __init__(self, owner: "RecordingSDKFileClient") -> None:
        self.files = _SDKContainerFiles(owner)


class _SDKFiles:
    def __init__(self, owner: "RecordingSDKFileClient") -> None:
        self._owner = owner

    async def content(self, file_id: str) -> _SDKBinaryResponse:
        self._owner.file_content_reads.append(file_id)
        return _SDKBinaryResponse(b"loose-bytes")


class RecordingSDKFileClient:
    def __init__(self) -> None:
        self.container_content_reads: list[tuple[str, str]] = []
        self.file_content_reads: list[str] = []
        self.containers = _SDKContainers(self)
        self.files = _SDKFiles(self)


def _adapter(
    responses: RecordingCreateResponses,
    *,
    audit_spool: RecordingAuditSpool | None = None,
    budget_guard: BudgetGuard | None = None,
    artifact_store: object | None = None,
    container_file_client: object | None = None,
) -> OpenAICodeInterpreterAdapter:
    return OpenAICodeInterpreterAdapter(
        responses_client=responses,
        egress_policy=DataEgressPolicy(),
        routing_policy=ModelRoutingPolicy(
            default_profile=ModelProfile(provider="openai", model="gpt-5.6-terra", role="structured_analysis"),
            high_reasoning_profile=ModelProfile(
                provider="openai",
                model="gpt-5.6-sol",
                role="high_reasoning_verifier",
            ),
        ),
        budget_guard=budget_guard or BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00")),
        audit_spool=audit_spool or RecordingAuditSpool(),
        artifact_store=artifact_store or InMemoryArtifactStore(),
        container_file_client=container_file_client or NoGeneratedFiles(),
    )


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self.by_id: dict[UUID, StoredArtifact] = {}
        self.payloads: dict[UUID, bytes] = {}

    def put_bytes(
        self,
        payload: bytes,
        *,
        media_type: str,
        artifact_id: UUID | None = None,
        source_snapshot_hash: str | None = None,
        sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> StoredArtifact:
        digest = sha256(payload).hexdigest()
        stored = StoredArtifact(
            artifact_id=artifact_id or uuid4(),
            content_hash=digest,
            source_snapshot_hash=source_snapshot_hash or digest,
            storage_ref=f"memory://{digest}",
            media_type=media_type,
            byte_size=len(payload),
            stored_at=datetime.now(UTC),
            sensitivity=sensitivity,
        )
        self.by_id[stored.artifact_id] = stored
        self.payloads[stored.artifact_id] = payload
        return stored

    def read_bytes(self, content_hash: str) -> bytes:
        return b""


def _artifact(
    sensitivity: SensitivityClass,
    *,
    media_type: str = "text/csv",
) -> CodeInterpreterArtifactInput:
    return CodeInterpreterArtifactInput(
        id=uuid4(),
        content=b"symbol,ratio\nACME,1.23\n",
        media_type=media_type,
        sensitivity=sensitivity,
        redacted=sensitivity is not SensitivityClass.PUBLIC,
        minimized=True,
        redaction_policy_version="redact@1",
    )


_CASE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _budget() -> LLMBudgetRequest:
    return LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("0.10"),
    )


def _routing(sensitivity: SensitivityClass) -> LLMRoutingContext:
    return LLMRoutingContext(
        task_complexity="standard",
        latency_budget_ms=30_000,
        schema_validation_failed=False,
        potential_finding_severity=FindingSeverity.MEDIUM,
        sensitivity=sensitivity,
    )


def _scope(sensitivity: SensitivityClass) -> object:
    from due_diligence_agent.application.policies.data_egress import DisclosureScope

    return DisclosureScope(
        approval_id=uuid4(),
        allowed_classes=frozenset({sensitivity}),
        destination="openai.code_interpreter",
        egress_policy_version=DataEgressPolicy.version,
        redaction_policy_versions=frozenset({"redact@1"}),
    )


def _trace(*, case_id: str | None = None) -> TraceContext:
    return TraceContext(
        request_id="req-10",
        run_id="run-10",
        case_id=case_id or str(_CASE_ID),
        correlation_id="corr-10",
        workflow_type="public_company",
        app_version="app@1",
        graph_version="graph@1",
        redaction_policy_version="redact@1",
    )

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Final, cast

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.observability.startup_langsmith import (
    StartupLangSmithNodeTracer,
    StartupLangSmithTracerConfig,
)
from due_diligence_agent.application.services.startup_trace_query_service import (
    StartupTraceQueryService,
)
from due_diligence_agent.bootstrap.container import (
    build_deterministic_startup_analysis_composer,
)
from due_diligence_agent.evals.output_root import (
    EVALUATION_OUTPUT_ERROR_CODES,
    prepare_evaluation_output_root,
)


SCHEMA_VERSION: Final[str] = "langsmith_trace_evidence@1"
EVIDENCE_FILENAME: Final[str] = "langsmith-trace-evidence.json"
CASE_ID: Final[str] = "00000000-0000-0000-0000-000000000951"
RUN_ID: Final[str] = "queue5-langsmith-run-951"
CORRELATION_ID: Final[str] = "queue5-langsmith-correlation-951"
PROJECT_NAME: Final[str] = "dda-queue5-frozen-smoke"
_FIXTURE_PDF: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "startup_synthetic_v1"
    / "cases"
    / "saas"
    / "pitch.pdf"
)
_SAFE_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "agent_role",
        "attempt",
        "case_id",
        "checkpoint_id",
        "correlation_id",
        "duration_ms",
        "error_code",
        "estimated_cost_usd",
        "exporter_provider",
        "gate",
        "gate4_decision",
        "gate_status",
        "input_tokens",
        "latency_ms",
        "ls_model_name",
        "ls_provider",
        "model",
        "node_name",
        "output_tokens",
        "provider",
        "report_checksum",
        "report_id",
        "report_revision",
        "retry_count",
        "run_id",
        "schema_version",
        "status",
        "tool",
        "total_tokens",
        "workflow_type",
    }
)
_SAFE_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        *_SAFE_METADATA_KEYS,
        "cost_usd",
    }
)
_SAFE_TOP_LEVEL_USAGE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "total_cost",
    }
)
_SENSITIVE_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"((?<![A-Za-z0-9])[A-Za-z]:[\\/]|"
    r"(?i:/Users/|/home/|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])|"
    r"\bbearer\s+\S+|api[_ -]?key|secret|private|%PDF|pitch\.pdf|"
    r"raw[_ -]?pdf|document[_ -]?text|filename|local[_ -]?path|"
    r"(?<![A-Za-z0-9_])prompt(?![A-Za-z0-9_])|"
    r"chain[_ -]?of[_ -]?thought|"
    r"(?<![A-Za-z0-9_])completion(?![A-Za-z0-9_])|system\s+instructions))"
)


class _LangSmithSmokeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    langsmith_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="LANGSMITH_API_KEY",
    )


@dataclass(frozen=True)
class LangSmithWorkflowEvidence:
    case_id: str
    run_id: str
    node_count: int
    node_names: tuple[str, ...]
    admin_langsmith_health: dict[str, str]
    report_lineage: dict[str, str]


@dataclass(frozen=True)
class Queue5LangSmithTraceEvidence:
    schema_version: str
    status: str
    credential_present: bool
    execute_live_requested: bool
    live_call_attempted: bool
    live_call_succeeded: bool
    client_constructed: bool
    workflow: LangSmithWorkflowEvidence
    langsmith_trace: dict[str, object]
    privacy: dict[str, object]
    semantic_hash: str
    artifact_paths: dict[str, str] = field(default_factory=dict)
    fail_reasons: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["workflow"]["node_names"] = list(self.workflow.node_names)
        payload["fail_reasons"] = list(self.fail_reasons)
        return payload


def run_queue5_langsmith_live_smoke(
    output_dir: Path,
    *,
    execute_live: bool = False,
    client_factory: Callable[..., object] | None = None,
    run_id: str = RUN_ID,
) -> Queue5LangSmithTraceEvidence:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", run_id) is None:
        raise ValueError("langsmith_smoke_run_id_invalid")
    output_root = prepare_evaluation_output_root(output_dir)
    credential_present = _langsmith_key_present()
    live_call_attempted = execute_live and credential_present
    should_export = live_call_attempted
    fail_reasons: list[str] = []

    settings = _LangSmithSmokeSettings()
    recording_factory = _RecordingFactory(
        client_factory or _default_langsmith_client_factory(settings.langsmith_api_key),
    )
    with _disabled_global_langsmith_tracing():
        workflow = _run_real_startup_workflow(
            output_root,
            enabled=execute_live or not credential_present,
            credential_present=credential_present,
            recording_factory=recording_factory if should_export else None,
            run_id=run_id,
        )
    capture_summary = recording_factory.summary()
    privacy = _privacy_proof(capture_summary)
    if privacy["privacy_leak_count"] != 0:
        fail_reasons.append("langsmith_capture_privacy_rejected")

    health_status = workflow.admin_langsmith_health.get("status")
    if not credential_present:
        status = "blocked_missing_credential"
    elif not execute_live:
        status = "armed_not_executed"
    elif health_status == "healthy" and privacy["privacy_leak_count"] == 0:
        status = "pass"
    else:
        status = "degraded"

    live_call_succeeded = live_call_attempted and status == "pass"
    if status == "degraded":
        fail_reasons.append("langsmith_export_degraded")

    public_payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "credential_present": credential_present,
        "execute_live_requested": execute_live,
        "live_call_attempted": live_call_attempted,
        "live_call_succeeded": live_call_succeeded,
        "client_constructed": recording_factory.constructed,
        "workflow": asdict(workflow),
        "langsmith_trace": capture_summary,
        "privacy": privacy,
        "semantic_hash": "",
        "artifact_paths": {"evidence": EVIDENCE_FILENAME},
        "fail_reasons": list(dict.fromkeys(fail_reasons)),
    }
    public_payload["semantic_hash"] = _semantic_hash(public_payload)
    evidence_path = output_root / EVIDENCE_FILENAME
    _write_json(evidence_path, public_payload)
    return _evidence_from_payload(public_payload)


def validate_langsmith_capture_privacy(capture: Mapping[str, object]) -> None:
    created = _mapping_list(capture.get("created"))
    updated = _mapping_list(capture.get("updated"))
    for call in created:
        _validate_safe_payload(call.get("inputs"))
        _validate_safe_payload(call.get("outputs"))
        if call.get("attachments") not in (None, [], {}):
            raise ValueError("langsmith_capture_privacy_rejected")
        if call.get("dangerously_allow_filesystem") is not False:
            raise ValueError("langsmith_capture_privacy_rejected")
        metadata = _metadata_from_call(call)
        if any(str(key) not in _SAFE_METADATA_KEYS for key in metadata):
            raise ValueError("langsmith_capture_privacy_rejected")
        _validate_top_level_usage(call)
    for call in updated:
        _validate_safe_payload(call.get("outputs"))
        if call.get("dangerously_allow_filesystem") is not False:
            raise ValueError("langsmith_capture_privacy_rejected")
    if _privacy_leak_count(capture):
        raise ValueError("langsmith_capture_privacy_rejected")


def _run_real_startup_workflow(
    output_root: Path,
    *,
    enabled: bool,
    credential_present: bool,
    recording_factory: _RecordingFactory | None,
    run_id: str,
) -> LangSmithWorkflowEvidence:
    data_dir = output_root / "runtime"
    payload = _prepare_case(data_dir, run_id)
    audit_spool = JsonlAuditSpool(data_dir / "startup-audit-spool")
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(
            enabled=enabled,
            credential_present=credential_present,
            project_name=PROJECT_NAME,
        ),
        audit_spool=audit_spool,
        client_factory=recording_factory,
    )
    service = build_deterministic_startup_analysis_composer(
        data_dir,
        external_node_tracer=tracer,
    )

    gate2 = service.start(payload, thread_id=run_id)
    if gate2.get("status") != "approval_required":
        raise ValueError("langsmith_smoke_gate2_not_reached")
    gate3 = service.resume(
        {
            "action": "approved",
            "actor": "founder",
            "destination": "openai.responses",
        },
        thread_id=run_id,
    )
    if gate3.get("status") != "review_required":
        raise ValueError("langsmith_smoke_gate3_not_reached")
    gate4 = service.resume(
        {
            "action": "approved",
            "exclusions": [],
            "gate4_deferred_to": "queue5_langsmith_live_smoke",
        },
        thread_id=run_id,
    )
    if (
        gate4.get("status") != "approval_required"
        or gate4.get("pending_gate") != "startup_gate4_freeze"
    ):
        raise ValueError("langsmith_smoke_gate4_not_reached")
    completed = service.resume(
        {
            "action": "approved",
            "actor": "founder",
            "report_snapshot_id": gate4.get("report_snapshot_id"),
            "report_snapshot_hash": gate4.get("report_snapshot_hash"),
            "report_snapshot_revision": gate4.get("report_snapshot_revision"),
        },
        thread_id=run_id,
    )
    if completed.get("status") not in {"completed", "completed_with_policy_blocks"}:
        raise ValueError("langsmith_smoke_gate4_not_completed")
    if not completed.get("report_snapshot_id"):
        raise ValueError("langsmith_smoke_report_missing")

    tracer.flush()
    view = StartupTraceQueryService(audit_spool).get_view(CASE_ID, run_id, max_events=200)
    node_names = tuple(sorted({row.node for row in view.node_rows if isinstance(row.node, str)}))
    health = (
        asdict(view.langsmith_health)
        if view.langsmith_health is not None
        else {
            "provider": "langsmith",
            "status": "missing",
            "error_code": "missing",
            "fallback_used": "local_audit",
        }
    )
    lineage = _report_lineage_from_completed_state(completed)
    return LangSmithWorkflowEvidence(
        case_id=CASE_ID,
        run_id=run_id,
        node_count=len(node_names),
        node_names=node_names,
        admin_langsmith_health={str(key): str(value) for key, value in health.items()},
        report_lineage=lineage,
    )


def _prepare_case(data_dir: Path, run_id: str) -> dict[str, object]:
    content = _FIXTURE_PDF.read_bytes()
    inbox = data_dir / "inbox" / CASE_ID
    inbox.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(_FIXTURE_PDF, inbox / "doc-0001.pdf")
    return {
        "case_id": CASE_ID,
        "run_id": run_id,
        "correlation_id": CORRELATION_ID if run_id == RUN_ID else f"{run_id}-correlation",
        "source_refs": [
            {
                "document_id": "doc-0001",
                "private_name": "doc-0001.pdf",
                "content_sha256": sha256(content).hexdigest(),
            }
        ],
    }


def _report_lineage_from_completed_state(completed: Mapping[str, object]) -> dict[str, str]:
    report_hash = str(completed.get("report_snapshot_hash") or "")
    return {
        "source": "workflow_completed_state",
        "report_id": str(completed["report_snapshot_id"]),
        "report_revision": str(completed.get("report_snapshot_revision") or ""),
        "report_checksum": report_hash.removeprefix("sha256:"),
        "gate4_status": "completed",
        "gate4_decision": str(completed.get("gate4_decision") or ""),
    }


class _RecordingFactory:
    def __init__(self, factory: Callable[..., object]) -> None:
        self._factory = factory
        self.constructed = False
        self._client: _SafeRecordingLangSmithClient | None = None

    def __call__(self, **kwargs: object) -> object:
        self.constructed = True
        delegate = self._factory(**kwargs)
        self._client = _SafeRecordingLangSmithClient(delegate)
        return self._client

    def summary(self) -> dict[str, object]:
        if self._client is None:
            return {
                "run_count": 0,
                "run_names": [],
                "metadata_keys": [],
                "created": [],
                "updated": [],
                "flush_count": 0,
                "export_errors": 0,
                "export_error_categories": [],
            }
        return self._client.summary()


class _SafeRecordingLangSmithClient:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._created: list[dict[str, object]] = []
        self._updated: list[dict[str, object]] = []
        self._flush_count = 0
        self._export_errors = 0
        self._export_error_categories: list[dict[str, object]] = []

    def create_run(
        self,
        name: str,
        inputs: Mapping[str, object],
        run_type: str,
        **kwargs: object,
    ) -> None:
        self._created.append(self._safe_create_call(name, inputs, run_type, kwargs))
        try:
            getattr(self._delegate, "create_run")(name, inputs, run_type, **kwargs)
        except Exception as exc:
            self._export_errors += 1
            self._record_export_error("create_run", exc)
            raise

    def update_run(self, run_id: object, **kwargs: object) -> None:
        self._updated.append(
            {
                "run_id": str(run_id),
                "outputs": kwargs.get("outputs"),
                "dangerously_allow_filesystem": kwargs.get("dangerously_allow_filesystem"),
            }
        )
        try:
            getattr(self._delegate, "update_run")(run_id, **kwargs)
        except Exception as exc:
            self._export_errors += 1
            self._record_export_error("update_run", exc)
            raise

    def flush(self, timeout: float | None = None) -> None:
        self._flush_count += 1
        try:
            getattr(self._delegate, "flush")(timeout=timeout)
        except Exception as exc:
            self._export_errors += 1
            self._record_export_error("flush", exc)
            raise

    def summary(self) -> dict[str, object]:
        validate_langsmith_capture_privacy({"created": self._created, "updated": self._updated})
        metadata_keys = sorted(
            {
                key
                for call in self._created
                for key in cast(list[str], call.get("metadata_keys", []))
            }
        )
        return {
            "run_count": len(self._created),
            "run_names": sorted({str(call["name"]) for call in self._created}),
            "metadata_keys": metadata_keys,
            "created": self._created,
            "updated": self._updated,
            "flush_count": self._flush_count,
            "export_errors": self._export_errors,
            "export_error_categories": list(self._export_error_categories),
        }

    def _record_export_error(self, stage: str, exc: Exception) -> None:
        exception_chain = _export_exception_chain(exc)
        exception_types = _export_exception_types(exception_chain)
        status = _export_http_status(exception_chain)
        entry: dict[str, object] = {
            "stage": stage,
            "category": _export_error_category(exception_types, status),
            "exception_types": list(exception_types),
        }
        if status is not None:
            entry["http_status"] = status
        self._export_error_categories.append(entry)

    def _safe_create_call(
        self,
        name: str,
        inputs: Mapping[str, object],
        run_type: str,
        kwargs: Mapping[str, object],
    ) -> dict[str, object]:
        metadata = _metadata_from_call(kwargs)
        safe_metadata = {
            key: _safe_metadata_value(key, value)
            for key, value in metadata.items()
            if key in _SAFE_METADATA_KEYS
        }
        call = {
            "name": name,
            "inputs": dict(inputs),
            "run_type": run_type,
            "metadata": safe_metadata,
            "metadata_keys": sorted(metadata),
            "attachments": kwargs.get("attachments"),
            "dangerously_allow_filesystem": kwargs.get("dangerously_allow_filesystem"),
        }
        for key in _SAFE_TOP_LEVEL_USAGE_KEYS:
            if key in kwargs:
                call[key] = kwargs[key]
        return call


def _default_langsmith_client_factory(
    api_key: SecretStr | None,
) -> Callable[..., object]:
    def create_client(**kwargs: object) -> object:
        module = importlib.import_module("langsmith")
        kwargs = {
            **kwargs,
            "auto_batch_tracing": False,
            "omit_traced_runtime_info": True,
            "timeout_ms": (5_000, 5_000),
        }
        kwargs.setdefault("hide_inputs", True)
        kwargs.setdefault("hide_outputs", True)
        if api_key is not None:
            kwargs = {**kwargs, "api_key": api_key.get_secret_value()}
        return module.Client(**kwargs)

    return create_client


def _export_exception_chain(exc: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and len(chain) < 4 and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _export_exception_types(chain: tuple[BaseException, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for exc in chain:
        name = type(exc).__name__
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) is None:
            name = "UnknownError"
        names.append(name)
    return tuple(names)


def _export_http_status(chain: tuple[BaseException, ...]) -> int | None:
    for exc in chain:
        status = getattr(exc, "status_code", None)
        if not isinstance(status, int) or isinstance(status, bool):
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
            return status
    return None


def _export_error_category(exception_types: tuple[str, ...], status: int | None) -> str:
    if status in {401, 403}:
        return "authentication"
    if status == 429:
        return "rate_limit"
    if status is not None and 400 <= status <= 499:
        return "client_request"
    if status is not None and 500 <= status <= 599:
        return "server"
    exception_name = " ".join(exception_types).lower()
    if "auth" in exception_name:
        return "authentication"
    if "ratelimit" in exception_name or "rate_limit" in exception_name:
        return "rate_limit"
    if "notfound" in exception_name or "not_found" in exception_name:
        return "client_request"
    if "apierror" in exception_name or "api_error" in exception_name:
        return "server"
    if "timeout" in exception_name:
        return "timeout"
    if "ssl" in exception_name or "tls" in exception_name:
        return "tls"
    if "connection" in exception_name:
        return "transport"
    if "usererror" in exception_name:
        return "configuration"
    return "unknown"


def _privacy_proof(capture: Mapping[str, object]) -> dict[str, object]:
    unsafe_capture_rejected = False
    try:
        validate_langsmith_capture_privacy(
            {
                "created": [
                    {
                        "name": "startup.report",
                        "inputs": {"raw": "%PDF"},
                        "extra": {"metadata": {"local_path": "C:\\secret\\pitch.pdf"}},
                        "dangerously_allow_filesystem": True,
                    }
                ],
                "updated": [{"outputs": {"raw": "secret@example.com"}}],
            }
        )
    except ValueError:
        unsafe_capture_rejected = True

    try:
        validate_langsmith_capture_privacy(capture)
        leak_count = 0
    except ValueError:
        leak_count = 1
    created = _mapping_list(capture.get("created"))
    updated = _mapping_list(capture.get("updated"))
    return {
        "inputs_sanitized": all(_payload_is_safe(call.get("inputs")) for call in created),
        "outputs_sanitized": all(_payload_is_safe(call.get("outputs")) for call in updated),
        "attachments_absent": all(call.get("attachments") in (None, [], {}) for call in created),
        "filesystem_disabled": all(
            call.get("dangerously_allow_filesystem") is False for call in (*created, *updated)
        )
        if created or updated
        else True,
        "unsafe_capture_rejected": unsafe_capture_rejected,
        "privacy_leak_count": leak_count,
    }


def _validate_safe_payload(payload: object) -> None:
    if not _payload_is_safe(payload):
        raise ValueError("langsmith_capture_privacy_rejected")


def _payload_is_safe(payload: object) -> bool:
    if payload in ({}, None):
        return True
    if not isinstance(payload, Mapping):
        return False
    if any(str(key) not in _SAFE_PAYLOAD_KEYS for key in payload):
        return False
    return _privacy_leak_count(payload) == 0


def _validate_top_level_usage(call: Mapping[str, object]) -> None:
    for key in _SAFE_TOP_LEVEL_USAGE_KEYS:
        if key not in call:
            continue
        value = call[key]
        if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            raise ValueError("langsmith_capture_privacy_rejected")


def _metadata_from_call(call: Mapping[str, object]) -> dict[str, object]:
    extra = call.get("extra")
    if isinstance(extra, Mapping):
        metadata = extra.get("metadata")
        if isinstance(metadata, Mapping):
            return {str(key): value for key, value in metadata.items()}
    metadata = call.get("metadata")
    if isinstance(metadata, Mapping):
        return {str(key): value for key, value in metadata.items()}
    return {}


def _safe_metadata_value(key: str, value: object) -> object:
    if key == "agent_role" and value == "finance":
        return "financial"
    return value


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _privacy_leak_count(value: object) -> int:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return len(_SENSITIVE_VALUE_RE.findall(serialized))


def _semantic_hash(payload: Mapping[str, object]) -> str:
    canonical = {str(key): value for key, value in payload.items() if key != "semantic_hash"}
    workflow = canonical.get("workflow")
    if isinstance(workflow, dict):
        normalized_workflow = dict(workflow)
        lineage = normalized_workflow.get("report_lineage")
        if isinstance(lineage, dict):
            normalized_workflow["report_lineage"] = {
                "source": lineage.get("source"),
                "report_id_present": bool(lineage.get("report_id")),
                "report_revision_present": bool(lineage.get("report_revision")),
                "report_checksum_present": bool(lineage.get("report_checksum")),
            }
        node_names = normalized_workflow.get("node_names")
        if isinstance(node_names, list):
            normalized_workflow["node_names"] = sorted({str(item) for item in node_names})
        canonical["workflow"] = normalized_workflow
    trace = canonical.get("langsmith_trace")
    if isinstance(trace, dict):
        canonical["langsmith_trace"] = {
            key: value for key, value in trace.items() if key not in {"created", "updated"}
        }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _evidence_from_payload(payload: Mapping[str, object]) -> Queue5LangSmithTraceEvidence:
    workflow = cast(Mapping[str, object], payload["workflow"])
    return Queue5LangSmithTraceEvidence(
        schema_version=str(payload["schema_version"]),
        status=str(payload["status"]),
        credential_present=payload.get("credential_present") is True,
        execute_live_requested=payload.get("execute_live_requested") is True,
        live_call_attempted=payload.get("live_call_attempted") is True,
        live_call_succeeded=payload.get("live_call_succeeded") is True,
        client_constructed=payload.get("client_constructed") is True,
        workflow=LangSmithWorkflowEvidence(
            case_id=str(workflow["case_id"]),
            run_id=str(workflow["run_id"]),
            node_count=int(cast(int, workflow["node_count"])),
            node_names=tuple(str(item) for item in cast(list[object], workflow["node_names"])),
            admin_langsmith_health={
                str(key): str(value)
                for key, value in cast(
                    Mapping[str, object], workflow["admin_langsmith_health"]
                ).items()
            },
            report_lineage={
                str(key): str(value)
                for key, value in cast(Mapping[str, object], workflow["report_lineage"]).items()
            },
        ),
        langsmith_trace=dict(cast(Mapping[str, object], payload["langsmith_trace"])),
        privacy=dict(cast(Mapping[str, object], payload["privacy"])),
        semantic_hash=str(payload["semantic_hash"]),
        artifact_paths={
            str(key): str(value)
            for key, value in cast(Mapping[str, object], payload["artifact_paths"]).items()
        },
        fail_reasons=tuple(str(item) for item in cast(list[object], payload["fail_reasons"])),
    )


@contextmanager
def _disabled_global_langsmith_tracing() -> Any:
    names = (
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING",
        "LANGCHAIN_TRACING_V2",
        "DDA_LANGSMITH_TRACING",
    )
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ[name] = "false"
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _langsmith_key_present() -> bool:
    settings = _LangSmithSmokeSettings()
    secret = settings.langsmith_api_key
    if secret is None:
        return False
    return bool(secret.get_secret_value())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="queue5-langsmith-live-smoke")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--run-id", default=RUN_ID)
    args = parser.parse_args(argv)
    try:
        result = run_queue5_langsmith_live_smoke(
            Path(args.output_dir),
            execute_live=bool(args.execute_live),
            run_id=str(args.run_id),
        )
    except ValueError as exc:
        if str(exc) in EVALUATION_OUTPUT_ERROR_CODES:
            print(str(exc), file=sys.stderr)
            return 2
        raise
    print(json.dumps(result.to_json_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

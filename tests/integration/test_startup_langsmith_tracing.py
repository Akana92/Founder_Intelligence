from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.observability.startup_langsmith import (
    StartupLangSmithNodeTracer,
    StartupLangSmithTracerConfig,
)
from due_diligence_agent.bootstrap.container import (
    build_deterministic_startup_analysis_composer,
)


CASE_ID = "00000000-0000-0000-0000-000000000951"
RUN_ID = "queue5-langsmith-run-951"
CORRELATION_ID = "queue5-langsmith-correlation-951"


def test_real_startup_workflow_exports_only_sanitized_langsmith_node_spans(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "startup-live-trace"
    payload = _prepare_case(data_dir)

    client = RecordingLangSmithClient()
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=True, credential_present=True),
        audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
        client_factory=lambda **_: client,
    )
    service = build_deterministic_startup_analysis_composer(
        data_dir,
        external_node_tracer=tracer,
    )
    completed = _run_to_report(service, payload)

    assert completed["report_snapshot_id"]
    child_calls = [
        call for call in client.created if call["name"] != "startup.workflow"
    ]
    metadata_by_node = {
        str(call["extra"]["metadata"]["node_name"]): call["extra"]["metadata"]
        for call in child_calls
    }
    assert {
        "initialize",
        "ingest",
        "parse",
        "classify_redact",
        "disclosure",
        "primary_profile",
        "product_validation",
        "market_research",
        "metrics",
        "financial_analysis",
        "risk_analysis",
        "market_analysis",
        "gtm",
        "report",
    } <= set(metadata_by_node)
    assert metadata_by_node["disclosure"]["agent_role"] == "privacy"
    assert metadata_by_node["disclosure"]["gate"] == "gate2"
    assert metadata_by_node["disclosure"]["gate_status"] == "approved"
    assert metadata_by_node["report"]["agent_role"] == "report"
    assert metadata_by_node["report"]["gate"] == "gate3"
    assert metadata_by_node["report"]["gate_status"] == "approved"
    assert metadata_by_node["report"]["report_id"] == completed["report_snapshot_id"]
    assert metadata_by_node["report"]["report_revision"] == completed[
        "report_snapshot_revision"
    ]
    assert metadata_by_node["report"]["report_checksum"] == str(
        completed["report_snapshot_hash"]
    ).removeprefix("sha256:")

    for call in child_calls:
        metadata = call["extra"]["metadata"]
        assert call["inputs"]["case_id"] == CASE_ID
        assert call["inputs"]["run_id"] == RUN_ID
        assert call["inputs"]["workflow_type"] == "startup"
        assert call["inputs"]["node_name"] == metadata["node_name"]
        assert call["inputs"]["agent_role"] == metadata["agent_role"]
        assert call["inputs"]["schema_version"] == "startup_langsmith_input@1"
        assert call["dangerously_allow_filesystem"] is False
        assert metadata["case_id"] == CASE_ID
        assert metadata["run_id"] == RUN_ID
        assert metadata["correlation_id"] == CORRELATION_ID
        assert metadata["workflow_type"] == "startup"
        assert metadata["input_tokens"] == 0
        assert metadata["output_tokens"] == 0
        assert metadata["total_tokens"] == 0
        assert metadata["estimated_cost_usd"] == 0.0
    child_updates = [
        call
        for call in client.updated
        if any(call["run_id"] == created["id"] for created in child_calls)
    ]
    assert child_updates
    assert all(call["outputs"].get("schema_version") == "startup_langsmith_output@1" for call in child_updates)
    assert all(call["outputs"].get("status") for call in child_updates)
    assert client.flush_calls == 1

    serialized = repr({"created": client.created, "updated": client.updated})
    for forbidden in (
        "%PDF",
        "doc-0001.pdf",
        str(tmp_path),
        "prompt",
        "completion",
        "email",
        "api_key",
        "private_name",
    ):
        assert forbidden not in serialized


def test_disabled_custom_tracing_runs_real_workflow_without_client_export(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "startup-disabled-trace"
    payload = _prepare_case(data_dir)
    client_creations = 0

    def fail_if_constructed(**_: object) -> object:
        nonlocal client_creations
        client_creations += 1
        raise AssertionError("disabled tracer must stay lazy")

    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=False, credential_present=True),
        audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
        client_factory=fail_if_constructed,
    )
    service = build_deterministic_startup_analysis_composer(
        data_dir,
        external_node_tracer=tracer,
    )

    gate2 = service.start(payload, thread_id=RUN_ID)

    assert gate2["status"] == "approval_required"
    assert client_creations == 0
    events = JsonlAuditSpool(data_dir / "startup-audit-spool").read_bounded(
        max_events=100
    )
    assert any(event.event_type == "span" for event in events)
    marker = next(
        event
        for event in events
        if event.event_type == "observability.langsmith_status"
    )
    assert marker.attributes["status"] == "disabled"
    assert marker.attributes["error_code"] == "tracing_disabled"
    assert "%PDF" not in repr(events)
    assert "doc-0001.pdf" not in repr(events)


def test_langsmith_outage_does_not_break_real_workflow_or_local_audit(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "startup-degraded-trace"
    payload = _prepare_case(data_dir)
    client = FailingLangSmithClient()
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=True, credential_present=True),
        audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
        client_factory=lambda **_: client,
    )
    service = build_deterministic_startup_analysis_composer(
        data_dir,
        external_node_tracer=tracer,
    )

    completed = _run_to_report(service, payload)

    assert completed["report_snapshot_id"]
    assert client.create_calls == 1
    events = JsonlAuditSpool(data_dir / "startup-audit-spool").read_bounded(
        max_events=500
    )
    span_nodes = {
        event.attributes.get("node_name")
        for event in events
        if event.event_type == "span"
    }
    assert {"initialize", "ingest", "report"} <= span_nodes
    markers = [
        event
        for event in events
        if event.event_type == "observability.langsmith_status"
    ]
    assert len(markers) == 1
    assert markers[0].attributes == {
        "case_id": CASE_ID,
        "status": "degraded",
        "error_code": "external_export_failed",
        "fallback_used": "local_audit",
        "exporter_provider": "langsmith",
    }
    assert "private exporter failure" not in repr(events)


def _prepare_case(data_dir: Path) -> dict[str, object]:
    source = (
        Path(__file__).parents[1]
        / "fixtures"
        / "startup_synthetic_v1"
        / "cases"
        / "saas"
        / "pitch.pdf"
    )
    content = source.read_bytes()
    inbox = data_dir / "inbox" / CASE_ID
    inbox.mkdir(parents=True)
    (inbox / "doc-0001.pdf").write_bytes(content)
    return {
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "correlation_id": CORRELATION_ID,
        "source_refs": [
            {
                "document_id": "doc-0001",
                "private_name": "doc-0001.pdf",
                "content_sha256": sha256(content).hexdigest(),
            }
        ],
    }


def _run_to_report(service: Any, payload: dict[str, object]) -> dict[str, Any]:
    gate2 = service.start(payload, thread_id=RUN_ID)
    assert gate2["status"] == "approval_required"
    gate3 = service.resume(
        {
            "action": "approved",
            "actor": "founder",
            "destination": "openai.responses",
        },
        thread_id=RUN_ID,
    )
    assert gate3["status"] == "review_required"
    gate4 = service.resume(
        {
            "action": "approved",
            "exclusions": [],
            "gate4_deferred_to": "task10_report_freeze_render_approval",
        },
        thread_id=RUN_ID,
    )
    assert gate4["status"] == "approval_required"
    assert gate4["pending_gate"] == "startup_gate4_freeze"
    completed = service.resume(
        {
            "action": "approved",
            "actor": "founder",
            "report_snapshot_id": gate4.get("report_snapshot_id"),
            "report_snapshot_hash": gate4.get("report_snapshot_hash"),
            "report_snapshot_revision": gate4.get("report_snapshot_revision"),
        },
        thread_id=RUN_ID,
    )
    assert isinstance(completed, dict)
    return completed


class RecordingLangSmithClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.flush_calls = 0

    def create_run(
        self,
        name: str,
        inputs: dict[str, object],
        run_type: str,
        **kwargs: Any,
    ) -> None:
        self.created.append(
            {"name": name, "inputs": inputs, "run_type": run_type, **kwargs}
        )

    def update_run(self, run_id: object, **kwargs: Any) -> None:
        self.updated.append({"run_id": run_id, **kwargs})

    def flush(self, timeout: float | None = None) -> None:
        del timeout
        self.flush_calls += 1


class FailingLangSmithClient:
    def __init__(self) -> None:
        self.create_calls = 0

    def create_run(
        self,
        name: str,
        inputs: dict[str, object],
        run_type: str,
        **kwargs: Any,
    ) -> None:
        del name, inputs, run_type, kwargs
        self.create_calls += 1
        raise RuntimeError("private exporter failure C:\\secret\\doc-0001.pdf")

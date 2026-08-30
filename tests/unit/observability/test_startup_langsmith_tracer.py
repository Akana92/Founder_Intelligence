from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.observability.startup_langsmith import (
    StartupLangSmithNodeTracer,
    StartupLangSmithTracerConfig,
)
from due_diligence_agent.workflows.startup.tracing import CompositeNodeTracer

CASE_ID = "0f4345af-4f5c-4e73-9347-859594db01d6"
REPORT_ID = "4d63b43b-93bb-45da-b453-cde5a81f137f"
RUN_ID = f"startup-api-{CASE_ID}"


def test_disabled_tracer_never_constructs_or_calls_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    factory = RecordingLangSmithFactory()
    spool = JsonlAuditSpool(_test_root() / "audit")
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=False, credential_present=True),
        audit_spool=spool,
        client_factory=factory,
    )

    tracer.record(**_safe_node_attributes(), prompt="must be ignored while disabled")

    assert factory.created == 0
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    marker = _langsmith_markers(spool)[-1]
    assert marker.attributes == {
        "case_id": CASE_ID,
        "status": "disabled",
        "error_code": "tracing_disabled",
        "fallback_used": "local_audit",
        "exporter_provider": "langsmith",
    }


def test_missing_credential_never_constructs_client() -> None:
    factory = RecordingLangSmithFactory()
    spool = JsonlAuditSpool(_test_root() / "audit")
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=True, credential_present=False),
        audit_spool=spool,
        client_factory=factory,
    )

    tracer.record(**_safe_node_attributes())

    assert factory.created == 0
    marker = _langsmith_markers(spool)[-1]
    assert marker.attributes["status"] == "blocked_missing_credential"
    assert marker.attributes["error_code"] == "missing_credential"


def test_enabled_tracer_creates_sanitized_payload_root_and_child_runs() -> None:
    client = RecordingLangSmithClient()
    spool = JsonlAuditSpool(_test_root() / "audit")
    tracer = _enabled_tracer(spool, client)

    tracer.record(**_safe_node_attributes(node_name="ingest"))
    tracer.record(
        **_safe_node_attributes(
            node_name="report",
            agent_role="report",
            gate="gate4",
            gate_status="completed",
            report_id=REPORT_ID,
            report_revision=1,
            report_checksum="a" * 64,
        )
    )

    assert {call["name"] for call in client.created} >= {
        "startup.workflow",
        "startup.ingest",
        "startup.report",
    }
    assert all(call.get("attachments") is None for call in client.created)
    root = next(call for call in client.created if call["name"] == "startup.workflow")
    ingest = next(call for call in client.created if call["name"] == "startup.ingest")
    report = next(call for call in client.created if call["name"] == "startup.report")
    assert root["inputs"] == {
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "workflow_type": "startup",
        "schema_version": "startup_langsmith_input@1",
    }
    assert ingest["inputs"] == {
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "workflow_type": "startup",
        "node_name": "ingest",
        "agent_role": "data_room",
        "attempt": 1,
        "retry_count": 0,
        "schema_version": "startup_langsmith_input@1",
    }
    report_update = next(
        call for call in client.updated if call["run_id"] == report["id"]
    )
    assert report_update["outputs"] == {
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "node_name": "report",
        "status": "success",
        "duration_ms": 7,
        "gate": "gate4",
        "gate_status": "completed",
        "report_id": REPORT_ID,
        "report_revision": 1,
        "schema_version": "startup_langsmith_output@1",
    }
    assert root["trace_id"] == root["id"]
    assert root["dotted_order"].endswith(str(root["id"]))
    assert root["start_time"] is not None
    assert ingest["trace_id"] == root["id"]
    assert ingest["parent_run_id"] == root["id"]
    assert ingest["dotted_order"].startswith(f"{root['dotted_order']}.")
    for call in client.created:
        UUID(str(call["id"]))
        metadata = call.get("extra", {}).get("metadata", {})
        assert "prompt" not in metadata
        assert "filename" not in metadata
        assert "local_path" not in metadata
    assert client.flush_calls == 1
    assert _langsmith_markers(spool)[-1].attributes["status"] == "healthy"


def test_enabled_tracer_exports_real_llm_usage_and_cost_for_langsmith_columns() -> None:
    client = RecordingLangSmithClient()
    spool = JsonlAuditSpool(_test_root() / "audit")
    tracer = _enabled_tracer(spool, client)

    tracer.record(
        **_safe_node_attributes(
            node_name="market_research",
            agent_role="market",
            input_tokens=120,
            output_tokens=45,
            total_tokens=165,
            cost_usd=0.00123,
            provider="openai",
            model="gpt-4o-mini",
            tool="web_search",
        )
    )
    tracer.flush()

    child = next(call for call in client.created if call["name"] == "startup.market_research")
    assert child["run_type"] == "llm"
    assert child["prompt_tokens"] == 120
    assert child["completion_tokens"] == 45
    assert child["total_tokens"] == 165
    assert child["total_cost"] == 0.00123
    metadata = child["extra"]["metadata"]
    assert metadata["ls_provider"] == "openai"
    assert metadata["ls_model_name"] == "gpt-4o-mini"
    assert metadata["usage_metadata"] == {
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
        "total_cost": 0.00123,
    }
    assert child["inputs"]["tool"] == "web_search"
    child_update = next(call for call in client.updated if call["run_id"] == child["id"])
    assert child_update["outputs"]["status"] == "success"
    assert child_update["outputs"]["total_tokens"] == 165
    assert child_update["outputs"]["cost_usd"] == 0.00123
    assert "first_token_time" not in child
    assert "events" not in child
    assert "first_token_time" not in child_update
    assert "events" not in child_update

    root = next(call for call in client.created if call["name"] == "startup.workflow")
    root_update = next(call for call in client.updated if call["run_id"] == root["id"])
    assert root_update["prompt_tokens"] == 120
    assert root_update["completion_tokens"] == 45
    assert root_update["total_tokens"] == 165
    assert root_update["total_cost"] == 0.00123
    assert root_update["extra"]["metadata"]["usage_metadata"] == {
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
        "total_cost": 0.00123,
    }
    assert root_update["outputs"]["input_tokens"] == 120
    assert root_update["outputs"]["output_tokens"] == 45
    assert root_update["outputs"]["total_tokens"] == 165
    assert root_update["outputs"]["cost_usd"] == 0.00123


def test_export_failure_spools_sanitized_health_without_raising() -> None:
    spool = JsonlAuditSpool(_test_root() / "audit")
    client = FailingLangSmithClient()
    tracer = _enabled_tracer(spool, client)

    tracer.record(**_safe_node_attributes())
    tracer.record(**_safe_node_attributes(node_name="parse"))

    markers = _langsmith_markers(spool)
    assert len(markers) == 1
    assert markers[0].attributes == {
        "case_id": CASE_ID,
        "status": "degraded",
        "error_code": "external_export_failed",
        "fallback_used": "local_audit",
        "exporter_provider": "langsmith",
    }
    serialized = repr(markers)
    assert "private" not in serialized
    assert "pitch.pdf" not in serialized
    assert "sk-test" not in serialized
    assert client.create_calls == 1


def test_repeated_node_checkpoints_get_distinct_child_run_ids() -> None:
    client = RecordingLangSmithClient()
    spool = JsonlAuditSpool(_test_root() / "audit")
    tracer = _enabled_tracer(spool, client)

    tracer.record(
        **_safe_node_attributes(
            node_name="reflexion",
            checkpoint_id="startup-reflexion-shared",
            checkpoint_hash="a" * 64,
        )
    )
    tracer.record(
        **_safe_node_attributes(
            node_name="reflexion",
            checkpoint_id="startup-reflexion-shared",
            checkpoint_hash="b" * 64,
        )
    )

    reflexion_runs = [
        call for call in client.created if call["name"] == "startup.reflexion"
    ]
    assert len(reflexion_runs) == 2
    assert reflexion_runs[0]["id"] != reflexion_runs[1]["id"]
    assert reflexion_runs[0]["dotted_order"] != reflexion_runs[1]["dotted_order"]


def test_unsafe_enabled_metadata_is_blocked_before_client_construction() -> None:
    spool = JsonlAuditSpool(_test_root() / "audit")
    factory = RecordingLangSmithFactory()
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=True, credential_present=True),
        audit_spool=spool,
        client_factory=factory,
    )

    tracer.record(**_safe_node_attributes(), private_name="pitch.pdf")

    assert factory.created == 0
    marker = _langsmith_markers(spool)[-1]
    assert marker.attributes["status"] == "degraded"
    assert marker.attributes["error_code"] == "telemetry_privacy_rejected"


def test_export_and_secondary_health_failure_do_not_escape_into_workflow() -> None:
    client = FailingLangSmithClient()
    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=True, credential_present=True),
        audit_spool=FailingAuditSpool(),
        client_factory=lambda **_: client,
    )

    tracer.record(**_safe_node_attributes())
    tracer.flush()

    assert client.create_calls == 1


def test_composite_tracer_forwards_records_checkpoint_keys_and_flush() -> None:
    first = RecordingNodeTracer()
    second = RecordingNodeTracer()
    tracer = CompositeNodeTracer(first, second)

    tracer.record(case_id=CASE_ID, run_id=RUN_ID, node_name="ingest")
    tracer.record_checkpoint_keys({"case_id", "status"})
    tracer.flush()

    assert first.records == second.records == [
        {"case_id": CASE_ID, "run_id": RUN_ID, "node_name": "ingest"}
    ]
    assert first.checkpoint_keys == second.checkpoint_keys == {"case_id", "status"}
    assert first.flush_calls == second.flush_calls == 1


def _safe_node_attributes(
    *,
    node_name: str = "ingest",
    agent_role: str = "data_room",
    gate: str | None = None,
    gate_status: str | None = None,
    report_id: str | None = None,
    report_revision: int | None = None,
    report_checksum: str | None = None,
    checkpoint_id: str | None = None,
    checkpoint_hash: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    cost_usd: float = 0.0,
    provider: str | None = None,
    model: str | None = None,
    tool: str | None = None,
) -> dict[str, object | None]:
    return {
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "correlation_id": RUN_ID,
        "workflow_type": "startup",
        "node_name": node_name,
        "agent_role": agent_role,
        "status": "success",
        "duration_ms": 7,
        "latency_ms": 7,
        "retry_count": 0,
        "attempt": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "cost_usd": cost_usd,
        "provider": provider,
        "model": model,
        "tool": tool,
        "schema_version": "startup_node_span@1",
        "gate": gate,
        "gate_status": gate_status,
        "report_id": report_id,
        "report_revision": report_revision,
        "report_checksum": report_checksum,
        "checkpoint_id": checkpoint_id,
        "checkpoint_hash": checkpoint_hash,
    }


def _enabled_tracer(
    spool: JsonlAuditSpool,
    client: RecordingLangSmithClient,
) -> StartupLangSmithNodeTracer:
    return StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=True, credential_present=True),
        audit_spool=spool,
        client_factory=lambda **_: client,
    )


def _langsmith_markers(spool: JsonlAuditSpool) -> list[Any]:
    return [
        event
        for event in spool.read_bounded(max_events=100)
        if event.event_type == "observability.langsmith_status"
    ]


def _test_root() -> Path:
    root = Path(".tmp-q5-langsmith-tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


class RecordingLangSmithFactory:
    def __init__(self) -> None:
        self.created = 0

    def __call__(self, **_: object) -> object:
        self.created += 1
        return RecordingLangSmithClient()


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


class FailingLangSmithClient(RecordingLangSmithClient):
    def __init__(self) -> None:
        super().__init__()
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
        raise RuntimeError("private C:\\secret\\pitch.pdf prompt sk-test")


class RecordingNodeTracer:
    def __init__(self) -> None:
        self.records: list[Mapping[str, object]] = []
        self.checkpoint_keys: set[str] = set()
        self.flush_calls = 0

    def record(self, **attributes: object) -> None:
        self.records.append(attributes)

    def record_checkpoint_keys(self, keys: set[str]) -> None:
        self.checkpoint_keys = set(keys)

    def flush(self) -> None:
        self.flush_calls += 1


class FailingAuditSpool:
    def append(self, event: object) -> str:
        del event
        raise OSError("secondary_health_marker_unavailable")

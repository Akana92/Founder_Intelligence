from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.evals.startup_trace_sidecar import (
    REQUIRED_PDF_JOURNEY_NODES,
    build_startup_trace_sidecar,
    write_startup_trace_sidecar,
)
from due_diligence_agent.ports.tracing import AuditEvent


CASE_ID = "case-pdf-browser-1"
RUN_ID = f"startup-api-{CASE_ID}"
EXPECTED_TOOL_BOUNDARIES = {
    "advisor_public_research": "public_web_search",
    "document_intelligence": "startup_document_intelligence",
    "market_research": "startup_market_research",
    "metrics": "python_metrics",
}


def test_sidecar_projects_authoritative_same_case_trace_without_sensitive_fields(
    tmp_path: Path,
) -> None:
    spool_root = tmp_path / "audit"
    _seed_complete_trace(spool_root)

    payload = build_startup_trace_sidecar(
        audit_spool_root=spool_root,
        case_id=CASE_ID,
        run_id=RUN_ID,
    )

    assert payload["schema_version"] == "startup_trace_view@1"
    assert payload["case_id"] == CASE_ID
    assert payload["run_id"] == RUN_ID
    node_rows = payload["node_rows"]
    assert isinstance(node_rows, list)
    assert {row["node"] for row in node_rows} >= REQUIRED_PDF_JOURNEY_NODES
    assert all(row["case_id"] == CASE_ID and row["run_id"] == RUN_ID for row in node_rows)
    tool_rows = {
        row["node"]: row
        for row in node_rows
        if row.get("tool") in EXPECTED_TOOL_BOUNDARIES.values()
    }
    assert {
        node: row.get("tool") for node, row in tool_rows.items()
    } == EXPECTED_TOOL_BOUNDARIES
    assert all(
        isinstance(row.get("duration_ms"), int | float)
        and row["duration_ms"] >= 0
        and isinstance(row.get("retry_count"), int)
        and row["retry_count"] >= 0
        and "timeout_ms" in row
        and "evidence_count" in row
        and "fallback_used" in row
        for row in tool_rows.values()
    )
    public_research = tool_rows["advisor_public_research"]
    assert public_research["status"] == "partial"
    assert public_research["timeout_ms"] == 15_000
    assert public_research["evidence_count"] == 2
    assert public_research["fallback_used"] == "cached_public_sources"
    assert public_research["error_code"] == "provider_unavailable"
    assert payload["report_lineage"] == {
        "decision": "approved",
        "gate4_status": "completed",
        "report_checksum": "a" * 64,
        "report_id": "report-browser-1",
        "report_revision": 7,
    }
    assert payload["langsmith_health"] == {
        "error_code": "tracing_disabled",
        "fallback_used": "local_audit",
        "provider": "langsmith",
        "status": "disabled",
    }
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "timestamp_utc",
        "event_id",
        "checkpoint_id",
        "filename",
        "document_path",
        "prompt",
        "pitch.pdf",
        "C:\\\\",
    ):
        assert forbidden not in serialized


def test_sidecar_fails_closed_when_required_pdf_journey_node_is_missing(
    tmp_path: Path,
) -> None:
    spool_root = tmp_path / "audit"
    _seed_complete_trace(spool_root, omitted_node="market_research")

    with pytest.raises(ValueError, match="startup_trace_sidecar_node_coverage_missing"):
        build_startup_trace_sidecar(
            audit_spool_root=spool_root,
            case_id=CASE_ID,
            run_id=RUN_ID,
        )


def test_sidecar_counts_disclosure_policy_block_as_covered_required_node(
    tmp_path: Path,
) -> None:
    spool_root = tmp_path / "audit"
    _seed_complete_trace(
        spool_root,
        blocked_nodes={"market_analysis"},
    )

    payload = build_startup_trace_sidecar(
        audit_spool_root=spool_root,
        case_id=CASE_ID,
        run_id=RUN_ID,
    )

    market_analysis = next(
        row for row in payload["node_rows"] if row["node"] == "market_analysis"
    )
    assert market_analysis["status"] == "blocked"
    assert market_analysis["error_code"] == "blocked_by_policy:startup_disclosure"


def test_sidecar_writer_is_canonical_and_refuses_output_collision(tmp_path: Path) -> None:
    spool_root = tmp_path / "audit"
    output_path = tmp_path / "admin-trace.json"
    _seed_complete_trace(spool_root)

    written = write_startup_trace_sidecar(
        audit_spool_root=spool_root,
        case_id=CASE_ID,
        run_id=RUN_ID,
        output_path=output_path,
    )

    assert written == output_path
    assert output_path.read_bytes().endswith(b"\n")
    assert json.loads(output_path.read_text(encoding="utf-8"))["case_id"] == CASE_ID
    with pytest.raises(FileExistsError, match="startup_trace_sidecar_output_exists"):
        write_startup_trace_sidecar(
            audit_spool_root=spool_root,
            case_id=CASE_ID,
            run_id=RUN_ID,
            output_path=output_path,
        )


def _seed_complete_trace(
    audit_root: Path,
    *,
    omitted_node: str | None = None,
    blocked_nodes: set[str] | None = None,
) -> None:
    spool = JsonlAuditSpool(audit_root, max_mb=1)
    started_at = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    for index, node_name in enumerate(sorted(REQUIRED_PDF_JOURNEY_NODES)):
        if node_name == omitted_node:
            continue
        is_blocked = node_name in (blocked_nodes or set())
        attributes: dict[str, str | int | float | bool | None] = {
            "case_id": CASE_ID,
            "node_name": node_name,
            "agent_role": "orchestration",
            "attempt": 1,
            "retry_count": 0,
            "status": "blocked" if is_blocked else "success",
            "duration_ms": 12.5,
            "evidence_count": 1,
            "fallback_used": "none",
        }
        if is_blocked:
            attributes["error_code"] = "blocked_by_policy:startup_disclosure"
        if tool := EXPECTED_TOOL_BOUNDARIES.get(node_name):
            attributes["tool"] = tool
        spool.append(
            _event(
                event_id=f"node-{index:02d}",
                timestamp=started_at + timedelta(seconds=index),
                attributes=attributes,
            )
        )
    spool.append(
        _event(
            event_id="advisor-public-research",
            timestamp=started_at + timedelta(seconds=30),
            attributes={
                "case_id": CASE_ID,
                "node_name": "advisor_public_research",
                "agent_role": "market",
                "attempt": 0,
                "retry_count": 0,
                "status": "partial",
                "duration_ms": 4.5,
                "timeout_ms": 15_000,
                "evidence_count": 2,
                "fallback_used": "cached_public_sources",
                "error_code": "provider_unavailable",
                "tool": "public_web_search",
            },
        )
    )
    spool.append(
        _event(
            event_id="langsmith-disabled",
            timestamp=started_at + timedelta(minutes=1),
            event_type="observability.langsmith_status",
            attributes={
                "case_id": CASE_ID,
                "status": "disabled",
                "error_code": "tracing_disabled",
                "fallback_used": "local_audit",
                "exporter_provider": "langsmith",
            },
        )
    )
    spool.append(
        _event(
            event_id="report-lineage",
            timestamp=started_at + timedelta(minutes=2),
            event_type="startup_report.canonical_snapshot",
            attributes={
                "case_id": CASE_ID,
                "status": "success",
                "report_status": "canonical",
                "decision": "approved",
                "gate4_status": "completed",
                "report_id": "report-browser-1",
                "report_revision": 7,
                "report_checksum": "a" * 64,
            },
        )
    )


def _event(
    *,
    event_id: str,
    timestamp: datetime,
    attributes: dict[str, str | int | float | bool | None],
    event_type: str = "span",
) -> AuditEvent:
    return AuditEvent(
        schema_version="audit_event@1",
        event_id=event_id,
        timestamp_utc=timestamp.isoformat().replace("+00:00", "Z"),
        run_id=RUN_ID,
        correlation_id=f"corr-{event_id}",
        span_name="analysis.module",
        event_type=event_type,
        attributes=attributes,
    )

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Mapping, cast

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.services.startup_trace_query_service import (
    StartupLangSmithHealth,
    StartupTraceExporterHealth,
    StartupTraceNodeRow,
    StartupTraceReportLineage,
    StartupTraceUsageSummary,
    StartupTraceView,
)
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.presentation.streamlit.components.audit import (
    build_admin_observability_snapshot,
    build_startup_trace_admin_snapshot,
)


def test_admin_snapshot_uses_bounded_safe_scalar_trace_metadata_only() -> None:
    events = [
        _event(
            "event-1",
            span_name="llm.call",
            attributes={
                "case_id": "case-1",
                "status": "success",
                "latency_ms": 125.5,
                "estimated_cost_usd": 0.032,
                "input_tokens": 1200,
                "output_tokens": 350,
                "model": "gpt-5.6-terra",
            },
        ),
        _event(
            "event-2",
            span_name="sec.fetch",
            attributes={
                "case_id": "case-1",
                "status": "failed",
                "error_code": "provider_unavailable",
                "latency_ms": 80,
            },
        ),
        _event(
            "event-3",
            span_name="report.generate",
            attributes={
                "case_id": "case-1",
                "status": "success",
                "report_format": "pdf",
                "artifact_hash": "a" * 64,
            },
        ),
    ]

    snapshot = build_admin_observability_snapshot(events)

    assert snapshot["trace_summary"]["total_events"] == 3
    assert snapshot["trace_summary"]["status_counts"] == {"success": 2, "failed": 1}
    assert snapshot["cost_latency"]["estimated_cost_usd"] == 0.032
    assert snapshot["cost_latency"]["latency_ms_total"] == 205.5
    assert snapshot["source_health"] == [
        {"source": "sec.fetch", "status": "failed", "error_code": "provider_unavailable"}
    ]
    assert snapshot["report_integrity"] == [
        {"status": "success", "report_format": "pdf", "artifact_hash": "a" * 64}
    ]
    serialized = repr(snapshot).lower()
    assert "input_tokens" not in serialized
    assert "output_tokens" not in serialized
    assert "1200" not in serialized
    assert "350" not in serialized
    assert "gpt-5.6-terra" not in serialized


def test_admin_snapshot_drops_sensitive_or_non_scalar_event_attributes() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            _event(
                "event-1",
                attributes={
                    "status": "success",
                    "latency_ms": 10,
                    "payload": {"raw": "document text"},
                    "source_text": "raw founder memo",
                    "document_path": "C:/Users/Akana/private.pdf",
                    "prompt": "system instructions",
                },
            )
        ]
    )

    serialized = repr(snapshot).lower()
    assert "document text" not in serialized
    assert "founder memo" not in serialized
    assert "private.pdf" not in serialized
    assert "system instructions" not in serialized
    assert snapshot["trace_summary"]["total_events"] == 1


def test_admin_snapshot_resanitizes_malformed_legacy_values_before_display() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            _event(
                "event-1",
                span_name="report.generate",
                attributes={
                    "status": "failed-after-secret-prompt",
                    "artifact_hash": "C:/Users/Akana/private.pdf",
                    "latency_ms": 5,
                },
            )
        ]
    )

    serialized = repr(snapshot).lower()
    assert "failed-after-secret-prompt" not in serialized
    assert "private.pdf" not in serialized
    assert snapshot["trace_summary"]["status_counts"] == {}
    assert snapshot["report_integrity"] == [{}]


def test_admin_snapshot_exposes_safe_real_startup_disclosure_denial_fields() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            _event(
                "event-1",
                span_name="startup.disclosure_gate",
                event_type="startup_disclosure.denied",
                attributes={
                    "case_id": "case-1",
                    "decision": "denied",
                    "reason": "approval_required",
                    "approval_id": None,
                    "data_revision": 2,
                    "content_hash": "a" * 64,
                    "overall_class": "confidential",
                    "detected_class_count": 3,
                    "artifact_count": 2,
                    "fragment_count": 9,
                    "redaction_policy_version": "startup-redaction@1",
                    "egress_policy_version": "data-egress@1",
                    "destination": "openai.responses",
                },
            )
        ]
    )

    assert snapshot["privacy_redaction"] == [
        {
            "event_type": "startup_disclosure.denied",
            "decision": "denied",
            "reason": "approval_required",
            "data_revision": 2,
            "overall_class": "confidential",
            "detected_class_count": 3,
            "artifact_count": 2,
            "fragment_count": 9,
            "redaction_policy_version": "startup-redaction@1",
            "egress_policy_version": "data-egress@1",
            "destination": "openai.responses",
        }
    ]


def test_admin_snapshot_drops_sensitive_startup_disclosure_identifiers_and_values() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            _event(
                "event-1",
                span_name="startup.disclosure_gate",
                event_type="startup_disclosure.secret-prompt",
                attributes={
                    "case_id": "case-1",
                    "decision": "denied",
                    "reason": "secret-prompt",
                    "destination": "sk-proj-secret",
                    "redaction_policy_version": "startup-redaction@1",
                    "data_revision": 1,
                },
            )
        ]
    )

    serialized = repr(snapshot).lower()
    assert "startup_disclosure.secret-prompt" not in serialized
    assert "secret-prompt" not in serialized
    assert "sk-proj-secret" not in serialized
    assert snapshot["privacy_redaction"] == [
        {
            "decision": "denied",
            "data_revision": 1,
            "redaction_policy_version": "startup-redaction@1",
        }
    ]


def test_admin_snapshot_categorizes_real_analysis_module_source_and_report_shapes() -> None:
    snapshot = build_admin_observability_snapshot(
        [
            _event(
                "event-1",
                span_name="analysis.module",
                attributes={
                    "node_name": "collector",
                    "status": "failed",
                    "error_code": "provider_unavailable",
                    "fallback_used": "true",
                },
            ),
            _event(
                "event-2",
                span_name="analysis.module",
                attributes={
                    "node_name": "report.generate",
                    "status": "success",
                    "report_format": "pdf",
                    "artifact_hash": "a" * 64,
                },
            ),
            _event(
                "event-3",
                span_name="analysis.module",
                attributes={
                    "node_name": "report",
                    "status": "success",
                    "report_format": "pdf",
                    "evidence_hash": "b" * 64,
                },
            ),
        ]
    )

    assert snapshot["source_health"] == [
        {
            "source": "collector",
            "status": "failed",
            "error_code": "provider_unavailable",
            "fallback_used": "true",
        }
    ]
    assert snapshot["report_integrity"] == [
        {"status": "success", "report_format": "pdf", "artifact_hash": "a" * 64},
        {"status": "success", "report_format": "pdf", "evidence_hash": "b" * 64},
    ]


def test_admin_cost_latency_is_unavailable_without_observations_and_does_not_double_count() -> None:
    no_observations = build_admin_observability_snapshot([_event("event-1")])
    assert no_observations["cost_latency"] == {
        "estimated_cost_usd": None,
        "latency_ms_total": None,
    }

    with_both_duration_shapes = build_admin_observability_snapshot(
        [
            _event(
                "event-1",
                attributes={
                    "status": "success",
                    "latency_ms": 125,
                    "duration_ms": 300,
                    "cost_usd": 0.02,
                },
            )
        ]
    )
    assert with_both_duration_shapes["cost_latency"] == {
        "estimated_cost_usd": 0.02,
        "latency_ms_total": 125.0,
    }


def test_startup_trace_admin_snapshot_uses_exporter_dto_without_private_raw_attributes() -> None:
    view = StartupTraceView(
        case_id="case-alpha",
        run_id="run-alpha",
        node_rows=(
            StartupTraceNodeRow(
                case_id="case-alpha",
                run_id="run-alpha",
                node="market_sizing",
                attempt=1,
                retry_count=0,
                status="failed",
                error_code="tool_timeout",
                checkpoint_id="checkpoint-001",
                tool="python_interpreter",
                latency_ms=80.0,
                event_id="event-1",
                timestamp_utc="2026-08-13T12:00:00Z",
            ),
            StartupTraceNodeRow(
                case_id="case-alpha",
                run_id="run-alpha",
                node="market_sizing",
                attempt=2,
                retry_count=1,
                status="success",
                error_code=None,
                checkpoint_id="checkpoint-002",
                tool="python_interpreter",
                latency_ms=120.5,
                event_id="event-2",
                timestamp_utc="2026-08-13T12:00:01Z",
            ),
        ),
        usage_summary=StartupTraceUsageSummary(
            input_tokens=100,
            output_tokens=40,
            total_tokens=140,
            cost_usd=Decimal("0.0125"),
        ),
        report_lineage=StartupTraceReportLineage(
            decision="approved",
            gate4_status="completed",
            report_id="report-001",
            report_revision=7,
            report_checksum="a" * 64,
        ),
        exporter_health=StartupTraceExporterHealth(
            status="degraded",
            error_code="external_export_failed",
            fallback_used="local_audit",
        ),
        langsmith_health=StartupLangSmithHealth(
            provider="langsmith",
            status="healthy",
            error_code="none",
            fallback_used="local_audit",
        ),
    )

    snapshot = build_startup_trace_admin_snapshot(view)

    assert snapshot["trace_summary"] == {
        "case_id": "case-alpha",
        "run_id": "run-alpha",
        "total_events": 2,
        "status_counts": {"failed": 1, "success": 1},
    }
    assert snapshot["node_timeline"] == [
        {
            "timestamp_utc": "2026-08-13T12:00:00Z",
            "node": "market_sizing",
            "attempt": 1,
            "retry_count": 0,
            "status": "failed",
            "error_code": "tool_timeout",
            "checkpoint_id": "checkpoint-001",
            "tool": "python_interpreter",
            "latency_ms": 80.0,
        },
        {
            "timestamp_utc": "2026-08-13T12:00:01Z",
            "node": "market_sizing",
            "attempt": 2,
            "retry_count": 1,
            "status": "success",
            "checkpoint_id": "checkpoint-002",
            "tool": "python_interpreter",
            "latency_ms": 120.5,
        },
    ]
    assert snapshot["usage_summary"] == {
        "input_tokens": 100,
        "output_tokens": 40,
        "total_tokens": 140,
        "cost_usd": "0.0125",
    }
    assert snapshot["report_lineage"] == {
        "decision": "approved",
        "gate4_status": "completed",
        "report_id": "report-001",
        "report_revision": 7,
        "report_checksum": "a" * 64,
    }
    assert snapshot["exporter_health"] == {
        "status": "degraded",
        "error_code": "external_export_failed",
        "fallback_used": "local_audit",
    }
    assert snapshot["langsmith_health"] == {
        "provider": "langsmith",
        "status": "healthy",
        "error_code": "none",
        "fallback_used": "local_audit",
    }
    serialized = repr(snapshot).lower()
    assert "prompt" not in serialized
    assert "source_text" not in serialized
    assert "raw" not in serialized


def test_jsonl_audit_spool_bounded_reader_limits_files_bytes_and_line_length(
    tmp_path: Path,
) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    first = _event("event-1", attributes={"status": "success"})
    spool.append(first)
    for index in range(5):
        path = tmp_path / "2026" / "08" / "14" / f"legacy-{index}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(first.__dict__) + "\n", encoding="utf-8")
    long_line = tmp_path / "2026" / "08" / "15" / "long.jsonl"
    long_line.parent.mkdir(parents=True, exist_ok=True)
    long_line.write_text("{" + (" " * 100) + "}\n", encoding="utf-8")

    events = spool.read_bounded(
        max_events=10,
        max_files=1,
        max_bytes=5000,
        max_line_chars=5000,
    )

    assert len(events) == 1
    assert events[0].event_id == "event-1"

    assert spool.read_bounded(
        max_events=10,
        max_files=10,
        max_bytes=5000,
        max_line_chars=50,
    ) == []


def _event(
    event_id: str,
    *,
    span_name: str = "llm.call",
    event_type: str = "span",
    attributes: dict[str, object] | None = None,
) -> AuditEvent:
    audit_attributes = cast(Mapping[str, str | int | float | bool | None], attributes or {})
    return AuditEvent(
        schema_version="audit_event@1",
        event_id=event_id,
        timestamp_utc=datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        run_id="run-1",
        correlation_id="corr-1",
        span_name=span_name,
        event_type=event_type,
        attributes=audit_attributes,
    )

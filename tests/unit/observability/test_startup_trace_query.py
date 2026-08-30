from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from due_diligence_agent.adapters.observability.privacy import PrimitiveTraceValue
from due_diligence_agent.application.services.startup_trace_query_service import (
    StartupLangSmithHealth,
    StartupTraceExporterHealth,
    StartupTraceQueryService,
    StartupTraceUsageSummary,
)
from due_diligence_agent.ports.tracing import AuditEvent


def test_get_view_rejects_unsafe_case_and_run_filters() -> None:
    service = StartupTraceQueryService(_FakeSpool(()))

    with pytest.raises(ValueError, match="trace_attribute.value_"):
        service.get_view(case_id="john@example.com", run_id="run-1")
    with pytest.raises(ValueError, match="trace_attribute.value_"):
        service.get_view(case_id="case-1", run_id="sk-proj-secret")


def test_get_view_keeps_the_selected_run_when_older_history_fills_the_scan_window() -> None:
    target_case_id = "case-current"
    target_run_id = "run-current"
    old_events = tuple(
        _event(
            f"old-{index}",
            "case-old",
            "run-old",
            "2026-08-13T11:%02d:%02dZ" % ((index // 60) % 60, index % 60),
            attributes={"status": "success"},
        )
        for index in range(2000)
    )
    target_event = _event(
        "current-gate4",
        target_case_id,
        target_run_id,
        "2026-08-13T12:00:00Z",
        event_type="startup_report.gate4_completed",
        span_name="report.generate",
        attributes={
            "status": "completed",
            "report_status": "canonical",
            "report_id": "report-current",
            "report_revision": 2,
            "report_checksum": "a" * 64,
            "gate4_status": "completed",
            "decision": "approved",
        },
    )

    class BoundedHistorySpool:
        def read_bounded(
            self,
            *,
            max_events: int = 100,
            max_files: int = 128,  # noqa: ARG002
            max_bytes: int = 1_000_000,  # noqa: ARG002
            max_line_chars: int = 1024,  # noqa: ARG002
            newest_first: bool = False,
        ) -> list[AuditEvent]:
            events = (*old_events, target_event)
            ordered = reversed(events) if newest_first else iter(events)
            return list(ordered)[:max_events]

    view = StartupTraceQueryService(BoundedHistorySpool()).get_view(
        target_case_id,
        target_run_id,
    )

    assert [row.event_id for row in view.node_rows] == ["current-gate4"]
    assert view.report_lineage.gate4_status == "completed"
    assert view.report_lineage.report_id == "report-current"


def test_get_view_keeps_late_gate4_lineage_after_same_run_exceeds_ui_limit() -> None:
    old_events = tuple(
        _event(
            f"old-{index:03d}",
            "case-current",
            "run-current",
            "2026-08-13T12:00:00Z",
            attributes={"node_name": "financial_analysis", "status": "success"},
        )
        for index in range(200)
    )
    gate4_event = _event(
        "zz-current-gate4",
        "case-current",
        "run-current",
        "2026-08-13T12:00:00Z",
        event_type="startup_report.gate4_completed",
        span_name="report.generate",
        attributes={
            "status": "completed",
            "report_status": "canonical",
            "report_id": "report-current",
            "report_revision": 2,
            "report_checksum": "a" * 64,
            "gate4_status": "completed",
            "decision": "approved",
        },
    )

    view = StartupTraceQueryService(_FakeSpool((*old_events, gate4_event))).get_view(
        "case-current",
        "run-current",
    )

    assert len(view.node_rows) == 200
    assert view.node_rows[-1].event_id == "zz-current-gate4"
    assert view.report_lineage.gate4_status == "completed"
    assert view.report_lineage.report_id == "report-current"


def test_get_view_filters_exact_case_and_run_and_caps_to_200_events() -> None:
    events = (
        [
            _event(
                f"event-case-1-{idx}",
                "case-1",
                "run-shared",
                "2026-08-13T12:00:%02dZ" % (idx % 60),
                attributes={"status": "success"},
            )
            for idx in range(250)
        ]
        + [
            _event(
                f"event-case-2-{idx}",
                "case-2",
                "run-shared",
                "2026-08-13T12:01:%02dZ" % (idx % 60),
                attributes={"status": "success"},
            )
            for idx in range(120)
        ]
    )
    service = StartupTraceQueryService(_FakeSpool(tuple(events)))

    view = service.get_view("case-1", "run-shared", max_events=350)

    assert view.schema_version == "startup_trace_view@1"
    assert view.case_id == "case-1"
    assert view.run_id == "run-shared"
    assert len(view.node_rows) == 200
    assert all(row.case_id == "case-1" for row in view.node_rows)
    assert all(row.run_id == "run-shared" for row in view.node_rows)
    assert view.node_rows[0].event_id.startswith("event-case-1-")


def test_get_view_clamps_internal_scan_limit_for_huge_caller_event_limit() -> None:
    spool = _RecordingSpool(
        tuple(
            _event(
                f"event-{idx}",
                "case-huge",
                "run-huge",
                "2026-08-13T12:00:%02dZ" % (idx % 60),
                attributes={"status": "success"},
            )
            for idx in range(500)
        )
    )
    service = StartupTraceQueryService(spool)

    view = service.get_view("case-huge", "run-huge", max_events=1_000_000)

    assert spool.max_events_calls == [2000]
    assert len(view.node_rows) == 200


def test_get_view_keeps_matching_case_when_unrelated_scanned_events_exceed_cap() -> None:
    events = tuple(
        _event(
            f"noise-{idx}",
            "case-noise",
            "run-shared",
            timestamp=f"2026-08-13T12:00:{idx % 60:02d}Z",
            attributes={"status": "success"},
        )
        for idx in range(250)
    ) + (
        _event(
            "target-match",
            "case-target",
            "run-shared",
            timestamp="2026-08-13T12:01:00Z",
            attributes={"status": "success"},
        ),
    )
    service = StartupTraceQueryService(_FakeSpool(events))

    view = service.get_view("case-target", "run-shared")

    assert len(view.node_rows) == 1
    assert view.node_rows[0].event_id == "target-match"


def test_view_orders_events_stably_by_timestamp_then_event_id() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event("b", "case-stable", "run-stable", "2026-08-13T12:00:01Z", attributes={"status": "success"}),
                _event("a", "case-stable", "run-stable", "2026-08-13T12:00:01Z", attributes={"status": "success"}),
                _event("c", "case-stable", "run-stable", "2026-08-13T12:00:00Z", attributes={"status": "success"}),
            )
        )
    )

    view = service.get_view("case-stable", "run-stable")

    assert [node.event_id for node in view.node_rows] == ["c", "a", "b"]


def test_get_view_keeps_optional_checkpoint_tool_and_report_fields_nullable() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "event-1",
                    "case-nulls",
                    "run-nulls",
                    attributes={
                        "status": "success",
                        "node_name": "analysis.module",
                        "input_tokens": 120,
                        "cost_usd": 0.12,
                    },
                ),
            )
        )
    )

    view = service.get_view("case-nulls", "run-nulls")

    assert view.node_rows[0].checkpoint_id is None
    assert view.node_rows[0].tool is None
    assert view.report_lineage.report_id is None
    assert view.report_lineage.report_checksum is None
    assert view.report_lineage.report_revision is None
    assert view.exporter_health is None
    assert view.langsmith_health is None
    assert view.usage_summary == StartupTraceUsageSummary(
        input_tokens=120,
        output_tokens=None,
        total_tokens=None,
        cost_usd=Decimal("0.12"),
    )


def test_exporter_degradation_is_correlated_without_becoming_a_fake_node() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "target-node",
                    "case-target",
                    "run-target",
                    attributes={"node_name": "metrics", "status": "success"},
                ),
                _event(
                    "other-run-marker",
                    "case-target",
                    "run-other",
                    event_type="observability.exporter_degraded",
                    attributes={
                        "status": "degraded",
                        "error_code": "external_export_failed",
                        "fallback_used": "local_audit",
                    },
                ),
                _event(
                    "other-case-marker",
                    "case-other",
                    "run-target",
                    event_type="observability.exporter_degraded",
                    attributes={
                        "status": "degraded",
                        "error_code": "external_export_failed",
                        "fallback_used": "local_audit",
                    },
                ),
                _event(
                    "target-marker",
                    "case-target",
                    "run-target",
                    event_type="observability.exporter_degraded",
                    attributes={
                        "status": "degraded",
                        "error_code": "external_export_failed",
                        "fallback_used": "local_audit",
                        "prompt": "secret system instructions",
                    },
                ),
            )
        )
    )

    view = service.get_view("case-target", "run-target")

    assert view.exporter_health == StartupTraceExporterHealth(
        status="degraded",
        error_code="external_export_failed",
        fallback_used="local_audit",
    )
    assert [row.event_id for row in view.node_rows] == ["target-node"]
    assert "secret system instructions" not in repr(view)


@pytest.mark.parametrize(
    ("status", "error_code"),
    (
        ("disabled", "tracing_disabled"),
        ("blocked_missing_credential", "missing_credential"),
        ("healthy", "none"),
        ("degraded", "external_export_failed"),
        ("degraded", "telemetry_privacy_rejected"),
    ),
)
def test_langsmith_health_is_separate_and_never_becomes_a_fake_node(
    status: str,
    error_code: str,
) -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "target-node",
                    "case-langsmith",
                    "run-langsmith",
                    attributes={"node_name": "report", "status": "success"},
                ),
                _event(
                    "langsmith-marker",
                    "case-langsmith",
                    "run-langsmith",
                    event_type="observability.langsmith_status",
                    attributes={
                        "status": status,
                        "error_code": error_code,
                        "fallback_used": "local_audit",
                        "exporter_provider": "langsmith",
                        "prompt": "secret system instructions",
                    },
                ),
            )
        )
    )

    view = service.get_view("case-langsmith", "run-langsmith")

    assert view.langsmith_health == StartupLangSmithHealth(
        provider="langsmith",
        status=status,
        error_code=error_code,
        fallback_used="local_audit",
    )
    assert [row.event_id for row in view.node_rows] == ["target-node"]
    assert "secret system instructions" not in repr(view)


def test_invalid_langsmith_health_is_ignored_without_becoming_a_fake_node() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "invalid-langsmith-marker",
                    "case-langsmith-invalid",
                    "run-langsmith-invalid",
                    event_type="observability.langsmith_status",
                    attributes={
                        "status": "healthy",
                        "error_code": "external_export_failed",
                        "fallback_used": "local_audit",
                        "exporter_provider": "other",
                    },
                ),
            )
        )
    )

    view = service.get_view("case-langsmith-invalid", "run-langsmith-invalid")

    assert view.langsmith_health is None
    assert view.node_rows == ()


def test_exporter_marker_does_not_consume_node_cap_and_is_detected_after_it() -> None:
    node_events = tuple(
        _event(
            f"node-{index:03d}",
            "case-cap",
            "run-cap",
            timestamp=f"2026-08-13T12:{index // 60:02d}:{index % 60:02d}Z",
            attributes={"node_name": "metrics", "status": "success"},
        )
        for index in range(250)
    )
    invalid_early_marker = _event(
        "000-invalid-marker",
        "case-cap",
        "run-cap",
        timestamp="2026-08-13T11:59:59Z",
        event_type="observability.exporter_degraded",
        attributes={
            "status": "unknown",
            "error_code": "external_export_failed",
            "fallback_used": "local_audit",
        },
    )
    valid_late_marker = _event(
        "zzz-valid-marker",
        "case-cap",
        "run-cap",
        timestamp="2026-08-13T13:00:00Z",
        event_type="observability.exporter_degraded",
        attributes={
            "status": "degraded",
            "error_code": "external_export_failed",
            "fallback_used": "local_audit",
        },
    )
    service = StartupTraceQueryService(
        _FakeSpool((invalid_early_marker, *node_events, valid_late_marker))
    )

    view = service.get_view("case-cap", "run-cap")

    assert len(view.node_rows) == 200
    assert view.exporter_health == StartupTraceExporterHealth(
        status="degraded",
        error_code="external_export_failed",
        fallback_used="local_audit",
    )


def test_view_drops_disallowed_event_attributes_and_uses_safe_scalars_only() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "event-bad",
                    "case-safe",
                    "run-safe",
                    attributes={
                        "status": "error",
                        "prompt": "secret system instructions",
                        "input.value": "private text",
                        "tool.result": "private tool result",
                        "attempt": 2,
                        "retry_count": 1,
                        "latency_ms": 12.5,
                        "artifact_hash": "a" * 64,
                        "node_name": "analysis.module",
                    },
                ),
            )
        )
    )

    view = service.get_view("case-safe", "run-safe")

    row = view.node_rows[0]
    assert row.status == "error"
    assert row.attempt == 2
    assert row.retry_count == 1
    assert row.latency_ms == 12.5
    assert "secret system instructions" not in repr(view)
    assert "private text" not in repr(view)
    assert "private tool result" not in repr(view)


def test_lineage_fields_are_populated_when_valid_startup_disclosure_present() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "event-0",
                    "case-lineage",
                    "run-lineage",
                    event_type="startup_disclosure.approved",
                    attributes={
                        "case_id": "case-lineage",
                        "decision": "approved",
                        "data_revision": 11,
                        "content_hash": "a" * 64,
                        "status": "success",
                    },
                    span_name="startup.disclosure_gate",
                ),
            )
        )
    )

    view = service.get_view("case-lineage", "run-lineage")

    assert view.report_lineage.decision == "approved"
    assert view.report_lineage.report_id is None
    assert view.report_lineage.report_revision == 11
    assert view.report_lineage.report_checksum == "a" * 64


def test_lineage_drops_invalid_startup_disclosure_content_hash_and_unsafe_decision() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "event-0",
                    "case-malformed-lineage",
                    "run-malformed-lineage",
                    event_type="startup_disclosure.approved",
                    attributes={
                        "case_id": "case-malformed-lineage",
                        "decision": "Not Approved",
                        "reason": "private secret text",
                        "content_hash": "not-a-hash",
                        "data_revision": 11,
                    },
                    span_name="startup.disclosure_gate",
                ),
            )
        )
    )

    view = service.get_view("case-malformed-lineage", "run-malformed-lineage")

    assert view.report_lineage.decision is None
    assert view.report_lineage.report_revision == 11
    assert view.report_lineage.report_checksum is None


def test_run_id_collision_does_not_cross_contaminate_views() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event("e1", "case-a", "shared-run", attributes={"status": "failed"}),
                _event("e2", "case-b", "shared-run", attributes={"status": "success"}),
                _event("e3", "case-a", "shared-run", attributes={"status": "success"}),
                _event("e4", "case-b", "other-run", attributes={"status": "success"}),
            )
        )
    )

    case_a = service.get_view("case-a", "shared-run")
    case_b = service.get_view("case-b", "shared-run")

    assert {row.event_id for row in case_a.node_rows} == {"e1", "e3"}
    assert {row.event_id for row in case_b.node_rows} == {"e2"}


def test_lineage_groups_exact_case_run_with_retries_tools_and_missing_fields() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "target-retry",
                    "case-alpha",
                    "run-alpha",
                    timestamp="2026-08-13T12:00:03Z",
                    attributes={
                        "node_name": "market_sizing",
                        "attempt": 2,
                        "retry_count": 1,
                        "status": "success",
                        "checkpoint_id": "checkpoint-002",
                        "tool": "python_interpreter",
                        "latency_ms": 120.5,
                    },
                ),
                _event(
                    "same-run-other-case",
                    "case-beta",
                    "run-alpha",
                    timestamp="2026-08-13T12:00:01Z",
                    attributes={"node_name": "market_sizing", "status": "failed", "tool": "web_search"},
                ),
                _event(
                    "target-first",
                    "case-alpha",
                    "run-alpha",
                    timestamp="2026-08-13T12:00:02Z",
                    attributes={
                        "node_name": "market_sizing",
                        "attempt": 1,
                        "retry_count": 0,
                        "status": "error",
                        "error_code": "tool_timeout",
                        "latency_ms": 80,
                    },
                ),
                _event(
                    "same-case-other-run",
                    "case-alpha",
                    "run-beta",
                    timestamp="2026-08-13T12:00:00Z",
                    attributes={"node_name": "risk_review", "status": "success", "tool": "sec_filings"},
                ),
                _event(
                    "target-missing",
                    "case-alpha",
                    "run-alpha",
                    timestamp="2026-08-13T12:00:04Z",
                    attributes={"node_name": "risk_review", "status": "success", "latency_ms": -1},
                ),
            )
        )
    )

    view = service.get_view("case-alpha", "run-alpha")

    assert [row.event_id for row in view.node_rows] == ["target-first", "target-retry", "target-missing"]
    assert [(row.node, row.attempt, row.retry_count, row.status) for row in view.node_rows] == [
        ("market_sizing", 1, 0, "error"),
        ("market_sizing", 2, 1, "success"),
        ("risk_review", None, None, "success"),
    ]
    assert view.node_rows[0].error_code == "tool_timeout"
    assert view.node_rows[1].tool == "python_interpreter"
    assert view.node_rows[1].checkpoint_id == "checkpoint-002"
    assert view.node_rows[1].latency_ms == 120.5
    assert view.node_rows[2].latency_ms is None
    assert all(row.case_id == "case-alpha" and row.run_id == "run-alpha" for row in view.node_rows)


def test_usage_and_report_lineage_use_only_valid_canonical_report_events() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "usage-valid",
                    "case-usage",
                    "run-usage",
                    timestamp="2026-08-13T12:00:00Z",
                    attributes={
                        "input_tokens": 100,
                        "output_tokens": 40,
                        "total_tokens": 140,
                        "cost_usd": 0.0125,
                        "tokens": 999,
                    },
                ),
                _event(
                    "usage-invalid",
                    "case-usage",
                    "run-usage",
                    timestamp="2026-08-13T12:00:01Z",
                    attributes={
                        "input_tokens": -10,
                        "output_tokens": 10_000_001,
                        "total_tokens": 50,
                        "estimated_cost_usd": float("nan"),
                    },
                ),
                _event(
                    "report-stale",
                    "case-usage",
                    "run-usage",
                    timestamp="2026-08-13T12:00:02Z",
                    event_type="startup_report.stale",
                    attributes={
                        "report_id": "report-stale",
                        "report_revision": 99,
                        "report_checksum": "b" * 64,
                        "gate4_status": "stale",
                        "status": "success",
                    },
                ),
                _event(
                    "report-rejected",
                    "case-usage",
                    "run-usage",
                    timestamp="2026-08-13T12:00:03Z",
                    event_type="startup_report.rejected",
                    attributes={
                        "report_id": "report-rejected",
                        "report_revision": 100,
                        "report_checksum": "d" * 64,
                        "gate4_status": "rejected",
                        "status": "success",
                    },
                ),
                _event(
                    "report-canonical",
                    "case-usage",
                    "run-usage",
                    timestamp="2026-08-13T12:00:04Z",
                    event_type="startup_report.canonical",
                    attributes={
                        "report_id": "report-001",
                        "report_revision": 7,
                        "report_checksum": "c" * 64,
                        "gate4_status": "completed",
                        "status": "success",
                    },
                ),
            )
        )
    )

    view = service.get_view("case-usage", "run-usage")

    assert view.usage_summary == StartupTraceUsageSummary(
        input_tokens=100,
        output_tokens=40,
        total_tokens=190,
        cost_usd=Decimal("0.0125"),
    )
    assert view.report_lineage.gate4_status == "completed"
    assert view.report_lineage.report_id == "report-001"
    assert view.report_lineage.report_revision == 7
    assert view.report_lineage.report_checksum == "c" * 64


def test_canonical_report_lineage_requires_safe_non_null_gate4_status() -> None:
    service = StartupTraceQueryService(
        _FakeSpool(
            (
                _event(
                    "report-missing-gate4",
                    "case-report-gate",
                    "run-report-gate",
                    timestamp="2026-08-13T12:00:00Z",
                    event_type="startup_report.canonical",
                    attributes={
                        "report_id": "report-missing",
                        "report_revision": 8,
                        "report_checksum": "e" * 64,
                        "status": "success",
                    },
                ),
                _event(
                    "report-unsafe-gate4",
                    "case-report-gate",
                    "run-report-gate",
                    timestamp="2026-08-13T12:00:01Z",
                    event_type="startup_report.canonical",
                    attributes={
                        "report_id": "report-unsafe",
                        "report_revision": 9,
                        "report_checksum": "f" * 64,
                        "gate4_status": "not completed",
                        "status": "success",
                    },
                ),
            )
        )
    )

    view = service.get_view("case-report-gate", "run-report-gate")

    assert view.report_lineage.gate4_status is None
    assert view.report_lineage.report_id is None
    assert view.report_lineage.report_revision is None
    assert view.report_lineage.report_checksum is None


@dataclass(frozen=True)
class _FakeSpool:
    events: tuple[AuditEvent, ...]

    def read_bounded(
        self,
        *,
        max_events: int = 100,
        max_files: int = 128,  # noqa: ARG004
        max_bytes: int = 1_000_000,  # noqa: ARG004
        max_line_chars: int = 1024,  # noqa: ARG004
        newest_first: bool = False,  # noqa: ARG004
    ) -> list[AuditEvent]:
        return list(self.events[:max_events])


@dataclass(frozen=True)
class _RecordingSpool:
    events: tuple[AuditEvent, ...]
    max_events_calls: list[int]

    def __init__(self, events: tuple[AuditEvent, ...]) -> None:
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "max_events_calls", [])

    def read_bounded(
        self,
        *,
        max_events: int = 100,
        max_files: int = 128,  # noqa: ARG004
        max_bytes: int = 1_000_000,  # noqa: ARG004
        max_line_chars: int = 1024,  # noqa: ARG004
        newest_first: bool = False,  # noqa: ARG004
    ) -> list[AuditEvent]:
        self.max_events_calls.append(max_events)
        return list(self.events[:max_events])


def _event(
    event_id: str,
    case_id: str,
    run_id: str,
    timestamp: str | None = None,
    *,
    span_name: str = "analysis.module",
    event_type: str = "span",
    attributes: dict[str, PrimitiveTraceValue] | None = None,
) -> AuditEvent:
    payload: dict[str, PrimitiveTraceValue] = {"case_id": case_id}
    payload.update(attributes or {})
    return AuditEvent(
        schema_version="audit_event@1",
        event_id=event_id,
        timestamp_utc=timestamp
        or datetime(2026, 8, 13, 12, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        run_id=run_id,
        correlation_id=f"corr-{event_id}",
        span_name=span_name,
        event_type=event_type,
        attributes=payload,
    )

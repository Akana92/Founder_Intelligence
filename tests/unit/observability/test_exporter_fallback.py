from __future__ import annotations

from dataclasses import dataclass

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext, TraceFlags, TraceState

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.observability.otel import (
    REQUIRED_SPAN_NAMES,
    AuditPersistenceError,
    DurableFallbackSpanExporter,
    configure_otel,
)
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer


def test_exporter_failure_spools_sanitized_event_without_failing_workflow(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    exporter = DurableFallbackSpanExporter(_FailingExporter(), spool, sanitizer=StrictTraceSanitizer())

    result = exporter.export([_unsafe_test_span(prompt="secret prompt", output="secret output")])

    assert result is SpanExportResult.FAILURE
    payload = "".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.jsonl"))
    assert "secret prompt" not in payload
    assert "secret output" not in payload
    assert "RuntimeError" not in payload
    assert '"span_name":"llm.call"' in payload
    assert '"correlation_id":"corr-1"' in payload

    events = spool.read_batch()
    assert [event.event_type for event in events] == [
        "span",
        "observability.exporter_degraded",
    ]
    assert events[1].run_id == "run-1"
    assert events[1].correlation_id == "corr-1"
    assert events[1].attributes == {
        "case_id": "case-1",
        "status": "degraded",
        "error_code": "external_export_failed",
        "fallback_used": "local_audit",
    }


def test_exporter_exception_spools_degradation_for_each_correlatable_startup_span(
    tmp_path,
) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    exporter = DurableFallbackSpanExporter(
        _RaisingExporter(),
        spool,
        sanitizer=StrictTraceSanitizer(),
    )

    result = exporter.export(
        [
            _unsafe_test_span(case_id="case-1", correlation_id="corr-1"),
            _unsafe_test_span(case_id="case-2", correlation_id="corr-2"),
            _unsafe_test_span(case_id=None, correlation_id="corr-no-case"),
        ]
    )

    assert result is SpanExportResult.FAILURE
    events = spool.read_batch()
    degradation_events = [
        event for event in events if event.event_type == "observability.exporter_degraded"
    ]
    assert [(event.attributes["case_id"], event.correlation_id) for event in degradation_events] == [
        ("case-1", "corr-1"),
        ("case-2", "corr-2"),
    ]
    assert all(
        event.attributes
        == {
            "case_id": event.attributes["case_id"],
            "status": "degraded",
            "error_code": "external_export_failed",
            "fallback_used": "local_audit",
        }
        for event in degradation_events
    )


def test_exporter_fails_closed_when_degradation_marker_cannot_be_persisted() -> None:
    spool = _FailingAfterFirstAppendSpool()
    exporter = DurableFallbackSpanExporter(
        _FailingExporter(),
        spool,
        sanitizer=StrictTraceSanitizer(),
        audit_required=True,
    )

    with pytest.raises(AuditPersistenceError, match="AUDIT_PERSISTENCE_ERROR"):
        exporter.export([_unsafe_test_span()])

    assert spool.append_calls == 2


def test_exporter_sanitizes_spans_before_delegate_export(tmp_path) -> None:
    delegate = _RecordingExporter()
    exporter = DurableFallbackSpanExporter(
        delegate,
        JsonlAuditSpool(tmp_path, max_mb=1),
        sanitizer=StrictTraceSanitizer(),
    )
    original_span = _FakeSpan(
        name="llm.call",
        attributes={
            "run_id": "run-1",
            "correlation_id": "corr-1",
            "case_id": "case-1",
            "status": "success",
            "input.value": "secret prompt",
            "output.value": "secret output",
            "exception.message": "RuntimeError: secret output",
            "tool.arguments": "secret tool args",
            "tool.result": "secret tool result",
            "retrieval.content": "raw chunk content",
        },
    )

    result = exporter.export([original_span])

    assert result is SpanExportResult.SUCCESS
    assert delegate.export_calls == 1
    assert len(delegate.exported_spans) == 1
    assert delegate.exported_spans[0] is not original_span
    exported_attributes = delegate.exported_spans[0].attributes
    assert exported_attributes == {
        "run_id": "run-1",
        "correlation_id": "corr-1",
        "case_id": "case-1",
        "status": "success",
    }
    serialized = repr(exported_attributes)
    for leaked in (
        "secret prompt",
        "secret output",
        "RuntimeError",
        "secret tool args",
        "secret tool result",
        "raw chunk content",
    ):
        assert leaked not in serialized


def test_exporter_removes_nested_span_payloads_before_delegate_export(tmp_path) -> None:
    delegate = _RecordingExporter()
    exporter = DurableFallbackSpanExporter(
        delegate,
        JsonlAuditSpool(tmp_path, max_mb=1),
        sanitizer=StrictTraceSanitizer(),
    )
    original_span = _FakeSpan(
        name="llm.call",
        attributes={
            "run_id": "run-1",
            "correlation_id": "corr-1",
            "case_id": "case-1",
            "status": "error",
        },
        events=(
            _FakeEvent(
                name="exception",
                attributes={
                    "exception.message": "RuntimeError: nested secret output",
                    "exception.stacktrace": "stack with secret prompt",
                },
            ),
        ),
        links=(
            _FakeLink(
                attributes={
                    "tool.arguments": "nested secret tool args",
                    "retrieval.content": "nested raw chunk content",
                }
            ),
        ),
        status=_FakeStatus(description="nested secret status description"),
    )

    result = exporter.export([original_span])

    assert result is SpanExportResult.SUCCESS
    assert delegate.export_calls == 1
    exported_span = delegate.exported_spans[0]
    assert exported_span.events == ()
    assert exported_span.links == ()
    assert getattr(exported_span.status, "description", None) is None
    serialized = repr((exported_span.events, exported_span.links, exported_span.status))
    serialized += exported_span.to_json()
    for leaked in (
        "nested secret output",
        "stack with secret prompt",
        "nested secret tool args",
        "nested raw chunk content",
        "nested secret status description",
    ):
        assert leaked not in serialized


def test_exporter_replaces_original_resource_before_delegate_export(tmp_path) -> None:
    delegate = _RecordingExporter()
    exporter = DurableFallbackSpanExporter(
        delegate,
        JsonlAuditSpool(tmp_path, max_mb=1),
        sanitizer=StrictTraceSanitizer(),
    )
    original_span = _FakeSpan(
        name="llm.call",
        attributes={
            "run_id": "run-1",
            "correlation_id": "corr-1",
            "case_id": "case-1",
            "status": "success",
        },
        resource=Resource.create(
            {
                "service.name": "unsafe service secret prompt",
                "deployment.environment": "customer email john@example.com",
            }
        ),
    )

    result = exporter.export([original_span])

    assert result is SpanExportResult.SUCCESS
    exported_span = delegate.exported_spans[0]
    exported_resource = dict(exported_span.resource.attributes)
    assert exported_resource["service.name"] == "investment-due-diligence-agent"
    serialized = exported_span.to_json()
    for leaked in (
        "unsafe service secret prompt",
        "customer email john@example.com",
        "deployment.environment",
    ):
        assert leaked not in serialized


def test_exporter_fails_closed_when_span_name_is_not_safe(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    exporter = DurableFallbackSpanExporter(_CountingExporter(), spool, sanitizer=StrictTraceSanitizer())

    with pytest.raises(AuditPersistenceError, match="AUDIT_PERSISTENCE_ERROR"):
        exporter.export([_unsafe_test_span(name="llm.call secret prompt")])

    assert exporter.delegate.export_calls == 0
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_audit_required_failure_raises_stable_error_before_export() -> None:
    exporter = DurableFallbackSpanExporter(
        _CountingExporter(),
        _FailingSpool(),
        sanitizer=StrictTraceSanitizer(),
        audit_required=True,
    )

    with pytest.raises(AuditPersistenceError, match="AUDIT_PERSISTENCE_ERROR"):
        exporter.export([_unsafe_test_span()])

    assert exporter.delegate.export_calls == 0


def test_audit_optional_failure_returns_failure_without_leaking_to_delegate() -> None:
    exporter = DurableFallbackSpanExporter(
        _CountingExporter(),
        _FailingSpool(),
        sanitizer=StrictTraceSanitizer(),
        audit_required=False,
    )

    assert exporter.export([_unsafe_test_span()]) is SpanExportResult.FAILURE
    assert exporter.delegate.export_calls == 0


def test_configure_otel_registers_required_span_contract_and_service_name(tmp_path) -> None:
    assert REQUIRED_SPAN_NAMES == (
        "workflow.invoke",
        "sec.fetch",
        "document.ingest",
        "chunk.create",
        "embedding.create",
        "retrieval.search",
        "llm.call",
        "analysis.module",
        "report.generate",
    )

    provider = configure_otel(
        audit_spool=JsonlAuditSpool(tmp_path, max_mb=1),
        exporter=_FailingExporter(),
    )

    resource_attributes = dict(provider.resource.attributes)
    assert resource_attributes["service.name"] == "investment-due-diligence-agent"


def test_configure_otel_rejects_unsafe_service_name_before_provider_creation(tmp_path) -> None:
    for service_name in (
        "secret prompt service",
        "john@example.com",
        "api-key-service",
        "Bearer-token",
        "service name with spaces",
    ):
        with pytest.raises(ValueError, match="service_name.invalid"):
            configure_otel(
                audit_spool=JsonlAuditSpool(tmp_path, max_mb=1),
                exporter=_FailingExporter(),
                service_name=service_name,
            )


@dataclass(frozen=True)
class _FakeSpan:
    name: str
    attributes: dict[str, object]
    events: tuple[object, ...] = ()
    links: tuple[object, ...] = ()
    status: object | None = None
    resource: Resource | None = None

    def get_span_context(self) -> SpanContext:
        return SpanContext(
            trace_id=1,
            span_id=2,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
            trace_state=TraceState(),
        )

    def to_json(self) -> str:
        return repr((self.attributes, self.events, self.links, self.status))


@dataclass(frozen=True)
class _FakeEvent:
    name: str
    attributes: dict[str, object]


@dataclass(frozen=True)
class _FakeLink:
    attributes: dict[str, object]


@dataclass(frozen=True)
class _FakeStatus:
    description: str | None


def _unsafe_test_span(
    prompt: str = "secret prompt",
    output: str = "secret output",
    *,
    name: str = "llm.call",
    case_id: str | None = "case-1",
    correlation_id: str = "corr-1",
) -> _FakeSpan:
    attributes: dict[str, object] = {
        "run_id": "run-1",
        "correlation_id": correlation_id,
        "graph_version": "public-graph@1",
        "redaction_policy_version": "privacy@1",
        "status": "error",
        "input.value": prompt,
        "output.value": output,
        "exception.message": "RuntimeError: secret output",
    }
    if case_id is not None:
        attributes["case_id"] = case_id
    return _FakeSpan(
        name=name,
        attributes=attributes,
    )


class _FailingExporter:
    def export(self, spans) -> SpanExportResult:  # noqa: ANN001
        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class _RaisingExporter(_FailingExporter):
    def export(self, spans) -> SpanExportResult:  # noqa: ANN001
        raise RuntimeError("external exporter leaked secret prompt")


class _CountingExporter(_FailingExporter):
    def __init__(self) -> None:
        self.export_calls = 0

    def export(self, spans) -> SpanExportResult:  # noqa: ANN001
        self.export_calls += 1
        return SpanExportResult.SUCCESS


class _RecordingExporter(_FailingExporter):
    def __init__(self) -> None:
        self.export_calls = 0
        self.exported_spans = []

    def export(self, spans) -> SpanExportResult:  # noqa: ANN001
        self.export_calls += 1
        self.exported_spans = list(spans)
        return SpanExportResult.SUCCESS


class _FailingSpool:
    def append(self, event) -> str:  # noqa: ANN001
        raise OSError("disk full with secret prompt")


class _FailingAfterFirstAppendSpool:
    def __init__(self) -> None:
        self.append_calls = 0

    def append(self, event) -> str:  # noqa: ANN001
        self.append_calls += 1
        if self.append_calls > 1:
            raise OSError("disk full with secret prompt")
        return "audit.jsonl"

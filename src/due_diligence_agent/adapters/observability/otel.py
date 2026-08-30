from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Status

from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool, TraceSanitizer

REQUIRED_SPAN_NAMES: Final[tuple[str, ...]] = (
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
DEFAULT_SERVICE_NAME: Final[str] = "investment-due-diligence-agent"


class AuditPersistenceError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("AUDIT_PERSISTENCE_ERROR")
        self.code = "AUDIT_PERSISTENCE_ERROR"


class DurableFallbackSpanExporter(SpanExporter):
    def __init__(
        self,
        delegate: SpanExporter,
        audit_spool: AuditSpool,
        *,
        sanitizer: TraceSanitizer | None = None,
        audit_required: bool = True,
        service_name: str = DEFAULT_SERVICE_NAME,
    ) -> None:
        self.delegate = delegate
        self.audit_spool = audit_spool
        self.sanitizer = sanitizer or StrictTraceSanitizer()
        self.audit_required = audit_required
        self.service_name = _validated_service_name(self.sanitizer, service_name)
        self.resource = Resource.create({"service.name": self.service_name})

    def export(self, spans: Iterable[Any]) -> SpanExportResult:
        materialized = list(spans)
        sanitized_spans: list[Any] = []
        audit_events: list[AuditEvent] = []
        try:
            for span in materialized:
                sanitized_span = self._sanitized_span(span)
                audit_event = self._audit_event_from_span(sanitized_span)
                self.audit_spool.append(audit_event)
                audit_events.append(audit_event)
                sanitized_spans.append(sanitized_span)
        except Exception as exc:
            if self.audit_required:
                raise AuditPersistenceError() from exc
            return SpanExportResult.FAILURE
        try:
            result = self.delegate.export(sanitized_spans)
        except Exception:
            result = SpanExportResult.FAILURE
        if result is not SpanExportResult.FAILURE:
            return result
        try:
            self._persist_degradation_markers(audit_events)
        except Exception as exc:
            if self.audit_required:
                raise AuditPersistenceError() from exc
        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self.delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.delegate.force_flush(timeout_millis)

    def _audit_event_from_span(self, span: Any) -> AuditEvent:
        raw_attributes = dict(getattr(span, "attributes", {}) or {})
        attributes = self.sanitizer.sanitize_attributes(raw_attributes, drop_disallowed=True)
        run_id = str(attributes.get("run_id") or "unknown-run")
        correlation_id = str(attributes.get("correlation_id") or self._trace_id(span))
        return AuditEvent(
            schema_version="audit_event@1",
            event_id=str(uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            run_id=run_id,
            correlation_id=correlation_id,
            span_name=str(getattr(span, "name", "unknown")),
            event_type="span",
            attributes=attributes,
        )

    def _persist_degradation_markers(self, audit_events: Iterable[AuditEvent]) -> None:
        for event in audit_events:
            case_id = event.attributes.get("case_id")
            if event.run_id == "unknown-run" or not isinstance(case_id, str):
                continue
            self.audit_spool.append(
                AuditEvent(
                    schema_version="audit_event@1",
                    event_id=str(uuid4()),
                    timestamp_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    run_id=event.run_id,
                    correlation_id=event.correlation_id,
                    span_name=event.span_name,
                    event_type="observability.exporter_degraded",
                    attributes={
                        "case_id": case_id,
                        "status": "degraded",
                        "error_code": "external_export_failed",
                        "fallback_used": "local_audit",
                    },
                )
            )

    def _trace_id(self, span: Any) -> str:
        context = span.get_span_context()
        return f"{context.trace_id:032x}"

    def _sanitized_span(self, span: Any) -> ReadableSpan:
        raw_attributes = dict(getattr(span, "attributes", {}) or {})
        attributes = self.sanitizer.sanitize_attributes(raw_attributes, drop_disallowed=True)
        otel_attributes = {key: value for key, value in attributes.items() if value is not None}
        return ReadableSpan(
            name=str(getattr(span, "name", "unknown")),
            context=span.get_span_context(),
            parent=getattr(span, "parent", None),
            resource=self.resource,
            attributes=otel_attributes,
            events=(),
            links=(),
            kind=getattr(span, "kind", trace.SpanKind.INTERNAL),
            instrumentation_info=None,
            status=self._sanitized_status(getattr(span, "status", None)),
            start_time=getattr(span, "start_time", None),
            end_time=getattr(span, "end_time", None),
            instrumentation_scope=None,
        )

    def _sanitized_status(self, status: Any) -> Status:
        status_code = getattr(status, "status_code", None)
        if status_code is None:
            return Status()
        return Status(status_code)


def configure_otel(
    *,
    audit_spool: AuditSpool,
    exporter: SpanExporter,
    sanitizer: TraceSanitizer | None = None,
    service_name: str = DEFAULT_SERVICE_NAME,
    audit_required: bool = True,
) -> TracerProvider:
    sanitizer_impl = sanitizer or StrictTraceSanitizer()
    validated_service_name = _validated_service_name(sanitizer_impl, service_name)
    provider = TracerProvider(resource=Resource.create({"service.name": validated_service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(
            DurableFallbackSpanExporter(
                exporter,
                audit_spool,
                sanitizer=sanitizer_impl,
                audit_required=audit_required,
                service_name=validated_service_name,
            )
        )
    )
    trace.set_tracer_provider(provider)
    return provider


def _validated_service_name(sanitizer: TraceSanitizer, service_name: str) -> str:
    try:
        sanitized = sanitizer.sanitize_attributes({"service.name": service_name})
    except ValueError as exc:
        raise ValueError("service_name.invalid") from exc
    value = sanitized["service.name"]
    if not isinstance(value, str):
        raise ValueError("service_name.invalid")
    return value

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Protocol

from opentelemetry import metrics

from due_diligence_agent.ports.tracing import TraceSanitizer
from due_diligence_agent.adapters.observability.privacy import (
    PrimitiveTraceValue,
    StrictTraceSanitizer,
)

REQUIRED_METRIC_NAMES: Final[tuple[str, ...]] = (
    "workflow.outcome.count",
    "workflow.duration.ms",
    "node.outcome.count",
    "node.duration.ms",
    "collector.call.count",
    "provider.call.count",
    "retry.count",
    "fallback.count",
    "policy.denial.count",
    "budget.denial.count",
    "audit_spool.bytes",
    "report_render.outcome.count",
)


@dataclass(frozen=True)
class MetricInstrument:
    name: str
    kind: str
    handle: Any


class MetricContract:
    def __init__(
        self,
        sanitizer: TraceSanitizer | None = None,
        meter: "MeterLike | None" = None,
    ) -> None:
        self._sanitizer = sanitizer or StrictTraceSanitizer()
        self._meter = meter or metrics.get_meter("due_diligence_agent.observability")
        self.instruments = tuple(
            self._create_instrument(name)
            for name in REQUIRED_METRIC_NAMES
        )
        self._by_name = {instrument.name: instrument for instrument in self.instruments}

    def sanitize_attributes(
        self, attributes: dict[str, object | None]
    ) -> dict[str, PrimitiveTraceValue]:
        return self._sanitizer.sanitize_attributes(attributes)

    def record(
        self,
        name: str,
        value: int | float,
        attributes: dict[str, object | None],
    ) -> None:
        instrument = self._by_name[name]
        safe_attributes = self.sanitize_attributes(attributes)
        if instrument.kind == "histogram":
            instrument.handle.record(value, safe_attributes)
            return
        instrument.handle.add(value, safe_attributes)

    def _create_instrument(self, name: str) -> MetricInstrument:
        kind = "histogram" if name.endswith(".ms") or name.endswith(".bytes") else "counter"
        if kind == "histogram":
            return MetricInstrument(name, kind, self._meter.create_histogram(name))
        return MetricInstrument(name, kind, self._meter.create_counter(name))


class MeterLike(Protocol):
    def create_counter(self, name: str) -> Any: ...
    def create_histogram(self, name: str) -> Any: ...

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, cast

from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer, PrimitiveTraceValue
from due_diligence_agent.ports.tracing import AuditEvent, TraceSanitizer


class _BoundedAuditSpool(Protocol):
    def read_bounded(
        self,
        *,
        max_events: int = ...,
        max_files: int = ...,
        max_bytes: int = ...,
        max_line_chars: int = ...,
        newest_first: bool = ...,
    ) -> list[AuditEvent]: ...


_STARTUP_DISCLOSURE_ATTRIBUTE_KEYS: frozenset[str] = frozenset(
    {
        "case_id",
        "decision",
        "reason",
        "approval_id",
        "data_revision",
        "content_hash",
        "overall_class",
        "detected_class_count",
        "artifact_count",
        "fragment_count",
        "redaction_policy_version",
        "egress_policy_version",
        "destination",
    }
)
_STARTUP_RUNTIME_ATTRIBUTE_KEYS: frozenset[str] = frozenset(
    {
        "checkpoint_id",
        "tool",
        "report_id",
        "report_revision",
        "report_checksum",
        "gate4_status",
        "report_status",
        "decision",
    }
)
_STARTUP_RUNTIME_NUMERIC_KEYS: frozenset[str] = frozenset({"report_revision"})
_STARTUP_RUNTIME_STATUS_KEYS: frozenset[str] = frozenset(
    {"gate4_status", "report_status", "decision"}
)
_STARTUP_REPORT_CANONICAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "startup_report.canonical",
        "startup_report.canonical_snapshot",
        "startup_report.gate4_completed",
    }
)
_EXPORTER_DEGRADATION_EVENT_TYPE = "observability.exporter_degraded"
_LANGSMITH_STATUS_EVENT_TYPE = "observability.langsmith_status"
_STARTUP_DISCLOSURE_NUMERIC_KEYS: frozenset[str] = frozenset(
    {"data_revision", "detected_class_count", "artifact_count", "fragment_count"}
)
_STARTUP_DISCLOSURE_STATUS_KEYS: frozenset[str] = frozenset({"decision", "reason", "overall_class"})
_STARTUP_DISCLOSURE_TOKEN_KEYS: frozenset[str] = frozenset(
    {"case_id", "approval_id", "redaction_policy_version", "egress_policy_version", "destination"}
)
_STARTUP_DISCLOSURE_SAFE_STATUS_RE: re.Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_STARTUP_DISCLOSURE_SAFE_TOKEN_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_STARTUP_DISCLOSURE_SAFE_ID_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_STARTUP_DISCLOSURE_SAFE_HASH_RE: re.Pattern[str] = re.compile(r"^[A-Fa-f0-9]{32,128}$")
_STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE: re.Pattern[str] = re.compile(
    r"(?i)([\w.+-]+@[\w.-]+\.[a-z]{2,}|bearer[\s_-]*\S+|sk-[\w-]+|"
    r"api[_ -]?key|secret|prompt|output|system\s+instructions|runtimeerror)"
)


@dataclass(frozen=True)
class StartupTraceNodeRow:
    case_id: str
    run_id: str
    node: str | None
    attempt: int | None
    retry_count: int | None
    status: str | None
    error_code: str | None
    checkpoint_id: str | None
    tool: str | None
    latency_ms: float | None
    event_id: str
    timestamp_utc: str
    evidence_count: int | None = None
    fallback_used: str | None = None
    timeout_ms: float | None = None


@dataclass(frozen=True)
class StartupTraceUsageSummary:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_usd: Decimal | None


@dataclass(frozen=True)
class StartupTraceReportLineage:
    decision: str | None
    gate4_status: str | None
    report_id: str | None
    report_revision: int | None
    report_checksum: str | None


@dataclass(frozen=True)
class StartupTraceExporterHealth:
    status: str
    error_code: str
    fallback_used: str


@dataclass(frozen=True)
class StartupLangSmithHealth:
    provider: str
    status: str
    error_code: str
    fallback_used: str


@dataclass(frozen=True)
class StartupTraceView:
    schema_version: str = "startup_trace_view@1"
    case_id: str = ""
    run_id: str = ""
    node_rows: tuple[StartupTraceNodeRow, ...] = field(default_factory=tuple)
    usage_summary: StartupTraceUsageSummary = field(
        default_factory=lambda: StartupTraceUsageSummary(
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cost_usd=None,
        )
    )
    report_lineage: StartupTraceReportLineage = field(
        default_factory=lambda: StartupTraceReportLineage(
            decision=None,
            gate4_status=None,
            report_id=None,
            report_revision=None,
            report_checksum=None,
        )
    )
    exporter_health: StartupTraceExporterHealth | None = None
    langsmith_health: StartupLangSmithHealth | None = None


class StartupTraceQueryService:
    def __init__(
        self,
        audit_spool: _BoundedAuditSpool,
        *,
        sanitizer: TraceSanitizer | None = None,
        max_files: int = 128,
        max_bytes: int = 1_048_576,
        max_line_chars: int = 8_192,
    ) -> None:
        self._audit_spool = audit_spool
        self._sanitizer = sanitizer or StrictTraceSanitizer()
        self._max_files = max_files
        self._max_bytes = max_bytes
        self._max_line_chars = max_line_chars

    def get_view(self, case_id: str, run_id: str, *, max_events: int = 200) -> StartupTraceView:
        safe_filters = self._sanitizer.sanitize_attributes(
            {"case_id": case_id, "run_id": run_id},
            drop_disallowed=True,
        )
        safe_case_id = cast(str, safe_filters["case_id"])
        safe_run_id = cast(str, safe_filters["run_id"])

        scan_limit = self._clamp_scan_events(max_events)
        limit = self._clamp_events(max_events)
        events = self._read_events(limit=scan_limit)

        matched_events: list[_EventRow] = []
        for event in events:
            if event.run_id != safe_run_id:
                continue
            sanitized = self._safe_attributes(event.event_type, event.attributes)
            if sanitized.get("case_id") != safe_case_id:
                continue
            timestamp = self._parse_timestamp(event.timestamp_utc)
            matched_events.append((timestamp, event.event_id, event, sanitized))

        matched_events.sort(key=lambda item: (item[0], item[1]))

        nodes: list[StartupTraceNodeRow] = []
        input_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None
        cost_usd: Decimal | None = None
        lineage = StartupTraceReportLineage(
            decision=None,
            gate4_status=None,
            report_id=None,
            report_revision=None,
            report_checksum=None,
        )
        exporter_health: StartupTraceExporterHealth | None = None
        langsmith_health: StartupLangSmithHealth | None = None

        node_events: list[_EventRow] = []
        for matched_event in matched_events:
            _, _, event, attributes = matched_event
            if event.event_type == _EXPORTER_DEGRADATION_EVENT_TYPE:
                marker_health = self._exporter_health(attributes)
                if marker_health is not None:
                    exporter_health = marker_health
                continue
            if event.event_type == _LANGSMITH_STATUS_EVENT_TYPE:
                langsmith_marker_health = self._langsmith_health(attributes)
                if langsmith_marker_health is not None:
                    langsmith_health = langsmith_marker_health
                continue
            node_events.append(matched_event)

        for _, _, event, attributes in node_events:
            input_tokens, output_tokens, total_tokens, cost_usd = self._aggregate_usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                attributes=attributes,
            )
            lineage = self._apply_lineage(lineage, event, attributes)

        for _, _, event, attributes in node_events[-limit:]:
            node = StartupTraceNodeRow(
                case_id=safe_case_id,
                run_id=safe_run_id,
                node=self._as_str(attributes.get("node_name")),
                attempt=self._as_int(attributes.get("attempt")),
                retry_count=self._as_int(attributes.get("retry_count")),
                status=self._as_str(attributes.get("status")),
                error_code=self._as_str(attributes.get("error_code")),
                checkpoint_id=self._as_str(attributes.get("checkpoint_id")),
                tool=self._as_str(attributes.get("tool")),
                latency_ms=self._as_float(attributes.get("latency_ms"))
                if attributes.get("latency_ms") is not None
                else self._as_float(attributes.get("duration_ms")),
                event_id=event.event_id,
                timestamp_utc=event.timestamp_utc,
                evidence_count=self._as_int(attributes.get("evidence_count")),
                fallback_used=self._as_str(attributes.get("fallback_used")),
                timeout_ms=self._as_float(attributes.get("timeout_ms")),
            )
            nodes.append(node)

        return StartupTraceView(
            case_id=safe_case_id,
            run_id=safe_run_id,
            node_rows=tuple(nodes),
            usage_summary=StartupTraceUsageSummary(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            ),
            report_lineage=lineage,
            exporter_health=exporter_health,
            langsmith_health=langsmith_health,
        )

    def _read_events(self, *, limit: int) -> list[AuditEvent]:
        return self._audit_spool.read_bounded(
            max_events=limit,
            max_files=self._max_files,
            max_bytes=self._max_bytes,
            max_line_chars=self._max_line_chars,
            newest_first=True,
        )

    def _safe_attributes(
        self,
        event_type: str,
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> dict[str, PrimitiveTraceValue]:
        if event_type.startswith("startup_disclosure."):
            disclosure_attributes = self._sanitize_startup_disclosure_attributes(attributes)
            general_attributes = {
                key: value
                for key, value in attributes.items()
                if key not in _STARTUP_DISCLOSURE_ATTRIBUTE_KEYS
            }
            safe_general = self._sanitize_general_attributes(general_attributes)
            disclosure_attributes.update(safe_general)
            disclosure_attributes.update(self._sanitize_startup_runtime_attributes(general_attributes))
            return disclosure_attributes
        safe_attributes = self._sanitize_general_attributes(attributes)
        safe_attributes.update(self._sanitize_startup_runtime_attributes(attributes))
        return safe_attributes

    def _sanitize_general_attributes(
        self,
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> dict[str, PrimitiveTraceValue]:
        sanitized: dict[str, PrimitiveTraceValue] = {}
        for key, value in attributes.items():
            try:
                sanitized.update(self._sanitizer.sanitize_attributes({key: value}, drop_disallowed=True))
            except ValueError:
                continue
        return sanitized

    def _sanitize_startup_disclosure_attributes(
        self,
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> dict[str, PrimitiveTraceValue]:
        sanitized: dict[str, PrimitiveTraceValue] = {}
        for key, value in attributes.items():
            if key not in _STARTUP_DISCLOSURE_ATTRIBUTE_KEYS:
                continue
            if not self._is_safe_disclosure_value(key, value):
                continue
            sanitized[key] = value
        return sanitized

    def _sanitize_startup_runtime_attributes(
        self,
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> dict[str, PrimitiveTraceValue]:
        sanitized: dict[str, PrimitiveTraceValue] = {}
        for key, value in attributes.items():
            if key not in _STARTUP_RUNTIME_ATTRIBUTE_KEYS:
                continue
            if not self._is_safe_runtime_value(key, value):
                continue
            sanitized[key] = value
        return sanitized

    @staticmethod
    def _is_safe_disclosure_value(key: str, value: PrimitiveTraceValue) -> bool:
        if value is None:
            return True
        if key in _STARTUP_DISCLOSURE_NUMERIC_KEYS:
            return isinstance(value, int) and not isinstance(value, bool)
        if key in _STARTUP_DISCLOSURE_STATUS_KEYS:
            return (
                isinstance(value, str)
                and _STARTUP_DISCLOSURE_SAFE_STATUS_RE.fullmatch(value) is not None
                and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
            )
        if key in _STARTUP_DISCLOSURE_TOKEN_KEYS:
            if key in {"case_id", "approval_id"}:
                return (
                    isinstance(value, str)
                    and _STARTUP_DISCLOSURE_SAFE_ID_RE.fullmatch(value) is not None
                    and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
                )
            return (
                isinstance(value, str)
                and _STARTUP_DISCLOSURE_SAFE_TOKEN_RE.fullmatch(value) is not None
                and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
            )
        if key == "content_hash":
            return (
                isinstance(value, str)
                and _STARTUP_DISCLOSURE_SAFE_HASH_RE.fullmatch(value) is not None
                and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
            )
        return False

    @staticmethod
    def _is_safe_runtime_value(key: str, value: PrimitiveTraceValue) -> bool:
        if value is None:
            return True
        if key in _STARTUP_RUNTIME_NUMERIC_KEYS:
            return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000_000
        if key in _STARTUP_RUNTIME_STATUS_KEYS:
            return (
                isinstance(value, str)
                and _STARTUP_DISCLOSURE_SAFE_STATUS_RE.fullmatch(value) is not None
                and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
            )
        if key in {"checkpoint_id", "report_id"}:
            return (
                isinstance(value, str)
                and _STARTUP_DISCLOSURE_SAFE_ID_RE.fullmatch(value) is not None
                and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
            )
        if key == "tool":
            return (
                isinstance(value, str)
                and _STARTUP_DISCLOSURE_SAFE_TOKEN_RE.fullmatch(value) is not None
                and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
            )
        if key == "report_checksum":
            return (
                isinstance(value, str)
                and _STARTUP_DISCLOSURE_SAFE_HASH_RE.fullmatch(value) is not None
                and _STARTUP_DISCLOSURE_SENSITIVE_VALUE_RE.search(value) is None
            )
        return False

    @staticmethod
    def _clamp_events(requested: int) -> int:
        if requested < 1:
            return 1
        return min(requested, 200)

    @staticmethod
    def _clamp_scan_events(requested: int) -> int:
        if requested < 1:
            return 2000
        return min(max(2000, requested), 2000)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        if not value.endswith("Z"):
            raise ValueError("trace_event.timestamp_invalid")
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
        if parsed.tzinfo != UTC:
            raise ValueError("trace_event.timestamp_invalid")
        return parsed

    @staticmethod
    def _as_str(value: object | None) -> str | None:
        if isinstance(value, str):
            return value
        if value is None:
            return None
        return None

    @staticmethod
    def _as_int(value: object | None) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if value < 0:
            return None
        if value > 10_000_000:
            return None
        return value

    @staticmethod
    def _as_float(value: object | None) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        if value < 0:
            return None
        if value > 1_000_000.0:
            return None
        return float(value)

    @staticmethod
    def _add_token(total: int | None, value: object | None) -> int | None:
        if not isinstance(value, int) or isinstance(value, bool):
            return total
        if value < 0 or value > 10_000_000:
            return total
        return (total or 0) + value

    def _aggregate_usage(
        self,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None,
        cost_usd: Decimal | None,
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> tuple[int | None, int | None, int | None, Decimal | None]:
        input_tokens = self._add_token(input_tokens, attributes.get("input_tokens"))
        output_tokens = self._add_token(output_tokens, attributes.get("output_tokens"))
        total_tokens = self._add_token(total_tokens, attributes.get("total_tokens"))
        cost = attributes.get("cost_usd")
        if cost is None:
            cost = attributes.get("estimated_cost_usd")
        if isinstance(cost, bool) or not isinstance(cost, int | float):
            return (input_tokens, output_tokens, total_tokens, cost_usd)
        if cost < 0 or cost > 1_000_000:
            return (input_tokens, output_tokens, total_tokens, cost_usd)
        if cost_usd is None:
            cost_usd = Decimal(str(cost))
        else:
            cost_usd = cost_usd + Decimal(str(cost))
        return (input_tokens, output_tokens, total_tokens, cost_usd)

    @staticmethod
    def _exporter_health(
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> StartupTraceExporterHealth | None:
        if attributes.get("status") != "degraded":
            return None
        if attributes.get("error_code") != "external_export_failed":
            return None
        if attributes.get("fallback_used") != "local_audit":
            return None
        return StartupTraceExporterHealth(
            status="degraded",
            error_code="external_export_failed",
            fallback_used="local_audit",
        )

    @staticmethod
    def _langsmith_health(
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> StartupLangSmithHealth | None:
        if attributes.get("exporter_provider") != "langsmith":
            return None
        if attributes.get("fallback_used") != "local_audit":
            return None
        status = attributes.get("status")
        error_code = attributes.get("error_code")
        allowed_pairs = {
            ("disabled", "tracing_disabled"),
            ("blocked_missing_credential", "missing_credential"),
            ("healthy", "none"),
            ("degraded", "external_export_failed"),
            ("degraded", "telemetry_privacy_rejected"),
        }
        if (status, error_code) not in allowed_pairs:
            return None
        return StartupLangSmithHealth(
            provider="langsmith",
            status=cast(str, status),
            error_code=cast(str, error_code),
            fallback_used="local_audit",
        )

    def _apply_lineage(
        self,
        lineage: StartupTraceReportLineage,
        event: AuditEvent,
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> StartupTraceReportLineage:
        if not event.event_type.startswith("startup_disclosure."):
            return self._apply_report_lineage(lineage, event, attributes)

        report_id = lineage.report_id
        report_revision = lineage.report_revision
        report_checksum = lineage.report_checksum
        decision = lineage.decision

        if "content_hash" in attributes:
            report_checksum = self._safe_content_hash(attributes["content_hash"])
        if "data_revision" in attributes:
            report_revision = self._as_int(attributes["data_revision"])
        if "decision" in attributes and isinstance(attributes["decision"], str):
            decision = self._as_str(attributes["decision"])

        return StartupTraceReportLineage(
            decision=decision,
            gate4_status=lineage.gate4_status,
            report_id=report_id,
            report_revision=report_revision,
            report_checksum=report_checksum,
        )

    def _apply_report_lineage(
        self,
        lineage: StartupTraceReportLineage,
        event: AuditEvent,
        attributes: Mapping[str, PrimitiveTraceValue],
    ) -> StartupTraceReportLineage:
        if event.event_type not in _STARTUP_REPORT_CANONICAL_EVENT_TYPES:
            return lineage
        if attributes.get("status") not in {None, "success", "completed"}:
            return lineage
        if attributes.get("report_status") not in {None, "canonical"}:
            return lineage

        report_id = self._as_str(attributes.get("report_id"))
        report_revision = self._as_int(attributes.get("report_revision"))
        report_checksum = self._safe_content_hash(attributes.get("report_checksum"))
        gate4_status = self._as_str(attributes.get("gate4_status"))
        decision = self._as_str(attributes.get("decision")) or lineage.decision
        if report_id is None or report_revision is None or report_checksum is None or gate4_status is None:
            return lineage

        return StartupTraceReportLineage(
            decision=decision,
            gate4_status=gate4_status,
            report_id=report_id,
            report_revision=report_revision,
            report_checksum=report_checksum,
        )

    @staticmethod
    def _safe_content_hash(value: PrimitiveTraceValue) -> str | None:
        return value if isinstance(value, str) and _STARTUP_DISCLOSURE_SAFE_HASH_RE.fullmatch(value) else None


type _EventRow = tuple[datetime, str, AuditEvent, dict[str, PrimitiveTraceValue]]

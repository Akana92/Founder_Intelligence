from __future__ import annotations

import re
from collections.abc import Mapping
from math import isfinite
from typing import Final

PrimitiveTraceValue = str | int | float | bool | None


ALLOWED_TRACE_ATTRIBUTE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "request_id",
        "run_id",
        "case_id",
        "correlation_id",
        "workflow_type",
        "app_version",
        "graph_version",
        "redaction_policy_version",
        "node_name",
        "agent_role",
        "gate",
        "gate_status",
        "span_name",
        "service.name",
        "provider",
        "model",
        "model_provider",
        "model_name",
        "ls_provider",
        "ls_model_name",
        "prompt_version",
        "schema_version",
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "tokens",
        "latency_ms",
        "duration_ms",
        "timeout_ms",
        "estimated_cost_usd",
        "cost_usd",
        "evidence_count",
        "query_count",
        "source_count",
        "status",
        "error_code",
        "failure_code",
        "fallback_used",
        "research_label",
        "inference_label",
        "reflexion_iteration",
        "artifact_id",
        "evidence_id",
        "artifact_hash",
        "evidence_hash",
        "checkpoint_id",
        "checkpoint_hash",
        "adapter_version",
        "retrieval_index_version",
        "index_version",
        "configuration_hash",
        "cik",
        "accession_number",
        "form_type",
        "fiscal_year",
        "fiscal_period",
        "score",
        "chunk_count",
        "retry_count",
        "attempt",
        "http_status_code",
        "budget_usd",
        "bytes",
        "report_format",
        "report_id",
        "report_revision",
        "report_checksum",
        "exporter_provider",
        "tool",
        "tool_call_observed",
    }
)

DENIED_TRACE_PREFIXES: Final[tuple[str, ...]] = (
    "gen_ai.",
    "tool.",
    "retrieval.",
    "exception.",
)

DENIED_TRACE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "input.value",
        "output.value",
        "source_text",
        "document_text",
        "document.content",
        "chunk_text",
        "chunk.content",
        "prompt",
        "completion",
        "company_name",
        "person_name",
        "email",
        "phone",
        "authorization",
        "authorization_header",
        "api_key",
        "secret",
        "payload",
    }
)

_SENSITIVE_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)([\w.+-]+@[\w.-]+\.[a-z]{2,}|bearer[\s_-]*\S+|sk-[\w-]+|"
    r"api[_ -]?key|secret|prompt|output|system\s+instructions|runtimeerror)"
)
_SAFE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_SAFE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SAFE_HASH_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Fa-f0-9]{32,128}$")
_SAFE_STATUS_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_SAFE_ACCESSION_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_SAFE_SENSITIVE_MACHINE_CODES: Final[dict[str, frozenset[str]]] = {
    "error_code": frozenset({"invalid_output"}),
    "failure_code": frozenset({"invalid_output"}),
}

_ID_KEYS: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "request_id",
        "run_id",
        "case_id",
        "correlation_id",
        "artifact_id",
        "evidence_id",
        "checkpoint_id",
        "report_id",
    }
)
_HASH_KEYS: Final[frozenset[str]] = frozenset(
    {
        "artifact_hash",
        "evidence_hash",
        "configuration_hash",
        "checkpoint_hash",
        "report_checksum",
    }
)
_VERSION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "app_version",
        "graph_version",
        "redaction_policy_version",
        "prompt_version",
        "schema_version",
        "adapter_version",
        "retrieval_index_version",
        "index_version",
    }
)
_NUMERIC_KEYS: Final[frozenset[str]] = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "tokens",
        "latency_ms",
        "duration_ms",
        "timeout_ms",
        "estimated_cost_usd",
        "cost_usd",
        "evidence_count",
        "query_count",
        "source_count",
        "reflexion_iteration",
        "score",
        "chunk_count",
        "retry_count",
        "attempt",
        "http_status_code",
        "budget_usd",
        "bytes",
        "report_revision",
    }
)
_BOOLEAN_KEYS: Final[frozenset[str]] = frozenset({"tool_call_observed"})


class StrictTraceSanitizer:
    def sanitize_attributes(
        self,
        attributes: Mapping[str, object | None],
        *,
        drop_disallowed: bool = False,
    ) -> dict[str, PrimitiveTraceValue]:
        sanitized: dict[str, PrimitiveTraceValue] = {}
        for key, value in attributes.items():
            if not self.is_allowed_key(key):
                if drop_disallowed:
                    continue
                raise ValueError(f"trace_attribute.disallowed:{key}")
            sanitized[key] = self._sanitize_value(key, value)
        return sanitized

    def is_allowed_key(self, key: str) -> bool:
        if key in DENIED_TRACE_KEYS:
            return False
        if any(key.startswith(prefix) for prefix in DENIED_TRACE_PREFIXES):
            return False
        return key in ALLOWED_TRACE_ATTRIBUTE_KEYS

    def _sanitize_value(self, key: str, value: object | None) -> PrimitiveTraceValue:
        if value is None:
            return None
        if key in _BOOLEAN_KEYS:
            if not isinstance(value, bool):
                raise ValueError(f"trace_attribute.value_type:{key}")
            return value
        if key in _NUMERIC_KEYS:
            if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
                raise ValueError(f"trace_attribute.value_type:{key}")
            return value
        if isinstance(value, bool | int | float):
            raise ValueError(f"trace_attribute.value_type:{key}")  # noqa: TRY004
        if not isinstance(value, str):
            raise ValueError(f"trace_attribute.value_type:{key}")  # noqa: TRY004
        allowed_sensitive_codes = _SAFE_SENSITIVE_MACHINE_CODES.get(key, frozenset())
        if _SENSITIVE_VALUE_RE.search(value) and value not in allowed_sensitive_codes:
            raise ValueError(f"trace_attribute.value_sensitive:{key}")
        if key in _ID_KEYS and not _SAFE_ID_RE.match(value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        if key in _HASH_KEYS and not _SAFE_HASH_RE.match(value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        if key in _VERSION_KEYS and not _SAFE_TOKEN_RE.match(value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        if key in {
            "status",
            "error_code",
            "failure_code",
            "fallback_used",
            "research_label",
            "inference_label",
            "workflow_type",
            "node_name",
            "agent_role",
            "gate",
            "gate_status",
            "span_name",
        } and not _SAFE_STATUS_RE.match(value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        if key in {
            "service.name",
            "provider",
            "model",
            "model_provider",
            "model_name",
            "ls_provider",
            "ls_model_name",
            "form_type",
            "report_format",
            "exporter_provider",
            "tool",
        } and not _SAFE_TOKEN_RE.match(value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        if key == "cik" and not re.fullmatch(r"[0-9]{1,10}", value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        if key == "accession_number" and not _SAFE_ACCESSION_RE.match(value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        if key in {"fiscal_year", "fiscal_period"} and not _SAFE_TOKEN_RE.match(value):
            raise ValueError(f"trace_attribute.value_format:{key}")
        return value

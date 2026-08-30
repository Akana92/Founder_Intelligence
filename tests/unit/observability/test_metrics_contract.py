from __future__ import annotations

import pytest

from due_diligence_agent.adapters.observability.metrics import (
    REQUIRED_METRIC_NAMES,
    MetricContract,
)
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.ports.tracing import TraceSanitizer


def test_strict_trace_sanitizer_satisfies_downstream_protocol_contract() -> None:
    sanitizer: TraceSanitizer = StrictTraceSanitizer()

    assert sanitizer.sanitize_attributes({"status": "success"}) == {"status": "success"}


def test_required_privacy_safe_metric_names_are_registered() -> None:
    contract = MetricContract()

    assert REQUIRED_METRIC_NAMES == (
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
    assert tuple(instrument.name for instrument in contract.instruments) == REQUIRED_METRIC_NAMES


def test_metrics_reuse_trace_allowlist_and_reject_company_or_raw_source_attributes() -> None:
    contract = MetricContract(sanitizer=StrictTraceSanitizer())

    assert contract.sanitize_attributes(
        {
            "case_id": "case-1",
            "node_name": "llm.call",
            "status": "success",
            "duration_ms": 12.5,
            "evidence_count": 3,
        }
    ) == {
        "case_id": "case-1",
        "node_name": "llm.call",
        "status": "success",
        "duration_ms": 12.5,
        "evidence_count": 3,
    }

    with pytest.raises(ValueError, match="trace_attribute.disallowed:company_name"):
        contract.sanitize_attributes({"company_name": "Apple Inc."})

    with pytest.raises(ValueError, match="trace_attribute.disallowed:source_text"):
        contract.sanitize_attributes({"source_text": "raw filing text"})


def test_sanitizer_rejects_genai_tool_retrieval_and_exception_payload_fields() -> None:
    sanitizer = StrictTraceSanitizer()

    for key in (
        "gen_ai.prompt",
        "gen_ai.completion",
        "tool.arguments",
        "tool.result",
        "retrieval.content",
        "exception.message",
        "input.value",
        "output.value",
    ):
        with pytest.raises(ValueError, match=f"trace_attribute.disallowed:{key}"):
            sanitizer.sanitize_attributes({key: "secret"})


def test_sanitizer_rejects_sensitive_values_under_allowed_keys() -> None:
    sanitizer = StrictTraceSanitizer()

    for attributes in (
        {"status": "failed after secret prompt"},
        {"error_code": "RuntimeError Bearer abcdef"},
        {"case_id": "alice@example.com"},
        {"correlation_id": "sk-proj-abcdef"},
        {"model": "gpt with secret output"},
        {"provider": "openai api_key abc"},
        {"graph_version": "system instructions v1"},
        {"redaction_policy_version": "Bearer token"},
    ):
        with pytest.raises(ValueError, match="trace_attribute.value_sensitive"):
            sanitizer.sanitize_attributes(attributes)

    assert sanitizer.sanitize_attributes(
        {
            "status": "success",
            "error_code": "AUDIT_PERSISTENCE_ERROR",
            "case_id": "case-1",
            "correlation_id": "corr-1",
            "model": "gpt-5.6-terra",
            "provider": "openai",
            "graph_version": "public-graph@1",
            "redaction_policy_version": "privacy@1",
            "artifact_hash": "a" * 64,
            "cik": "0000320193",
            "accession_number": "0000320193-26-000001",
        }
    )["status"] == "success"


def test_sanitizer_rejects_type_bypasses_for_string_and_numeric_keys() -> None:
    sanitizer = StrictTraceSanitizer()

    for attributes in (
        {"case_id": 123},
        {"model": True},
        {"status": 1.0},
        {"duration_ms": "12.5"},
    ):
        with pytest.raises(ValueError, match="trace_attribute.value_type"):
            sanitizer.sanitize_attributes(attributes)

    assert sanitizer.sanitize_attributes(
        {
            "case_id": "case-123",
            "model": "gpt-5.6-terra",
            "status": "success",
            "duration_ms": 12.5,
        }
    ) == {
        "case_id": "case-123",
        "model": "gpt-5.6-terra",
        "status": "success",
        "duration_ms": 12.5,
    }


def test_metric_contract_uses_real_meter_instruments_and_rejects_before_recording() -> None:
    meter = _FakeMeter()
    contract = MetricContract(meter=meter, sanitizer=StrictTraceSanitizer())

    assert [(kind, name) for kind, name in meter.created] == [
        ("counter", "workflow.outcome.count"),
        ("histogram", "workflow.duration.ms"),
        ("counter", "node.outcome.count"),
        ("histogram", "node.duration.ms"),
        ("counter", "collector.call.count"),
        ("counter", "provider.call.count"),
        ("counter", "retry.count"),
        ("counter", "fallback.count"),
        ("counter", "policy.denial.count"),
        ("counter", "budget.denial.count"),
        ("histogram", "audit_spool.bytes"),
        ("counter", "report_render.outcome.count"),
    ]

    contract.record("workflow.outcome.count", 1, {"status": "success", "case_id": "case-1"})
    contract.record("workflow.duration.ms", 12.5, {"status": "success", "duration_ms": 12.5})

    assert meter.instruments["workflow.outcome.count"].calls == [
        ("add", 1, {"status": "success", "case_id": "case-1"})
    ]
    assert meter.instruments["workflow.duration.ms"].calls == [
        ("record", 12.5, {"status": "success", "duration_ms": 12.5})
    ]

    with pytest.raises(ValueError, match="trace_attribute.disallowed:source_text"):
        contract.record("workflow.outcome.count", 1, {"source_text": "raw filing"})

    assert len(meter.instruments["workflow.outcome.count"].calls) == 1


class _FakeInstrument:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[str, int | float, dict[str, object]]] = []

    def add(self, value: int | float, attributes: dict[str, object]) -> None:
        self.calls.append(("add", value, attributes))

    def record(self, value: int | float, attributes: dict[str, object]) -> None:
        self.calls.append(("record", value, attributes))


class _FakeMeter:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.instruments: dict[str, _FakeInstrument] = {}

    def create_counter(self, name: str) -> _FakeInstrument:
        self.created.append(("counter", name))
        self.instruments[name] = _FakeInstrument(name)
        return self.instruments[name]

    def create_histogram(self, name: str) -> _FakeInstrument:
        self.created.append(("histogram", name))
        self.instruments[name] = _FakeInstrument(name)
        return self.instruments[name]

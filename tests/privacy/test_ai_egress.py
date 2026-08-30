from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import ClassVar
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from due_diligence_agent.adapters.openai.gateway import (
    OpenAIAuditPersistenceError,
    OpenAIGateway,
    OpenAIMetadataSanitizationError,
    OpenAISchemaValidationError,
)
from due_diligence_agent.adapters.openai.startup_web_research import (
    OpenAIStartupWebResearchAdapter,
)
from due_diligence_agent.application.policies.budget import BudgetGuard, BudgetReservation
from due_diligence_agent.application.policies.data_egress import (
    DataEgressDenied,
    DataEgressPolicy,
    DisclosureScope,
    EgressDecision,
)
from due_diligence_agent.application.policies.model_routing import (
    ModelDecision,
    ModelProfile,
    ModelRoutingPolicy,
)
from due_diligence_agent.application.services.startup_advisor_research_service import (
    StartupAdvisorResearchService,
)
from due_diligence_agent.application.services.startup_market_research_service import (
    StartupMarketResearchService,
)
from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.domain.startup.advisor import AdvisorAnswer, AdvisorQuestion
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.ports.llm import (
    LLMBudgetRequest,
    LLMContextFragment,
    LLMRoutingContext,
    LLMUsage,
)
from due_diligence_agent.ports.tracing import AuditEvent, TraceContext


class RiskOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk: str
    evidence_ids: tuple[str, ...]


class RecordingResponses:
    def __init__(self, outcomes: list[object] | None = None) -> None:
        self.outcomes = outcomes or [_Parsed(RiskOutput(risk="liquidity", evidence_ids=("ev-1",)))]
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class BlockingResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.entered = asyncio.Event()

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        self.entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class RecordingAuditSpool:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> str:
        self.events.append(event)
        return "memory://audit"

    def read_batch(self, limit: int = 100) -> list[AuditEvent]:
        return self.events[:limit]

    def mark_flushed(self, event_ids: list[str]) -> None:
        return None


class FailingAuditSpool(RecordingAuditSpool):
    def append(self, event: AuditEvent) -> str:
        self.events.append(event)
        raise OSError("disk full with raw secret prompt")


class CountingEgressPolicy(DataEgressPolicy):
    def __init__(self) -> None:
        self.decisions: list[EgressDecision] = []

    def evaluate(self, *args: object, **kwargs: object) -> EgressDecision:
        decision = super().evaluate(*args, **kwargs)  # type: ignore[arg-type]
        self.decisions.append(decision)
        return decision


class _Parsed:
    def __init__(self, output: RiskOutput, *, total_tokens: int = 12, usage: object | None = None) -> None:
        self.output_parsed = output
        self.output_text = "RAW_SENTINEL model free-form text must be ignored"
        self.content = [{"text": "RAW_SENTINEL content must be ignored"}]
        self.usage = usage if usage is not None else _Usage(total_tokens=total_tokens)


class _Usage:
    def __init__(self, *, total_tokens: int) -> None:
        self.total_tokens = total_tokens
        self.input_tokens = total_tokens // 2
        self.output_tokens = total_tokens - self.input_tokens


class _AliasUsage:
    prompt_tokens = 5
    completion_tokens = 6
    total_tokens = 11


class _MissingUsageParsed:
    def __init__(self) -> None:
        self.output_parsed = RiskOutput(risk="missing-usage", evidence_ids=("ev-1",))
        self.output_text = "RAW_SENTINEL missing usage output text"


class _InvalidParsed:
    output_parsed: ClassVar[dict[str, str]] = {"risk": "missing evidence ids"}
    output_text = "RAW_SENTINEL invalid dict output text"
    usage: ClassVar[dict[str, int]] = {
        "total_tokens": 13,
        "input_tokens": 6,
        "output_tokens": 7,
    }


class _ParsedWithUsage:
    def __init__(self, usage: object) -> None:
        self.output_parsed = RiskOutput(risk="usage-shape", evidence_ids=("ev-1",))
        self.output_text = "RAW_SENTINEL usage output text"
        self.usage = usage


def test_llm_dtos_are_frozen_and_forbid_extra_fields() -> None:
    fragment = _fragment(SensitivityClass.PUBLIC)

    with pytest.raises(ValidationError):
        LLMContextFragment(
            id=fragment.id,
            minimized_text=fragment.minimized_text,
            sensitivity=fragment.sensitivity,
            redacted=fragment.redacted,
            minimized=fragment.minimized,
            redaction_policy_version=fragment.redaction_policy_version,
            raw_text="RAW_SENTINEL",
        )
    with pytest.raises(ValidationError):
        fragment.minimized = False  # type: ignore[misc]


def test_confidential_scope_invalidates_on_current_metadata_changes() -> None:
    policy = DataEgressPolicy()
    fragment = _fragment(SensitivityClass.CONFIDENTIAL)
    valid_scope = DisclosureScope(
        approval_id=uuid4(),
        allowed_classes=frozenset({SensitivityClass.CONFIDENTIAL}),
        destination="openai.responses",
        egress_policy_version=policy.version,
        redaction_policy_versions=frozenset({"redact@1"}),
    )

    assert policy.evaluate([fragment], destination="openai.responses", disclosure_scope=None).reason == "approval_required"
    assert (
        policy.evaluate(
            [fragment],
            destination="langsmith",
            disclosure_scope=valid_scope,
        ).reason
        == "destination_mismatch"
    )
    assert (
        policy.evaluate(
            [fragment],
            destination="openai.responses",
            disclosure_scope=valid_scope.model_copy(update={"allowed_classes": frozenset({SensitivityClass.INTERNAL})}),
        ).reason
        == "approval_required"
    )
    assert (
        policy.evaluate(
            [fragment],
            destination="openai.responses",
            disclosure_scope=valid_scope.model_copy(update={"egress_policy_version": "egress@old"}),
        ).reason
        == "egress_policy_mismatch"
    )
    assert (
        policy.evaluate(
            [fragment.model_copy(update={"redaction_policy_version": "redact@2"})],
            destination="openai.responses",
            disclosure_scope=valid_scope,
        ).reason
        == "redaction_policy_mismatch"
    )
    assert (
        policy.evaluate(
            [fragment.model_copy(update={"redacted": False})],
            destination="openai.responses",
            disclosure_scope=valid_scope,
        ).reason
        == "redaction_required"
    )
    assert (
        policy.evaluate(
            [fragment.model_copy(update={"minimized": False})],
            destination="openai.responses",
            disclosure_scope=valid_scope,
        ).reason
        == "minimization_required"
    )


@pytest.mark.asyncio
async def test_restricted_context_never_reaches_external_provider() -> None:
    responses = RecordingResponses()
    gateway = _gateway(responses)

    with pytest.raises(DataEgressDenied):
        await gateway.complete_structured(
            task="risk_analysis",
            fragments=[_fragment(SensitivityClass.RESTRICTED)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.RESTRICTED),
            trace_context=_trace(),
        )

    assert responses.calls == []


@pytest.mark.asyncio
async def test_primary_repair_and_fallback_each_recheck_policy_and_reserve_budget() -> None:
    egress_policy = CountingEgressPolicy()
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    responses = RecordingResponses(
        [
            ValueError("schema invalid with raw provider text"),
            TimeoutError("primary timed out with raw provider text"),
            _Parsed(RiskOutput(risk="fallback", evidence_ids=("ev-1",))),
        ]
    )
    gateway = _gateway(responses, egress_policy=egress_policy, budget_guard=budget_guard)

    result = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert result.data == RiskOutput(risk="fallback", evidence_ids=("ev-1",))
    assert result.fallback_used == "high_reasoning_verifier"
    assert result.errors == ("SCHEMA_REPAIR_FAILED", "PRIMARY_TIMEOUT")
    assert len(egress_policy.decisions) == 3
    assert [record.attempt for record in budget_guard.usage_for_case(_CASE_ID)] == [
        "schema_repair",
        "fallback",
    ]
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert [call["text_format"] for call in responses.calls] == [RiskOutput, RiskOutput, RiskOutput]
    assert [call["store"] for call in responses.calls] == [False, False, False]
    assert "RAW_SENTINEL" not in repr(responses.calls)


@pytest.mark.asyncio
async def test_gateway_provider_metadata_is_sanitized_and_sdk_string_compatible() -> None:
    responses = RecordingResponses()
    gateway = _gateway(responses)

    await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    metadata = responses.calls[0]["metadata"]
    assert metadata == {
        "case_id": str(_CASE_ID),
        "correlation_id": "corr-10",
        "provider": "openai",
        "model": "gpt-5.6-terra",
        "prompt_version": "pv@1",
        "schema_version": "schema@1",
        "redaction_policy_version": "redact@1",
        "attempt": "1",
    }
    assert all(isinstance(value, str) for value in metadata.values())  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_gateway_unsafe_provider_metadata_fails_closed_before_provider() -> None:
    responses = RecordingResponses()
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    gateway = _gateway(responses, budget_guard=budget_guard)

    with pytest.raises(OpenAIMetadataSanitizationError, match="METADATA_SANITIZATION_ERROR"):
        await gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment(SensitivityClass.PUBLIC)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(case_id="john@example.com"),
        )

    assert responses.calls == []
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0


@pytest.mark.asyncio
async def test_privacy_denial_performs_no_fallback() -> None:
    responses = RecordingResponses([TimeoutError("primary timed out")])
    gateway = _gateway(responses)

    with pytest.raises(DataEgressDenied):
        await gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment(SensitivityClass.RESTRICTED)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.RESTRICTED),
            trace_context=_trace(),
        )

    assert responses.calls == []


@pytest.mark.asyncio
async def test_each_attempt_uses_policy_routing_budget_audit_provider_order() -> None:
    order: list[str] = []
    responses = RecordingResponses([_Parsed(RiskOutput(risk="ordered", evidence_ids=("ev-1",)))])
    gateway = OpenAIGateway(
        responses_client=_OrderedResponses(responses, order),
        egress_policy=_OrderedEgressPolicy(order),
        routing_policy=_OrderedRoutingPolicy(order),
        budget_guard=_OrderedBudgetGuard(order),
        audit_spool=_OrderedAuditSpool(order),
    )

    await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert order == ["policy", "routing", "budget", "audit", "provider"]


@pytest.mark.asyncio
async def test_audit_failure_releases_reservation_and_never_calls_provider_or_fallback() -> None:
    responses = RecordingResponses()
    audit_spool = FailingAuditSpool()
    budget_guard = BudgetGuard(default_token_limit=100, default_usd_limit=Decimal("1.00"))
    gateway = _gateway(responses, budget_guard=budget_guard, audit_spool=audit_spool)

    with pytest.raises(OpenAIAuditPersistenceError, match="AUDIT_PERSISTENCE_ERROR"):
        await gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment(SensitivityClass.PUBLIC)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )

    assert responses.calls == []
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert len(audit_spool.events) == 1


@pytest.mark.asyncio
async def test_fallback_reclassification_denial_blocks_second_provider_call() -> None:
    responses = RecordingResponses([TimeoutError("primary timed out")])
    gateway = _gateway(responses, egress_policy=_DenyAfterFirstPolicy())

    with pytest.raises(DataEgressDenied, match="restricted_data"):
        await gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment(SensitivityClass.PUBLIC)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )

    assert len(responses.calls) == 1


@pytest.mark.asyncio
async def test_gateway_ignores_raw_response_text_and_accepts_usage_shapes() -> None:
    responses = RecordingResponses(
        [
            _Parsed(RiskOutput(risk="object-usage", evidence_ids=("ev-1",))),
            _Parsed(
                RiskOutput(risk="dict-usage", evidence_ids=("ev-1",)),
                usage={"total_tokens": 7, "input_tokens": 3, "output_tokens": 4},
            ),
            _MissingUsageParsed(),
        ]
    )
    audit_spool = RecordingAuditSpool()
    gateway = _gateway(responses, audit_spool=audit_spool)

    for _ in range(3):
        result = await gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment(SensitivityClass.PUBLIC)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )
        assert isinstance(result.data, RiskOutput)

    serialized_audit = repr(audit_spool.events)
    assert "RAW_SENTINEL" not in serialized_audit
    assert "raw provider text" not in serialized_audit


@pytest.mark.asyncio
async def test_invalid_present_output_uses_one_high_reasoning_repair_attempt() -> None:
    responses = RecordingResponses(
        [
            _InvalidParsed(),
            _Parsed(RiskOutput(risk="repaired", evidence_ids=("ev-1",))),
        ]
    )
    gateway = _gateway(responses)

    result = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert result.data == RiskOutput(risk="repaired", evidence_ids=("ev-1",))
    assert [call["model"] for call in responses.calls] == ["gpt-5.6-terra", "gpt-5.6-sol"]
    assert [call["text_format"] for call in responses.calls] == [RiskOutput, RiskOutput]


@pytest.mark.asyncio
async def test_schema_repair_reconciles_billed_usage_from_invalid_response() -> None:
    responses = RecordingResponses(
        [
            _InvalidParsed(),
            _Parsed(RiskOutput(risk="repaired", evidence_ids=("ev-1",))),
        ]
    )
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    gateway = _gateway(
        responses,
        budget_guard=budget_guard,
        usage_cost_calculator=lambda usage: Decimal(usage.total_tokens) / Decimal(1_000),
    )

    await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    usage_records = budget_guard.usage_for_case(_CASE_ID)
    assert [record.tokens for record in usage_records] == [13, 12]
    assert [record.usd_cost for record in usage_records] == [Decimal("0.013"), Decimal("0.012")]


@pytest.mark.asyncio
async def test_invalid_fallback_terminates_with_stable_schema_error() -> None:
    responses = RecordingResponses([_InvalidParsed(), _InvalidParsed(), _InvalidParsed()])
    gateway = _gateway(responses)

    with pytest.raises(OpenAISchemaValidationError, match="SCHEMA_VALIDATION_FAILED"):
        await gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment(SensitivityClass.PUBLIC)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )

    assert len(responses.calls) == 3
    assert [call["model"] for call in responses.calls] == [
        "gpt-5.6-terra",
        "gpt-5.6-sol",
        "gpt-5.6-sol",
    ]


@pytest.mark.asyncio
async def test_openai_api_timeout_maps_stable_error_and_falls_back() -> None:
    import httpx
    from openai import APITimeoutError

    responses = RecordingResponses(
        [
            APITimeoutError(request=httpx.Request("POST", "https://example.invalid")),
            _Parsed(RiskOutput(risk="fallback", evidence_ids=("ev-1",))),
        ]
    )
    gateway = _gateway(responses)

    result = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert result.errors == ("PRIMARY_TIMEOUT",)
    assert result.fallback_used == "high_reasoning_verifier"
    assert "example.invalid" not in repr(result)


@pytest.mark.asyncio
async def test_gateway_releases_budget_reservation_when_provider_call_is_cancelled() -> None:
    responses = BlockingResponses()
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    gateway = _gateway(responses, budget_guard=budget_guard)  # type: ignore[arg-type]

    task = asyncio.create_task(
        gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment(SensitivityClass.PUBLIC)],
            expected_schema=RiskOutput,
            budget_request=_budget(),
            routing_context=_routing(SensitivityClass.PUBLIC),
            trace_context=_trace(),
        )
    )
    await responses.entered.wait()
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 100

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0


@pytest.mark.asyncio
async def test_gateway_passes_routing_latency_budget_to_provider_timeout() -> None:
    responses = RecordingResponses()
    gateway = _gateway(responses)

    await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC).model_copy(
            update={"latency_budget_ms": 42_000}
        ),
        trace_context=_trace(),
    )

    assert responses.calls[0]["timeout"] == 42.0


@pytest.mark.asyncio
async def test_successful_missing_usage_consumes_full_reservation() -> None:
    responses = RecordingResponses([_MissingUsageParsed()])
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    gateway = _gateway(
        responses,
        budget_guard=budget_guard,
        usage_cost_calculator=lambda usage: Decimal(usage.total_tokens) / Decimal(1_000),
    )

    await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    usage_record = budget_guard.usage_for_case(_CASE_ID)[0]
    assert usage_record.tokens == 100
    assert usage_record.usd_cost == Decimal("0.10")


@pytest.mark.asyncio
async def test_gateway_usage_aliases_return_actual_record_cost() -> None:
    responses = RecordingResponses(
        [
            _ParsedWithUsage({"prompt_tokens": 4, "completion_tokens": 9, "total_tokens": 13}),
            _ParsedWithUsage(_AliasUsage()),
        ]
    )
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    gateway = _gateway(responses, budget_guard=budget_guard)

    first = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )
    second = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert first.usage.total_tokens == 13
    assert first.usage.input_tokens == 4
    assert first.usage.output_tokens == 9
    assert first.cost_usd == Decimal("0.10")
    assert second.usage.total_tokens == 11
    assert second.usage.input_tokens == 5
    assert second.usage.output_tokens == 6
    assert second.cost_usd == Decimal("0.10")


@pytest.mark.asyncio
async def test_gateway_reconciles_successful_usage_with_injected_actual_cost() -> None:
    responses = RecordingResponses(
        [
            _ParsedWithUsage(
                {"input_tokens": 2_000, "output_tokens": 500, "total_tokens": 2_500}
            )
        ]
    )
    budget_guard = BudgetGuard(default_token_limit=10_000, default_usd_limit=Decimal("1.00"))
    gateway = _gateway(
        responses,
        budget_guard=budget_guard,
        usage_cost_calculator=lambda usage: (
            Decimal(usage.input_tokens) * Decimal("1.00")
            + Decimal(usage.output_tokens) * Decimal("6.00")
        )
        / Decimal(1_000_000),
    )

    result = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=7_500,
            worst_case_usd_cost=Decimal("0.05"),
        ),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert result.usage.total_tokens == 2_500
    assert result.cost_usd == Decimal("0.005")
    assert budget_guard.usage_for_case(_CASE_ID)[0].usd_cost == Decimal("0.005")


@pytest.mark.asyncio
async def test_gateway_invalid_or_partial_usage_pessimistically_consumes_reservation() -> None:
    responses = RecordingResponses(
        [
            _ParsedWithUsage({"total_tokens": "not-an-int", "input_tokens": 3, "output_tokens": 4}),
            _ParsedWithUsage({"input_tokens": 3, "output_tokens": 4}),
        ]
    )
    budget_guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))
    gateway = _gateway(
        responses,
        budget_guard=budget_guard,
        usage_cost_calculator=lambda usage: Decimal(usage.total_tokens) / Decimal(1_000),
    )

    first = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )
    second = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment(SensitivityClass.PUBLIC)],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(SensitivityClass.PUBLIC),
        trace_context=_trace(),
    )

    assert first.usage.total_tokens == 100
    assert first.cost_usd == Decimal("0.10")
    assert second.usage.total_tokens == 100
    assert second.cost_usd == Decimal("0.10")
    assert budget_guard.reserved_tokens_for_case(_CASE_ID) == 0
    assert [record.tokens for record in budget_guard.usage_for_case(_CASE_ID)] == [100, 100]


def _gateway(
    responses: RecordingResponses,
    *,
    egress_policy: DataEgressPolicy | None = None,
    budget_guard: BudgetGuard | None = None,
    audit_spool: RecordingAuditSpool | None = None,
    usage_cost_calculator: Callable[[LLMUsage], Decimal] | None = None,
) -> OpenAIGateway:
    return OpenAIGateway(
        responses_client=responses,
        egress_policy=egress_policy or DataEgressPolicy(),
        routing_policy=ModelRoutingPolicy(
            default_profile=ModelProfile(provider="openai", model="gpt-5.6-terra", role="structured_analysis"),
            high_reasoning_profile=ModelProfile(
                provider="openai",
                model="gpt-5.6-sol",
                role="high_reasoning_verifier",
            ),
        ),
        budget_guard=budget_guard or BudgetGuard(
            default_token_limit=1_000,
            default_usd_limit=Decimal("10.00"),
        ),
        audit_spool=audit_spool or RecordingAuditSpool(),
        usage_cost_calculator=usage_cost_calculator,
    )


class _OrderedResponses:
    def __init__(self, delegate: RecordingResponses, order: list[str]) -> None:
        self.delegate = delegate
        self.order = order

    async def parse(self, **kwargs: object) -> object:
        self.order.append("provider")
        return await self.delegate.parse(**kwargs)


class _OrderedEgressPolicy(DataEgressPolicy):
    def __init__(self, order: list[str]) -> None:
        self.order = order

    def evaluate(self, *args: object, **kwargs: object) -> EgressDecision:
        self.order.append("policy")
        return super().evaluate(*args, **kwargs)  # type: ignore[arg-type]


class _OrderedRoutingPolicy(ModelRoutingPolicy):
    def __init__(self, order: list[str]) -> None:
        self.order = order
        super().__init__(
            default_profile=ModelProfile(provider="openai", model="gpt-5.6-terra", role="structured_analysis"),
            high_reasoning_profile=ModelProfile(
                provider="openai",
                model="gpt-5.6-sol",
                role="high_reasoning_verifier",
            ),
        )

    def select(self, *args: object, **kwargs: object) -> ModelDecision:
        self.order.append("routing")
        return super().select(*args, **kwargs)  # type: ignore[arg-type]


class _OrderedBudgetGuard(BudgetGuard):
    def __init__(self, order: list[str]) -> None:
        self.order = order
        super().__init__(default_token_limit=1_000, default_usd_limit=Decimal("10.00"))

    def reserve(self, *args: object, **kwargs: object) -> BudgetReservation:
        self.order.append("budget")
        return super().reserve(*args, **kwargs)  # type: ignore[arg-type]


class _OrderedAuditSpool(RecordingAuditSpool):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self.order = order

    def append(self, event: AuditEvent) -> str:
        self.order.append("audit")
        return super().append(event)


class _DenyAfterFirstPolicy(DataEgressPolicy):
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, *args: object, **kwargs: object) -> EgressDecision:
        self.calls += 1
        if self.calls > 1:
            return EgressDecision(
                allowed=False,
                reason="restricted_data",
                policy_version=self.version,
                denied_fragment_ids=("reclassified",),
            )
        return super().evaluate(*args, **kwargs)  # type: ignore[arg-type]


def test_startup_public_research_egress_excludes_hostile_producer_input() -> None:
    case_id = UUID("00000000-0000-0000-0000-000000000399")
    now = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)
    sentinels = (
        "%PDF-RAW-DOCUMENT-EGRESS-SENTINEL",
        "private-founder-deck.pdf",
        "finance-internal.docx",
        "customer-counts.xlsx",
        "contract-register.csv",
        "cap-table.pptx",
        "C:\\Users\\Akana\\private\\founder-deck.pdf",
        "PROMPT-EGRESS-SENTINEL",
        "founder.egress@example.com",
        "sk-" + "proj-EGRESS-SENTINEL-1234567890",
        "MRR 9000 ARR 108000 revenue pricing",
        "burn cash balance customers contracts cap table",
    )
    fields = {
        name.value: StartupProfileField(
            name=name,
            status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
            confidence=Decimal(0),
        )
        for name in StartupProfileFieldName
    }
    for name, values in (
        (
            StartupProfileFieldName.SOLUTION,
            ("AI research copilot MRR 9000 ARR 108000 revenue pricing private-founder-deck.pdf finance-internal.docx",),
        ),
        (
            StartupProfileFieldName.ICP,
            ("seed-stage founders customers contracts cap table customer-counts.xlsx",),
        ),
        (
            StartupProfileFieldName.GEOGRAPHY,
            ("Kazakhstan burn cash balance contract-register.csv cap-table.pptx",),
        ),
        (StartupProfileFieldName.TRACTION, sentinels[:8]),
    ):
        fields[name.value] = StartupProfileField(
            name=name,
            status=StartupProfileFieldStatus.INFERENCE,
            values=values,
            confidence=Decimal("0.7"),
            dependency_refs=(uuid5(NAMESPACE_URL, f"dependency:{name.value}"),),
            reason_code="founder_provided",
        )
    profile = StartupProfile.build(
        case_id=case_id,
        schema_version="startup_profile@1",
        profile_version="primary@1",
        extractor_version="privacy-test@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=1,
        source_hashes={"upload": "sha256:" + ("a" * 64)},
        parse_outcomes={"upload": "parsed"},
        fields=fields,
        case_revision_at=now,
    )

    class ProfileRepository:
        def get_current(self, requested_case_id: UUID) -> StartupProfile:
            assert requested_case_id == case_id
            return profile

    class ResponsesClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return SimpleNamespace(
                output=(
                    SimpleNamespace(
                        type="message",
                        content=(
                            SimpleNamespace(
                                type="output_text",
                                text="Inference only",
                                annotations=(
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.com/public-market",
                                        "title": "Public market source",
                                    },
                                ),
                            ),
                        ),
                    ),
                ),
                usage=SimpleNamespace(
                    input_tokens=50,
                    output_tokens=20,
                    total_tokens=70,
                ),
            )

    class NeverFallback:
        def collect(self, _plan: object) -> object:
            raise AssertionError("successful live research must not use fallback")

    client = ResponsesClient()
    service = StartupAdvisorResearchService(
        profile_repository=ProfileRepository(),
        market_research_service=StartupMarketResearchService(clock=lambda: now),
        live_research_port=OpenAIStartupWebResearchAdapter(
            responses_client=client,
            clock=lambda: now,
        ),
        fallback_research_port=NeverFallback(),
    )
    hostile_question_text = " ".join(sentinels)

    delta = service.research(
        case_id,
        AdvisorQuestion(
            question_id=f"{case_id}:icp",
            field_key="icp",
            question_ru=hostile_question_text,
            reason_ru=hostile_question_text,
            unlocks_ru=hostile_question_text,
            answer_modes=("public_research",),
        ),
        AdvisorAnswer(
            answer_type="public_research",
            value=hostile_question_text,
            consent_public_research=True,
        ),
    )

    assert delta.status == "deferred"
    assert delta.fallback_used is False
    assert delta.source_ids == ()
    assert client.calls == []
    provider_payload = delta.model_dump_json()
    assert all(sentinel not in provider_payload for sentinel in sentinels)
    assert delta.fail_reason_ru is not None
    assert "durable research job flow" in delta.fail_reason_ru


_CASE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _fragment(sensitivity: SensitivityClass) -> LLMContextFragment:
    return LLMContextFragment(
        id=uuid4(),
        minimized_text="10-K liquidity risk",
        sensitivity=sensitivity,
        redacted=sensitivity is not SensitivityClass.PUBLIC,
        minimized=True,
        redaction_policy_version="redact@1",
    )


def _budget() -> LLMBudgetRequest:
    return LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("0.10"),
    )


def _routing(sensitivity: SensitivityClass) -> LLMRoutingContext:
    return LLMRoutingContext(
        task_complexity="standard",
        latency_budget_ms=30_000,
        schema_validation_failed=False,
        potential_finding_severity=FindingSeverity.MEDIUM,
        sensitivity=sensitivity,
    )


def _trace(*, case_id: str | None = None) -> TraceContext:
    return TraceContext(
        request_id="req-10",
        run_id="run-10",
        case_id=case_id or str(_CASE_ID),
        correlation_id="corr-10",
        workflow_type="public_company",
        app_version="app@1",
        graph_version="graph@1",
        redaction_policy_version="redact@1",
    )

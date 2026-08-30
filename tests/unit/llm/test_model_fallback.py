from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from due_diligence_agent.adapters.openai.gateway import OpenAIGateway
from due_diligence_agent.application.policies.budget import BudgetGuard
from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
from due_diligence_agent.application.policies.model_routing import ModelProfile, ModelRoutingPolicy
from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.llm import LLMBudgetRequest, LLMContextFragment, LLMRoutingContext
from due_diligence_agent.ports.tracing import AuditEvent, TraceContext
from pydantic import BaseModel, ConfigDict


class RiskOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk: str
    evidence_ids: tuple[str, ...]


class RecordingAuditSpool:
    def append(self, event: AuditEvent) -> str:
        return "memory://audit"

    def read_batch(self, limit: int = 100) -> list[AuditEvent]:
        return []

    def mark_flushed(self, event_ids: list[str]) -> None:
        return None


class RecordingResponses:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _Parsed:
    def __init__(self, output: RiskOutput) -> None:
        self.output_parsed = output
        self.output_text = "RAW_SENTINEL model free-form text must be ignored"
        self.usage = {"total_tokens": 12, "input_tokens": 6, "output_tokens": 6}


@pytest.mark.asyncio
async def test_fallback_preserves_schema_and_records_primary_error() -> None:
    responses = RecordingResponses(
        [
            TimeoutError("primary timed out with raw provider text"),
            _Parsed(RiskOutput(risk="fallback", evidence_ids=("ev-1",))),
        ]
    )
    gateway = _gateway(responses)

    result = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment()],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(schema_validation_failed=False),
        trace_context=_trace(),
    )

    assert result.data == RiskOutput(risk="fallback", evidence_ids=("ev-1",))
    assert result.fallback_used == "high_reasoning_verifier"
    assert result.errors == ("PRIMARY_TIMEOUT",)
    assert [call["text_format"] for call in responses.calls] == [RiskOutput, RiskOutput]
    assert responses.calls[1]["model"] == "gpt-5.6-sol"


@pytest.mark.asyncio
async def test_more_than_one_schema_repair_attempt_is_impossible() -> None:
    responses = RecordingResponses(
        [
            ValueError("schema invalid"),
            ValueError("schema invalid again"),
            _Parsed(RiskOutput(risk="fallback", evidence_ids=("ev-1",))),
        ]
    )
    gateway = _gateway(responses)

    result = await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment()],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(schema_validation_failed=False),
        trace_context=_trace(),
    )

    assert result.fallback_used == "high_reasoning_verifier"
    assert result.errors == ("SCHEMA_REPAIR_FAILED",)
    assert len(responses.calls) == 3


@pytest.mark.asyncio
async def test_gateway_applies_provider_side_output_token_ceiling() -> None:
    responses = RecordingResponses(
        [_Parsed(RiskOutput(risk="bounded", evidence_ids=("ev-1",)))]
    )
    gateway = _gateway(responses, max_output_tokens=640)

    await gateway.complete_structured(
        task="public_risk",
        fragments=[_fragment()],
        expected_schema=RiskOutput,
        budget_request=_budget(),
        routing_context=_routing(schema_validation_failed=False),
        trace_context=_trace(),
    )

    assert responses.calls[0]["max_output_tokens"] == 640
    assert responses.calls[0]["instructions"] == "public_risk"


def _gateway(
    responses: RecordingResponses,
    *,
    max_output_tokens: int | None = None,
) -> OpenAIGateway:
    return OpenAIGateway(
        responses_client=responses,
        egress_policy=DataEgressPolicy(),
        routing_policy=ModelRoutingPolicy(
            default_profile=ModelProfile(provider="openai", model="gpt-5.6-terra", role="structured_analysis"),
            high_reasoning_profile=ModelProfile(
                provider="openai",
                model="gpt-5.6-sol",
                role="high_reasoning_verifier",
            ),
        ),
        budget_guard=BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("10.00")),
        audit_spool=RecordingAuditSpool(),
        max_output_tokens=max_output_tokens,
    )


_CASE_ID = UUID("00000000-0000-0000-0000-000000000010")


def _fragment() -> LLMContextFragment:
    return LLMContextFragment(
        id=UUID("00000000-0000-0000-0000-000000000011"),
        minimized_text="10-K liquidity risk",
        sensitivity=SensitivityClass.PUBLIC,
        redacted=False,
        minimized=True,
        redaction_policy_version="redact@1",
    )


def _budget() -> LLMBudgetRequest:
    return LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("0.10"),
    )


def _routing(*, schema_validation_failed: bool) -> LLMRoutingContext:
    return LLMRoutingContext(
        task_complexity="standard",
        latency_budget_ms=30_000,
        schema_validation_failed=schema_validation_failed,
        potential_finding_severity=FindingSeverity.MEDIUM,
        sensitivity=SensitivityClass.PUBLIC,
    )


def _trace() -> TraceContext:
    return TraceContext(
        request_id="req-10",
        run_id="run-10",
        case_id=str(_CASE_ID),
        correlation_id="corr-10",
        workflow_type="public_company",
        app_version="app@1",
        graph_version="graph@1",
        redaction_policy_version="redact@1",
    )

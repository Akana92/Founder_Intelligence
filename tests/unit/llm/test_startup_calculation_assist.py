from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.llm import (
    CodeInterpreterResult,
    LLMBudgetRequest,
    LLMRoutingContext,
)
from due_diligence_agent.ports.startup_calculation_assist import (
    StartupCalculationAssistArtifact,
    StartupCalculationAssistPolicy,
    StartupCalculationAssistRequest,
    StartupCalculationAssistUnavailable,
)
from due_diligence_agent.ports.tracing import TraceContext


class RecordingCodeInterpreter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run_public_analysis(self, artifact: object, **kwargs: object) -> CodeInterpreterResult:
        self.calls.append({"artifact": artifact, **kwargs})
        return CodeInterpreterResult(
            provisional=True,
            code_hash="a" * 64,
            code_artifact_id=uuid4(),
            output_artifact_id=uuid4(),
            output_hash="b" * 64,
            canonical_calculation_ids=(),
        )


@pytest.mark.asyncio
async def test_calculation_assist_is_disabled_by_default_and_makes_zero_calls() -> None:
    provider = RecordingCodeInterpreter()
    policy = StartupCalculationAssistPolicy(provider=provider)

    with pytest.raises(StartupCalculationAssistUnavailable, match="calculation_assist_disabled"):
        await policy.run(_request(), disclosure_scope=_scope(), budget_request=_budget())

    assert provider.calls == []


@pytest.mark.asyncio
async def test_calculation_assist_requires_explicit_disclosure_and_positive_budget() -> None:
    provider = RecordingCodeInterpreter()
    policy = StartupCalculationAssistPolicy(provider=provider, enabled=True)

    with pytest.raises(StartupCalculationAssistUnavailable, match="disclosure_required"):
        await policy.run(_request(), disclosure_scope=None, budget_request=_budget())
    with pytest.raises(StartupCalculationAssistUnavailable, match="budget_required"):
        await policy.run(
            _request(),
            disclosure_scope=_scope(),
            budget_request=LLMBudgetRequest(
                case_id=_CASE_ID,
                worst_case_tokens=0,
                worst_case_usd_cost=Decimal("0"),
            ),
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_calculation_assist_binds_disclosure_routing_and_case_before_provider_call() -> None:
    provider = RecordingCodeInterpreter()
    policy = StartupCalculationAssistPolicy(provider=provider, enabled=True)

    wrong_destination = _scope().model_copy(update={"destination": "openai.responses"})
    with pytest.raises(StartupCalculationAssistUnavailable, match="disclosure_destination_mismatch"):
        await policy.run(_request(), disclosure_scope=wrong_destination, budget_request=_budget())

    wrong_policy = _scope().model_copy(update={"egress_policy_version": "egress@0"})
    with pytest.raises(StartupCalculationAssistUnavailable, match="egress_policy_mismatch"):
        await policy.run(_request(), disclosure_scope=wrong_policy, budget_request=_budget())

    public_routing = _request().model_copy(
        update={"routing_context": _request().routing_context.model_copy(update={"sensitivity": SensitivityClass.PUBLIC})}
    )
    with pytest.raises(StartupCalculationAssistUnavailable, match="routing_sensitivity_mismatch"):
        await policy.run(public_routing, disclosure_scope=_scope(), budget_request=_budget())

    invalid_case = _request().model_copy(
        update={
            "trace_context": TraceContext(
                request_id="req-21",
                run_id="run-21",
                case_id="not-a-uuid",
                correlation_id="corr-21",
                workflow_type="startup",
                app_version="app@1",
                graph_version="startup@1",
                redaction_policy_version="rules-redactor@1",
            )
        }
    )
    with pytest.raises(StartupCalculationAssistUnavailable, match="invalid_trace_case_id"):
        await policy.run(invalid_case, disclosure_scope=_scope(), budget_request=_budget())

    assert provider.calls == []


@pytest.mark.asyncio
async def test_calculation_assist_rejects_unapproved_template_and_unsafe_artifact() -> None:
    provider = RecordingCodeInterpreter()
    policy = StartupCalculationAssistPolicy(provider=provider, enabled=True)

    with pytest.raises(StartupCalculationAssistUnavailable, match="template_not_allowed"):
        await policy.run(
            _request(template_id="arbitrary_python"),
            disclosure_scope=_scope(),
            budget_request=_budget(),
        )
    with pytest.raises(StartupCalculationAssistUnavailable, match="artifact_not_egress_ready"):
        await policy.run(
            _request(redacted=False),
            disclosure_scope=_scope(),
            budget_request=_budget(),
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_calculation_assist_runs_allowlisted_network_disabled_provisional_analysis() -> None:
    provider = RecordingCodeInterpreter()
    policy = StartupCalculationAssistPolicy(provider=provider, enabled=True)

    result = await policy.run(
        _request(template_id="unit_economics_summary@1"),
        disclosure_scope=_scope(),
        budget_request=_budget(),
    )

    assert result.provisional is True
    assert result.canonical_calculation_ids == ()
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["code"] == StartupCalculationAssistPolicy.ALLOWED_TEMPLATES["unit_economics_summary@1"]
    assert "requests" not in str(call["code"])
    assert "socket" not in str(call["code"])


_CASE_ID = UUID("00000000-0000-0000-0000-000000000021")


def _request(
    *,
    template_id: str = "unit_economics_summary@1",
    redacted: bool = True,
) -> StartupCalculationAssistRequest:
    return StartupCalculationAssistRequest(
        artifact=StartupCalculationAssistArtifact(
            id=uuid4(),
            content=b"metric,value\nrevenue,100\n",
            media_type="text/csv",
            sensitivity=SensitivityClass.CONFIDENTIAL,
            redacted=redacted,
            minimized=True,
            redaction_policy_version="rules-redactor@1",
        ),
        template_id=template_id,
        routing_context=LLMRoutingContext(
            task_complexity="standard",
            latency_budget_ms=30_000,
            schema_validation_failed=False,
            potential_finding_severity=FindingSeverity.MEDIUM,
            sensitivity=SensitivityClass.CONFIDENTIAL,
        ),
        trace_context=TraceContext(
            request_id="req-21",
            run_id="run-21",
            case_id=str(_CASE_ID),
            correlation_id="corr-21",
            workflow_type="startup",
            app_version="app@1",
            graph_version="startup@1",
            redaction_policy_version="rules-redactor@1",
        ),
        network_policy="disabled",
    )


def _budget() -> LLMBudgetRequest:
    return LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=200,
        worst_case_usd_cost=Decimal("0.01"),
    )


def _scope() -> DisclosureScope:
    return DisclosureScope(
        approval_id=uuid4(),
        allowed_classes=frozenset({SensitivityClass.CONFIDENTIAL}),
        destination="openai.code_interpreter",
        egress_policy_version="egress@1",
        redaction_policy_versions=frozenset({"rules-redactor@1"}),
    )

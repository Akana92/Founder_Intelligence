from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID

import pytest

from due_diligence_agent.adapters.openai.gateway import OpenAIGateway
from due_diligence_agent.application.policies.budget import BudgetExceeded, BudgetGuard
from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
from due_diligence_agent.application.policies.model_routing import ModelProfile, ModelRoutingPolicy
from due_diligence_agent.domain.common import FindingSeverity, SensitivityClass
from due_diligence_agent.ports.llm import LLMBudgetRequest, LLMContextFragment, LLMRoutingContext, LLMUsage
from due_diligence_agent.ports.tracing import AuditEvent, TraceContext
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError


class RiskOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk: str
    evidence_ids: tuple[str, ...]


class RecordingResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return object()


class StructuredResponse:
    def __init__(
        self,
        *,
        output_parsed: object,
        usage: dict[str, int] | None = None,
    ) -> None:
        self.output_parsed = output_parsed
        self.usage = usage


class SequenceResponses:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingLLMCalls:
    def __init__(self) -> None:
        self.records: list[dict[str, object | None]] = []

    def __call__(self, **attributes: object | None) -> None:
        self.records.append(attributes)


class RecordingAuditSpool:
    def append(self, event: AuditEvent) -> str:
        return "memory://audit"

    def read_batch(self, limit: int = 100) -> list[AuditEvent]:
        return []

    def mark_flushed(self, event_ids: list[str]) -> None:
        return None


def test_concurrent_reservations_cannot_oversubscribe_remaining_budget() -> None:
    guard = BudgetGuard(default_token_limit=150, default_usd_limit=Decimal("1.50"))
    request = LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("1.00"),
    )
    start = Barrier(3)
    outcomes: list[str] = []

    def reserve() -> None:
        start.wait()
        try:
            guard.reserve(request, attempt="primary")
        except BudgetExceeded:
            outcomes.append("denied")
        else:
            outcomes.append("reserved")

    threads = [Thread(target=reserve), Thread(target=reserve)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["denied", "reserved"]


def test_persistent_budget_guard_counts_active_reservations_across_instances(tmp_path: Path) -> None:
    ledger_path = tmp_path / "budget.sqlite3"
    first = BudgetGuard(
        default_token_limit=150,
        default_usd_limit=Decimal("1.50"),
        persistence_path=ledger_path,
    )
    second = BudgetGuard(
        default_token_limit=150,
        default_usd_limit=Decimal("1.50"),
        persistence_path=ledger_path,
    )
    request = LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("1.00"),
    )

    reservation = first.reserve(request, attempt="primary")

    with pytest.raises(BudgetExceeded):
        second.reserve(request, attempt="retry")
    assert second.reserved_tokens_for_case(_CASE_ID) == 100
    first.release(reservation)
    assert second.reserved_tokens_for_case(_CASE_ID) == 0


def test_persistent_budget_guard_concurrent_instances_do_not_oversubscribe(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "budget.sqlite3"
    first = BudgetGuard(
        default_token_limit=150,
        default_usd_limit=Decimal("1.50"),
        persistence_path=ledger_path,
    )
    second = BudgetGuard(
        default_token_limit=150,
        default_usd_limit=Decimal("1.50"),
        persistence_path=ledger_path,
    )
    request = LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("1.00"),
    )
    start = Barrier(3)
    outcomes: list[str] = []

    def reserve(guard: BudgetGuard) -> None:
        start.wait()
        try:
            guard.reserve(request, attempt="primary")
        except BudgetExceeded:
            outcomes.append("denied")
        else:
            outcomes.append("reserved")

    threads = [Thread(target=reserve, args=(first,)), Thread(target=reserve, args=(second,))]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["denied", "reserved"]


def test_persistent_budget_guard_counts_reconciled_usage_across_instances(tmp_path: Path) -> None:
    ledger_path = tmp_path / "budget.sqlite3"
    first = BudgetGuard(
        default_token_limit=150,
        default_usd_limit=Decimal("1.50"),
        persistence_path=ledger_path,
    )
    request = LLMBudgetRequest(
        case_id=_CASE_ID,
        worst_case_tokens=100,
        worst_case_usd_cost=Decimal("1.00"),
    )
    reservation = first.reserve(request, attempt="primary")
    record = first.reconcile(
        reservation,
        usage=LLMUsage(input_tokens=40, output_tokens=20, total_tokens=60),
        actual_usd_cost=Decimal("0.60"),
    )
    reconstructed = BudgetGuard(
        default_token_limit=150,
        default_usd_limit=Decimal("1.50"),
        persistence_path=ledger_path,
    )

    assert reconstructed.usage_for_case(_CASE_ID) == (record,)
    with pytest.raises(BudgetExceeded):
        reconstructed.reserve(request, attempt="retry")


def test_persistent_budget_guard_closes_sqlite_handles(tmp_path: Path) -> None:
    ledger_path = tmp_path / "budget.sqlite3"
    guard = BudgetGuard(
        default_token_limit=150,
        default_usd_limit=Decimal("1.50"),
        persistence_path=ledger_path,
    )
    reservation = guard.reserve(
        LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=10,
            worst_case_usd_cost=Decimal("0.10"),
        ),
        attempt="primary",
    )
    guard.release(reservation)

    ledger_path.unlink()
    assert not ledger_path.exists()


def test_negative_budget_request_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=-1,
            worst_case_usd_cost=Decimal("0.10"),
        )
    with pytest.raises(ValidationError):
        LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=1,
            worst_case_usd_cost=Decimal("-0.01"),
        )


def test_duplicate_reservation_reconciliation_is_rejected() -> None:
    guard = BudgetGuard(default_token_limit=150, default_usd_limit=Decimal("1.50"))
    reservation = guard.reserve(
        LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=100,
            worst_case_usd_cost=Decimal("1.00"),
        ),
        attempt="primary",
    )

    guard.reconcile(reservation, usage=None)

    with pytest.raises(ValueError, match="BUDGET_RESERVATION_ALREADY_RECONCILED"):
        guard.reconcile(reservation, usage=None)


def test_negative_actual_cost_does_not_consume_reservation() -> None:
    guard = BudgetGuard(default_token_limit=150, default_usd_limit=Decimal("1.50"))
    reservation = guard.reserve(
        LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=100,
            worst_case_usd_cost=Decimal("1.00"),
        ),
        attempt="primary",
    )

    with pytest.raises(ValueError, match="budget usage must be non-negative"):
        guard.reconcile(
            reservation,
            usage=LLMUsage(input_tokens=1, output_tokens=1, total_tokens=2),
            actual_usd_cost=Decimal("-0.01"),
        )

    assert guard.reserved_tokens_for_case(_CASE_ID) == 100
    guard.release(reservation)
    assert guard.reserved_tokens_for_case(_CASE_ID) == 0


@pytest.mark.asyncio
async def test_hard_budget_blocks_provider_call() -> None:
    responses = RecordingResponses()
    gateway = OpenAIGateway(
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
        budget_guard=BudgetGuard(default_token_limit=50, default_usd_limit=Decimal("0.05")),
        audit_spool=RecordingAuditSpool(),
    )

    with pytest.raises(BudgetExceeded):
        await gateway.complete_structured(
            task="public_risk",
            fragments=[_fragment()],
            expected_schema=RiskOutput,
            budget_request=LLMBudgetRequest(
                case_id=_CASE_ID,
                worst_case_tokens=100,
                worst_case_usd_cost=Decimal("0.10"),
            ),
            routing_context=_routing(),
            trace_context=_trace(),
        )

    assert responses.calls == []


@pytest.mark.asyncio
async def test_gateway_reconciles_success_with_priced_usage_not_full_reservation() -> None:
    responses = SequenceResponses(
        [
            StructuredResponse(
                output_parsed=RiskOutput(risk="concentration", evidence_ids=()),
                usage={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
            )
        ]
    )
    guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("1.00"))
    recorder = RecordingLLMCalls()
    gateway = _gateway_for_budget_pricing(responses, guard, llm_call_recorder=recorder)

    result = await gateway.complete_structured(
        task="risk",
        fragments=[_fragment()],
        expected_schema=RiskOutput,
        budget_request=LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=800,
            worst_case_usd_cost=Decimal("0.50"),
        ),
        routing_context=_routing(),
        trace_context=_trace(),
    )

    [record] = guard.usage_for_case(_CASE_ID)
    assert record.tokens == 150
    assert record.usd_cost == Decimal("0.000300")
    assert result.cost_usd == Decimal("0.000300")
    assert recorder.records == [
        {
            "case_id": str(_CASE_ID),
            "run_id": "run-10",
            "correlation_id": "corr-10",
            "workflow_type": "public_company",
            "request_id": "req-10",
            "node_name": "llm_call",
            "agent_role": "startup_due_diligence",
            "status": "success",
            "attempt": 1,
            "retry_count": 0,
            "provider": "openai",
            "model": "gpt-5.6-luna",
            "tool": "responses.parse",
            "evidence_count": 1,
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
            "cost_usd": 0.0003,
            "schema_version": "startup_llm_call_span@1",
            "duration_ms": pytest.approx(recorder.records[0]["duration_ms"]),
            "latency_ms": pytest.approx(recorder.records[0]["latency_ms"]),
            "checkpoint_id": recorder.records[0]["checkpoint_id"],
        }
    ]
    assert isinstance(recorder.records[0]["checkpoint_id"], str)
    serialized = repr(recorder.records)
    assert "10-K liquidity risk" not in serialized
    assert "concentration" not in serialized


@pytest.mark.asyncio
async def test_gateway_reconciles_schema_retry_with_response_usage_before_repair() -> None:
    responses = SequenceResponses(
        [
            StructuredResponse(
                output_parsed=None,
                usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            ),
            StructuredResponse(
                output_parsed=RiskOutput(risk="validated", evidence_ids=()),
                usage={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
            ),
        ]
    )
    guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("1.00"))
    recorder = RecordingLLMCalls()
    gateway = _gateway_for_budget_pricing(responses, guard, llm_call_recorder=recorder)

    await gateway.complete_structured(
        task="risk",
        fragments=[_fragment()],
        expected_schema=RiskOutput,
        budget_request=LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=800,
            worst_case_usd_cost=Decimal("0.50"),
        ),
        routing_context=_routing(),
        trace_context=_trace(),
    )

    records = guard.usage_for_case(_CASE_ID)
    assert [(record.attempt, record.tokens, record.usd_cost) for record in records] == [
        ("primary", 150, Decimal("0.000400")),
        ("schema_repair", 100, Decimal("0.000200")),
    ]
    assert [record["status"] for record in recorder.records] == [
        "invalid",
        "success",
    ]
    assert recorder.records[0]["error_code"] == "invalid_output"
    assert [record["attempt"] for record in recorder.records] == [1, 2]
    assert [record["total_tokens"] for record in recorder.records] == [150, 100]
    assert [record["cost_usd"] for record in recorder.records] == [0.0004, 0.0002]


@pytest.mark.asyncio
async def test_gateway_does_not_report_reserved_usage_when_response_has_no_usage() -> None:
    responses = SequenceResponses(
        [StructuredResponse(output_parsed=RiskOutput(risk="unknown", evidence_ids=()))]
    )
    guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("1.00"))
    recorder = RecordingLLMCalls()
    gateway = _gateway_for_budget_pricing(responses, guard, llm_call_recorder=recorder)

    await gateway.complete_structured(
        task="risk",
        fragments=[_fragment()],
        expected_schema=RiskOutput,
        budget_request=LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=800,
            worst_case_usd_cost=Decimal("0.50"),
        ),
        routing_context=_routing(),
        trace_context=_trace(),
    )

    assert recorder.records == []


@pytest.mark.asyncio
async def test_gateway_releases_budget_when_schema_client_fails_before_response() -> None:
    responses = SequenceResponses(
        [
            ValueError("SCHEMA_VALIDATION_FAILED"),
            StructuredResponse(
                output_parsed=RiskOutput(risk="validated", evidence_ids=()),
                usage={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
            ),
        ]
    )
    guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("0.05"))
    gateway = _gateway_for_budget_pricing(responses, guard)

    await gateway.complete_structured(
        task="risk",
        fragments=[_fragment()],
        expected_schema=RiskOutput,
        budget_request=LLMBudgetRequest(
            case_id=_CASE_ID,
            worst_case_tokens=800,
            worst_case_usd_cost=Decimal("0.05"),
        ),
        routing_context=_routing(),
        trace_context=_trace(),
    )

    records = guard.usage_for_case(_CASE_ID)
    assert [(record.attempt, record.tokens, record.usd_cost) for record in records] == [
        ("schema_repair", 100, Decimal("0.000200")),
    ]
    assert responses.calls[0]["text_format"] is RiskOutput
    assert responses.calls[1]["text_format"] is RiskOutput


@pytest.mark.asyncio
async def test_gateway_releases_budget_when_client_fails_before_response() -> None:
    responses = SequenceResponses([RuntimeError("client_event_loop_closed")])
    guard = BudgetGuard(default_token_limit=1_000, default_usd_limit=Decimal("0.05"))
    gateway = _gateway_for_budget_pricing(responses, guard)

    with pytest.raises(RuntimeError, match="client_event_loop_closed"):
        await gateway.complete_structured(
            task="risk",
            fragments=[_fragment()],
            expected_schema=RiskOutput,
            budget_request=LLMBudgetRequest(
                case_id=_CASE_ID,
                worst_case_tokens=800,
                worst_case_usd_cost=Decimal("0.05"),
            ),
            routing_context=_routing(),
            trace_context=_trace(),
        )

    assert guard.usage_for_case(_CASE_ID) == ()
    assert guard.reserved_tokens_for_case(_CASE_ID) == 0


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


def _routing() -> LLMRoutingContext:
    return LLMRoutingContext(
        task_complexity="standard",
        latency_budget_ms=30_000,
        schema_validation_failed=False,
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


def _gateway_for_budget_pricing(
    responses: SequenceResponses,
    budget_guard: BudgetGuard,
    *,
    llm_call_recorder: RecordingLLMCalls | None = None,
) -> OpenAIGateway:
    return OpenAIGateway(
        responses_client=responses,
        egress_policy=DataEgressPolicy(),
        routing_policy=ModelRoutingPolicy(
            default_profile=ModelProfile(
                provider="openai",
                model="gpt-5.6-luna",
                role="startup_due_diligence",
            ),
            high_reasoning_profile=ModelProfile(
                provider="openai",
                model="gpt-5.6-luna",
                role="startup_due_diligence",
            ),
        ),
        budget_guard=budget_guard,
        audit_spool=RecordingAuditSpool(),
        usage_cost_calculator=lambda usage: (
            Decimal(usage.input_tokens) * Decimal("1.00")
            + Decimal(usage.output_tokens) * Decimal("6.00")
        )
        / Decimal(1_000_000),
        llm_call_recorder=llm_call_recorder,
    )

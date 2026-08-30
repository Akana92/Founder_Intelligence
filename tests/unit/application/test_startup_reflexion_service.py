from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from due_diligence_agent.application.services.startup_reflexion_service import (
    StartupArbiterService,
    StartupArbiterStatus,
    StartupCriticIssueCode,
    StartupCriticService,
)
from due_diligence_agent.domain.common import (
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchSchema,
    StartupResearchSource,
    StartupResearchSourceMode,
)
from due_diligence_agent.workflows.startup.ports import StartupReflexionWorkflowAdapter
from due_diligence_agent.workflows.startup.runtime import InMemoryStartupWorkflowRuntimeStore


_CASE_ID = UUID("10000000-0000-0000-0000-000000000001")
_FACT_ID = UUID("20000000-0000-0000-0000-000000000001")
_COUNTER_FACT_ID = UUID("20000000-0000-0000-0000-000000000002")
_UNSUPPORTED_FINDING_ID = UUID("30000000-0000-0000-0000-000000000001")
_COUNTER_FINDING_ID = UUID("30000000-0000-0000-0000-000000000002")
_METRIC_CONTRADICTION_ID = UUID("40000000-0000-0000-0000-000000000001")
_STALE_SOURCE_ID = UUID("50000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 12, tzinfo=UTC)
_RAW_SENTINEL = "founder-private-raw-critic-input"


def test_critic_detects_required_issue_classes_as_safe_deterministic_refs() -> None:
    critic = StartupCriticService()
    findings = (_unsupported_finding(), _counter_evidence_finding())
    contradiction = _metric_contradiction()
    stale_source = _stale_source()

    review = critic.review(
        case_id=_CASE_ID,
        round_number=1,
        findings=findings,
        contradictions=(contradiction,),
        market_sources=(stale_source,),
    )
    repeated = critic.review(
        case_id=_CASE_ID,
        round_number=1,
        findings=tuple(reversed(findings)),
        contradictions=(contradiction,),
        market_sources=(stale_source,),
    )

    assert [issue.code for issue in review.issues] == [
        StartupCriticIssueCode.UNSUPPORTED_CONCLUSION,
        StartupCriticIssueCode.COUNTER_EVIDENCE,
        StartupCriticIssueCode.METRIC_CONFLICT,
        StartupCriticIssueCode.STALE_SOURCE,
    ]
    assert review == repeated
    assert len({issue.issue_id for issue in review.issues}) == 4
    assert _RAW_SENTINEL not in repr(review)


def test_arbiter_accepts_a_corrected_synthesis_without_open_issues() -> None:
    review = StartupCriticService().review(
        case_id=_CASE_ID,
        round_number=2,
        findings=(_supported_finding(),),
        contradictions=(),
        market_sources=(),
    )
    repository = _ContradictionRepository()

    decision = StartupArbiterService(contradiction_repository=repository).decide(review)

    assert decision.status is StartupArbiterStatus.ACCEPTED
    assert decision.accepted_finding_ids == (_COUNTER_FINDING_ID,)
    assert decision.contradiction_ids == ()
    assert decision.new_contradiction_ids == ()
    assert decision.progress is False
    assert repository.items == []


def test_arbiter_persists_unresolved_critic_results_once_and_stops_after_round_two() -> None:
    critic = StartupCriticService()
    repository = _ContradictionRepository(items=[_metric_contradiction()])
    arbiter = StartupArbiterService(contradiction_repository=repository)
    first_review = critic.review(
        case_id=_CASE_ID,
        round_number=1,
        findings=(_unsupported_finding(), _counter_evidence_finding()),
        contradictions=(_metric_contradiction(),),
        market_sources=(_stale_source(),),
    )

    first = arbiter.decide(first_review)
    repeated = arbiter.decide(first_review)
    final = arbiter.decide(first_review.model_copy(update={"round_number": 2}))

    assert first.status is StartupArbiterStatus.REVISION_REQUIRED
    assert first.progress is True
    assert len(first.new_contradiction_ids) == 3
    assert repeated.status is StartupArbiterStatus.REVISION_REQUIRED
    assert repeated.progress is False
    assert repeated.contradiction_ids == first.contradiction_ids
    assert final.status is StartupArbiterStatus.UNRESOLVED
    assert final.progress is False
    assert final.contradiction_ids == first.contradiction_ids
    assert len(repository.items) == 4
    assert _RAW_SENTINEL not in repr(first)
    materialized = [
        item for item in repository.items if item.id != _METRIC_CONTRADICTION_ID
    ]
    assert _RAW_SENTINEL not in repr(materialized)


def test_reflexion_adapter_binds_selected_case_data_and_persists_safe_round_history() -> None:
    finding_repository = _FindingRepository(
        items=[_unsupported_finding(), _counter_evidence_finding()]
    )
    contradiction_repository = _ContradictionRepository(items=[_metric_contradiction()])
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(
        str(_CASE_ID),
        {
            "startup_market_research_artifact": {
                "schema_version": StartupResearchSchema.VERSION,
                "snapshot": _market_snapshot().model_dump(mode="json"),
            }
        },
    )
    adapter = StartupReflexionWorkflowAdapter(
        finding_repository=finding_repository,
        contradiction_repository=contradiction_repository,
        workflow_store=workflow_store,
    )

    result = adapter.review(
        case_id=str(_CASE_ID),
        round_number=1,
        finding_ids=[str(_UNSUPPORTED_FINDING_ID), str(_COUNTER_FINDING_ID)],
        contradiction_ids=[str(_METRIC_CONTRADICTION_ID)],
    )
    repeated = adapter.review(
        case_id=str(_CASE_ID),
        round_number=1,
        finding_ids=[str(_UNSUPPORTED_FINDING_ID), str(_COUNTER_FINDING_ID)],
        contradiction_ids=[str(_METRIC_CONTRADICTION_ID)],
    )
    runtime = workflow_store.load(str(_CASE_ID))

    assert result["arbiter_status"] == StartupArbiterStatus.REVISION_REQUIRED
    assert result["critic_issue_codes"] == [
        code.value
        for code in (
            StartupCriticIssueCode.UNSUPPORTED_CONCLUSION,
            StartupCriticIssueCode.COUNTER_EVIDENCE,
            StartupCriticIssueCode.METRIC_CONFLICT,
            StartupCriticIssueCode.STALE_SOURCE,
        )
    ]
    assert repeated["contradiction_ids"] == result["contradiction_ids"]
    assert repeated["progress"] is False
    assert len(runtime["startup_reflexion_history"]) == 1
    assert runtime["startup_reflexion_artifact"]["round_number"] == 1
    assert _RAW_SENTINEL not in repr(runtime["startup_reflexion_artifact"])


def test_reflexion_adapter_atomically_merges_restart_round_history() -> None:
    workflow_store = _AtomicUpdateOnlyWorkflowStore(
        {
            "startup_reflexion_artifact": {"round_number": 1},
            "startup_reflexion_history": [
                {
                    "schema_version": "startup_reflexion_roles@1",
                    "round_number": 1,
                    "critic": {"issue_count": 0, "issues": []},
                    "arbiter": {
                        "status": "accepted",
                        "issue_ids": [],
                        "accepted_finding_ids": [str(_COUNTER_FINDING_ID)],
                        "contradiction_ids": [],
                        "new_contradiction_ids": [],
                        "progress": False,
                    },
                }
            ],
        }
    )
    adapter = StartupReflexionWorkflowAdapter(
        finding_repository=_FindingRepository(items=[_supported_finding()]),
        contradiction_repository=_ContradictionRepository(),
        workflow_store=workflow_store,
    )

    result = adapter.review(
        case_id=str(_CASE_ID),
        round_number=2,
        finding_ids=[str(_COUNTER_FINDING_ID)],
        contradiction_ids=[],
    )

    assert result["arbiter_status"] == StartupArbiterStatus.ACCEPTED
    assert workflow_store.update_calls == 2
    assert [
        item["round_number"]
        for item in workflow_store.record["startup_reflexion_history"]
    ] == [1, 2]


class _FindingRepository:
    def __init__(self, *, items: list[Finding] | None = None) -> None:
        self.items = list(items or [])

    def list_for_case(self, case_id: UUID) -> list[Finding]:
        return [item for item in self.items if item.case_id == case_id]


class _ContradictionRepository:
    def __init__(self, *, items: list[Contradiction] | None = None) -> None:
        self.items = list(items or [])

    def add(self, contradiction: Contradiction) -> None:
        if any(item.id == contradiction.id for item in self.items):
            raise ValueError("contradiction_already_exists")
        self.items.append(contradiction)

    def list_for_case(self, case_id: UUID) -> list[Contradiction]:
        return [item for item in self.items if item.case_id == case_id]


class _AtomicUpdateOnlyWorkflowStore:
    def __init__(self, record: dict[str, object]) -> None:
        self.record = dict(record)
        self.update_calls = 0

    def load(self, case_id: str) -> dict[str, object]:
        del case_id
        return dict(self.record)

    def save(self, case_id: str, values: dict[str, object]) -> None:
        del case_id, values
        raise AssertionError("reflexion history must use atomic update")

    def update(
        self,
        case_id: str,
        mutator: Callable[[dict[str, object]], dict[str, object]],
    ) -> dict[str, object]:
        del case_id
        self.update_calls += 1
        values = mutator(dict(self.record))
        self.record.update(values)
        return dict(self.record)


def _unsupported_finding() -> Finding:
    return Finding(
        id=_UNSUPPORTED_FINDING_ID,
        case_id=_CASE_ID,
        category="financial",
        severity=FindingSeverity.HIGH,
        claim=_RAW_SENTINEL,
        evidence_fact_ids=(),
        calculation_ids=(),
        confidence=Decimal("0.82"),
        status=FindingStatus.VERIFIED,
        counter_evidence_fact_ids=(),
        author_node="financial_analysis",
        author_model="fixture-provider",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=_NOW,
    )


def _counter_evidence_finding() -> Finding:
    return Finding(
        id=_COUNTER_FINDING_ID,
        case_id=_CASE_ID,
        category="risk",
        severity=FindingSeverity.CRITICAL,
        claim=_RAW_SENTINEL,
        evidence_fact_ids=(_FACT_ID,),
        calculation_ids=(),
        confidence=Decimal("0.71"),
        status=FindingStatus.VERIFIED,
        counter_evidence_fact_ids=(_COUNTER_FACT_ID,),
        author_node="risk_analysis",
        author_model="fixture-provider",
        sensitivity=SensitivityClass.RESTRICTED,
        created_at=_NOW,
    )


def _supported_finding() -> Finding:
    return _counter_evidence_finding().model_copy(
        update={
            "status": FindingStatus.VERIFIED,
            "counter_evidence_fact_ids": (),
        }
    )


def _metric_contradiction() -> Contradiction:
    return Contradiction(
        id=_METRIC_CONTRADICTION_ID,
        case_id=_CASE_ID,
        conflict_type="source_fact_value_conflict",
        fact_ids=(_FACT_ID, _COUNTER_FACT_ID),
        finding_ids=(_COUNTER_FINDING_ID,),
        explanation=_RAW_SENTINEL,
        severity=FindingSeverity.HIGH,
        status=ContradictionStatus.OPEN,
        recommended_resolution="Review source references.",
        resolved_by_approval_id=None,
        sensitivity=SensitivityClass.RESTRICTED,
        detected_at=_NOW,
    )


def _stale_source() -> StartupResearchSource:
    return StartupResearchSource(
        source_id=_STALE_SOURCE_ID,
        source_mode=StartupResearchSourceMode.FROZEN,
        source_hash="sha256:" + "a" * 64,
        source_url="https://example.com/research",
        source_label=_RAW_SENTINEL,
        as_of=date(2024, 1, 1),
        retrieved_at=_NOW,
        query=_RAW_SENTINEL,
        provenance="fixture",
        stale=True,
    )


def _market_snapshot() -> StartupMarketResearchSnapshot:
    return StartupMarketResearchSnapshot.build(
        case_id=_CASE_ID,
        research_id=uuid4(),
        as_of=_NOW,
        source_mode=StartupResearchSourceMode.FROZEN,
        competitors=(),
        sources=(_stale_source(),),
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=(),
        data_revision=1,
    )

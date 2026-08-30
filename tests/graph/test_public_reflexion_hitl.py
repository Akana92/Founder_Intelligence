from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from due_diligence_agent.adapters.local_storage.repositories import (
    LocalApprovalRepository,
    LocalArtifactRepository,
    LocalCalculationRepository,
    LocalContradictionDecisionRepository,
    LocalContradictionRepository,
    LocalEvidenceRepository,
    LocalFindingRepository,
    LocalReportRepository,
    LocalReviewRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.common import (
    ArtifactParsingStatus,
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.approvals.models import ContradictionDecision
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.findings.risk import RiskFinding
from due_diligence_agent.domain.reports.models import ReproducibilityManifest, ReportSnapshot
from due_diligence_agent.workflows.public_company.graph import build_public_graph
from due_diligence_agent.workflows.public_company.nodes.approvals import (
    PublicReviewService,
    SnapshotFreezeService,
    prepare_report_freeze,
)
from due_diligence_agent.workflows.public_company.nodes.reflexion import reflexion
from due_diligence_agent.workflows.public_company.plan import (
    PUBLIC_NODE_REGISTRY,
    validate_public_plan,
)
from due_diligence_agent.workflows.public_company.state import PublicCaseState
from due_diligence_agent.workflows.shared.plan import AnalysisPlan, PlanStep
from due_diligence_agent.workflows.shared.reflexion import (
    ReflexionDecision,
    ReflexionReview,
    should_continue_reflexion,
)

sys.path.insert(0, str(Path(__file__).parent))
from test_public_collection_graph import (  # noqa: E402
    CALCULATION_ID as COLLECTION_CALCULATION_ID,
    _deps as collection_graph_deps,
    _local_deps as local_collection_graph_deps,
)


AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
CASE_ID = UUID("11111111-1111-4111-8111-111111111111")
ARTIFACT_ID = UUID("22222222-2222-4222-8222-222222222222")
FACT_ID = UUID("33333333-3333-4333-8333-333333333333")
CALCULATION_ID = UUID("44444444-4444-4444-8444-444444444444")
FINDING_ID = UUID("55555555-5555-4555-8555-555555555555")
CONTRADICTION_ID = UUID("66666666-6666-4666-8666-666666666666")
REPORT_SNAPSHOT_ID = UUID("77777777-7777-4777-8777-777777777777")


def test_reflexion_stops_after_two_rounds_even_when_critic_requests_more() -> None:
    state = _state(reflexion_round_count=2, new_evidence_ids=[str(uuid4())])

    assert should_continue_reflexion(state, max_rounds=2) is False


def test_reflexion_continues_only_when_below_limit_and_progress_exists() -> None:
    assert should_continue_reflexion(
        _state(reflexion_round_count=1, updated_finding_ids=[str(FINDING_ID)]), max_rounds=2
    )
    assert not should_continue_reflexion(_state(reflexion_round_count=1), max_rounds=2)


def test_risk_finding_proposal_converts_to_shared_immutable_finding() -> None:
    proposal = RiskFinding(
        case_id=CASE_ID,
        category="liquidity",
        probability=Decimal("0.70"),
        impact=Decimal("0.80"),
        severity=FindingSeverity.HIGH,
        claim="Liquidity risk is material.",
        evidence_fact_ids=(FACT_ID,),
        calculation_ids=(CALCULATION_ID,),
        counter_evidence_fact_ids=(),
        confidence=Decimal("0.82"),
        status=FindingStatus.REQUIRES_REVIEW,
        author_node="risk_analysis",
        author_model="deterministic-test-critic",
        sensitivity=SensitivityClass.PUBLIC,
        created_at=AS_OF,
    )

    finding = proposal.to_finding(finding_id=FINDING_ID)

    assert isinstance(finding, Finding)
    assert finding.id == FINDING_ID
    assert finding.category == "risk:liquidity"
    assert finding.evidence_fact_ids == (FACT_ID,)
    assert finding.calculation_ids == (CALCULATION_ID,)
    assert finding.status is FindingStatus.REQUIRES_REVIEW
    assert finding.version == 1


def test_excluding_artifact_invalidates_complete_dependency_closure_and_snapshot() -> None:
    repositories = SeededReviewRepositories()
    service = PublicReviewService(repositories, clock=lambda: AS_OF)

    result = service.exclude_artifact(ARTIFACT_ID, actor="reviewer")

    assert result.action == "exclude_artifact"
    assert result.data_revision == 2
    assert result.invalidated_artifact_ids == (ARTIFACT_ID,)
    assert result.invalidated_fact_ids == (FACT_ID,)
    assert result.invalidated_calculation_ids == (CALCULATION_ID,)
    assert result.invalidated_finding_ids == (FINDING_ID,)
    assert result.invalidated_contradiction_ids == (CONTRADICTION_ID,)
    assert result.affected_report_snapshot_ids == (REPORT_SNAPSHOT_ID,)
    assert result.report_snapshot_invalidated is True
    assert repositories.audit_events[-1]["action"] == "exclude_artifact"


def test_gate3_unresolved_critical_contradictions_are_forced_into_executive_summary() -> None:
    repositories = SeededReviewRepositories()
    service = PublicReviewService(repositories, clock=lambda: AS_OF)

    result = service.leave_unresolved(CONTRADICTION_ID, actor="reviewer")

    assert result.status is ContradictionStatus.UNRESOLVED
    assert result.forced_executive_summary_contradiction_ids == (CONTRADICTION_ID,)
    assert repositories.audit_events[-1]["gate"] == "gate_3"


def test_gate3_review_actions_record_state_and_revision_without_mutating_facts() -> None:
    repositories = SeededReviewRepositories()
    service = PublicReviewService(repositories, clock=lambda: AS_OF)
    original_fact = repositories.facts[0]

    accepted = service.accept_source(CONTRADICTION_ID, actor="reviewer", comment="10-K wins")
    requested = service.request_evidence(CONTRADICTION_ID, actor="reviewer")
    reclassified = service.reclassify(
        CONTRADICTION_ID, actor="reviewer", severity=FindingSeverity.MEDIUM
    )

    assert accepted.status is ContradictionStatus.ACCEPTED_SOURCE
    assert requested.status is ContradictionStatus.AWAITING_EVIDENCE
    assert requested.case_status == "awaiting_evidence"
    assert reclassified.status is ContradictionStatus.RECLASSIFIED
    assert reclassified.severity is FindingSeverity.MEDIUM
    assert repositories.facts[0] == original_fact
    assert [event["action"] for event in repositories.audit_events] == [
        "accept_source",
        "request_evidence",
        "reclassify",
    ]


def test_rejected_freeze_preserves_draft_refs_and_never_allows_final_pdf() -> None:
    repositories = SeededReviewRepositories()
    service = SnapshotFreezeService(repositories, clock=lambda: AS_OF)

    outcome = service.apply_freeze_decision(
        REPORT_SNAPSHOT_ID, approved=False, actor="reviewer", data_revision=1
    )

    assert outcome.approved is False
    assert outcome.final_pdf_allowed is False
    assert outcome.json_artifact_ref == "artifact://draft.json"
    assert outcome.html_artifact_ref == "artifact://draft.html"
    assert outcome.pdf_artifact_ref is None
    assert repositories.approvals[-1].action == "rejected"


def test_freeze_approval_is_bound_to_current_data_revision_and_does_not_render_pdf() -> None:
    repositories = SeededReviewRepositories()
    service = SnapshotFreezeService(repositories, clock=lambda: AS_OF)

    outcome = service.apply_freeze_decision(
        REPORT_SNAPSHOT_ID, approved=True, actor="reviewer", data_revision=1
    )

    assert outcome.approved is True
    assert outcome.final_pdf_allowed is True
    assert outcome.approval is not None
    assert outcome.approval.data_revision == 1
    assert outcome.pdf_artifact_ref is None


def test_stale_freeze_decision_is_rejected_when_data_revision_changed() -> None:
    repositories = SeededReviewRepositories()
    service = SnapshotFreezeService(repositories, clock=lambda: AS_OF)

    outcome = service.apply_freeze_decision(
        REPORT_SNAPSHOT_ID, approved=True, actor="reviewer", data_revision=0
    )

    assert outcome.approved is False
    assert outcome.final_pdf_allowed is False
    assert outcome.reason == "stale_data_revision"
    assert repositories.approvals == []


def test_public_plan_registry_accepts_task12_nodes() -> None:
    plan = AnalysisPlan(
        objectives=["analysis", "review"],
        token_budget=12000,
        max_reflexion_rounds=2,
        steps=[
            PlanStep(
                task_id="sec", node_name="collect_sec", required_output_schema="SecCollectionResult"
            ),
            PlanStep(
                task_id="financial",
                node_name="financial_analysis",
                depends_on=["sec"],
                required_output_schema="FindingResult",
            ),
            PlanStep(
                task_id="risk",
                node_name="risk_analysis",
                depends_on=["financial"],
                required_output_schema="FindingResult",
            ),
            PlanStep(
                task_id="market",
                node_name="market_analysis",
                depends_on=["financial"],
                required_output_schema="FindingResult",
            ),
            PlanStep(
                task_id="reflexion",
                node_name="reflexion",
                depends_on=["risk", "market"],
                required_output_schema="ReflexionDecision",
            ),
            PlanStep(
                task_id="synthesize",
                node_name="synthesize",
                depends_on=["reflexion"],
                required_output_schema="SynthesisReadiness",
            ),
        ],
    )

    assert PUBLIC_NODE_REGISTRY["reflexion"] == "ReflexionDecision"
    assert validate_public_plan(plan) == plan


def test_public_graph_pauses_for_gate3_then_gate4_without_rendering_pdf() -> None:
    deps = GraphDependencies()
    graph = build_public_graph(deps, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": str(CASE_ID)}}

    graph.invoke(
        {"ticker": "AAPL", "case_id": str(CASE_ID), "as_of": AS_OF.isoformat()}, config=config
    )
    gate3 = graph.invoke(Command(resume={"approved": True}), config=config)
    assert gate3["status"] == "awaiting_review"
    assert gate3["forced_executive_summary_contradiction_ids"] == [str(CONTRADICTION_ID)]

    gate4 = graph.invoke(
        Command(resume={"gate": "gate_3", "action": "leave_unresolved"}), config=config
    )
    assert gate4["status"] == "awaiting_report_freeze"
    assert gate4["report_snapshot_id"] == str(REPORT_SNAPSHOT_ID)

    rejected = graph.invoke(
        Command(
            resume={"gate": "gate_4", "approved": False, "snapshot_id": str(REPORT_SNAPSHOT_ID)}
        ),
        config=config,
    )
    assert rejected["status"] == "draft_rejected"
    assert rejected["final_pdf_allowed"] is False
    assert rejected["draft_json_artifact_ref"] == "artifact://draft.json"
    assert rejected["draft_html_artifact_ref"] == "artifact://draft.html"
    assert "pdf_artifact_ref" not in rejected


def test_local_graph_persists_analysis_findings_with_exact_refs(tmp_path: Path) -> None:
    db_path = tmp_path / "task12.sqlite3"
    deps = local_collection_graph_deps(db_path=db_path, object_path=tmp_path / "objects")
    db = deps.db
    assert db is not None
    calculation_repository = LocalCalculationRepository(db)
    finding_repository = LocalFindingRepository(db)
    contradiction_repository = LocalContradictionRepository(db)
    report_repository = LocalReportRepository(db)
    deps.metric_service = PersistingMetricService(calculation_repository)
    deps.calculation_repository = calculation_repository
    deps.finding_repository = finding_repository
    deps.contradiction_repository = contradiction_repository
    deps.report_repository = report_repository
    deps.risk_analyzer = OfflineRiskAnalyzer()
    deps.reflexion_reviewer = NoProgressReviewer()
    review_repository = LocalReviewRepository(
        artifact_repository=LocalArtifactRepository(db),
        evidence_repository=LocalEvidenceRepository(db),
        calculation_repository=calculation_repository,
        finding_repository=finding_repository,
        contradiction_repository=contradiction_repository,
        report_repository=report_repository,
        approval_repository=LocalApprovalRepository(db),
        decision_repository=LocalContradictionDecisionRepository(db),
    )
    deps.review_service = PublicReviewService(review_repository, clock=lambda: AS_OF)
    deps.freeze_service = SnapshotFreezeService(review_repository, clock=lambda: AS_OF)
    report_repository.add_snapshot(_snapshot())
    graph = build_public_graph(deps, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": str(CASE_ID)}}

    graph.invoke({"ticker": "AAPL", "case_id": str(CASE_ID), "as_of": AS_OF.isoformat()}, config)
    result = graph.invoke(Command(resume={"approved": True}), config)

    findings = {finding.category: finding for finding in finding_repository.list_for_case(CASE_ID)}
    assert result["status"] == "awaiting_report_freeze"
    assert findings["financial:gross_margin"].calculation_ids == (COLLECTION_CALCULATION_ID,)
    assert findings["financial:gross_margin"].evidence_fact_ids == (
        UUID("33333333-3333-4333-8333-333333333333"),
        UUID("33333333-3333-4333-8333-333333333334"),
    )
    assert findings["risk:liquidity"].calculation_ids == (COLLECTION_CALCULATION_ID,)
    assert findings["market:secondary_source"].evidence_fact_ids == (
        UUID("12c3f39b-6759-5742-ac7a-a2f6571f2fac"),
        UUID("bfaa50d9-eb35-5126-99cc-3a744f356014"),
    )
    assert "secondary source" in findings["market:secondary_source"].claim.lower()


def test_gate3_pause_actions_do_not_reach_synthesis_or_freeze() -> None:
    for action in ("request_evidence", "exclude_artifact"):
        deps = GraphDependencies()
        graph = build_public_graph(deps, checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": f"{CASE_ID}-{action}"}}

        graph.invoke(
            {"ticker": "AAPL", "case_id": str(CASE_ID), "as_of": AS_OF.isoformat()},
            config=config,
        )
        graph.invoke(Command(resume={"approved": True}), config=config)
        decision = {"gate": "gate_3", "action": action}
        if action == "exclude_artifact":
            decision["artifact_id"] = str(ARTIFACT_ID)
        result = graph.invoke(Command(resume=decision), config=config)

        assert result["status"] == "awaiting_evidence"
        assert "synthesize" not in deps.audit.events
        assert "prepare_report_freeze" not in deps.audit.events
        assert "gate_4" not in deps.audit.events


def test_local_review_service_persists_decision_and_closure_immutably(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "review.sqlite3")
    repositories = _seed_local_review_repositories(db)
    original_fact = repositories.evidence_repository.list_for_case(CASE_ID)[0]
    original_calculation = repositories.calculation_repository.list_for_case(CASE_ID)[0]
    original_snapshot = repositories.report_repository.get_snapshot(REPORT_SNAPSHOT_ID)
    service = PublicReviewService(repositories.review_repository, clock=lambda: AS_OF)

    outcome = service.exclude_artifact(ARTIFACT_ID, actor="reviewer")

    persisted = repositories.decision_repository.list_for_case(CASE_ID)
    assert outcome.invalidated_fact_ids == (FACT_ID,)
    assert outcome.invalidated_calculation_ids == (CALCULATION_ID,)
    assert outcome.invalidated_finding_ids == (FINDING_ID,)
    assert outcome.affected_report_snapshot_ids == (REPORT_SNAPSHOT_ID,)
    assert persisted == [
        ContradictionDecision(
            id=persisted[0].id,
            case_id=CASE_ID,
            contradiction_id=CONTRADICTION_ID,
            approval_id=outcome.approval.id,
            action="exclude_artifact",
            status=ContradictionStatus.AWAITING_EVIDENCE,
            data_revision=outcome.data_revision,
            invalidated_artifact_ids=(ARTIFACT_ID,),
            invalidated_fact_ids=(FACT_ID,),
            invalidated_calculation_ids=(CALCULATION_ID,),
            invalidated_finding_ids=(FINDING_ID,),
            invalidated_contradiction_ids=(CONTRADICTION_ID,),
            affected_report_snapshot_ids=(REPORT_SNAPSHOT_ID,),
            report_snapshot_invalidated=True,
            forced_executive_summary_contradiction_ids=(),
            decided_at=AS_OF,
        )
    ]
    assert repositories.evidence_repository.list_for_case(CASE_ID)[0] == original_fact
    assert repositories.calculation_repository.list_for_case(CASE_ID)[0] == original_calculation
    assert repositories.report_repository.get_snapshot(REPORT_SNAPSHOT_ID) == original_snapshot


def test_repeated_same_gate3_action_persists_one_decision_per_revision(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "repeat-decisions.sqlite3")
    repositories = _seed_local_review_repositories(db)
    service = PublicReviewService(repositories.review_repository, clock=lambda: AS_OF)

    first = service.exclude_artifact(ARTIFACT_ID, actor="reviewer")
    second = service.exclude_artifact(ARTIFACT_ID, actor="reviewer")

    approvals = LocalApprovalRepository(db).list_for_case(CASE_ID)
    decisions = repositories.decision_repository.list_for_case(CASE_ID)
    assert [decision.data_revision for decision in decisions] == [
        first.data_revision,
        second.data_revision,
    ]
    assert [decision.approval_id for decision in decisions] == [
        approval.id for approval in approvals
    ]
    assert [decision.action for decision in decisions] == ["exclude_artifact", "exclude_artifact"]
    assert len({decision.id for decision in decisions}) == 2


def test_exact_same_contradiction_decision_replay_is_idempotent(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "replay-decision.sqlite3")
    repositories = _seed_local_review_repositories(db)
    decision = _decision_for_repository(repositories, data_revision=2)

    repositories.decision_repository.add(decision)
    repositories.decision_repository.add(decision)

    assert repositories.decision_repository.list_for_case(CASE_ID) == [decision]


def test_same_contradiction_decision_id_with_conflicting_payload_raises(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "conflicting-decision.sqlite3")
    repositories = _seed_local_review_repositories(db)
    decision = _decision_for_repository(repositories, data_revision=2)
    conflicting = decision.model_copy(update={"data_revision": 3})

    repositories.decision_repository.add(decision)

    try:
        repositories.decision_repository.add(conflicting)
    except ValueError as exc:
        assert str(exc) == "contradiction_decision_conflict"
    else:
        raise AssertionError("conflicting contradiction decision replay was accepted")


def test_reclassify_decision_round_trips_target_severity(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "reclassify-decision.sqlite3")
    repositories = _seed_local_review_repositories(db)
    service = PublicReviewService(repositories.review_repository, clock=lambda: AS_OF)

    service.reclassify(CONTRADICTION_ID, actor="reviewer", severity=FindingSeverity.MEDIUM)

    decisions = repositories.decision_repository.list_for_case(CASE_ID)
    assert decisions[0].action == "reclassify"
    assert decisions[0].target_severity is FindingSeverity.MEDIUM


def test_reflexion_reviewer_progress_no_progress_and_max_two_are_enforced() -> None:
    finding_repository = ListRepository([_finding()])
    contradiction_repository = ListRepository([_contradiction()])
    progress_reviewer = ReplacementReviewer()
    first = reflexion(
        _state(reflexion_round_count=0),
        contradiction_repository=contradiction_repository,
        finding_repository=finding_repository,
        reviewer=progress_reviewer,
        audit=None,
    )
    second = reflexion(
        {**_state(reflexion_round_count=1), **first},
        contradiction_repository=contradiction_repository,
        finding_repository=finding_repository,
        reviewer=NoProgressReviewer(),
        audit=None,
    )
    third = reflexion(
        _state(reflexion_round_count=1),
        contradiction_repository=contradiction_repository,
        finding_repository=finding_repository,
        reviewer=progress_reviewer,
        audit=None,
    )

    assert should_continue_reflexion({**_state(reflexion_round_count=0), **first}, max_rounds=2)
    assert first["updated_finding_ids"] == [str(REPLACEMENT_FINDING_ID)]
    assert any(
        item.id == REPLACEMENT_FINDING_ID and item.version == 2
        for item in finding_repository._items
    )
    assert second["updated_finding_ids"] == []
    assert not should_continue_reflexion(
        {**_state(reflexion_round_count=1), **second}, max_rounds=2
    )
    assert third["reflexion_round_count"] == 2
    assert not should_continue_reflexion({**_state(reflexion_round_count=1), **third}, max_rounds=2)


def test_prepare_report_freeze_uses_real_current_draft_query(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "draft.sqlite3")
    repositories = _seed_local_review_repositories(db)
    update = prepare_report_freeze(
        _state(reflexion_round_count=0),
        report_repository=repositories.report_repository,
        audit=None,
    )

    assert update["status"] == "awaiting_report_freeze"
    assert update["report_snapshot_id"] == str(REPORT_SNAPSHOT_ID)


def _state(
    *,
    reflexion_round_count: int,
    new_evidence_ids: list[str] | None = None,
    updated_finding_ids: list[str] | None = None,
) -> PublicCaseState:
    return {
        "case_id": str(CASE_ID),
        "ticker": "AAPL",
        "as_of": AS_OF.isoformat(),
        "status": "running",
        "reflexion_round_count": reflexion_round_count,
        "new_evidence_ids": new_evidence_ids or [],
        "updated_finding_ids": updated_finding_ids or [],
    }


@dataclass
class SeededReviewRepositories:
    current_data_revision: int = 1

    def __post_init__(self) -> None:
        self.artifacts = [_artifact()]
        self.facts = [_fact()]
        self.calculations = [_calculation()]
        self.findings = [_finding()]
        self.contradictions = [_contradiction()]
        self.snapshots = [_snapshot()]
        self.approvals = []
        self.audit_events = []

    def list_facts_for_artifact(self, artifact_id: UUID) -> list[EvidenceFact]:
        return [fact for fact in self.facts if fact.artifact_id == artifact_id]

    def list_calculations_for_facts(self, fact_ids: set[UUID]) -> list[Calculation]:
        return [
            calculation
            for calculation in self.calculations
            if set(calculation.input_fact_ids) & fact_ids
        ]

    def list_findings_for_dependencies(
        self, fact_ids: set[UUID], calculation_ids: set[UUID]
    ) -> list[Finding]:
        return [
            finding
            for finding in self.findings
            if set(finding.evidence_fact_ids) & fact_ids
            or set(finding.calculation_ids) & calculation_ids
            or set(finding.counter_evidence_fact_ids) & fact_ids
        ]

    def list_contradictions_for_dependencies(
        self, fact_ids: set[UUID], finding_ids: set[UUID]
    ) -> list[Contradiction]:
        return [
            contradiction
            for contradiction in self.contradictions
            if set(contradiction.fact_ids) & fact_ids
            or set(contradiction.finding_ids) & finding_ids
        ]

    def list_report_snapshots_for_case(self, case_id: UUID) -> list[ReportSnapshot]:
        return [snapshot for snapshot in self.snapshots if snapshot.case_id == case_id]

    def get_snapshot(self, snapshot_id: UUID) -> ReportSnapshot:
        for snapshot in self.snapshots:
            if snapshot.id == snapshot_id:
                return snapshot
        raise KeyError(snapshot_id)

    def add_approval(self, approval: object) -> None:
        self.approvals.append(approval)

    def record_audit(self, event: dict[str, object]) -> None:
        self.audit_events.append(event)


@dataclass
class GraphDependencies:
    def __post_init__(self) -> None:
        base = collection_graph_deps()
        self.sec = base.sec
        self.market = base.market
        self.news = base.news
        self.retrieval = base.retrieval
        self.metric_service = base.metric_service
        self.artifact_repository = base.artifact_repository
        self.evidence_repository = base.evidence_repository
        self.artifact_store = base.artifact_store
        self.guard = base.guard
        self.audit = base.audit
        self.async_sleeper = base.async_sleeper
        self.sync_sleeper = base.sync_sleeper
        self.finding_repository = ListRepository([_finding()])
        self.contradiction_repository = ListRepository([_contradiction()])
        self.report_repository = ReportRepository(_snapshot())
        self.review_service = PublicReviewService(SeededReviewRepositories(), clock=lambda: AS_OF)
        self.freeze_service = SnapshotFreezeService(SeededReviewRepositories(), clock=lambda: AS_OF)


class ListRepository:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def list_for_case(self, case_id: UUID) -> list[object]:
        return self._items

    def add(self, item: object) -> None:
        if item not in self._items:
            self._items.append(item)


class ReportRepository:
    def __init__(self, snapshot: ReportSnapshot) -> None:
        self.snapshot = snapshot

    def get_snapshot(self, snapshot_id: UUID) -> ReportSnapshot:
        if snapshot_id != self.snapshot.id:
            raise KeyError(snapshot_id)
        return self.snapshot

    def get_current_draft(self, case_id: UUID) -> ReportSnapshot | None:
        return self.snapshot if self.snapshot.case_id == case_id else None


def _artifact() -> Artifact:
    return Artifact(
        id=ARTIFACT_ID,
        case_id=CASE_ID,
        content_hash="a" * 64,
        mime_type="text/html",
        source="sec",
        source_url="https://example.test/10k",
        retrieved_at=AS_OF,
        published_at=AS_OF,
        source_snapshot_hash="b" * 64,
        storage_ref="artifact://10k",
        parsing_status=ArtifactParsingStatus.PARSED,
        sensitivity=SensitivityClass.PUBLIC,
    )


def _fact() -> EvidenceFact:
    return EvidenceFact(
        id=FACT_ID,
        artifact_id=ARTIFACT_ID,
        name="revenue",
        value=Decimal("100"),
        value_type="decimal",
        unit="USD",
        period="2026",
        locator=SourceLocator(kind="sec_fact", value="Revenue", artifact_id=ARTIFACT_ID),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.95"),
        source_priority=1,
        extraction_method="fixture",
        supporting_text_hash="c" * 64,
        retrieved_at=AS_OF,
    )


def _calculation() -> Calculation:
    return Calculation(
        id=CALCULATION_ID,
        case_id=CASE_ID,
        metric_name="gross_margin",
        formula_version="gross_margin@1",
        input_fact_ids=(FACT_ID,),
        value=Decimal("0.40"),
        unit="ratio",
        period="2026",
        calculated_at=AS_OF,
        sensitivity=SensitivityClass.PUBLIC,
    )


def _finding() -> Finding:
    return Finding(
        id=FINDING_ID,
        case_id=CASE_ID,
        category="risk:liquidity",
        severity=FindingSeverity.HIGH,
        claim="Liquidity risk is material.",
        evidence_fact_ids=(FACT_ID,),
        calculation_ids=(CALCULATION_ID,),
        confidence=Decimal("0.82"),
        status=FindingStatus.REQUIRES_REVIEW,
        author_node="risk_analysis",
        author_model="deterministic-test-critic",
        sensitivity=SensitivityClass.PUBLIC,
        created_at=AS_OF,
    )


def _contradiction() -> Contradiction:
    return Contradiction(
        id=CONTRADICTION_ID,
        case_id=CASE_ID,
        conflict_type="metric_mismatch",
        fact_ids=(FACT_ID,),
        finding_ids=(FINDING_ID,),
        explanation="ARR and revenue claims disagree.",
        severity=FindingSeverity.CRITICAL,
        status=ContradictionStatus.OPEN,
        recommended_resolution="review",
        sensitivity=SensitivityClass.PUBLIC,
        detected_at=AS_OF,
    )


def _snapshot() -> ReportSnapshot:
    return ReportSnapshot(
        id=REPORT_SNAPSHOT_ID,
        case_id=CASE_ID,
        report_hash="d" * 64,
        case_snapshot_hash="e" * 64,
        source_hashes={"sec": "f" * 64},
        as_of=AS_OF,
        graph_version="public-company-local@1",
        prompt_versions={"risk": "risk@1"},
        formula_versions={"gross_margin": "gross_margin@1"},
        model_versions={"critic": "deterministic-test-critic"},
        trace_ids=("trace-1",),
        json_artifact_ref="artifact://draft.json",
        html_artifact_ref="artifact://draft.html",
        pdf_artifact_ref=None,
        content_hashes={"json": "1" * 64, "html": "2" * 64},
        reproducibility=ReproducibilityManifest(
            code_commit="ddef8ba6b6ba76ed981aed8fd47d9b0da586657d",
            build_id="test",
            dependency_lock_hash="3" * 64,
            python_version="3.13",
            package_versions={"due_diligence_agent": "0"},
            provider_model_id="none",
            model_alias_snapshot="offline",
            reasoning_parameters={},
            adapter_versions={},
            parser_versions={},
            embedding_model_version=None,
            index_version=None,
            redaction_policy_version="public-company-local@1",
            locale="en-US",
            timezone="UTC",
            fx_source=None,
            deterministic_seeds={"test": 1},
            configuration_hash="4" * 64,
        ),
        sensitivity=SensitivityClass.PUBLIC,
        created_at=AS_OF,
    )


def _decision_for_repository(
    repositories: LocalReviewRepositories, *, data_revision: int
) -> ContradictionDecision:
    approval = _approval(data_revision=data_revision)
    LocalApprovalRepository(repositories.decision_repository._db).add(approval)
    return ContradictionDecision(
        id=UUID("99999999-9999-4999-8999-999999999999"),
        case_id=CASE_ID,
        contradiction_id=CONTRADICTION_ID,
        approval_id=approval.id,
        action="accept_source",
        status=ContradictionStatus.ACCEPTED_SOURCE,
        data_revision=data_revision,
        decided_at=AS_OF,
    )


def _approval(*, data_revision: int) -> object:
    from due_diligence_agent.domain.approvals.models import Approval

    return Approval(
        id=UUID(f"aaaaaaaa-aaaa-4aaa-8aaa-{data_revision:012d}"),
        case_id=CASE_ID,
        gate="gate_3",
        action="accept_source",
        actor="reviewer",
        comment=None,
        decided_at=AS_OF,
        data_revision=data_revision,
    )


REPLACEMENT_FINDING_ID = UUID("88888888-8888-4888-8888-888888888888")


class OfflineRiskAnalyzer:
    def propose(
        self, state: PublicCaseState, facts: list[EvidenceFact], calculations: list[Calculation]
    ) -> list[RiskFinding]:
        return [
            RiskFinding(
                case_id=CASE_ID,
                category="liquidity",
                probability=Decimal("0.70"),
                impact=Decimal("0.80"),
                severity=FindingSeverity.HIGH,
                claim="Liquidity risk is material.",
                evidence_fact_ids=(facts[0].id,),
                calculation_ids=(calculations[0].id,),
                confidence=Decimal("0.82"),
                status=FindingStatus.REQUIRES_REVIEW,
                author_model="offline-risk-test",
                sensitivity=SensitivityClass.PUBLIC,
                created_at=AS_OF,
            )
        ]


class NoProgressReviewer:
    def review(
        self,
        state: PublicCaseState,
        findings: list[Finding],
        contradictions: list[Contradiction],
    ) -> ReflexionReview:
        return ReflexionReview(
            decision=ReflexionDecision(continue_loop=False, reason="no_progress")
        )


class ReplacementReviewer:
    def review(
        self,
        state: PublicCaseState,
        findings: list[Finding],
        contradictions: list[Contradiction],
    ) -> ReflexionReview:
        return ReflexionReview(
            decision=ReflexionDecision(
                continue_loop=True,
                reason="new_counter_evidence",
                updated_finding_ids=[str(REPLACEMENT_FINDING_ID)],
            ),
            replacement_findings=[
                _finding().model_copy(
                    update={
                        "id": REPLACEMENT_FINDING_ID,
                        "status": FindingStatus.REQUIRES_REVIEW,
                        "version": 2,
                    }
                )
            ],
        )


class PersistingMetricService:
    def __init__(self, calculation_repository: LocalCalculationRepository) -> None:
        self.calls = 0
        self._calculation_repository = calculation_repository

    def calculate(
        self,
        case_id: UUID,
        metric_name: str,
        *,
        evidence_fact_ids: list[UUID],
        as_of: datetime | None = None,
    ) -> object:
        from due_diligence_agent.domain.metrics import MetricCalculationResult, MetricStatus

        self.calls += 1
        financial_fact_ids = [
            UUID("33333333-3333-4333-8333-333333333333"),
            UUID("33333333-3333-4333-8333-333333333334"),
        ]
        input_fact_ids = [fact_id for fact_id in financial_fact_ids if fact_id in evidence_fact_ids]
        calculation = Calculation(
            id=COLLECTION_CALCULATION_ID,
            case_id=case_id,
            metric_name=metric_name,
            formula_version="gross_margin@1",
            input_fact_ids=tuple(input_fact_ids),
            value=Decimal("0.400000"),
            unit="ratio",
            period="2025",
            calculated_at=as_of or AS_OF,
            sensitivity=SensitivityClass.PUBLIC,
        )
        try:
            self._calculation_repository.add(calculation)
        except ValueError as exc:
            if str(exc) != "calculation_already_exists":
                raise
        return MetricCalculationResult(
            status=MetricStatus.CALCULATED,
            metric_name=metric_name,
            formula_version=calculation.formula_version,
            value=calculation.value,
            display_value="40.0000%",
            unit=calculation.unit,
            period=calculation.period,
            input_evidence_ids=calculation.input_fact_ids,
            calculation_id=calculation.id,
        )


@dataclass
class LocalReviewRepositories:
    evidence_repository: LocalEvidenceRepository
    calculation_repository: LocalCalculationRepository
    finding_repository: LocalFindingRepository
    contradiction_repository: LocalContradictionRepository
    report_repository: LocalReportRepository
    decision_repository: LocalContradictionDecisionRepository
    review_repository: LocalReviewRepository


def _seed_local_review_repositories(db: SQLiteDatabase) -> LocalReviewRepositories:
    from due_diligence_agent.adapters.local_storage.repositories import LocalCaseRepository
    from test_public_collection_graph import _case

    try:
        LocalCaseRepository(db).add(_case())
    except ValueError as exc:
        if str(exc) != "case_already_exists":
            raise
    artifact_repository = LocalArtifactRepository(db)
    evidence_repository = LocalEvidenceRepository(db)
    calculation_repository = LocalCalculationRepository(db)
    finding_repository = LocalFindingRepository(db)
    contradiction_repository = LocalContradictionRepository(db)
    report_repository = LocalReportRepository(db)
    approval_repository = LocalApprovalRepository(db)
    decision_repository = LocalContradictionDecisionRepository(db)
    for repo, item, duplicate in (
        (artifact_repository, _artifact(), "artifact_already_exists"),
        (evidence_repository, _fact(), "evidence_fact_already_exists"),
        (calculation_repository, _calculation(), "calculation_already_exists"),
        (finding_repository, _finding(), "finding_already_exists"),
        (contradiction_repository, _contradiction(), "contradiction_already_exists"),
    ):
        try:
            repo.add(item)
        except ValueError as exc:
            if str(exc) != duplicate:
                raise
    report_repository.add_snapshot(_snapshot())
    review_repository = LocalReviewRepository(
        artifact_repository=artifact_repository,
        evidence_repository=evidence_repository,
        calculation_repository=calculation_repository,
        finding_repository=finding_repository,
        contradiction_repository=contradiction_repository,
        report_repository=report_repository,
        approval_repository=approval_repository,
        decision_repository=decision_repository,
    )
    return LocalReviewRepositories(
        evidence_repository=evidence_repository,
        calculation_repository=calculation_repository,
        finding_repository=finding_repository,
        contradiction_repository=contradiction_repository,
        report_repository=report_repository,
        decision_repository=decision_repository,
        review_repository=review_repository,
    )

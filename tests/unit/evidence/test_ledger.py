from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.application.policies.source_priority import (
    SourcePriority,
    SourcePriorityPolicy,
)
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.common import FindingSeverity, FindingStatus, SensitivityClass
from due_diligence_agent.domain.evidence.ledger import EvidenceLedger
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction, Finding


def test_add_fact_preserves_conflicting_primary_facts_and_links_contradiction_fact_ids():
    case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    artifact_id = repos.add_artifact(case_id)
    first = _make_fact(
        artifact_id=artifact_id,
        name="revenue",
        value=Decimal("100"),
        priority="official_filing",
    )
    second = _make_fact(
        artifact_id=artifact_id,
        name="revenue",
        value=Decimal("120"),
        priority="official_filing",
    )

    ledger.add_fact(first)
    ledger.add_fact(second)

    assert repos.evidence.list_for_case(case_id) == [first, second]
    conflicts = ledger.find_conflicts(name="revenue", period=first.period)
    assert len(conflicts) == 1
    assert set(conflicts[0].fact_ids) == {first.id, second.id}
    assert repos.contradictions.list_for_case(case_id) == conflicts


def test_add_fact_rejects_artifact_from_another_case_before_writing_evidence():
    case_id = uuid4()
    other_case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    other_artifact_id = repos.add_artifact(other_case_id)
    fact = _make_fact(artifact_id=other_artifact_id)

    with pytest.raises(ValueError, match="^evidence_fact_case_mismatch$"):
        ledger.add_fact(fact)

    assert repos.evidence.add_calls == []
    assert repos.evidence.list_for_case(case_id) == []
    assert repos.evidence.list_for_case(other_case_id) == []


def test_add_fact_rejects_missing_artifact_before_writing_evidence():
    case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    fact = _make_fact(artifact_id=uuid4())

    with pytest.raises(ValueError, match="^evidence_fact_artifact_not_found$"):
        ledger.add_fact(fact)

    assert repos.evidence.add_calls == []
    assert repos.evidence.list_for_case(case_id) == []


def test_add_fact_accepts_same_case_artifact_once():
    case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    artifact_id = repos.add_artifact(case_id)
    fact = _make_fact(artifact_id=artifact_id)

    assert ledger.add_fact(fact) == fact

    assert repos.evidence.add_calls == [fact]
    assert repos.evidence.list_for_case(case_id) == [fact]


def test_conflict_identity_normalizes_name_period_and_unit_inside_bound_case_only():
    case_id = uuid4()
    other_case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    artifact_id = repos.add_artifact(case_id)
    other_artifact_id = repos.add_artifact(other_case_id)
    first = _make_fact(
        artifact_id=artifact_id,
        name=" Revenue ",
        value=Decimal("100"),
        unit="usd",
        period=" FY2025 ",
        priority="official_filing",
    )
    same_value = _make_fact(
        artifact_id=artifact_id,
        name="revenue",
        value=Decimal("100"),
        unit="USD",
        period="FY2025",
        priority="official_filing",
    )
    conflict = _make_fact(
        artifact_id=artifact_id,
        name="REVENUE",
        value=Decimal("120"),
        unit="USD",
        period="FY2025",
        priority="official_filing",
    )
    unrelated_case_conflict = _make_fact(
        artifact_id=other_artifact_id,
        name="revenue",
        value=Decimal("130"),
        unit="USD",
        period="FY2025",
        priority="official_filing",
    )
    for fact in (first, same_value, conflict, unrelated_case_conflict):
        repos.evidence.add(fact)

    conflicts = ledger.find_conflicts(name=" revenue ", period="fy2025")

    assert len(conflicts) == 1
    assert set(conflicts[0].fact_ids) == {first.id, same_value.id, conflict.id}


def test_conflict_state_is_idempotent_for_same_values_and_immutable_for_changed_value_set():
    case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    artifact_id = repos.add_artifact(case_id)
    first = _make_fact(
        artifact_id=artifact_id,
        name="Revenue",
        value=Decimal("100"),
        unit="usd",
        period=" FY2025 ",
    )
    duplicate_value = _make_fact(
        artifact_id=artifact_id,
        name=" revenue ",
        value=Decimal("100.0"),
        unit="USD",
        period="FY2025",
    )
    second_value = _make_fact(
        artifact_id=artifact_id,
        name="REVENUE",
        value=Decimal("120"),
        unit="USD",
        period="fy2025",
    )
    for fact in (first, duplicate_value, second_value):
        repos.evidence.add(fact)

    first_discovery = ledger.find_conflicts(name=" revenue ", period="FY2025")
    second_discovery = ledger.find_conflicts(name="REVENUE", period=" fy2025 ")

    assert first_discovery == second_discovery
    assert len(repos.contradictions.list_for_case(case_id)) == 1
    assert set(first_discovery[0].fact_ids) == {first.id, duplicate_value.id, second_value.id}

    third_value = _make_fact(
        artifact_id=artifact_id,
        name="revenue",
        value=Decimal("130"),
        unit="USD",
        period="FY2025",
    )
    repos.evidence.add(third_value)

    expanded_discovery = ledger.find_conflicts(name="revenue", period="FY2025")

    assert len(expanded_discovery) == 1
    assert expanded_discovery[0].id != first_discovery[0].id
    assert set(expanded_discovery[0].fact_ids) == {
        first.id,
        duplicate_value.id,
        second_value.id,
        third_value.id,
    }
    assert len(repos.contradictions.list_for_case(case_id)) == 2
    assert ledger.find_conflicts(name="revenue", period="FY2025") == expanded_discovery
    assert len(repos.contradictions.list_for_case(case_id)) == 2


def test_source_priority_policy_uses_numeric_priority_and_rejects_secondary_critical_claim():
    policy = SourcePriorityPolicy()
    secondary = _make_fact(priority="secondary_aggregator")
    official = _make_fact(priority="official_filing")

    assert secondary.source_priority == SourcePriority.SECONDARY_AGGREGATOR
    assert official.source_priority == SourcePriority.OFFICIAL_OR_SIGNED
    assert policy.can_support_critical_claim([secondary], category="liquidity") is False
    assert policy.can_support_critical_claim([official], category="liquidity") is True
    assert policy.can_support_critical_claim([secondary], category="market_context") is True


def test_coverage_counts_primary_evidence_calculations_and_explicit_insufficient_data_only():
    case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    artifact_id = repos.add_artifact(case_id)
    official = _make_fact(
        artifact_id=artifact_id,
        name="revenue",
        priority="official_filing",
    )
    secondary = _make_fact(
        artifact_id=artifact_id,
        name="cash",
        priority="secondary_aggregator",
    )
    calculation = _make_calculation(case_id)
    for fact in (official, secondary):
        repos.evidence.add(fact)
    repos.calculations.add(calculation)
    repos.findings.add(
        _make_finding(case_id, category="valuation", evidence_fact_ids=(official.id,))
    )
    repos.findings.add(_make_finding(case_id, category="growth", calculation_ids=(calculation.id,)))
    repos.findings.add(
        _make_finding(case_id, category="debt", status=FindingStatus.INSUFFICIENT_DATA)
    )
    repos.findings.add(
        _make_finding(case_id, category="liquidity", evidence_fact_ids=(secondary.id,))
    )
    repos.findings.add(_make_finding(case_id, category="market_context"))

    assert ledger.coverage() == Decimal("0.75")


def test_coverage_returns_zero_when_case_has_no_critical_financial_findings():
    case_id = uuid4()
    repos = _Repositories()
    ledger = EvidenceLedger(
        case_id=case_id,
        artifact_repository=repos.artifacts,
        evidence_repository=repos.evidence,
        contradiction_repository=repos.contradictions,
        finding_repository=repos.findings,
        calculation_repository=repos.calculations,
    )
    repos.findings.add(_make_finding(case_id, category="market_context"))

    assert ledger.coverage() == Decimal("0")


class _Repositories:
    def __init__(self) -> None:
        self.artifacts = _ArtifactRepository()
        self.evidence = _EvidenceRepository(self.artifacts)
        self.contradictions = _CaseRepository[Contradiction]()
        self.findings = _CaseRepository[Finding]()
        self.calculations = _CaseRepository[Calculation]()

    def add_artifact(self, case_id: UUID) -> UUID:
        artifact_id = uuid4()
        self.artifacts.add(_make_artifact(artifact_id, case_id))
        return artifact_id


class _CaseRepository[T]:
    def __init__(self) -> None:
        self.items: list[T] = []

    def add(self, item: T) -> None:
        self.items.append(item)

    def list_for_case(self, case_id: UUID) -> list[T]:
        return [item for item in self.items if item.case_id == case_id]


class _EvidenceRepository:
    def __init__(self, artifacts: "_ArtifactRepository") -> None:
        self.artifacts = artifacts
        self.items: list[EvidenceFact] = []
        self.add_calls: list[EvidenceFact] = []

    def add(self, fact: EvidenceFact) -> None:
        self.add_calls.append(fact)
        self.items.append(fact)

    def list_for_case(self, case_id: UUID) -> list[EvidenceFact]:
        return [
            fact
            for fact in self.items
            if self.artifacts.case_id_for_artifact(fact.artifact_id) == case_id
        ]


class _ArtifactRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, Artifact] = {}

    def add(self, artifact: Artifact) -> None:
        self.items[artifact.id] = artifact

    def get(self, artifact_id: UUID) -> Artifact:
        try:
            return self.items[artifact_id]
        except KeyError as exc:
            raise KeyError(f"artifact_not_found:{artifact_id}") from exc

    def case_id_for_artifact(self, artifact_id: UUID) -> UUID | None:
        artifact = self.items.get(artifact_id)
        if artifact is None:
            return None
        return artifact.case_id


def _make_artifact(artifact_id: UUID, case_id: UUID) -> Artifact:
    return Artifact(
        id=artifact_id,
        case_id=case_id,
        content_hash="a" * 64,
        mime_type="application/json",
        source="unit-test",
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
        source_snapshot_hash="b" * 64,
        sensitivity=SensitivityClass.PUBLIC,
    )


def _make_fact(
    *,
    artifact_id: UUID | None = None,
    name: str = "revenue",
    value: Decimal = Decimal("100"),
    unit: str = "USD",
    period: str = "FY2025",
    priority: str = "official_filing",
) -> EvidenceFact:
    source_priority = {
        "official_filing": SourcePriority.OFFICIAL_OR_SIGNED,
        "secondary_aggregator": SourcePriority.SECONDARY_AGGREGATOR,
        "model_inference": SourcePriority.MODEL_INFERENCE,
    }[priority]
    fact_artifact_id = artifact_id or uuid4()
    return EvidenceFact(
        id=uuid4(),
        artifact_id=fact_artifact_id,
        name=name,
        value=value,
        value_type="decimal",
        unit=unit,
        period=period,
        locator=SourceLocator(kind="sec_fact", value=name, artifact_id=fact_artifact_id),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.95"),
        source_priority=source_priority,
        extraction_method="xbrl",
        supporting_text_hash="c" * 64,
        source_freshness_at=datetime(2026, 8, 8, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


def _make_calculation(case_id: UUID) -> Calculation:
    return Calculation(
        id=uuid4(),
        case_id=case_id,
        metric_name="revenue_growth",
        formula_version="revenue-growth@1",
        input_fact_ids=(uuid4(),),
        value=Decimal("10"),
        unit="percent",
        period="FY2025",
        warnings=(),
        calculated_at=datetime(2026, 8, 9, tzinfo=UTC),
        sensitivity=SensitivityClass.PUBLIC,
    )


def _make_finding(
    case_id: UUID,
    *,
    category: str,
    evidence_fact_ids: tuple[UUID, ...] = (),
    calculation_ids: tuple[UUID, ...] = (),
    status: FindingStatus = FindingStatus.VERIFIED,
) -> Finding:
    return Finding(
        id=uuid4(),
        case_id=case_id,
        category=category,
        severity=FindingSeverity.HIGH,
        claim=f"{category} claim",
        evidence_fact_ids=evidence_fact_ids,
        calculation_ids=calculation_ids,
        confidence=Decimal("0.80"),
        status=status,
        counter_evidence_fact_ids=(),
        author_node="risk_node",
        author_model=None,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
    )

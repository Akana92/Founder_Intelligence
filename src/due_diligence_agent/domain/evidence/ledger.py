from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from due_diligence_agent.application.policies.source_priority import (
    CRITICAL_FINANCIAL_CATEGORIES,
    SourcePriorityPolicy,
)
from due_diligence_agent.domain.common import (
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.ports.repositories import (
    ArtifactRepository,
    CalculationRepository,
    ContradictionRepository,
    EvidenceRepository,
    FindingRepository,
)


_CONTRADICTION_NAMESPACE = UUID("e4376e21-7bc8-4f61-a9c0-425ac7f2ac59")


class EvidenceLedger:
    def __init__(
        self,
        *,
        case_id: UUID,
        artifact_repository: ArtifactRepository,
        evidence_repository: EvidenceRepository,
        contradiction_repository: ContradictionRepository,
        finding_repository: FindingRepository,
        calculation_repository: CalculationRepository,
        source_priority_policy: SourcePriorityPolicy | None = None,
    ) -> None:
        self.case_id = case_id
        self._artifact_repository = artifact_repository
        self._evidence_repository = evidence_repository
        self._contradiction_repository = contradiction_repository
        self._finding_repository = finding_repository
        self._calculation_repository = calculation_repository
        self._source_priority_policy = source_priority_policy or SourcePriorityPolicy()

    def add_fact(self, fact: EvidenceFact) -> EvidenceFact:
        try:
            artifact = self._artifact_repository.get(fact.artifact_id)
        except KeyError as exc:
            raise ValueError("evidence_fact_artifact_not_found") from exc
        if artifact.case_id != self.case_id:
            raise ValueError("evidence_fact_case_mismatch")
        self._evidence_repository.add(fact)
        return fact

    def find_conflicts(self, *, name: str, period: str | None) -> list[Contradiction]:
        target_name = _normalize_text(name)
        target_period = _normalize_optional_text(period)
        facts = [
            fact
            for fact in self._evidence_repository.list_for_case(self.case_id)
            if _normalize_text(fact.name) == target_name
            and _normalize_optional_text(fact.period) == target_period
        ]

        conflicts: list[Contradiction] = []
        for normalized_unit, unit_facts in _facts_by_unit(facts).items():
            value_buckets = _facts_by_value(unit_facts)
            if len(value_buckets) < 2:
                continue
            fact_ids = tuple(fact.id for fact in unit_facts)
            value_set = tuple(sorted(value_buckets))
            conflicts.append(
                self._record_conflict(
                    fact_ids=fact_ids,
                    facts=unit_facts,
                    normalized_name=target_name,
                    normalized_period=target_period,
                    normalized_unit=normalized_unit,
                    normalized_values=value_set,
                )
            )
        return conflicts

    def coverage(self) -> Decimal:
        critical_findings = [
            finding
            for finding in self._finding_repository.list_for_case(self.case_id)
            if _normalize_text(finding.category) in CRITICAL_FINANCIAL_CATEGORIES
        ]
        if not critical_findings:
            return Decimal("0")

        facts_by_id = {
            fact.id: fact for fact in self._evidence_repository.list_for_case(self.case_id)
        }
        calculation_ids = {
            calculation.id for calculation in self._calculation_repository.list_for_case(self.case_id)
        }
        covered_count = sum(
            1
            for finding in critical_findings
            if self._finding_has_coverage(
                finding,
                facts_by_id=facts_by_id,
                calculation_ids=calculation_ids,
            )
        )
        return Decimal(covered_count) / Decimal(len(critical_findings))

    def _record_conflict(
        self,
        *,
        fact_ids: tuple[UUID, ...],
        facts: Iterable[EvidenceFact],
        normalized_name: str,
        normalized_period: str | None,
        normalized_unit: str | None,
        normalized_values: tuple[str, ...],
    ) -> Contradiction:
        contradiction_id = _contradiction_id(
            case_id=self.case_id,
            normalized_name=normalized_name,
            normalized_period=normalized_period,
            normalized_unit=normalized_unit,
            normalized_values=normalized_values,
        )
        existing = _find_existing_conflict(
            self._contradiction_repository.list_for_case(self.case_id),
            contradiction_id=contradiction_id,
        )
        if existing is not None:
            return existing

        contradiction = Contradiction(
            id=contradiction_id,
            case_id=self.case_id,
            conflict_type="evidence_value",
            fact_ids=fact_ids,
            finding_ids=(),
            explanation="Conflicting evidence values for the same normalized fact identity.",
            severity=FindingSeverity.HIGH,
            status=ContradictionStatus.OPEN,
            recommended_resolution="Prefer the highest-priority primary source or request review.",
            resolved_by_approval_id=None,
            sensitivity=_most_restrictive_sensitivity(facts),
            detected_at=datetime.now(UTC),
        )
        self._contradiction_repository.add(contradiction)
        return contradiction

    def _finding_has_coverage(
        self,
        finding: Finding,
        *,
        facts_by_id: dict[UUID, EvidenceFact],
        calculation_ids: set[UUID],
    ) -> bool:
        if finding.status is FindingStatus.INSUFFICIENT_DATA:
            return True
        if any(calculation_id in calculation_ids for calculation_id in finding.calculation_ids):
            return True
        evidence = [
            facts_by_id[fact_id]
            for fact_id in finding.evidence_fact_ids
            if fact_id in facts_by_id
        ]
        return self._source_priority_policy.can_support_critical_claim(
            evidence, category=finding.category
        )


def _facts_by_unit(facts: Iterable[EvidenceFact]) -> dict[str | None, list[EvidenceFact]]:
    grouped: dict[str | None, list[EvidenceFact]] = {}
    for fact in facts:
        grouped.setdefault(_normalize_optional_text(fact.unit), []).append(fact)
    return grouped


def _facts_by_value(facts: Iterable[EvidenceFact]) -> dict[str, list[EvidenceFact]]:
    grouped: dict[str, list[EvidenceFact]] = {}
    for fact in facts:
        grouped.setdefault(_normalize_value(fact.value), []).append(fact)
    return grouped


def _find_existing_conflict(
    contradictions: Iterable[Contradiction], *, contradiction_id: UUID
) -> Contradiction | None:
    for contradiction in contradictions:
        if contradiction.id == contradiction_id:
            return contradiction
    return None


def _contradiction_id(
    *,
    case_id: UUID,
    normalized_name: str,
    normalized_period: str | None,
    normalized_unit: str | None,
    normalized_values: tuple[str, ...],
) -> UUID:
    state_key = "\x1f".join(
        (
            str(case_id),
            normalized_name,
            normalized_period or "",
            normalized_unit or "",
            "\x1e".join(normalized_values),
        )
    )
    return uuid5(_CONTRADICTION_NAMESPACE, state_key)


def _normalize_value(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value.normalize())
    return str(value).strip()


def _normalize_text(value: str) -> str:
    return value.strip().casefold()


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _normalize_text(value)


def _most_restrictive_sensitivity(facts: Iterable[EvidenceFact]) -> SensitivityClass:
    rank = {
        SensitivityClass.PUBLIC: 0,
        SensitivityClass.INTERNAL: 1,
        SensitivityClass.CONFIDENTIAL: 2,
        SensitivityClass.RESTRICTED: 3,
    }
    return max((fact.sensitivity for fact in facts), key=lambda sensitivity: rank[sensitivity])

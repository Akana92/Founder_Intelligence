from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid5

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.domain.common import ContradictionStatus, FindingSeverity
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import (
    ClaimCategory,
    ClaimEvidenceLink,
    ClaimEvidenceMatrix,
    ClaimEvidenceMatrixRow,
    ClaimStatus,
    StartupClaim,
)
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.ports.repositories import ContradictionRepository


_CONTRADICTION_NAMESPACE = UUID("8698888f-2ec2-4623-9976-b18845f6a1c7")
_CONTRADICTION_CATEGORIES = {
    ClaimCategory.ARR,
    ClaimCategory.GROSS_MARGIN,
    ClaimCategory.RUNWAY,
    ClaimCategory.CUSTOMER_COUNT,
}
ClaimRelation = Literal["supports", "partially_supports", "contradicts", "missing"]


class ClaimEvidenceService:
    def __init__(
        self,
        *,
        contradiction_repository: ContradictionRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._contradiction_repository = contradiction_repository
        self._clock = clock or _utc_now

    def build(
        self,
        *,
        case_id: UUID,
        claims: Iterable[StartupClaim],
        evidence_facts: Iterable[EvidenceFact],
        calculations: Iterable[Calculation] = (),
    ) -> ClaimEvidenceMatrix:
        claims_by_id = _dedupe_claims(claims)
        _ensure_claims_belong_to_case(case_id, claims_by_id.values())
        facts_by_id = _dedupe_facts(evidence_facts)
        calculations_by_id = _dedupe_calculations(calculations)
        _ensure_calculations_belong_to_case(case_id, calculations_by_id.values())
        rows = tuple(
            self._build_row(
                claim,
                case_id=case_id,
                facts=facts_by_id.values(),
                calculations=calculations_by_id.values(),
            )
            for claim in claims_by_id.values()
        )
        return ClaimEvidenceMatrix(case_id=case_id, rows=rows)

    def _build_row(
        self,
        claim: StartupClaim,
        *,
        case_id: UUID,
        facts: Iterable[EvidenceFact],
        calculations: Iterable[Calculation],
    ) -> ClaimEvidenceMatrixRow:
        fact_matches = _fact_matches(claim, facts)
        calculation_matches = _calculation_matches(claim, calculations)
        if fact_matches.incompatible_units or calculation_matches.incompatible_units:
            return ClaimEvidenceMatrixRow(
                claim=claim,
                status=ClaimStatus.INSUFFICIENT_DATA,
                links=(
                    ClaimEvidenceLink(
                        claim_id=claim.id,
                        evidence_fact_id=None,
                        calculation_id=None,
                        relation="missing",
                        confidence=Decimal("0"),
                        reason="incompatible units for same metric and period",
                    ),
                ),
                contradictions=(),
                contradiction_ids=(),
                executive_summary_eligible=False,
            )
        matching_facts = tuple(fact_matches.items)
        matching_calculations = tuple(calculation_matches.items)
        evidence_links = tuple(_link_for_fact(claim, fact) for fact in matching_facts)
        calculation_links = tuple(_link_for_calculation(claim, calculation) for calculation in matching_calculations)
        links = _sort_links(evidence_links + calculation_links)

        if not links:
            missing = ClaimEvidenceLink(
                claim_id=claim.id,
                evidence_fact_id=None,
                calculation_id=None,
                relation="missing",
                confidence=Decimal("0"),
                reason="no matching metric, unit, and period evidence",
            )
            return ClaimEvidenceMatrixRow(
                claim=claim,
                status=ClaimStatus.UNSUPPORTED,
                links=(missing,),
                contradictions=(),
                executive_summary_eligible=False,
            )

        if any(link.relation == "contradicts" for link in links):
            contradictions = (
                (self._contradiction(case_id, claim, links),)
                if claim.category in _CONTRADICTION_CATEGORIES
                else ()
            )
            return ClaimEvidenceMatrixRow(
                claim=claim,
                status=ClaimStatus.CONTRADICTED,
                links=links,
                contradictions=contradictions,
                contradiction_ids=tuple(contradiction.id for contradiction in contradictions),
                executive_summary_eligible=False,
            )

        if any(link.relation == "supports" for link in links):
            return ClaimEvidenceMatrixRow(
                claim=claim,
                status=ClaimStatus.VERIFIED,
                links=links,
                contradictions=(),
                executive_summary_eligible=True,
            )

        return ClaimEvidenceMatrixRow(
            claim=claim,
            status=ClaimStatus.PARTIALLY_VERIFIED,
            links=links,
            contradictions=(),
            executive_summary_eligible=False,
        )


    def _contradiction(
        self,
        case_id: UUID,
        claim: StartupClaim,
        links: tuple[ClaimEvidenceLink, ...],
    ) -> Contradiction:
        contradiction = Contradiction(
            id=_contradiction_id(case_id=case_id, claim=claim, links=links),
            case_id=case_id,
            conflict_type=f"startup_claim_{claim.category.value}",
            fact_ids=tuple(
                link.evidence_fact_id for link in links if link.evidence_fact_id is not None
            ),
            finding_ids=(),
            explanation=(
                "Startup claim value is incompatible with normalized evidence for the "
                "same metric, unit, and period."
            ),
            severity=FindingSeverity.HIGH,
            status=ContradictionStatus.OPEN,
            recommended_resolution="Prefer highest-priority source or request founder review.",
            resolved_by_approval_id=None,
            sensitivity=claim.sensitivity,
            detected_at=self._clock(),
        )
        if self._contradiction_repository is not None:
            existing = _find_existing(
                self._contradiction_repository.list_for_case(case_id),
                contradiction.id,
            )
            if existing is not None:
                return existing
            self._contradiction_repository.add(contradiction)
        return contradiction


class _Matches[T]:
    def __init__(self, items: list[T], *, incompatible_units: bool) -> None:
        self.items = items
        self.incompatible_units = incompatible_units


def _fact_matches(claim: StartupClaim, facts: Iterable[EvidenceFact]) -> _Matches[EvidenceFact]:
    items: list[EvidenceFact] = []
    incompatible_units = False
    for fact in facts:
        if not _same_identity(claim.normalized_name, fact.name):
            continue
        if not _same_optional(claim.period, fact.period):
            continue
        if not _compatible_units(claim.unit, fact.unit):
            incompatible_units = True
            continue
        items.append(fact)
    return _Matches(items, incompatible_units=incompatible_units)


def _calculation_matches(
    claim: StartupClaim,
    calculations: Iterable[Calculation],
) -> _Matches[Calculation]:
    items: list[Calculation] = []
    incompatible_units = False
    for calculation in calculations:
        if not _same_identity(claim.normalized_name, calculation.metric_name):
            continue
        if not _same_optional(claim.period, calculation.period):
            continue
        if not _compatible_units(claim.unit, calculation.unit):
            incompatible_units = True
            continue
        items.append(calculation)
    return _Matches(items, incompatible_units=incompatible_units)


def _link_for_fact(claim: StartupClaim, fact: EvidenceFact) -> ClaimEvidenceLink:
    relation = _relation(claim, fact.value, priority=fact.source_priority)
    return ClaimEvidenceLink(
        claim_id=claim.id,
        evidence_fact_id=fact.id,
        calculation_id=None,
        relation=relation,
        confidence=_link_confidence(claim.confidence, fact.confidence),
        reason=f"fact:{fact.name}:{relation}",
    )


def _link_for_calculation(claim: StartupClaim, calculation: Calculation) -> ClaimEvidenceLink:
    relation = _relation(
        claim,
        calculation.value,
        priority=SourcePriority.SYSTEM_EXPORT,
        calculation=True,
    )
    return ClaimEvidenceLink(
        claim_id=claim.id,
        evidence_fact_id=None,
        calculation_id=calculation.id,
        relation=relation,
        confidence=Decimal("0.98"),
        reason=f"calculation:{calculation.metric_name}:{relation}",
    )


def _relation(
    claim: StartupClaim,
    value: object,
    *,
    priority: int | None,
    calculation: bool = False,
) -> ClaimRelation:
    if claim.normalized_value is None:
        return "partially_supports"
    try:
        evidence_value = _as_decimal(value)
    except ValueError:
        return "partially_supports"
    if _within_tolerance(claim, evidence_value):
        if calculation or priority is not None and priority >= SourcePriority.SYSTEM_EXPORT:
            return "supports"
        return "partially_supports"
    return "contradicts"


def _sort_links(links: tuple[ClaimEvidenceLink, ...]) -> tuple[ClaimEvidenceLink, ...]:
    relation_rank = {"contradicts": 0, "supports": 1, "partially_supports": 2, "missing": 3}
    return tuple(
        sorted(
            links,
            key=lambda link: (
                relation_rank[link.relation],
                str(link.evidence_fact_id or link.calculation_id or ""),
            ),
        )
    )


def _dedupe_facts(facts: Iterable[EvidenceFact]) -> dict[UUID, EvidenceFact]:
    return {fact.id: fact for fact in facts}


def _dedupe_claims(claims: Iterable[StartupClaim]) -> dict[UUID, StartupClaim]:
    return {claim.id: claim for claim in claims}


def _dedupe_calculations(calculations: Iterable[Calculation]) -> dict[UUID, Calculation]:
    return {calculation.id: calculation for calculation in calculations}


def _ensure_claims_belong_to_case(case_id: UUID, claims: Iterable[StartupClaim]) -> None:
    if any(claim.case_id != case_id for claim in claims):
        raise ValueError("claim_case_mismatch")


def _ensure_calculations_belong_to_case(
    case_id: UUID,
    calculations: Iterable[Calculation],
) -> None:
    if any(calculation.case_id != case_id for calculation in calculations):
        raise ValueError("calculation_case_mismatch")


def _same_identity(left: str, right: str) -> bool:
    return _normalize_name(left) == _normalize_name(right)


def _normalize_name(value: str) -> str:
    return value.strip().casefold().replace(" ", "_").replace("-", "_")


def _same_optional(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return left == right
    return left.strip().casefold() == right.strip().casefold()


def _compatible_units(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return left == right
    return _normalize_unit(left) == _normalize_unit(right)


def _normalize_unit(unit: str) -> str:
    normalized = unit.strip().casefold()
    return {
        "usd": "usd",
        "$": "usd",
        "percent": "percent",
        "%": "percent",
        "percentage_points": "percent",
        "months": "months",
        "month": "months",
        "count": "count",
        "customers": "count",
    }.get(normalized, normalized)


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError("not decimal-compatible")


def _within_tolerance(claim: StartupClaim, right: Decimal) -> bool:
    left = claim.normalized_value
    if left is None:
        return False
    unit = _normalize_unit(claim.unit or "")
    category = claim.category
    difference = abs(left - right)
    if unit == "count" or category is ClaimCategory.CUSTOMER_COUNT:
        return difference == 0
    if unit == "percent" or category in {ClaimCategory.GROSS_MARGIN, ClaimCategory.GROWTH}:
        return difference <= Decimal("0.1")
    if unit == "months" or category is ClaimCategory.RUNWAY:
        return difference <= Decimal("0.1")
    if unit == "usd" or category in {
        ClaimCategory.ARR,
        ClaimCategory.MARKET_SIZE,
        ClaimCategory.VALUATION,
    }:
        relative = abs(left) * Decimal("0.005")
        return difference <= max(Decimal("10000"), relative)
    return difference == 0


def _link_confidence(left: Decimal, right: Decimal) -> Decimal:
    return min(left, right)


def _contradiction_id(
    *,
    case_id: UUID,
    claim: StartupClaim,
    links: tuple[ClaimEvidenceLink, ...],
) -> UUID:
    linked_ids = sorted(str(link.evidence_fact_id or link.calculation_id) for link in links)
    key = "\x1f".join((str(case_id), str(claim.id), claim.category.value, "\x1e".join(linked_ids)))
    return uuid5(_CONTRADICTION_NAMESPACE, key)


def _find_existing(contradictions: Iterable[Contradiction], target_id: UUID) -> Contradiction | None:
    for contradiction in contradictions:
        if contradiction.id == target_id:
            return contradiction
    return None


def _utc_now() -> datetime:
    return datetime.now(UTC)

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
import re
from uuid import UUID, uuid5

from due_diligence_agent.domain.common import (
    ContradictionStatus,
    FindingSeverity,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.ports.repositories import ContradictionRepository


_CONTRADICTION_NAMESPACE = UUID("5446d576-22dd-452e-ac88-9d72034e05db")
_CONFLICT_TYPE = "source_fact_value_conflict"
_SENSITIVITY_RANK = {
    SensitivityClass.PUBLIC: 0,
    SensitivityClass.INTERNAL: 1,
    SensitivityClass.CONFIDENTIAL: 2,
    SensitivityClass.RESTRICTED: 3,
}


class SourceFactContradictionService:
    def __init__(
        self,
        *,
        contradiction_repository: ContradictionRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._contradiction_repository = contradiction_repository
        self._clock = clock or _utc_now

    def materialize(
        self,
        *,
        case_id: UUID,
        evidence_facts: Iterable[EvidenceFact],
    ) -> tuple[Contradiction, ...]:
        grouped: dict[tuple[str, str, str], dict[UUID, EvidenceFact]] = {}
        for fact in evidence_facts:
            if fact.value_type not in {"decimal", "integer"}:
                continue
            identity = (
                _normalize_name(fact.name),
                _normalize_unit(fact.unit),
                _normalize_period(fact.period),
            )
            grouped.setdefault(identity, {})[fact.id] = fact

        existing_by_id = {
            item.id: item for item in self._contradiction_repository.list_for_case(case_id)
        }
        materialized: list[Contradiction] = []
        for identity, facts_by_id in sorted(grouped.items()):
            facts = tuple(sorted(facts_by_id.values(), key=lambda item: str(item.id)))
            if _has_unique_founder_accepted_value(facts) or not _has_cross_source_value_conflict(facts):
                continue
            contradiction_id = _contradiction_id(
                case_id=case_id,
                identity=identity,
                facts=facts,
            )
            contradiction = existing_by_id.get(contradiction_id)
            if contradiction is None:
                contradiction = Contradiction(
                    id=contradiction_id,
                    case_id=case_id,
                    conflict_type=_CONFLICT_TYPE,
                    fact_ids=tuple(fact.id for fact in facts),
                    finding_ids=(),
                    explanation=(
                        "Conflicting normalized numeric values were extracted from "
                        "different source artifacts."
                    ),
                    severity=FindingSeverity.HIGH,
                    status=ContradictionStatus.OPEN,
                    recommended_resolution=(
                        "Review the linked source facts and select the authoritative source."
                    ),
                    resolved_by_approval_id=None,
                    sensitivity=max(
                        (fact.sensitivity for fact in facts),
                        key=_SENSITIVITY_RANK.__getitem__,
                    ),
                    detected_at=self._clock(),
                )
                self._contradiction_repository.add(contradiction)
                existing_by_id[contradiction.id] = contradiction
            materialized.append(contradiction)
        return tuple(sorted(materialized, key=lambda item: str(item.id)))


def _has_unique_founder_accepted_value(facts: tuple[EvidenceFact, ...]) -> bool:
    accepted_values = {
        _numeric_value(fact)
        for fact in facts
        if fact.metadata.get("founder_clarification") == "accepted_source"
    }
    return len(accepted_values) == 1


def _has_cross_source_value_conflict(facts: tuple[EvidenceFact, ...]) -> bool:
    return any(
        left.artifact_id != right.artifact_id
        and _numeric_value(left) != _numeric_value(right)
        for index, left in enumerate(facts)
        for right in facts[index + 1 :]
    )


def _contradiction_id(
    *,
    case_id: UUID,
    identity: tuple[str, str, str],
    facts: tuple[EvidenceFact, ...],
) -> UUID:
    fact_fingerprint = "\x1e".join(
        f"{fact.id}:{_canonical_decimal(_numeric_value(fact))}" for fact in facts
    )
    return uuid5(
        _CONTRADICTION_NAMESPACE,
        "\x1f".join((str(case_id), *identity, fact_fingerprint)),
    )


def _numeric_value(fact: EvidenceFact) -> Decimal:
    if fact.value_type == "integer":
        return Decimal(fact.value)
    if isinstance(fact.value, Decimal):
        return fact.value
    return Decimal(str(fact.value))


def _canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s-]+", "_", value.strip().casefold())


def _normalize_unit(value: str | None) -> str:
    normalized = (value or "").strip().casefold()
    return {
        "$": "usd",
        "%": "percent",
        "customers": "count",
        "month": "months",
    }.get(normalized, normalized)


def _normalize_period(value: str | None) -> str:
    return (value or "").strip().casefold()


def _utc_now() -> datetime:
    return datetime.now(UTC)

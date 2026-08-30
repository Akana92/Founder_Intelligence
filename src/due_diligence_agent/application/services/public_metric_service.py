from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid5

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.domain.common import SensitivityClass, require_utc
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.metrics import MetricCalculationResult, MetricEngine, MetricStatus
from due_diligence_agent.domain.metrics.definitions import PUBLIC_METRICS
from due_diligence_agent.ports.repositories import CalculationRepository, EvidenceRepository


_CALCULATION_NAMESPACE = UUID("d81ef39b-a885-44af-a698-ac8222be9b56")
_SENSITIVITY_RANK = {
    SensitivityClass.PUBLIC: 0,
    SensitivityClass.INTERNAL: 1,
    SensitivityClass.CONFIDENTIAL: 2,
    SensitivityClass.RESTRICTED: 3,
}


class PublicMetricService:
    def __init__(
        self,
        *,
        evidence_repository: EvidenceRepository,
        calculation_repository: CalculationRepository,
        clock: Callable[[], datetime],
        engine: MetricEngine | None = None,
    ) -> None:
        self._evidence_repository = evidence_repository
        self._calculation_repository = calculation_repository
        self._clock = clock
        self._engine = engine or MetricEngine()

    def calculate(
        self,
        case_id: UUID,
        metric_name: str,
        *,
        evidence_fact_ids: Sequence[UUID],
        as_of: datetime | None = None,
    ) -> MetricCalculationResult:
        seen_ids: set[UUID] = set()
        for fact_id in evidence_fact_ids:
            if fact_id in seen_ids:
                raise ValueError(f"evidence_fact_id.duplicate:{fact_id}")
            seen_ids.add(fact_id)

        case_facts = self._evidence_repository.list_for_case(case_id)
        facts_by_id = {fact.id: fact for fact in case_facts}
        selected: list[EvidenceFact] = []
        for fact_id in evidence_fact_ids:
            try:
                selected.append(facts_by_id[fact_id])
            except KeyError as exc:
                raise ValueError(f"evidence_fact_id.not_in_case:{fact_id}") from exc

        result = self._engine.calculate(metric_name, tuple(selected), as_of=as_of)
        if result.status is not MetricStatus.CALCULATED:
            return result

        source_warning = self._source_warning(metric_name, selected, result, as_of)
        if source_warning is not None:
            definition = PUBLIC_METRICS[metric_name]
            return MetricCalculationResult(
                status=MetricStatus.INSUFFICIENT_DATA,
                metric_name=definition.name,
                formula_version=definition.formula_version,
                value=None,
                display_value=None,
                unit="ratio" if definition.unit_policy == "ratio" else "",
                period="",
                input_evidence_ids=result.input_evidence_ids,
                warnings=(source_warning,),
            )

        calculation_id = _calculation_id(case_id, result)
        existing = next(
            (
                item
                for item in self._calculation_repository.list_for_case(case_id)
                if item.id == calculation_id
            ),
            None,
        )
        sensitivity = _most_restrictive(fact.sensitivity for fact in selected)
        if existing is not None:
            _assert_same_deterministic(existing, case_id, result, sensitivity)
            return result.model_copy(update={"calculation_id": existing.id})

        calculation = Calculation(
            id=calculation_id,
            case_id=case_id,
            metric_name=result.metric_name,
            formula_version=result.formula_version,
            input_fact_ids=result.input_evidence_ids,
            value=_calculated_value(result),
            unit=result.unit,
            period=result.period,
            warnings=(),
            calculated_at=_require_utc_clock(self._clock),
            sensitivity=sensitivity,
        )
        self._calculation_repository.add(calculation)
        return result.model_copy(update={"calculation_id": calculation_id})

    def _source_warning(
        self,
        metric_name: str,
        facts: Sequence[EvidenceFact],
        result: MetricCalculationResult,
        as_of: datetime | None,
    ) -> str | None:
        definition = PUBLIC_METRICS[metric_name]
        selected_by_id = {fact.id: fact for fact in facts}
        for slot_index, slot in enumerate(definition.slots):
            fact = selected_by_id.get(result.input_evidence_ids[slot_index])
            if fact is None:
                continue
            if slot.name == "market_cap":
                if fact.locator.kind != "market_data" or not _has_priority(
                    fact, SourcePriority.SECONDARY_AGGREGATOR
                ):
                    return "source.ineligible:market_cap"
                if as_of is None:
                    return "as_of.required"
                if fact.period != as_of.date().isoformat():
                    return "as_of.mismatch:market_cap"
                continue
            if _is_ineligible_financial_locator(fact.locator.kind) or not _has_priority(
                fact, SourcePriority.OFFICIAL_OR_SIGNED
            ):
                return f"source.ineligible:{slot.name}"
        return None


def _has_priority(fact: EvidenceFact, minimum: SourcePriority) -> bool:
    return fact.source_priority is not None and fact.source_priority >= minimum


def _is_ineligible_financial_locator(kind: str) -> bool:
    normalized = kind.strip().casefold()
    return normalized == "market_data" or normalized.startswith("news") or "model" in normalized


def _calculation_id(case_id: UUID, result: MetricCalculationResult) -> UUID:
    material = "|".join(
        (
            str(case_id),
            result.formula_version,
            ",".join(str(item) for item in result.input_evidence_ids),
            str(result.value),
            result.unit,
            result.period,
        )
    )
    return uuid5(_CALCULATION_NAMESPACE, material)


def _calculated_value(result: MetricCalculationResult) -> Decimal:
    if result.value is None:
        raise ValueError("calculated_result_missing_value")
    return result.value


def _require_utc_clock(clock: Callable[[], datetime]) -> datetime:
    checked = require_utc(clock())
    if checked is None:
        raise ValueError("timestamp is required")
    return checked


def _most_restrictive(values: Iterable[SensitivityClass]) -> SensitivityClass:
    return max(tuple(values), key=lambda value: _SENSITIVITY_RANK[value])


def _assert_same_deterministic(
    existing: Calculation,
    case_id: UUID,
    result: MetricCalculationResult,
    sensitivity: SensitivityClass,
) -> None:
    expected = {
        "id": _calculation_id(case_id, result),
        "case_id": case_id,
        "metric_name": result.metric_name,
        "formula_version": result.formula_version,
        "input_fact_ids": result.input_evidence_ids,
        "value": result.value,
        "unit": result.unit,
        "period": result.period,
        "warnings": (),
        "sensitivity": sensitivity,
        "version": 1,
    }
    actual = {key: getattr(existing, key) for key in expected}
    if actual != expected:
        raise ValueError("calculation_id_conflict")

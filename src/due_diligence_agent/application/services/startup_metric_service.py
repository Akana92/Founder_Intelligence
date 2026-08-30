from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import re
from typing import cast
from uuid import UUID, uuid5

from due_diligence_agent.domain.common import SensitivityClass, require_decimal, require_utc
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.metrics import MetricCalculationResult, MetricStatus
from due_diligence_agent.domain.metrics.startup import (
    STARTUP_METRICS,
    STARTUP_QUANT,
    StartupMetricDefinition,
    StartupMetricInput,
)
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.scenario import ScenarioConfidence, ScenarioMetric, ScenarioRange
from due_diligence_agent.ports.repositories import CalculationRepository, EvidenceRepository


_CALCULATION_NAMESPACE = UUID("2d1d6e3c-7ef3-49c9-8b3a-bbc2c1a3d773")
_SCENARIO_NAMESPACE = UUID("94a17b5c-9423-4dfc-b68e-d55883c38cc1")
_SCENARIO_CASE_ID = UUID("00000000-0000-4000-8000-000000000001")
_SENSITIVITY_RANK = {
    SensitivityClass.PUBLIC: 0,
    SensitivityClass.INTERNAL: 1,
    SensitivityClass.CONFIDENTIAL: 2,
    SensitivityClass.RESTRICTED: 3,
}
_LTV_MODEL = "gross_margin_adjusted_arpa_churn"
_SUPPORTED_CURRENCIES = frozenset({"USD", "EUR", "GBP", "KZT"})


class StartupMetricService:
    def __init__(
        self,
        *,
        evidence_repository: EvidenceRepository | None = None,
        calculation_repository: CalculationRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._evidence_repository = evidence_repository
        self._calculation_repository = calculation_repository
        self._clock = clock

    def calculate(
        self,
        metric_name: str,
        facts: tuple[EvidenceFact, ...] | list[EvidenceFact],
        *,
        assumptions: Mapping[str, str] | None = None,
    ) -> MetricCalculationResult:
        try:
            definition = STARTUP_METRICS[metric_name]
        except KeyError as exc:
            raise KeyError(f"unknown_startup_metric:{metric_name}") from exc

        selected, warning = _select_exact(definition, tuple(facts), assumptions or {})
        if warning is not None:
            return _insufficient(definition, warning, selected)

        values: dict[str, Decimal] = {}
        for slot in definition.slots:
            slot_facts = selected[slot.slot]
            try:
                raw_values = tuple(require_decimal(fact.value) for fact in slot_facts)
            except (InvalidOperation, ValueError):
                return _insufficient(definition, f"input.non_numeric:{slot.slot}", selected)
            if any(not value.is_finite() for value in raw_values):
                return _insufficient(definition, f"input.non_numeric:{slot.slot}", selected)
            values[slot.slot] = sum(raw_values, Decimal("0"))

        for slot_name in definition.denominator_slots:
            if values[slot_name] <= 0:
                return _insufficient(definition, f"denominator.non_positive:{slot_name}", selected)

        with localcontext() as context:
            context.prec = 50
            value = definition.formula(values).quantize(STARTUP_QUANT, rounding=ROUND_HALF_EVEN)
        if value == 0:
            value = Decimal("0.000000")
        display = value.quantize(
            Decimal("1").scaleb(-definition.display_places),
            rounding=ROUND_HALF_EVEN,
        )
        return MetricCalculationResult(
            status=MetricStatus.CALCULATED,
            metric_name=definition.name,
            formula_version=definition.formula_version,
            value=value,
            display_value=format(display, f".{definition.display_places}f"),
            unit=_result_unit(definition, selected),
            period=_result_period(definition, selected),
            input_evidence_ids=_ordered_ids(definition, selected),
        )

    def calculate_available(
        self,
        facts: tuple[EvidenceFact, ...] | list[EvidenceFact],
        *,
        assumptions: Mapping[str, str] | None = None,
    ) -> tuple[MetricCalculationResult, ...]:
        results: list[MetricCalculationResult] = []
        for metric_name, definition in STARTUP_METRICS.items():
            candidates = _available_candidates(definition, tuple(facts))
            if candidates is None:
                continue
            result = self.calculate(metric_name, candidates, assumptions=assumptions)
            if result.status is MetricStatus.CALCULATED:
                results.append(result)
        return tuple(results)

    def calculate_scenario(
        self,
        metric_key: str,
        inputs: Mapping[str, ScenarioRange],
    ) -> ScenarioMetric:
        normalized_key = _normalize_scenario_metric_key(metric_key)
        formula = _SCENARIO_FORMULAS.get(normalized_key)
        if formula is None:
            raise KeyError(f"unknown_startup_scenario_metric:{metric_key}")
        missing = tuple(key for key in formula.required_inputs if key not in inputs)
        dependency_refs = _scenario_dependency_refs(normalized_key, inputs)
        if missing:
            return _scenario_metric_gap(
                normalized_key,
                formula,
                tuple(f"input.missing:{key}" for key in missing),
                dependency_refs=dependency_refs,
            )
        denominator_gap = _scenario_denominator_gap(normalized_key, inputs)
        if denominator_gap is not None:
            return _scenario_metric_gap(
                normalized_key,
                formula,
                (denominator_gap,),
                dependency_refs=dependency_refs,
            )
        domain_gap = _scenario_domain_gap(normalized_key, inputs)
        if domain_gap is not None:
            return _scenario_metric_gap(
                normalized_key,
                formula,
                (domain_gap,),
                dependency_refs=dependency_refs,
            )
        value_range = _calculate_scenario_range(normalized_key, inputs)
        if value_range is None:
            return _scenario_metric_gap(
                normalized_key,
                formula,
                (f"ineligible.{normalized_key}:revenue_exceeds_expenses",),
                dependency_refs=dependency_refs,
            )
        unit, period = _scenario_unit_period(formula.unit)
        return ScenarioMetric(
            metric_id=_scenario_metric_id(normalized_key, value_range),
            case_id=_SCENARIO_CASE_ID,
            data_revision=1,
            metric_key=normalized_key,
            value_range=value_range,
            unit=unit,
            period=period,
            provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
            dependency_refs=dependency_refs,
            formula_key=normalized_key,
            formula_description=formula.description,
            confidence=cast(ScenarioConfidence, formula.confidence),
            rationale=formula.rationale,
            validation_plan=formula.validation_plan,
            what_would_confirm=formula.what_would_confirm,
            acceptance="proposed",
        )

    def calculate_for_case(
        self,
        case_id: UUID,
        metric_name: str,
        *,
        evidence_fact_ids: Sequence[UUID],
        assumptions: Mapping[str, str] | None = None,
    ) -> MetricCalculationResult:
        if self._evidence_repository is None or self._calculation_repository is None:
            raise ValueError("startup_metric_repositories_required")

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

        result = self.calculate(metric_name, tuple(selected), assumptions=assumptions)
        if result.status is not MetricStatus.CALCULATED:
            return result

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


def _select_exact(
    definition: StartupMetricDefinition,
    facts: tuple[EvidenceFact, ...],
    assumptions: Mapping[str, str],
) -> tuple[dict[str, tuple[EvidenceFact, ...]], str | None]:
    assumption_warning = _validate_assumptions(definition, assumptions)
    if assumption_warning is not None:
        return {}, assumption_warning

    expected_names = {_norm(slot.fact_name) for slot in definition.slots}
    for fact in facts:
        if _norm(fact.name) not in expected_names:
            return {}, "input.unexpected"
        if _period_key(fact.period) is None:
            return {}, "period.invalid"

    current_period = _current_period(facts)
    if current_period == "__MIXED__":
        return {}, "period.mismatch"
    prior_period = _prior_period(facts, current_period)
    if _has_duplicate_single_slots(definition, facts):
        return {}, _duplicate_warning(definition, facts, current_period, prior_period)

    selected: dict[str, tuple[EvidenceFact, ...]] = {}
    used_ids: set[UUID] = set()
    for slot in definition.slots:
        candidates = _slot_candidates(slot, facts, used_ids, current_period, prior_period)
        if not candidates:
            if _has_same_name_unused(slot, facts, used_ids):
                return selected, "period.mismatch"
            return selected, f"input.missing:{slot.slot}"
        if len(candidates) > 1 and slot.aggregation != "sum":
            return selected, f"input.duplicate:{slot.slot}"
        selected[slot.slot] = tuple(sorted(candidates, key=lambda fact: str(fact.id)))
        used_ids.update(fact.id for fact in candidates)

    if len(used_ids) != len(facts):
        return selected, "input.unexpected"

    warning = _validate_units(definition, selected)
    if warning is not None:
        return selected, warning
    warning = _validate_cohorts(definition, selected)
    return selected, warning


def _validate_assumptions(
    definition: StartupMetricDefinition,
    assumptions: Mapping[str, str],
) -> str | None:
    for required in definition.required_assumptions:
        actual = assumptions.get(required)
        if actual is None:
            return f"assumption.missing:{required}"
        if actual != _LTV_MODEL:
            return f"assumption.unsupported:{required}"
    if definition.name == "rule_of_40" and (
        assumptions.get("business_model") != "saas" or assumptions.get("stage") != "growth"
    ):
        return "condition.inapplicable:rule_of_40"
    return None


def _slot_candidates(
    slot: StartupMetricInput,
    facts: tuple[EvidenceFact, ...],
    used_ids: set[UUID],
    current_period: str | None,
    prior_period: str | None,
) -> list[EvidenceFact]:
    expected_period = {"single": current_period, "current": current_period, "prior": prior_period}[
        slot.period_role
    ]
    return [
        fact
        for fact in facts
        if fact.id not in used_ids
        and _norm(fact.name) == _norm(slot.fact_name)
        and fact.period == expected_period
    ]


def _has_same_name_unused(
    slot: StartupMetricInput,
    facts: tuple[EvidenceFact, ...],
    used_ids: set[UUID],
) -> bool:
    return any(_norm(fact.name) == _norm(slot.fact_name) and fact.id not in used_ids for fact in facts)


def _has_duplicate_single_slots(
    definition: StartupMetricDefinition,
    facts: tuple[EvidenceFact, ...],
) -> bool:
    multi_names = {
        _norm(slot.fact_name)
        for slot in definition.slots
        if slot.aggregation == "sum" or _slot_name_count(definition, slot.fact_name) > 1
    }
    seen: set[tuple[str, str | None]] = set()
    for fact in facts:
        key = (_norm(fact.name), fact.period)
        if key in seen and key[0] not in multi_names:
            return True
        seen.add(key)
    return False


def _slot_name_count(definition: StartupMetricDefinition, fact_name: str) -> int:
    normalized = _norm(fact_name)
    return sum(1 for slot in definition.slots if _norm(slot.fact_name) == normalized)


def _duplicate_warning(
    definition: StartupMetricDefinition,
    facts: tuple[EvidenceFact, ...],
    current_period: str | None,
    prior_period: str | None,
) -> str:
    counts: dict[tuple[str, str | None], int] = {}
    for fact in facts:
        key = (_norm(fact.name), fact.period)
        counts[key] = counts.get(key, 0) + 1
    duplicated = {key for key, count in counts.items() if count > 1}
    for slot in definition.slots:
        expected_period = {"single": current_period, "current": current_period, "prior": prior_period}[
            slot.period_role
        ]
        if (_norm(slot.fact_name), expected_period) in duplicated:
            return f"input.duplicate:{slot.slot}"
    return "input.duplicate"


def _current_period(facts: tuple[EvidenceFact, ...]) -> str | None:
    periods = [
        (key, fact.period)
        for fact in facts
        for key in [_period_key(fact.period)]
        if key is not None
    ]
    if not periods:
        return None
    kinds = {key[2] for key, _period in periods}
    if len(kinds) > 1:
        return "__MIXED__"
    return max(periods)[1]


def _prior_period(facts: tuple[EvidenceFact, ...], current_period: str | None) -> str | None:
    current_key = _period_key(current_period)
    if current_key is None:
        return None
    candidates = [
        (key, fact.period)
        for fact in facts
        for key in [_period_key(fact.period)]
        if key is not None and key[2] == current_key[2] and key < current_key
    ]
    if not candidates:
        return None
    return max(candidates)[1]


def _period_key(period: str | None) -> tuple[int, int, str] | None:
    if period is None:
        return None
    if match := re.fullmatch(r"(\d{4})", period):
        return (int(match.group(1)), 0, "annual")
    if match := re.fullmatch(r"(\d{4})-Q([1-4])", period):
        return (int(match.group(1)), int(match.group(2)), "quarterly")
    if match := re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", period):
        return (int(match.group(1)), int(match.group(2)), "monthly")
    return None


def _validate_units(
    definition: StartupMetricDefinition,
    selected: dict[str, tuple[EvidenceFact, ...]],
) -> str | None:
    currencies: set[str] = set()
    monthly_currencies: set[str] = set()
    for slot in definition.slots:
        for fact in selected[slot.slot]:
            normalized = _norm_unit(fact.unit)
            if slot.unit_policy == "currency":
                if not _is_supported_currency(normalized):
                    return f"unit.unsupported:{slot.slot}"
                if normalized in {"ratio", "count", "months"} or normalized.endswith("/month"):
                    return f"unit.mismatch:{slot.slot}"
                currencies.add(normalized)
            if slot.unit_policy == "currency_per_month":
                if not normalized.endswith("/month"):
                    return f"unit.mismatch:{slot.slot}"
                if not _is_supported_currency(normalized.removesuffix("/month")):
                    return f"unit.unsupported:{slot.slot}"
                monthly_currencies.add(normalized.removesuffix("/month"))
            if slot.unit_policy == "ratio" and normalized != "ratio":
                return f"unit.mismatch:{slot.slot}"
            if slot.unit_policy == "count" and normalized != "count":
                return f"unit.mismatch:{slot.slot}"
    if len(currencies) > 1 or len(monthly_currencies) > 1:
        return "unit.currency_mismatch"
    if currencies and monthly_currencies and currencies != monthly_currencies:
        return "unit.currency_mismatch"
    return None


def _validate_cohorts(
    definition: StartupMetricDefinition,
    selected: dict[str, tuple[EvidenceFact, ...]],
) -> str | None:
    if definition.name != "cohort_retention":
        return None
    starts = selected["starting_cohort_customers"]
    ends = selected["ending_cohort_customers"]
    cohort_ids = {fact.metadata.get("cohort_id", "") for fact in (*starts, *ends)}
    if "" in cohort_ids or len(cohort_ids) != 1:
        return "cohort.mismatch"
    start_period = starts[0].metadata.get("cohort_start_period")
    end_start_period = ends[0].metadata.get("cohort_start_period")
    if not start_period or start_period != end_start_period:
        return "cohort.mismatch"
    return None


def _result_unit(
    definition: StartupMetricDefinition,
    selected: dict[str, tuple[EvidenceFact, ...]],
) -> str:
    if definition.unit == "currency":
        currency = _currency(selected)
        return currency or "currency"
    if definition.unit == "currency_per_month":
        currency = _currency(selected)
        return f"{currency}/month" if currency else "currency/month"
    return definition.unit


def _currency(selected: dict[str, tuple[EvidenceFact, ...]]) -> str | None:
    for slot_facts in selected.values():
        for fact in slot_facts:
            unit = _norm_unit(fact.unit)
            if unit.endswith("/month"):
                return unit.removesuffix("/month").upper()
            if unit not in {"ratio", "count", "months"}:
                return unit.upper()
    return None


def _result_period(
    definition: StartupMetricDefinition,
    selected: dict[str, tuple[EvidenceFact, ...]],
) -> str:
    for slot in definition.slots:
        if slot.period_role in {"single", "current"}:
            slot_facts = selected.get(slot.slot)
            if slot_facts:
                return slot_facts[0].period or ""
    for slot_facts in selected.values():
        if slot_facts:
            return slot_facts[0].period or ""
    return ""


def _ordered_ids(
    definition: StartupMetricDefinition,
    selected: dict[str, tuple[EvidenceFact, ...]],
) -> tuple[UUID, ...]:
    return tuple(
        fact.id
        for slot in definition.slots
        for fact in selected.get(slot.slot, ())
    )


def _insufficient(
    definition: StartupMetricDefinition,
    warning: str,
    selected: dict[str, tuple[EvidenceFact, ...]],
) -> MetricCalculationResult:
    return MetricCalculationResult(
        status=MetricStatus.INSUFFICIENT_DATA,
        metric_name=definition.name,
        formula_version=definition.formula_version,
        value=None,
        display_value=None,
        unit=definition.unit,
        period=_result_period(definition, selected) if selected else "",
        input_evidence_ids=_ordered_ids(definition, selected) if selected else (),
        warnings=(warning,),
    )


def _norm(value: str) -> str:
    return value.strip().casefold()


def _available_candidates(
    definition: StartupMetricDefinition,
    facts: tuple[EvidenceFact, ...],
) -> tuple[EvidenceFact, ...] | None:
    if definition.name == "cohort_retention":
        return _available_cohort_candidates(facts)
    required_names = {_norm(slot.fact_name) for slot in definition.slots}
    if not required_names.issubset({_norm(fact.name) for fact in facts}):
        return None
    relevant = tuple(fact for fact in facts if _norm(fact.name) in required_names)
    periods = [
        (key, fact.period)
        for fact in relevant
        for key in [_period_key(fact.period)]
        if key is not None
    ]
    if not periods:
        return relevant
    kinds = {key[2] for key, _period in periods}
    if len(kinds) > 1:
        return relevant
    current_period = max(periods)[1]
    current_key = _period_key(current_period)
    prior_period = None
    if current_key is not None:
        prior_candidates = [
            (key, period)
            for key, period in periods
            if key[2] == current_key[2] and key < current_key
        ]
        if prior_candidates:
            prior_period = max(prior_candidates)[1]

    selected: list[EvidenceFact] = []
    for slot in definition.slots:
        period = {"single": current_period, "current": current_period, "prior": prior_period}[
            slot.period_role
        ]
        if period is None:
            return None
        selected.extend(
            fact
            for fact in relevant
            if _norm(fact.name) == _norm(slot.fact_name) and fact.period == period
        )
    return tuple(selected)


def _available_cohort_candidates(facts: tuple[EvidenceFact, ...]) -> tuple[EvidenceFact, ...] | None:
    starts = [
        fact
        for fact in facts
        if _norm(fact.name) == "starting_cohort_customers" and _period_key(fact.period) is not None
    ]
    ends = [
        fact
        for fact in facts
        if _norm(fact.name) == "ending_cohort_customers" and _period_key(fact.period) is not None
    ]
    if not starts or not ends:
        return None
    pairs: list[tuple[tuple[int, int, str], str, EvidenceFact, EvidenceFact]] = []
    for start in starts:
        cohort_id = start.metadata.get("cohort_id")
        cohort_start_period = start.metadata.get("cohort_start_period")
        if not cohort_id or not cohort_start_period:
            continue
        for end in ends:
            if end.metadata.get("cohort_id") != cohort_id:
                continue
            if end.metadata.get("cohort_start_period") != cohort_start_period:
                continue
            end_key = _period_key(end.period)
            if end_key is None:
                continue
            pairs.append((end_key, str(start.id), start, end))
    if not pairs:
        return None
    pairs.sort(key=lambda item: (item[0], item[1]), reverse=True)
    latest_end_key = pairs[0][0]
    latest_pairs = [pair for pair in pairs if pair[0] == latest_end_key]
    if len(latest_pairs) > 1:
        return tuple(fact for _key, _id, start, end in latest_pairs for fact in (start, end))
    _key, _id, start, end = latest_pairs[0]
    return (start, end)


def _norm_unit(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip().casefold()
    aliases = {
        "$": "usd",
        "percent": "ratio",
        "%": "ratio",
        "customers": "count",
        "customer": "count",
        "months": "months",
    }
    return aliases.get(normalized, normalized)


def _is_supported_currency(unit: str) -> bool:
    return unit.upper() in _SUPPORTED_CURRENCIES


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


def _require_utc_clock(clock: Callable[[], datetime] | None) -> datetime:
    if clock is None:
        raise ValueError("startup_metric_clock_required")
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


class _ScenarioFormula:
    def __init__(
        self,
        *,
        required_inputs: tuple[str, ...],
        unit: str,
        description: str,
        rationale: str,
        validation_plan: str,
        what_would_confirm: str,
        confidence: str = "medium",
    ) -> None:
        self.required_inputs = required_inputs
        self.unit = unit
        self.description = description
        self.rationale = rationale
        self.validation_plan = validation_plan
        self.what_would_confirm = what_would_confirm
        self.confidence = confidence


_SCENARIO_FORMULAS = {
    "mrr": _ScenarioFormula(
        required_inputs=("monthly_price", "paying_customers"),
        unit="KZT/month",
        description="Monthly price multiplied by projected paying customers.",
        rationale="Planning MRR is derived from accepted pricing and customer-count assumptions.",
        validation_plan="Validate against signed customers and invoices after launch.",
        what_would_confirm="Signed paid customers and invoices for the forecast month.",
    ),
    "arr": _ScenarioFormula(
        required_inputs=("mrr",),
        unit="KZT/year",
        description="Monthly recurring revenue multiplied by 12.",
        rationale="Planning ARR annualizes the selected scenario MRR.",
        validation_plan="Validate once MRR is evidenced for a stable month.",
        what_would_confirm="A verified MRR source fact for a representative month.",
    ),
    "gross_margin": _ScenarioFormula(
        required_inputs=("revenue", "cogs"),
        unit="ratio/month",
        description="Revenue minus cost of goods sold divided by revenue.",
        rationale="Planning gross margin compares expected delivery cost against revenue.",
        validation_plan="Validate using invoices, cloud bills, support costs and recognized revenue.",
        what_would_confirm="Recognized revenue and cost-of-goods evidence for the same period.",
    ),
    "net_burn": _ScenarioFormula(
        required_inputs=("monthly_operating_expenses", "monthly_revenue"),
        unit="KZT/month",
        description="Monthly operating expenses minus monthly revenue.",
        rationale="Planning net burn estimates monthly cash consumption.",
        validation_plan="Validate using bank, payroll, expense and revenue records.",
        what_would_confirm="Monthly revenue and expense source facts for the same period.",
    ),
    "runway": _ScenarioFormula(
        required_inputs=("cash_balance", "net_burn"),
        unit="months/month",
        description="Cash balance divided by positive monthly net burn.",
        rationale="Planning runway is meaningful only when the scenario burns cash.",
        validation_plan="Validate using cash balance and monthly burn evidence.",
        what_would_confirm="A current cash balance and positive net burn source fact.",
    ),
    "cac": _ScenarioFormula(
        required_inputs=("acquisition_spend", "acquired_customers"),
        unit="KZT/customer",
        description="Acquisition spend divided by acquired customers.",
        rationale="Planning CAC estimates paid acquisition efficiency.",
        validation_plan="Validate using channel spend and customer acquisition records.",
        what_would_confirm="Attributed acquisition spend and acquired customer counts.",
    ),
    "ltv": _ScenarioFormula(
        required_inputs=("arpa", "gross_margin", "churn"),
        unit="KZT/customer",
        description="ARPA multiplied by gross margin and divided by churn.",
        rationale="Planning LTV requires eligible ARPA, gross margin and non-zero churn.",
        validation_plan="Validate using cohort retention and revenue evidence.",
        what_would_confirm="Observed cohort churn or a cited comparable churn benchmark.",
        confidence="low",
    ),
    "ltv_cac": _ScenarioFormula(
        required_inputs=("ltv", "cac"),
        unit="ratio/customer",
        description="LTV divided by CAC.",
        rationale="Planning LTV/CAC compares customer value against acquisition cost.",
        validation_plan="Validate after LTV and CAC are independently evidenced.",
        what_would_confirm="Eligible LTV and CAC calculations for the same customer segment.",
    ),
    "cac_payback": _ScenarioFormula(
        required_inputs=("cac", "arpa", "gross_margin"),
        unit="months/customer",
        description="CAC divided by ARPA multiplied by gross margin.",
        rationale="Planning CAC payback estimates months to recover acquisition spend.",
        validation_plan="Validate using CAC, ARPA and gross margin evidence.",
        what_would_confirm="Eligible CAC, ARPA and gross margin for the same segment.",
    ),
}


def _calculate_scenario_range(
    metric_key: str,
    inputs: Mapping[str, ScenarioRange],
) -> ScenarioRange | None:
    if metric_key == "mrr":
        return _range_mul(inputs["monthly_price"], inputs["paying_customers"])
    if metric_key == "arr":
        return _range_mul(inputs["mrr"], ScenarioRange(lower=Decimal("12"), upper=Decimal("12")))
    if metric_key == "gross_margin":
        revenue = inputs["revenue"]
        cogs = inputs["cogs"]
        return ScenarioRange(
            lower=_q((revenue.lower - cogs.upper) / revenue.lower),
            upper=_q((revenue.upper - cogs.lower) / revenue.upper),
        )
    if metric_key == "net_burn":
        expenses = inputs["monthly_operating_expenses"]
        revenue = inputs["monthly_revenue"]
        lower = expenses.lower - revenue.upper
        upper = expenses.upper - revenue.lower
        if upper <= 0:
            return None
        return ScenarioRange(lower=_q(max(lower, Decimal("0"))), upper=_q(upper))
    if metric_key == "runway":
        return _range_div(inputs["cash_balance"], inputs["net_burn"])
    if metric_key == "cac":
        return _range_div(inputs["acquisition_spend"], inputs["acquired_customers"])
    if metric_key == "ltv":
        arpa_margin = _range_mul(inputs["arpa"], inputs["gross_margin"])
        return _range_div(arpa_margin, inputs["churn"])
    if metric_key == "ltv_cac":
        return _range_div(inputs["ltv"], inputs["cac"])
    if metric_key == "cac_payback":
        arpa_margin = _range_mul(inputs["arpa"], inputs["gross_margin"])
        return _range_div(inputs["cac"], arpa_margin)
    raise KeyError(f"unknown_startup_scenario_metric:{metric_key}")


def _scenario_denominator_gap(metric_key: str, inputs: Mapping[str, ScenarioRange]) -> str | None:
    denominators = {
        "gross_margin": ("revenue",),
        "runway": ("net_burn",),
        "cac": ("acquired_customers",),
        "ltv": ("churn",),
        "ltv_cac": ("cac",),
        "cac_payback": ("arpa", "gross_margin"),
    }.get(metric_key, ())
    for key in denominators:
        if key in inputs and inputs[key].lower <= 0:
            return f"denominator.non_positive:{key}"
    return None


def _scenario_domain_gap(metric_key: str, inputs: Mapping[str, ScenarioRange]) -> str | None:
    if metric_key == "gross_margin":
        revenue = inputs["revenue"]
        cogs = inputs["cogs"]
        if cogs.lower > revenue.upper:
            return "ineligible.gross_margin:cogs_exceeds_revenue"
        if cogs.upper > revenue.lower:
            return "ineligible.gross_margin:range_crosses_negative_margin"
    return None


def _range_mul(left: ScenarioRange, right: ScenarioRange) -> ScenarioRange:
    products = (
        left.lower * right.lower,
        left.lower * right.upper,
        left.upper * right.lower,
        left.upper * right.upper,
    )
    return ScenarioRange(lower=_q(min(products)), upper=_q(max(products)))


def _range_div(numerator: ScenarioRange, denominator: ScenarioRange) -> ScenarioRange:
    values = (
        numerator.lower / denominator.lower,
        numerator.lower / denominator.upper,
        numerator.upper / denominator.lower,
        numerator.upper / denominator.upper,
    )
    return ScenarioRange(lower=_q(min(values)), upper=_q(max(values)))


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01")).normalize()


def _scenario_metric_gap(
    metric_key: str,
    formula: _ScenarioFormula,
    gaps: tuple[str, ...],
    *,
    dependency_refs: tuple[UUID, ...],
) -> ScenarioMetric:
    unit, period = _scenario_unit_period(formula.unit)
    return ScenarioMetric(
        metric_id=uuid5(_SCENARIO_NAMESPACE, f"scenario-metric-gap:{metric_key}:{','.join(gaps)}"),
        case_id=_SCENARIO_CASE_ID,
        data_revision=1,
        metric_key=metric_key,
        value_range=None,
        unit=unit,
        period=period,
        provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
        dependency_refs=dependency_refs or (uuid5(_SCENARIO_NAMESPACE, f"scenario-gap:{metric_key}"),),
        formula_key=metric_key,
        formula_description=formula.description,
        confidence="low",
        rationale=formula.rationale,
        validation_plan=formula.validation_plan,
        what_would_confirm=formula.what_would_confirm,
        acceptance="proposed",
        gaps=gaps,
    )


def _scenario_dependency_refs(metric_key: str, inputs: Mapping[str, ScenarioRange]) -> tuple[UUID, ...]:
    refs: list[UUID] = []
    for key in sorted(inputs):
        if key in _SCENARIO_FORMULAS:
            refs.append(_scenario_metric_id(key, inputs[key]))
        else:
            refs.append(_scenario_input_id(metric_key, key, inputs[key]))
    return tuple(refs)


def _scenario_metric_id(metric_key: str, value_range: ScenarioRange) -> UUID:
    return uuid5(
        _SCENARIO_NAMESPACE,
        f"scenario-metric:{metric_key}:{value_range.lower}:{value_range.upper}",
    )


def _scenario_input_id(metric_key: str, input_key: str, value_range: ScenarioRange) -> UUID:
    return uuid5(
        _SCENARIO_NAMESPACE,
        f"scenario-input:{metric_key}:{input_key}:{value_range.lower}:{value_range.upper}",
    )


def _normalize_scenario_metric_key(metric_key: str) -> str:
    normalized = metric_key.strip().casefold()
    aliases = {
        "runway_months": "runway",
        "cac_payback_months": "cac_payback",
    }
    return aliases.get(normalized, normalized)


def _scenario_unit_period(value: str) -> tuple[str, str]:
    if "/" not in value:
        return value, "point_in_time"
    unit, period = value.split("/", 1)
    return unit, period

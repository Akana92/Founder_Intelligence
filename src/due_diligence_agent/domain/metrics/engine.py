from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from due_diligence_agent.domain.common import require_decimal
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.metrics.definitions import PUBLIC_METRICS, QUANT, MetricDefinition


class MetricStatus(StrEnum):
    CALCULATED = "calculated"
    INSUFFICIENT_DATA = "insufficient_data"


class MetricCalculationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MetricStatus
    metric_name: str
    formula_version: str
    value: Decimal | None
    display_value: str | None
    unit: str
    period: str
    input_evidence_ids: tuple[UUID, ...] = ()
    warnings: tuple[str, ...] = ()
    calculation_id: UUID | None = None

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, float):
            raise ValueError("metric value must be Decimal, not float")
        checked = require_decimal(value)
        if not checked.is_finite():
            raise ValueError("metric value must be finite")
        return Decimal("0.000000") if checked == 0 else checked

    @model_validator(mode="after")
    def validate_status_shape(self) -> "MetricCalculationResult":
        if self.status is MetricStatus.CALCULATED:
            if self.value is None or self.display_value is None or self.warnings:
                raise ValueError("calculated metrics require value/display and no warnings")
        if self.status is MetricStatus.INSUFFICIENT_DATA and self.value is not None:
            raise ValueError("insufficient metrics cannot carry a value")
        return self


class MetricEngine:
    def calculate(
        self,
        metric_name: str,
        facts: tuple[EvidenceFact, ...] | list[EvidenceFact],
        *,
        as_of: datetime | None = None,
    ) -> MetricCalculationResult:
        try:
            definition = PUBLIC_METRICS[metric_name]
        except KeyError as exc:
            raise KeyError(f"unknown_metric:{metric_name}") from exc

        selected, warning = _select_exact(definition, tuple(facts))
        if warning is not None:
            return _insufficient(definition, warning, selected)
        warning = _validate_as_of(definition, selected, as_of)
        if warning is not None:
            return _insufficient(definition, warning, selected)

        values: dict[str, Decimal] = {}
        for slot in definition.slots:
            fact = selected[slot.name]
            try:
                value = require_decimal(fact.value)
            except (InvalidOperation, ValueError):
                return _insufficient(definition, f"input.non_numeric:{slot.name}", selected)
            if not value.is_finite():
                return _insufficient(definition, f"input.non_numeric:{slot.name}", selected)
            values[slot.name] = value

        if definition.name == "free_cash_flow" and values["capital_expenditures"] < 0:
            return _insufficient(definition, "capex.negative", selected)
        for slot_name in definition.denominator_slots:
            if values[slot_name] <= 0:
                return _insufficient(definition, f"denominator.non_positive:{slot_name}", selected)

        with localcontext() as context:
            context.prec = 50
            value = definition.formula(values).quantize(QUANT, rounding=ROUND_HALF_EVEN)
        if value == 0:
            value = Decimal("0.000000")
        display = value.quantize(
            Decimal("1").scaleb(-definition.display_places), rounding=ROUND_HALF_EVEN
        )
        unit = "ratio" if definition.unit_policy == "ratio" else _currency_unit(selected)
        period = _result_period(definition, selected)
        return MetricCalculationResult(
            status=MetricStatus.CALCULATED,
            metric_name=definition.name,
            formula_version=definition.formula_version,
            value=value,
            display_value=format(display, f".{definition.display_places}f"),
            unit=unit,
            period=period,
            input_evidence_ids=tuple(selected[slot.name].id for slot in definition.slots),
        )


def public_metric_names() -> tuple[str, ...]:
    return tuple(PUBLIC_METRICS)


def _select_exact(
    definition: MetricDefinition, facts: tuple[EvidenceFact, ...]
) -> tuple[dict[str, EvidenceFact], str | None]:
    expected_names = {_norm(slot.fact_name) for slot in definition.slots}
    market_names = {_norm(slot.fact_name) for slot in definition.slots if slot.period_role == "market_as_of"}
    for fact in facts:
        fact_name = _norm(fact.name)
        if fact_name not in expected_names:
            return {}, "input.unexpected"
        if _is_market_date(fact.period) and fact_name not in market_names:
            return {}, "period.invalid"
        if _period_key(fact.period) is None and not _is_market_date(fact.period):
            return {}, "period.invalid"
    current_period = _current_financial_period(facts)
    if current_period == "__MIXED__":
        return {}, "period.mismatch"
    prior_period = _available_prior_period(facts, current_period)
    if _has_duplicate_name_period(facts):
        return {}, _duplicate_warning(definition, facts, current_period, prior_period)
    if len(facts) > len(definition.slots):
        return {}, "input.unexpected"

    selected: dict[str, EvidenceFact] = {}
    used_ids: set[UUID] = set()
    for slot in definition.slots:
        expected_period = {
            "single": current_period,
            "current": current_period,
            "prior": prior_period,
            "market_as_of": None,
        }[slot.period_role]
        candidates = [
            fact
            for fact in facts
            if _norm(fact.name) == _norm(slot.fact_name)
            and fact.id not in used_ids
            and (slot.period_role == "market_as_of" or fact.period == expected_period)
        ]
        if not candidates:
            same_name_unused = any(
                _norm(fact.name) == _norm(slot.fact_name) and fact.id not in used_ids
                for fact in facts
            )
            if same_name_unused and slot.period_role != "market_as_of":
                return selected, "period.mismatch"
            return selected, f"input.missing:{slot.name}"
        if len(candidates) > 1:
            return selected, f"input.duplicate:{slot.name}"
        selected[slot.name] = candidates[0]
        used_ids.add(candidates[0].id)

    if len(used_ids) != len(facts):
        return selected, "input.unexpected"
    warning = _validate_periods(definition, selected, current_period, prior_period)
    if warning is not None:
        return selected, warning
    warning = _validate_units(definition, selected)
    return selected, warning


def _norm(value: str) -> str:
    return value.strip().casefold()


def _has_duplicate_name_period(facts: tuple[EvidenceFact, ...]) -> bool:
    seen: set[tuple[str, str | None]] = set()
    for fact in facts:
        key = (_norm(fact.name), fact.period)
        if key in seen:
            return True
        seen.add(key)
    return False


def _duplicate_warning(
    definition: MetricDefinition,
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
        expected_period = {
            "single": current_period,
            "current": current_period,
            "prior": prior_period,
            "market_as_of": None,
        }[slot.period_role]
        for name, period in duplicated:
            if name == _norm(slot.fact_name) and (
                slot.period_role == "market_as_of" or period == expected_period
            ):
                return f"input.duplicate:{slot.name}"
    return "input.duplicate"


def _current_financial_period(facts: tuple[EvidenceFact, ...]) -> str | None:
    periods = [
        (key, fact.period)
        for fact in facts
        if not _is_market_date(fact.period)
        for key in [_period_key(fact.period)]
        if key is not None
    ]
    if not periods:
        return None
    kinds = {key[2] for key, _period in periods}
    if len(kinds) > 1:
        return "__MIXED__"
    return max(periods)[1]


def _period_key(period: str | None) -> tuple[int, int, str] | None:
    if period is None:
        return None
    if match := re.fullmatch(r"(\d{4})", period):
        return (int(match.group(1)), 0, "annual")
    if match := re.fullmatch(r"(\d{4})-Q([1-4])", period):
        return (int(match.group(1)), int(match.group(2)), "quarterly")
    return None


def _is_market_date(period: str | None) -> bool:
    return bool(period and re.fullmatch(r"\d{4}-\d{2}-\d{2}", period))


def _available_prior_period(facts: tuple[EvidenceFact, ...], current_period: str | None) -> str | None:
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


def _validate_periods(
    definition: MetricDefinition,
    selected: dict[str, EvidenceFact],
    current_period: str | None,
    prior_period: str | None,
) -> str | None:
    if current_period == "__MIXED__" or current_period is None:
        return "period.mismatch"
    for slot in definition.slots:
        period = selected[slot.name].period
        if slot.period_role == "market_as_of":
            if not _is_market_date(period):
                return "period.invalid"
            continue
        if _period_key(period) is None:
            return "period.invalid"
        expected = prior_period if slot.period_role == "prior" else current_period
        if period != expected:
            return "period.mismatch"
    return None


def _validate_as_of(
    definition: MetricDefinition,
    selected: dict[str, EvidenceFact],
    as_of: datetime | None,
) -> str | None:
    for slot in definition.slots:
        if slot.period_role != "market_as_of":
            continue
        fact = selected[slot.name]
        if as_of is None:
            return "as_of.required"
        if fact.period != as_of.date().isoformat():
            return "as_of.mismatch:market_cap"
    return None


def _validate_units(definition: MetricDefinition, selected: dict[str, EvidenceFact]) -> str | None:
    for slot in definition.slots:
        fact = selected[slot.name]
        if slot.unit_kind == "shares" and fact.unit != "shares":
            return "unit.mismatch"
    units = {
        selected[slot.name].unit
        for slot in definition.slots
        if slot.unit_kind == "currency"
    }
    if len(units) > 1:
        return "unit.mismatch"
    return None


def _currency_unit(selected: dict[str, EvidenceFact]) -> str:
    return next(fact.unit for fact in selected.values() if fact.unit is not None)


def _result_period(definition: MetricDefinition, selected: dict[str, EvidenceFact]) -> str:
    for slot in definition.slots:
        if slot.period_role in {"single", "current"}:
            period = selected[slot.name].period
            if period is not None:
                return period
    return ""


def _insufficient(
    definition: MetricDefinition,
    warning: str,
    selected: dict[str, EvidenceFact] | None = None,
) -> MetricCalculationResult:
    return MetricCalculationResult(
        status=MetricStatus.INSUFFICIENT_DATA,
        metric_name=definition.name,
        formula_version=definition.formula_version,
        value=None,
        display_value=None,
        unit="ratio" if definition.unit_policy == "ratio" else "",
        period=_result_period(definition, selected) if selected else "",
        input_evidence_ids=tuple(selected[slot.name].id for slot in definition.slots if slot.name in selected)
        if selected
        else (),
        warnings=(warning,),
    )

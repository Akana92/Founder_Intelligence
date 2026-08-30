from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.common import require_decimal
from due_diligence_agent.domain.startup.case_intake import CaseValueKind


ScenarioAcceptance = Literal["proposed", "accepted", "rejected", "needs_validation"]
ScenarioConfidence = Literal["low", "medium", "high"]
ScenarioKey = Literal["conservative", "base", "optimistic"]


class ScenarioRange(BaseModel):
    """A bounded Decimal range; no calculations are performed here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lower: Decimal
    upper: Decimal

    @field_validator("lower", "upper", mode="before")
    @classmethod
    def validate_decimal(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @model_validator(mode="after")
    def validate_range(self) -> "ScenarioRange":
        if self.lower < 0 or self.upper < 0:
            raise ValueError("scenario ranges must be non-negative")
        if self.lower > self.upper:
            raise ValueError("scenario range requires lower <= upper")
        if _decimal_places(self.lower) > 2 or _decimal_places(self.upper) > 2:
            raise ValueError("scenario range rejects fake precision")
        return self


class ScenarioInput(BaseModel):
    """One explicit assumption or sourced input for a scenario."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_id: UUID = Field(default_factory=uuid4)
    case_id: UUID | None = None
    data_revision: int | None = Field(default=None, ge=1)
    input_key: str
    value_range: ScenarioRange
    unit: str
    period: str | None = None
    provenance: CaseValueKind
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    dependency_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    confidence: ScenarioConfidence
    rationale: str
    validation_plan: str
    what_would_confirm: str = "Independent source evidence or founder validation of this planning input."
    acceptance: ScenarioAcceptance

    @field_validator(
        "input_key",
        "unit",
        "rationale",
        "validation_plan",
        "what_would_confirm",
        mode="before",
    )
    @classmethod
    def validate_text(cls, value: Any) -> str:
        return _normalize_required_text(value)

    @field_validator("period", mode="before")
    @classmethod
    def validate_period(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value)

    @model_validator(mode="after")
    def enforce_input_contract(self) -> "ScenarioInput":
        period = self.period or _legacy_period_from_unit(self.unit)
        if period is None:
            raise ValueError("scenario values require currency/period units")
        object.__setattr__(self, "period", period)
        _validate_currency_period_unit(self.unit, period=period)
        _validate_provenance_refs(
            provenance=self.provenance,
            source_refs=self.source_refs,
            dependency_refs=self.dependency_refs,
            acceptance=self.acceptance,
            context="scenario provenance",
        )
        return self


class ScenarioMetric(BaseModel):
    """One projected metric derived elsewhere and referenced here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    data_revision: int = Field(ge=1)
    metric_key: str
    value_range: ScenarioRange | None
    unit: str
    period: str | None = None
    provenance: CaseValueKind
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    dependency_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    formula_key: str
    formula_description: str
    confidence: ScenarioConfidence
    rationale: str
    validation_plan: str
    what_would_confirm: str = "Independent source evidence or founder validation of this scenario metric."
    acceptance: ScenarioAcceptance
    gaps: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator(
        "metric_key",
        "unit",
        "rationale",
        "validation_plan",
        "what_would_confirm",
        mode="before",
    )
    @classmethod
    def validate_text(cls, value: Any) -> str:
        return _normalize_required_text(value)

    @field_validator("period", mode="before")
    @classmethod
    def validate_period(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value)

    @field_validator("formula_key", "formula_description", mode="before")
    @classmethod
    def validate_formula_text(cls, value: Any) -> str:
        return _normalize_required_text(value, field_name="formula metadata")

    @model_validator(mode="after")
    def enforce_metric_contract(self) -> "ScenarioMetric":
        period = self.period or _legacy_period_from_unit(self.unit)
        if period is None:
            raise ValueError("scenario values require currency/period units")
        object.__setattr__(self, "period", period)
        _validate_currency_period_unit(self.unit, period=period)
        _validate_provenance_refs(
            provenance=self.provenance,
            source_refs=self.source_refs,
            dependency_refs=self.dependency_refs,
            acceptance=self.acceptance,
            context="scenario provenance",
        )
        return self


class StartupScenarioVariant(BaseModel):
    """One of the three planning variants inside a scenario set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_key: ScenarioKey
    inputs: dict[str, ScenarioInput] = Field(default_factory=dict)
    metrics: dict[str, ScenarioMetric] = Field(default_factory=dict)
    gaps: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_keyed_items(self) -> "StartupScenarioVariant":
        for key, input_item in self.inputs.items():
            if key != input_item.input_key:
                raise ValueError("scenario input keys must match their mapping keys")
        for key, metric_item in self.metrics.items():
            if key != metric_item.metric_key:
                raise ValueError("scenario metric keys must match their mapping keys")
        return self


class StartupScenarioSet(BaseModel):
    """A revision-bound scenario package for one founder case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_set_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    scenario_key: str = "base"
    inputs: tuple[ScenarioInput, ...] = Field(default_factory=tuple)
    metrics: tuple[ScenarioMetric, ...] = Field(default_factory=tuple)
    scenarios: dict[ScenarioKey, StartupScenarioVariant] = Field(default_factory=dict)
    selected_scenario_key: ScenarioKey = "base"
    rationale: str
    validation_plan: str
    acceptance: ScenarioAcceptance

    @field_validator("scenario_key", "rationale", "validation_plan", mode="before")
    @classmethod
    def validate_text(cls, value: Any) -> str:
        return _normalize_required_text(value)

    @model_validator(mode="after")
    def enforce_case_revision_ownership(self) -> "StartupScenarioSet":
        if self.scenarios:
            if set(self.scenarios) != {"conservative", "base", "optimistic"}:
                raise ValueError("scenario set must contain exactly conservative, base and optimistic scenarios")
            for key, variant in self.scenarios.items():
                if key != variant.scenario_key:
                    raise ValueError("scenario mapping key must match variant scenario_key")
                self._validate_items(tuple(variant.inputs.values()), tuple(variant.metrics.values()))
            selected = self.scenarios[self.selected_scenario_key]
            object.__setattr__(self, "scenario_key", self.selected_scenario_key)
            object.__setattr__(self, "inputs", tuple(selected.inputs.values()))
            object.__setattr__(self, "metrics", tuple(selected.metrics.values()))
            return self
        self._validate_items(self.inputs, self.metrics)
        return self

    def _validate_items(
        self,
        inputs: tuple[ScenarioInput, ...],
        metrics: tuple[ScenarioMetric, ...],
    ) -> None:
        for input_item in inputs:
            if input_item.case_id is not None and input_item.case_id != self.case_id:
                raise ValueError("scenario items must share the same case_id and data_revision")
            if input_item.data_revision is not None and input_item.data_revision != self.data_revision:
                raise ValueError("scenario items must share the same case_id and data_revision")
        for metric_item in metrics:
            if metric_item.case_id != self.case_id:
                raise ValueError("scenario items must share the same case_id and data_revision")
            if metric_item.data_revision != self.data_revision:
                raise ValueError("scenario items must share the same case_id and data_revision")


class ScenarioSelectionRecord(BaseModel):
    """Immutable durable record for scenario selection idempotency replay."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    data_revision: int = Field(ge=1)
    scenario_set_id: UUID
    old_scenario_key: ScenarioKey
    new_scenario_key: ScenarioKey
    changed_keys: tuple[str, ...] = ("selected_scenario_key",)

    @field_validator("changed_keys", mode="after")
    @classmethod
    def freeze_changed_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(value)


def _validate_provenance_refs(
    *,
    provenance: CaseValueKind,
    source_refs: tuple[UUID, ...],
    dependency_refs: tuple[UUID, ...],
    acceptance: ScenarioAcceptance,
    context: str,
) -> None:
    if provenance in {
        CaseValueKind.SOURCE_FACT,
        CaseValueKind.PUBLIC_BENCHMARK,
    } and not source_refs:
        raise ValueError(f"{provenance.value} requires source refs")
    if provenance is CaseValueKind.FOUNDER_STATEMENT:
        if not source_refs:
            raise ValueError("founder_statement requires source refs")
        if acceptance != "accepted":
            raise ValueError("accepted founder_statement provenance requires accepted acceptance")
    if provenance is CaseValueKind.DETERMINISTIC_CALCULATION and not dependency_refs:
        raise ValueError("deterministic_calculation requires dependency refs")


def _validate_currency_period_unit(unit: str, *, period: str) -> None:
    if "/" in unit:
        currency, legacy_period = unit.split("/", 1)
        if not currency.strip() or not legacy_period.strip():
            raise ValueError("scenario values require currency/period units")
        if legacy_period.strip() != period:
            raise ValueError("scenario values require matching unit and period metadata")
        return
    if not unit.strip() or not period.strip():
        raise ValueError("scenario values require currency/period units")


def _legacy_period_from_unit(unit: str) -> str | None:
    if "/" not in unit:
        return None
    _, period = unit.split("/", 1)
    normalized = " ".join(period.strip().split())
    return normalized or None


def _normalize_required_text(value: Any, *, field_name: str = "text value") -> str:
    if value is None:
        raise ValueError(f"{field_name} must be a string")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent >= 0:
        return 0
    return abs(exponent)


__all__ = [
    "ScenarioInput",
    "ScenarioKey",
    "ScenarioMetric",
    "ScenarioRange",
    "ScenarioSelectionRecord",
    "StartupScenarioVariant",
    "StartupScenarioSet",
]

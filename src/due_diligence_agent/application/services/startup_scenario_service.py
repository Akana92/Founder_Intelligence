from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from due_diligence_agent.application.services.startup_metric_service import StartupMetricService
from due_diligence_agent.application.startup_cases import StartupGateConflict
from due_diligence_agent.domain.startup.case_intake import CaseValueKind, FounderStatement
from due_diligence_agent.domain.startup.scenario import (
    ScenarioInput,
    ScenarioKey,
    ScenarioMetric,
    ScenarioRange,
    ScenarioSelectionRecord,
    StartupScenarioSet,
    StartupScenarioVariant,
)


ScenarioSelectionKey = Literal["conservative", "base", "optimistic"]
_SCENARIO_NAMESPACE = UUID("c2538a79-f15e-4d2c-b546-5c024158d6b7")
_DEFAULTS = {
    "conservative": {
        "monthly_price": ScenarioRange(lower=Decimal("30000"), upper=Decimal("35000")),
        "paying_customers": ScenarioRange(lower=Decimal("20"), upper=Decimal("35")),
        "revenue": ScenarioRange(lower=Decimal("600000"), upper=Decimal("1225000")),
        "cogs": ScenarioRange(lower=Decimal("180000"), upper=Decimal("490000")),
        "monthly_operating_expenses": ScenarioRange(lower=Decimal("1200000"), upper=Decimal("1600000")),
        "monthly_revenue": ScenarioRange(lower=Decimal("600000"), upper=Decimal("1225000")),
        "cash_balance": ScenarioRange(lower=Decimal("2500000"), upper=Decimal("3500000")),
        "acquisition_spend": ScenarioRange(lower=Decimal("600000"), upper=Decimal("900000")),
        "acquired_customers": ScenarioRange(lower=Decimal("8"), upper=Decimal("15")),
        "arpa": ScenarioRange(lower=Decimal("30000"), upper=Decimal("35000")),
    },
    "base": {
        "monthly_price": ScenarioRange(lower=Decimal("35000"), upper=Decimal("40000")),
        "paying_customers": ScenarioRange(lower=Decimal("40"), upper=Decimal("50")),
        "revenue": ScenarioRange(lower=Decimal("1400000"), upper=Decimal("2000000")),
        "cogs": ScenarioRange(lower=Decimal("420000"), upper=Decimal("800000")),
        "monthly_operating_expenses": ScenarioRange(lower=Decimal("1800000"), upper=Decimal("2400000")),
        "monthly_revenue": ScenarioRange(lower=Decimal("1400000"), upper=Decimal("2000000")),
        "cash_balance": ScenarioRange(lower=Decimal("4000000"), upper=Decimal("6000000")),
        "acquisition_spend": ScenarioRange(lower=Decimal("900000"), upper=Decimal("1300000")),
        "acquired_customers": ScenarioRange(lower=Decimal("15"), upper=Decimal("25")),
        "arpa": ScenarioRange(lower=Decimal("35000"), upper=Decimal("40000")),
    },
    "optimistic": {
        "monthly_price": ScenarioRange(lower=Decimal("40000"), upper=Decimal("50000")),
        "paying_customers": ScenarioRange(lower=Decimal("50"), upper=Decimal("70")),
        "revenue": ScenarioRange(lower=Decimal("2000000"), upper=Decimal("3500000")),
        "cogs": ScenarioRange(lower=Decimal("500000"), upper=Decimal("1050000")),
        "monthly_operating_expenses": ScenarioRange(lower=Decimal("2200000"), upper=Decimal("3000000")),
        "monthly_revenue": ScenarioRange(lower=Decimal("2000000"), upper=Decimal("3500000")),
        "cash_balance": ScenarioRange(lower=Decimal("6000000"), upper=Decimal("9000000")),
        "acquisition_spend": ScenarioRange(lower=Decimal("1200000"), upper=Decimal("1800000")),
        "acquired_customers": ScenarioRange(lower=Decimal("25"), upper=Decimal("40")),
        "arpa": ScenarioRange(lower=Decimal("40000"), upper=Decimal("50000")),
    },
}
_INPUT_UNITS = {
    "monthly_price": ("KZT", "month"),
    "paying_customers": ("count", "month"),
    "revenue": ("KZT", "month"),
    "cogs": ("KZT", "month"),
    "monthly_operating_expenses": ("KZT", "month"),
    "monthly_revenue": ("KZT", "month"),
    "cash_balance": ("KZT", "month"),
    "acquisition_spend": ("KZT", "month"),
    "acquired_customers": ("count", "month"),
    "arpa": ("KZT", "month"),
}
_METRIC_KEYS: tuple[str, ...] = (
    "mrr",
    "arr",
    "gross_margin",
    "net_burn",
    "runway",
    "cac",
    "ltv",
    "ltv_cac",
    "cac_payback",
)


class ScenarioSelectionDelta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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


@dataclass(frozen=True)
class _SelectionReplay:
    scenario_key: ScenarioKey
    delta: ScenarioSelectionDelta


class StartupScenarioService:
    def __init__(
        self,
        *,
        case_repository: Any,
        assumption_repository: Any,
        scenario_repository: Any,
        public_benchmark_repository: Any | None = None,
        metric_service: StartupMetricService | None = None,
    ) -> None:
        self._case_repository = case_repository
        self._assumption_repository = assumption_repository
        self._scenario_repository = scenario_repository
        self._public_benchmark_repository = public_benchmark_repository
        self._metric_service = metric_service or StartupMetricService()
        self._selection_replays: dict[tuple[UUID, str], _SelectionReplay] = {}

    def build(
        self,
        case_id: UUID,
        *,
        expected_case_revision: int,
        idempotency_key: str,
    ) -> StartupScenarioSet:
        existing = _repo_get_by_idempotency(
            self._scenario_repository,
            case_id,
            _operation_idempotency_key("build", idempotency_key),
        )
        if existing is not None:
            return existing
        revision = self._require_current_revision(case_id, expected_case_revision)
        statements = tuple(self._assumption_repository.get_current(case_id))
        statement_inputs = _founder_statement_inputs(statements)
        benchmark_inputs = _public_benchmark_inputs(
            tuple(self._public_benchmark_repository.get_current(case_id))
            if self._public_benchmark_repository is not None
            else ()
        )
        scenario_keys: tuple[ScenarioKey, ...] = ("conservative", "base", "optimistic")
        scenarios: dict[ScenarioKey, StartupScenarioVariant] = {
            key: self._build_variant(
                case_id=case_id,
                data_revision=revision,
                scenario_key=key,
                founder_inputs=statement_inputs,
                benchmark_inputs=benchmark_inputs,
            )
            for key in scenario_keys
        }
        scenario_set = StartupScenarioSet(
            scenario_set_id=_scenario_set_id(case_id, revision, scenarios),
            case_id=case_id,
            data_revision=revision,
            scenarios=scenarios,
            selected_scenario_key="base",
            rationale="Deterministic planning scenarios from accepted statements and bounded defaults.",
            validation_plan="Replace planning assumptions with source facts, accepted founder statements or cited benchmarks.",
            acceptance="proposed",
        )
        try:
            return cast(StartupScenarioSet, self._scenario_repository.save(
                scenario_set,
                expected_revision=expected_case_revision,
                idempotency_key=_operation_idempotency_key("build", idempotency_key),
            ))
        except ValueError as exc:
            raise StartupGateConflict("case_revision_conflict") from exc

    def select(
        self,
        case_id: UUID,
        scenario_key: ScenarioSelectionKey,
        *,
        expected_case_revision: int,
        idempotency_key: str,
    ) -> ScenarioSelectionDelta:
        replay_key = (case_id, idempotency_key)
        replay = self._selection_replays.get(replay_key)
        if replay is not None:
            if replay.scenario_key != scenario_key:
                raise StartupGateConflict("idempotency_key_conflict")
            return replay.delta
        persisted_replay = _repo_get_selection_by_idempotency(
            self._scenario_repository,
            case_id,
            _operation_idempotency_key("select", idempotency_key),
        )
        if persisted_replay is not None:
            if persisted_replay.new_scenario_key != scenario_key:
                raise StartupGateConflict("idempotency_key_conflict")
            return _delta_from_record(persisted_replay)
        revision = self._require_current_revision(case_id, expected_case_revision)
        try:
            current: StartupScenarioSet = self._scenario_repository.get_current(case_id)
        except KeyError as exc:
            raise StartupGateConflict("scenario_set_missing") from exc
        if current.case_id != case_id or current.data_revision != revision:
            raise StartupGateConflict("case_revision_conflict")
        updated = current.model_copy(update={"selected_scenario_key": scenario_key})
        try:
            saved = self._scenario_repository.save(
                updated,
                expected_revision=expected_case_revision,
                idempotency_key=_operation_idempotency_key("select", idempotency_key),
            )
        except ValueError as exc:
            raise StartupGateConflict("case_revision_conflict") from exc
        delta = ScenarioSelectionDelta(
            case_id=case_id,
            data_revision=revision,
            scenario_set_id=saved.scenario_set_id,
            old_scenario_key=current.selected_scenario_key,
            new_scenario_key=scenario_key,
        )
        record = ScenarioSelectionRecord(
            selection_id=_selection_id(case_id, idempotency_key),
            case_id=case_id,
            data_revision=revision,
            scenario_set_id=saved.scenario_set_id,
            old_scenario_key=current.selected_scenario_key,
            new_scenario_key=scenario_key,
        )
        try:
            saved_record = _repo_save_selection(
                self._scenario_repository,
                record,
                expected_revision=expected_case_revision,
                idempotency_key=_operation_idempotency_key("select", idempotency_key),
            )
        except ValueError as exc:
            raise StartupGateConflict("case_revision_conflict") from exc
        if saved_record != record:
            if saved_record.new_scenario_key != scenario_key:
                raise StartupGateConflict("idempotency_key_conflict")
            delta = _delta_from_record(saved_record)
        self._selection_replays[replay_key] = _SelectionReplay(scenario_key=scenario_key, delta=delta)
        return delta

    def _build_variant(
        self,
        *,
        case_id: UUID,
        data_revision: int,
        scenario_key: ScenarioKey,
        founder_inputs: dict[str, _FounderInput],
        benchmark_inputs: dict[str, ScenarioInput],
    ) -> StartupScenarioVariant:
        defaults = _DEFAULTS[scenario_key]
        inputs = {
            input_key: _scenario_input(
                case_id=case_id,
                data_revision=data_revision,
                scenario_key=scenario_key,
                input_key=input_key,
                default_range=defaults[input_key],
                unit=_INPUT_UNITS[input_key][0],
                period=_INPUT_UNITS[input_key][1],
                founder_inputs=founder_inputs,
                benchmark_inputs=benchmark_inputs,
            )
            for input_key in _INPUT_UNITS
        }
        mrr = self._metric_service.calculate_scenario(
            "mrr",
            {
                "monthly_price": inputs["monthly_price"].value_range,
                "paying_customers": inputs["paying_customers"].value_range,
            },
        )
        mrr = _bind_metric(
            mrr,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=(mrr_dependencies := (inputs["monthly_price"].input_id, inputs["paying_customers"].input_id)),
            source_refs=_dependency_source_refs(mrr_dependencies, inputs, {}),
        )
        arr = self._metric_service.calculate_scenario("arr", {"mrr": _require_range(mrr)})
        arr_dependencies = (mrr.metric_id,)
        arr = _bind_metric(
            arr,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=arr_dependencies,
            source_refs=_dependency_source_refs(arr_dependencies, inputs, {"mrr": mrr}),
        )
        gross_margin = self._metric_service.calculate_scenario(
            "gross_margin",
            {
                "revenue": inputs["revenue"].value_range,
                "cogs": inputs["cogs"].value_range,
            },
        )
        gross_margin = _bind_metric(
            gross_margin,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=(
                gross_margin_dependencies := (inputs["revenue"].input_id, inputs["cogs"].input_id)
            ),
            source_refs=_dependency_source_refs(gross_margin_dependencies, inputs, {}),
        )
        net_burn = self._metric_service.calculate_scenario(
            "net_burn",
            {
                "monthly_operating_expenses": inputs["monthly_operating_expenses"].value_range,
                "monthly_revenue": inputs["monthly_revenue"].value_range,
            },
        )
        net_burn = _bind_metric(
            net_burn,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=(
                net_burn_dependencies := (
                    inputs["monthly_operating_expenses"].input_id,
                    inputs["monthly_revenue"].input_id,
                )
            ),
            source_refs=_dependency_source_refs(net_burn_dependencies, inputs, {}),
        )
        runway_inputs = {"cash_balance": inputs["cash_balance"].value_range}
        runway_dependencies = [inputs["cash_balance"].input_id]
        if net_burn.value_range is not None:
            runway_inputs["net_burn"] = net_burn.value_range
            runway_dependencies.append(net_burn.metric_id)
        runway = self._metric_service.calculate_scenario("runway", runway_inputs)
        runway = _bind_metric(
            runway,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=tuple(runway_dependencies),
            source_refs=_dependency_source_refs(
                tuple(runway_dependencies),
                inputs,
                {"net_burn": net_burn},
            ),
        )
        cac = self._metric_service.calculate_scenario(
            "cac",
            {
                "acquisition_spend": inputs["acquisition_spend"].value_range,
                "acquired_customers": inputs["acquired_customers"].value_range,
            },
        )
        cac = _bind_metric(
            cac,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=(
                cac_dependencies := (
                    inputs["acquisition_spend"].input_id,
                    inputs["acquired_customers"].input_id,
                )
            ),
            source_refs=_dependency_source_refs(cac_dependencies, inputs, {}),
        )
        ltv_inputs = {"arpa": inputs["arpa"].value_range}
        ltv_dependencies = [inputs["arpa"].input_id]
        if gross_margin.value_range is not None:
            ltv_inputs["gross_margin"] = gross_margin.value_range
            ltv_dependencies.append(gross_margin.metric_id)
        churn = inputs.get("churn")
        if churn is not None:
            ltv_inputs["churn"] = churn.value_range
            ltv_dependencies.append(churn.input_id)
        ltv = self._metric_service.calculate_scenario(
            "ltv",
            ltv_inputs,
        )
        ltv = _bind_metric(
            ltv,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=tuple(ltv_dependencies),
            source_refs=_dependency_source_refs(
                tuple(ltv_dependencies),
                inputs,
                {"gross_margin": gross_margin},
            ),
        )
        ltv_cac_inputs: dict[str, ScenarioRange] = {}
        ltv_cac_dependencies: list[UUID] = []
        if ltv.value_range is not None:
            ltv_cac_inputs["ltv"] = ltv.value_range
            ltv_cac_dependencies.append(ltv.metric_id)
        if cac.value_range is not None:
            ltv_cac_inputs["cac"] = cac.value_range
            ltv_cac_dependencies.append(cac.metric_id)
        ltv_cac = self._metric_service.calculate_scenario("ltv_cac", ltv_cac_inputs)
        ltv_cac = _bind_metric(
            ltv_cac,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=tuple(ltv_cac_dependencies),
            source_refs=_dependency_source_refs(
                tuple(ltv_cac_dependencies),
                inputs,
                {"ltv": ltv, "cac": cac},
            ),
        )
        cac_payback_inputs = {"arpa": inputs["arpa"].value_range}
        cac_payback_dependencies = [inputs["arpa"].input_id]
        if cac.value_range is not None:
            cac_payback_inputs["cac"] = cac.value_range
            cac_payback_dependencies.append(cac.metric_id)
        if gross_margin.value_range is not None:
            cac_payback_inputs["gross_margin"] = gross_margin.value_range
            cac_payback_dependencies.append(gross_margin.metric_id)
        cac_payback = self._metric_service.calculate_scenario("cac_payback", cac_payback_inputs)
        cac_payback = _bind_metric(
            cac_payback,
            case_id=case_id,
            data_revision=data_revision,
            dependencies=tuple(cac_payback_dependencies),
            source_refs=_dependency_source_refs(
                tuple(cac_payback_dependencies),
                inputs,
                {"cac": cac, "gross_margin": gross_margin},
            ),
        )
        metrics = {
            "mrr": mrr,
            "arr": arr,
            "gross_margin": gross_margin,
            "net_burn": net_burn,
            "runway": runway,
            "cac": cac,
            "ltv": ltv,
            "ltv_cac": ltv_cac,
            "cac_payback": cac_payback,
        }
        gaps = {
            gap.removeprefix("input.missing:"): "Required before this formula can execute."
            for metric in metrics.values()
            for gap in metric.gaps
            if gap.startswith("input.missing:")
        }
        return StartupScenarioVariant(
            scenario_key=scenario_key,
            inputs=inputs,
            metrics=metrics,
            gaps=gaps,
        )

    def _require_current_revision(self, case_id: UUID, expected_revision: int) -> int:
        try:
            case = self._case_repository.get(case_id)
        except KeyError as exc:
            raise StartupGateConflict("case_scope_mismatch") from exc
        actual = getattr(case, "data_revision", None)
        if isinstance(actual, bool) or not isinstance(actual, int) or actual != expected_revision:
            raise StartupGateConflict("case_revision_conflict")
        return actual


@dataclass(frozen=True)
class _FounderInput:
    value_range: ScenarioRange
    source_ref: UUID
    period: str | None
    rationale: str
    validation_plan: str


def _founder_statement_inputs(statements: tuple[FounderStatement, ...]) -> dict[str, _FounderInput]:
    inputs: dict[str, _FounderInput] = {}
    for statement in sorted(statements, key=lambda item: (item.data_revision, str(item.statement_id))):
        input_key = _normalize_input_key(statement.field_key)
        if input_key not in _INPUT_UNITS:
            continue
        parsed = _parse_statement_range(statement.value)
        if parsed is None:
            continue
        inputs[input_key] = _FounderInput(
            value_range=parsed,
            source_ref=statement.statement_id,
            period=statement.period,
            rationale=statement.rationale,
            validation_plan=statement.validation_plan,
        )
    return inputs


def _public_benchmark_inputs(inputs: tuple[ScenarioInput, ...]) -> dict[str, ScenarioInput]:
    selected: dict[str, ScenarioInput] = {}
    for item in sorted(inputs, key=lambda value: (value.data_revision or 0, str(value.input_id))):
        input_key = _normalize_input_key(item.input_key)
        if input_key not in _INPUT_UNITS:
            continue
        if item.provenance is not CaseValueKind.PUBLIC_BENCHMARK:
            continue
        if not item.source_refs:
            continue
        selected[input_key] = item
    return selected


def _scenario_input(
    *,
    case_id: UUID,
    data_revision: int,
    scenario_key: ScenarioKey,
    input_key: str,
    default_range: ScenarioRange,
    unit: str,
    period: str,
    founder_inputs: dict[str, _FounderInput],
    benchmark_inputs: dict[str, ScenarioInput],
) -> ScenarioInput:
    founder_input = founder_inputs.get(input_key)
    if founder_input is not None and scenario_key == "base":
        return ScenarioInput(
            input_id=_input_id(case_id, data_revision, scenario_key, input_key, founder_input.value_range),
            case_id=case_id,
            data_revision=data_revision,
            input_key=input_key,
            value_range=founder_input.value_range,
            unit=unit,
            period=founder_input.period or period,
            provenance=CaseValueKind.FOUNDER_STATEMENT,
            source_refs=(founder_input.source_ref,),
            confidence="medium",
            rationale=founder_input.rationale,
            validation_plan=founder_input.validation_plan,
            what_would_confirm="Eligible uploaded evidence matching the founder statement.",
            acceptance="accepted",
        )
    if founder_input is not None:
        derived_range = _derive_founder_variant_range(founder_input.value_range, scenario_key)
        return ScenarioInput(
            input_id=_input_id(case_id, data_revision, scenario_key, input_key, derived_range),
            case_id=case_id,
            data_revision=data_revision,
            input_key=input_key,
            value_range=derived_range,
            unit=unit,
            period=period,
            provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
            source_refs=(founder_input.source_ref,),
            dependency_refs=(founder_input.source_ref,),
            confidence="medium",
            rationale="Deterministically derived from the accepted founder planning statement.",
            validation_plan="Replace with eligible source evidence when available.",
            what_would_confirm="Eligible uploaded evidence matching or replacing the founder statement.",
            acceptance="proposed",
        )
    benchmark_input = benchmark_inputs.get(input_key)
    if benchmark_input is not None:
        return ScenarioInput(
            input_id=_input_id(case_id, data_revision, scenario_key, input_key, benchmark_input.value_range),
            case_id=case_id,
            data_revision=data_revision,
            input_key=input_key,
            value_range=benchmark_input.value_range,
            unit=benchmark_input.unit,
            period=benchmark_input.period or period,
            provenance=CaseValueKind.PUBLIC_BENCHMARK,
            source_refs=benchmark_input.source_refs,
            confidence=benchmark_input.confidence,
            rationale="Cited public benchmark planning input.",
            validation_plan=benchmark_input.validation_plan,
            what_would_confirm=benchmark_input.what_would_confirm,
            acceptance="proposed",
        )
    return ScenarioInput(
        input_id=_input_id(case_id, data_revision, scenario_key, input_key, default_range),
        case_id=case_id,
        data_revision=data_revision,
        input_key=input_key,
        value_range=default_range,
        unit=unit,
        period=period,
        provenance=CaseValueKind.AI_SCENARIO,
        source_refs=(),
        confidence="low",
        rationale="Bounded planning default for an idea-stage scenario.",
        validation_plan="Ask the founder to accept, reject or replace this planning assumption.",
        what_would_confirm="Founder acceptance, cited benchmark range or later source evidence.",
        acceptance="proposed",
    )


def _bind_metric(
    metric: ScenarioMetric,
    *,
    case_id: UUID,
    data_revision: int,
    dependencies: tuple[UUID, ...],
    source_refs: tuple[UUID, ...],
) -> ScenarioMetric:
    value_range = metric.value_range
    metric_id = (
        _metric_id(case_id, data_revision, metric.metric_key, value_range)
        if value_range is not None
        else _gap_metric_id(case_id, data_revision, metric.metric_key, metric.gaps)
    )
    return metric.model_copy(
        update={
            "metric_id": metric_id,
            "case_id": case_id,
            "data_revision": data_revision,
            "source_refs": source_refs,
            "dependency_refs": dependencies,
        }
    )


def _dependency_source_refs(
    dependencies: tuple[UUID, ...],
    inputs: dict[str, ScenarioInput],
    metrics: dict[str, ScenarioMetric],
) -> tuple[UUID, ...]:
    input_by_id = {value.input_id: value for value in inputs.values()}
    metric_by_id = {value.metric_id: value for value in metrics.values()}
    refs: list[UUID] = []
    for dependency in dependencies:
        input_value = input_by_id.get(dependency)
        if input_value is not None:
            refs.extend(input_value.source_refs)
        metric_value = metric_by_id.get(dependency)
        if metric_value is not None:
            refs.extend(metric_value.source_refs)
    return tuple(dict.fromkeys(refs))


def _repo_get_by_idempotency(
    repository: Any,
    case_id: UUID,
    idempotency_key: str,
) -> StartupScenarioSet | None:
    getter = getattr(repository, "get_by_idempotency", None)
    if getter is None:
        return None
    existing = getter(case_id, idempotency_key)
    if existing is None:
        return None
    return cast(StartupScenarioSet, existing)


def _repo_get_selection_by_idempotency(
    repository: Any,
    case_id: UUID,
    idempotency_key: str,
) -> ScenarioSelectionRecord | None:
    getter = getattr(repository, "get_selection_by_idempotency", None)
    if getter is None:
        return None
    existing = getter(case_id, idempotency_key)
    if existing is None:
        return None
    return cast(ScenarioSelectionRecord, existing)


def _repo_save_selection(
    repository: Any,
    value: ScenarioSelectionRecord,
    *,
    expected_revision: int,
    idempotency_key: str,
) -> ScenarioSelectionRecord:
    saver = getattr(repository, "save_selection", None)
    if saver is None:
        return value
    return cast(
        ScenarioSelectionRecord,
        saver(value, expected_revision=expected_revision, idempotency_key=idempotency_key),
    )


def _delta_from_record(record: ScenarioSelectionRecord) -> ScenarioSelectionDelta:
    return ScenarioSelectionDelta(
        case_id=record.case_id,
        data_revision=record.data_revision,
        scenario_set_id=record.scenario_set_id,
        old_scenario_key=record.old_scenario_key,
        new_scenario_key=record.new_scenario_key,
        changed_keys=record.changed_keys,
    )


def _parse_statement_range(value: str) -> ScenarioRange | None:
    numeric_value = value.split(";", 1)[0]
    numbers = re.findall(r"\d+(?:[.,]\d+)?", numeric_value)
    if not numbers:
        return None
    try:
        lower = Decimal(numbers[0].replace(",", "."))
        upper = Decimal(numbers[1].replace(",", ".")) if len(numbers) > 1 else lower
    except InvalidOperation:
        return None
    return ScenarioRange(lower=lower, upper=upper)


def _normalize_input_key(value: str) -> str:
    normalized = value.strip().casefold()
    aliases = {
        "customer_count": "paying_customers",
        "projected_paying_customers": "paying_customers",
        "paying_customer_count": "paying_customers",
        "sales_marketing_spend": "acquisition_spend",
        "new_customers": "acquired_customers",
        "monthly_arpa": "arpa",
        "mrr": "monthly_revenue",
        "monthly_recurring_revenue": "monthly_revenue",
    }
    return aliases.get(normalized, normalized)


def _derive_founder_variant_range(value_range: ScenarioRange, scenario_key: ScenarioKey) -> ScenarioRange:
    if scenario_key == "conservative":
        return _scale_range(value_range, Decimal("0.90"))
    if scenario_key == "optimistic":
        return _scale_range(value_range, Decimal("1.10"))
    return value_range


def _scale_range(value_range: ScenarioRange, factor: Decimal) -> ScenarioRange:
    return ScenarioRange(
        lower=_scenario_decimal(value_range.lower * factor),
        upper=_scenario_decimal(value_range.upper * factor),
    )


def _scenario_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01")).normalize()


def _require_range(metric: ScenarioMetric) -> ScenarioRange:
    if metric.value_range is None:
        raise StartupGateConflict(f"scenario_metric_missing_value:{metric.metric_key}")
    return metric.value_range


def _scenario_set_id(
    case_id: UUID,
    data_revision: int,
    scenarios: dict[ScenarioKey, StartupScenarioVariant],
) -> UUID:
    material = "|".join(
        [
            str(case_id),
            str(data_revision),
            *[
                f"{key}:{variant.metrics['mrr'].value_range}"
                for key, variant in scenarios.items()
            ],
        ]
    )
    return uuid5(_SCENARIO_NAMESPACE, f"scenario-set:{material}")


def _selection_id(case_id: UUID, idempotency_key: str) -> UUID:
    return uuid5(_SCENARIO_NAMESPACE, f"scenario-selection:{case_id}:{idempotency_key}")


def _operation_idempotency_key(operation: str, raw_key: str) -> str:
    return f"{operation}:{raw_key}"


def _input_id(
    case_id: UUID,
    data_revision: int,
    scenario_key: str,
    input_key: str,
    value_range: ScenarioRange,
) -> UUID:
    return uuid5(
        _SCENARIO_NAMESPACE,
        f"scenario-input:{case_id}:{data_revision}:{scenario_key}:{input_key}:{value_range.lower}:{value_range.upper}",
    )


def _metric_id(
    case_id: UUID,
    data_revision: int,
    metric_key: str,
    value_range: ScenarioRange,
) -> UUID:
    return uuid5(
        _SCENARIO_NAMESPACE,
        f"scenario-metric:{case_id}:{data_revision}:{metric_key}:{value_range.lower}:{value_range.upper}",
    )


def _gap_metric_id(
    case_id: UUID,
    data_revision: int,
    metric_key: str,
    gaps: tuple[str, ...],
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"scenario-metric-gap:{case_id}:{data_revision}:{metric_key}:{','.join(gaps)}",
    )


__all__ = [
    "ScenarioSelectionDelta",
    "StartupScenarioService",
]

from __future__ import annotations

import json
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from due_diligence_agent.application.services.startup_scenario_service import (
    ScenarioSelectionDelta,
    StartupScenarioService,
)
from due_diligence_agent.application.startup_cases import StartupGateConflict
from due_diligence_agent.domain.startup.case_intake import CaseValueKind, FounderStatement
from due_diligence_agent.domain.startup.scenario import (
    ScenarioInput,
    ScenarioRange,
    ScenarioSelectionRecord,
    StartupScenarioSet,
)


CASE_ID = UUID("12121212-1212-4212-8212-121212121212")


def test_build_returns_three_differentiated_scenarios_with_base_mrr_arr_lineage_and_no_float_json() -> None:
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(
            (
                _statement("monthly_price", "35000..40000; currency=KZT; period=month"),
                _statement("paying_customers", "40..50; unit=count; period=month"),
            )
        ),
        scenario_repository=_ScenarioRepo(revision=2),
    )

    result = service.build(CASE_ID, expected_case_revision=2, idempotency_key="build-2")
    base = result.scenarios["base"]

    assert tuple(result.scenarios) == ("conservative", "base", "optimistic")
    assert result.scenarios["conservative"].metrics["mrr"].value_range != base.metrics["mrr"].value_range
    assert result.scenarios["optimistic"].metrics["mrr"].value_range != base.metrics["mrr"].value_range
    assert base.metrics["mrr"].value_range == ScenarioRange(lower=Decimal("1400000"), upper=Decimal("2000000"))
    assert base.metrics["arr"].value_range == ScenarioRange(lower=Decimal("16800000"), upper=Decimal("24000000"))
    assert base.metrics["arr"].dependency_refs == (base.metrics["mrr"].metric_id,)
    assert base.metrics["arr"].provenance is CaseValueKind.DETERMINISTIC_CALCULATION
    assert base.inputs["monthly_price"].provenance is CaseValueKind.FOUNDER_STATEMENT
    assert base.inputs["monthly_price"].provenance.value != CaseValueKind.SOURCE_FACT.value
    assert base.metrics["mrr"].formula_key == "mrr"
    assert base.metrics["mrr"].what_would_confirm

    serialized = json.loads(result.model_dump_json())
    assert _contains_float(serialized) is False


def test_build_is_durable_idempotent_and_stale_safe() -> None:
    repository = _ScenarioRepo(revision=2)
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )

    first = service.build(CASE_ID, expected_case_revision=2, idempotency_key="same-build")
    replay = service.build(CASE_ID, expected_case_revision=2, idempotency_key="same-build")

    assert replay == first
    assert repository.saved == [first]

    stale_service = StartupScenarioService(
        case_repository=_CaseRepo(revision=3),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=_ScenarioRepo(revision=3),
    )
    with pytest.raises(StartupGateConflict, match="case_revision_conflict"):
        stale_service.build(CASE_ID, expected_case_revision=2, idempotency_key="stale-build")


def test_select_changes_only_selection_metadata_and_rejects_stale_revision() -> None:
    repository = _ScenarioRepo(revision=2)
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )
    built = service.build(CASE_ID, expected_case_revision=2, idempotency_key="build")

    delta = service.select(
        CASE_ID,
        "optimistic",
        expected_case_revision=2,
        idempotency_key="select-optimistic",
    )
    replay = service.select(
        CASE_ID,
        "optimistic",
        expected_case_revision=2,
        idempotency_key="select-optimistic",
    )

    assert isinstance(delta, ScenarioSelectionDelta)
    assert delta.old_scenario_key == "base"
    assert delta.new_scenario_key == "optimistic"
    assert delta.scenario_set_id == built.scenario_set_id
    assert repository.get_current(CASE_ID).selected_scenario_key == "optimistic"
    assert repository.get_current(CASE_ID).scenarios["base"].metrics == built.scenarios["base"].metrics
    assert replay == delta

    stale = StartupScenarioService(
        case_repository=_CaseRepo(revision=3),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )
    with pytest.raises(StartupGateConflict, match="case_revision_conflict"):
        stale.select(CASE_ID, "base", expected_case_revision=2, idempotency_key="stale-select")


def test_missing_inputs_create_explicit_gaps_without_zero_metrics_or_actual_churn_invention() -> None:
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo((_statement("monthly_price", "35000; currency=KZT; period=month"),)),
        scenario_repository=_ScenarioRepo(revision=2),
    )

    result = service.build(CASE_ID, expected_case_revision=2, idempotency_key="gap-build")
    base = result.scenarios["base"]

    assert "paying_customers" in base.inputs
    assert base.inputs["paying_customers"].provenance is CaseValueKind.AI_SCENARIO
    assert base.metrics["ltv"].value_range is None
    assert "input.missing:churn" in base.metrics["ltv"].gaps
    assert base.metrics["ltv"].value_range != ScenarioRange(lower=Decimal("0"), upper=Decimal("0"))
    assert base.metrics["ltv"].what_would_confirm == "Observed cohort churn or a cited comparable churn benchmark."


def test_build_emits_full_metric_set_with_public_benchmark_priority_periods_and_no_source_fact_promotion() -> None:
    benchmark_source_id = UUID("abababab-abab-4aba-8bab-abababababab")
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(
            (
                _statement("monthly_price", "35000..40000; currency=KZT; period=month"),
                _statement("paying_customers", "40..50; unit=count; period=month"),
            )
        ),
        public_benchmark_repository=_PublicBenchmarkRepo(
            (
                _benchmark_input(
                    "acquisition_spend",
                    ScenarioRange(lower=Decimal("900000"), upper=Decimal("1200000")),
                    unit="KZT",
                    period="month",
                    source_refs=(benchmark_source_id,),
                ),
                _benchmark_input(
                    "acquired_customers",
                    ScenarioRange(lower=Decimal("15"), upper=Decimal("20")),
                    unit="count",
                    period="month",
                    source_refs=(benchmark_source_id,),
                ),
            )
        ),
        scenario_repository=_ScenarioRepo(revision=2),
    )

    result = service.build(CASE_ID, expected_case_revision=2, idempotency_key="complete-build")
    base = result.scenarios["base"]

    assert set(base.metrics) == {
        "mrr",
        "arr",
        "gross_margin",
        "net_burn",
        "runway",
        "cac",
        "ltv",
        "ltv_cac",
        "cac_payback",
    }
    assert base.inputs["monthly_price"].provenance is CaseValueKind.FOUNDER_STATEMENT
    assert base.inputs["acquisition_spend"].provenance is CaseValueKind.PUBLIC_BENCHMARK
    assert base.inputs["acquisition_spend"].source_refs == (benchmark_source_id,)
    input_provenance = {
        item.provenance for variant in result.scenarios.values() for item in variant.inputs.values()
    }
    metric_provenance = {
        item.provenance for variant in result.scenarios.values() for item in variant.metrics.values()
    }
    assert input_provenance.isdisjoint({CaseValueKind.SOURCE_FACT})
    assert metric_provenance.isdisjoint({CaseValueKind.SOURCE_FACT})
    assert base.inputs["monthly_price"].unit == "KZT"
    assert base.inputs["monthly_price"].period == "month"
    assert base.metrics["mrr"].unit == "KZT"
    assert base.metrics["mrr"].period == "month"
    assert base.metrics["arr"].unit == "KZT"
    assert base.metrics["arr"].period == "year"
    for metric in base.metrics.values():
        assert metric.value_range is not None or metric.gaps
        assert metric.validation_plan
        assert metric.what_would_confirm
    assert base.metrics["ltv"].value_range is None
    assert base.metrics["ltv"].gaps == ("input.missing:churn",)
    assert base.metrics["ltv_cac"].value_range is None
    assert base.metrics["ltv_cac"].gaps
    assert base.metrics["cac"].provenance is CaseValueKind.DETERMINISTIC_CALCULATION

    serialized = json.loads(result.model_dump_json())
    assert serialized["scenarios"]["base"]["inputs"]["monthly_price"]["unit"] == "KZT"
    assert serialized["scenarios"]["base"]["inputs"]["monthly_price"]["period"] == "month"
    assert serialized["scenarios"]["base"]["metrics"]["arr"]["unit"] == "KZT"
    assert serialized["scenarios"]["base"]["metrics"]["arr"]["period"] == "year"
    assert _contains_float(serialized) is False


def test_founder_statement_stays_first_for_all_variants_when_public_benchmark_conflicts() -> None:
    price_statement = _statement("monthly_price", "35000..40000; currency=KZT; period=month")
    customer_statement = _statement("paying_customers", "40..50; unit=count; period=month")
    benchmark_source_id = UUID("cdcdcdcd-cdcd-4cdc-8dcd-cdcdcdcdcdcd")
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo((price_statement, customer_statement)),
        public_benchmark_repository=_PublicBenchmarkRepo(
            (
                _benchmark_input(
                    "monthly_price",
                    ScenarioRange(lower=Decimal("10000"), upper=Decimal("12000")),
                    unit="KZT",
                    period="month",
                    source_refs=(benchmark_source_id,),
                ),
                _benchmark_input(
                    "paying_customers",
                    ScenarioRange(lower=Decimal("5"), upper=Decimal("8")),
                    unit="count",
                    period="month",
                    source_refs=(benchmark_source_id,),
                ),
            )
        ),
        scenario_repository=_ScenarioRepo(revision=2),
    )

    result = service.build(CASE_ID, expected_case_revision=2, idempotency_key="founder-first")

    for scenario_key, variant in result.scenarios.items():
        price = variant.inputs["monthly_price"]
        customers = variant.inputs["paying_customers"]
        assert price.source_refs == (price_statement.statement_id,)
        assert customers.source_refs == (customer_statement.statement_id,)
        assert price.provenance is not CaseValueKind.PUBLIC_BENCHMARK
        assert customers.provenance is not CaseValueKind.PUBLIC_BENCHMARK
        assert price.provenance.value != CaseValueKind.SOURCE_FACT.value
        assert customers.provenance.value != CaseValueKind.SOURCE_FACT.value
        if scenario_key == "base":
            assert price.provenance is CaseValueKind.FOUNDER_STATEMENT
            assert customers.provenance is CaseValueKind.FOUNDER_STATEMENT
            assert price.value_range == ScenarioRange(lower=Decimal("35000"), upper=Decimal("40000"))
            assert customers.value_range == ScenarioRange(lower=Decimal("40"), upper=Decimal("50"))
        else:
            assert price.provenance is CaseValueKind.DETERMINISTIC_CALCULATION
            assert customers.provenance is CaseValueKind.DETERMINISTIC_CALCULATION
            assert price.dependency_refs == (price_statement.statement_id,)
            assert customers.dependency_refs == (customer_statement.statement_id,)
            assert price.value_range != ScenarioRange(lower=Decimal("10000"), upper=Decimal("12000"))
            assert customers.value_range != ScenarioRange(lower=Decimal("5"), upper=Decimal("8"))


def test_selection_replay_survives_service_recreation_later_selection_and_conflicting_retry() -> None:
    repository = _ScenarioRepo(revision=2)
    first_service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )
    first_service.build(CASE_ID, expected_case_revision=2, idempotency_key="replay-build")
    original = first_service.select(
        CASE_ID,
        "optimistic",
        expected_case_revision=2,
        idempotency_key="select-original",
    )

    restarted = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )
    later = restarted.select(
        CASE_ID,
        "conservative",
        expected_case_revision=2,
        idempotency_key="select-later",
    )
    replay = restarted.select(
        CASE_ID,
        "optimistic",
        expected_case_revision=2,
        idempotency_key="select-original",
    )

    assert original.old_scenario_key == "base"
    assert original.new_scenario_key == "optimistic"
    assert later.old_scenario_key == "optimistic"
    assert later.new_scenario_key == "conservative"
    assert replay == original
    assert repository.get_current(CASE_ID).selected_scenario_key == "conservative"
    with pytest.raises(StartupGateConflict, match="idempotency_key_conflict"):
        restarted.select(CASE_ID, "base", expected_case_revision=2, idempotency_key="select-original")


def test_selection_can_reuse_raw_build_idempotency_key_without_replaying_build_record() -> None:
    repository = _ScenarioRepo(revision=2)
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )
    built = service.build(CASE_ID, expected_case_revision=2, idempotency_key="same-raw-key")

    selected = service.select(
        CASE_ID,
        "optimistic",
        expected_case_revision=2,
        idempotency_key="same-raw-key",
    )

    assert selected.scenario_set_id == built.scenario_set_id
    assert selected.old_scenario_key == "base"
    assert selected.new_scenario_key == "optimistic"
    assert repository.get_current(CASE_ID).selected_scenario_key == "optimistic"
    persisted_record = repository.get_selection_by_idempotency(CASE_ID, "select:same-raw-key")
    assert persisted_record is not None
    assert persisted_record.old_scenario_key == "base"
    assert persisted_record.new_scenario_key == "optimistic"

    restarted = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )
    replay = restarted.select(
        CASE_ID,
        "optimistic",
        expected_case_revision=2,
        idempotency_key="same-raw-key",
    )

    assert replay == selected
    assert repository.get_current(CASE_ID).selected_scenario_key == "optimistic"
    with pytest.raises(StartupGateConflict, match="idempotency_key_conflict"):
        restarted.select(CASE_ID, "base", expected_case_revision=2, idempotency_key="same-raw-key")
    assert repository.get_current(CASE_ID).selected_scenario_key == "optimistic"


def test_build_raw_key_that_looks_scoped_does_not_replay_prior_build_command() -> None:
    repository = _ScenarioRepo(revision=2)
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo((_statement("monthly_price", "35000..40000"),)),
        scenario_repository=repository,
    )
    first = service.build(CASE_ID, expected_case_revision=2, idempotency_key="foo")

    second_service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo((_statement("monthly_price", "45000..50000"),)),
        scenario_repository=repository,
    )
    second = second_service.build(CASE_ID, expected_case_revision=2, idempotency_key="build:foo")

    assert second != first
    assert second.scenario_set_id != first.scenario_set_id
    assert second.scenarios["base"].inputs["monthly_price"].value_range == ScenarioRange(
        lower=Decimal("45000"),
        upper=Decimal("50000"),
    )
    assert repository.get_by_idempotency(CASE_ID, "build:foo") == first
    assert repository.get_by_idempotency(CASE_ID, "build:build:foo") == second


def test_build_raw_key_that_looks_like_select_key_does_not_replay_selected_state() -> None:
    repository = _ScenarioRepo(revision=2)
    service = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo(()),
        scenario_repository=repository,
    )
    built = service.build(CASE_ID, expected_case_revision=2, idempotency_key="foo")
    service.select(CASE_ID, "optimistic", expected_case_revision=2, idempotency_key="foo")
    assert repository.get_current(CASE_ID).selected_scenario_key == "optimistic"

    rebuilt = StartupScenarioService(
        case_repository=_CaseRepo(revision=2),
        assumption_repository=_AssumptionRepo((_statement("monthly_price", "45000..50000"),)),
        scenario_repository=repository,
    ).build(CASE_ID, expected_case_revision=2, idempotency_key="select:foo")

    assert rebuilt != built
    assert rebuilt.selected_scenario_key == "base"
    assert rebuilt.scenarios["base"].inputs["monthly_price"].value_range == ScenarioRange(
        lower=Decimal("45000"),
        upper=Decimal("50000"),
    )
    assert repository.get_current(CASE_ID) == rebuilt
    selected_replay = repository.get_by_idempotency(CASE_ID, "select:foo")
    assert selected_replay is not None
    assert selected_replay.selected_scenario_key == "optimistic"
    assert repository.get_by_idempotency(CASE_ID, "build:select:foo") == rebuilt


class _Case:
    def __init__(self, revision: int) -> None:
        self.data_revision = revision


class _CaseRepo:
    def __init__(self, *, revision: int) -> None:
        self.revision = revision

    def get(self, case_id: UUID) -> _Case:
        assert case_id == CASE_ID
        return _Case(self.revision)


class _AssumptionRepo:
    def __init__(self, statements: tuple[FounderStatement, ...]) -> None:
        self._statements = statements

    def get_current(self, case_id: UUID) -> tuple[FounderStatement, ...]:
        assert case_id == CASE_ID
        return self._statements


class _PublicBenchmarkRepo:
    def __init__(self, inputs: tuple[ScenarioInput, ...]) -> None:
        self._inputs = inputs

    def get_current(self, case_id: UUID) -> tuple[ScenarioInput, ...]:
        assert case_id == CASE_ID
        return self._inputs


class _ScenarioRepo:
    def __init__(self, *, revision: int) -> None:
        self.revision = revision
        self.saved: list[StartupScenarioSet] = []
        self._by_idempotency: dict[str, StartupScenarioSet] = {}
        self._selection_by_idempotency: dict[str, ScenarioSelectionRecord] = {}

    def save(
        self,
        value: StartupScenarioSet,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> StartupScenarioSet:
        if idempotency_key in self._by_idempotency:
            return self._by_idempotency[idempotency_key]
        if expected_revision != self.revision or value.data_revision != self.revision:
            raise ValueError("case_revision_conflict")
        self.saved.append(value)
        self._by_idempotency[idempotency_key] = value
        return value

    def get_current(self, case_id: UUID) -> StartupScenarioSet:
        assert case_id == CASE_ID
        if not self.saved:
            raise KeyError("not_found")
        return self.saved[-1]

    def get_by_idempotency(self, case_id: UUID, idempotency_key: str) -> StartupScenarioSet | None:
        assert case_id == CASE_ID
        return self._by_idempotency.get(idempotency_key)

    def get_selection_by_idempotency(
        self,
        case_id: UUID,
        idempotency_key: str,
    ) -> ScenarioSelectionRecord | None:
        assert case_id == CASE_ID
        return self._selection_by_idempotency.get(idempotency_key)

    def save_selection(
        self,
        value: ScenarioSelectionRecord,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> ScenarioSelectionRecord:
        if idempotency_key in self._selection_by_idempotency:
            return self._selection_by_idempotency[idempotency_key]
        if expected_revision != self.revision:
            raise ValueError("case_revision_conflict")
        self._selection_by_idempotency[idempotency_key] = value
        return value


def _statement(field_key: str, value: str) -> FounderStatement:
    return FounderStatement(
        statement_id=uuid5(NAMESPACE_URL, f"statement:{field_key}:{value}"),
        case_id=CASE_ID,
        data_revision=2,
        field_key=field_key,
        value=value,
        confidence=Decimal("0.80"),
        rationale="Founder accepted planning statement",
    )


def _benchmark_input(
    input_key: str,
    value_range: ScenarioRange,
    *,
    unit: str,
    period: str,
    source_refs: tuple[UUID, ...],
) -> ScenarioInput:
    return ScenarioInput(
        input_id=uuid5(NAMESPACE_URL, f"benchmark:{input_key}:{value_range.lower}:{value_range.upper}"),
        case_id=CASE_ID,
        data_revision=2,
        input_key=input_key,
        value_range=value_range,
        unit=unit,
        period=period,
        provenance=CaseValueKind.PUBLIC_BENCHMARK,
        source_refs=source_refs,
        confidence="low",
        rationale="Cited public benchmark range.",
        validation_plan="Confirm with founder-specific source evidence.",
        what_would_confirm="Comparable public benchmark citation and later source evidence.",
        acceptance="proposed",
    )


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False

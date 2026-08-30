from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.scenario import (
    ScenarioInput,
    ScenarioMetric,
    ScenarioRange,
    StartupScenarioVariant,
    StartupScenarioSet,
)


def test_scenario_input_preserves_evidenced_source_fact_provenance() -> None:
    source_id = uuid4()
    source_fact = _make_input(
        provenance=CaseValueKind.SOURCE_FACT,
        source_refs=(source_id,),
        acceptance="accepted",
    )

    assert source_fact.provenance is CaseValueKind.SOURCE_FACT
    assert source_fact.source_refs == (source_id,)

    with pytest.raises(ValidationError, match="source refs"):
        ScenarioInput(
            input_key="monthly_price",
            value_range=ScenarioRange(lower=Decimal("30000"), upper=Decimal("50000")),
            unit="KZT/month",
            provenance=CaseValueKind.SOURCE_FACT,
            source_refs=(),
            dependency_refs=(),
            confidence="low",
            rationale="Copilot estimate",
            validation_plan="Run five paid pilots",
            acceptance="proposed",
        )


def test_scenario_input_preserves_accepted_founder_statement_provenance() -> None:
    statement_id = uuid4()
    founder_input = _make_input(
        provenance=CaseValueKind.FOUNDER_STATEMENT,
        source_refs=(statement_id,),
        acceptance="accepted",
    )

    assert founder_input.provenance is CaseValueKind.FOUNDER_STATEMENT
    assert founder_input.source_refs == (statement_id,)

    with pytest.raises(ValidationError, match="accepted founder_statement"):
        _make_input(
            provenance=CaseValueKind.FOUNDER_STATEMENT,
            source_refs=(statement_id,),
            acceptance="proposed",
        )


def test_scenario_range_rejects_negative_values_reversed_bounds_and_fake_precision() -> None:
    with pytest.raises(ValidationError, match="non-negative"):
        ScenarioRange(lower=Decimal("-1"), upper=Decimal("10"))

    with pytest.raises(ValidationError, match="lower <= upper"):
        ScenarioRange(lower=Decimal("10"), upper=Decimal("1"))

    with pytest.raises(ValidationError, match="fake precision"):
        ScenarioRange(lower=Decimal("30000.001"), upper=Decimal("50000.001"))


def test_scenario_input_requires_currency_period_refs_and_dependency_refs_by_kind() -> None:
    with pytest.raises(ValidationError, match="currency/period"):
        _make_input(unit="KZT")

    with pytest.raises(ValidationError, match="source refs"):
        _make_input(
            provenance=CaseValueKind.PUBLIC_BENCHMARK,
            source_refs=(),
            dependency_refs=(),
        )

    with pytest.raises(ValidationError, match="dependency refs"):
        _make_input(
            provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
            source_refs=(),
            dependency_refs=(),
        )


def test_startup_scenario_set_requires_one_case_revision_and_explicit_input_provenance() -> None:
    case_id = uuid4()
    scenario = StartupScenarioSet(
        scenario_set_id=uuid4(),
        case_id=case_id,
        data_revision=3,
        scenario_key="base_case",
        inputs=(
            _make_input(case_id=case_id, data_revision=3, input_key="monthly_price"),
        ),
        metrics=(
            ScenarioMetric(
                case_id=case_id,
                data_revision=3,
                metric_key="monthly_revenue",
                value_range=ScenarioRange(lower=Decimal("300000"), upper=Decimal("500000")),
                unit="KZT/month",
                provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
                dependency_refs=(uuid4(),),
                formula_key="monthly_price_times_customers",
                formula_description="Monthly price multiplied by paying customer count",
                confidence="medium",
                rationale="Depends on paid pilots and monthly price",
                validation_plan="Validate after first paid month",
                acceptance="proposed",
            ),
        ),
        rationale="Founder case projection",
        validation_plan="Review after three customer interviews",
        acceptance="proposed",
    )

    assert scenario.inputs[0].provenance is CaseValueKind.AI_SCENARIO

    with pytest.raises(ValidationError, match="same case_id and data_revision"):
        StartupScenarioSet(
            scenario_set_id=uuid4(),
            case_id=case_id,
            data_revision=3,
            scenario_key="mismatched_case",
            inputs=(
                _make_input(case_id=uuid4(), data_revision=3, input_key="monthly_price"),
            ),
            metrics=(),
            rationale="Founder case projection",
            validation_plan="Review after three customer interviews",
            acceptance="proposed",
        )

    with pytest.raises(ValidationError, match="same case_id and data_revision"):
        StartupScenarioSet(
            scenario_set_id=uuid4(),
            case_id=case_id,
            data_revision=3,
            scenario_key="mismatched_metric",
            inputs=(),
            metrics=(
                ScenarioMetric(
                    case_id=case_id,
                    data_revision=4,
                    metric_key="monthly_revenue",
                    value_range=ScenarioRange(lower=Decimal("300000"), upper=Decimal("500000")),
                    unit="KZT/month",
                    provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
                    dependency_refs=(uuid4(),),
                    formula_key="monthly_price_times_customers",
                    formula_description="Monthly price multiplied by paying customer count",
                    confidence="medium",
                    rationale="Depends on paid pilots and monthly price",
                    validation_plan="Validate after first paid month",
                    acceptance="proposed",
                ),
            ),
            rationale="Founder case projection",
            validation_plan="Review after three customer interviews",
            acceptance="proposed",
        )


def test_scenario_metric_requires_ownership_and_formula_metadata() -> None:
    with pytest.raises(ValidationError, match="formula"):
        ScenarioMetric(
            case_id=uuid4(),
            data_revision=1,
            metric_key="monthly_revenue",
            value_range=ScenarioRange(lower=Decimal("300000"), upper=Decimal("500000")),
            unit="KZT/month",
            provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
            dependency_refs=(uuid4(),),
            formula_key="",
            formula_description="Monthly price multiplied by paying customer count",
            confidence="medium",
            rationale="Depends on paid pilots and monthly price",
            validation_plan="Validate after first paid month",
            acceptance="proposed",
        )


def test_startup_scenario_set_can_expose_three_keyed_variants_without_losing_legacy_tuple_access() -> None:
    case_id = uuid4()
    conservative = _variant(case_id=case_id, data_revision=2, scenario_key="conservative")
    base = _variant(case_id=case_id, data_revision=2, scenario_key="base")
    optimistic = _variant(case_id=case_id, data_revision=2, scenario_key="optimistic")

    scenario_set = StartupScenarioSet(
        scenario_set_id=uuid4(),
        case_id=case_id,
        data_revision=2,
        scenarios={
            "conservative": conservative,
            "base": base,
            "optimistic": optimistic,
        },
        selected_scenario_key="base",
        rationale="Three planning scenarios for one founder case",
        validation_plan="Review after paid pilots",
        acceptance="proposed",
    )

    assert tuple(scenario_set.scenarios) == ("conservative", "base", "optimistic")
    assert scenario_set.scenarios["base"].metrics["mrr"].metric_key == "mrr"
    assert scenario_set.inputs == tuple(base.inputs.values())
    assert scenario_set.metrics == tuple(base.metrics.values())

    with pytest.raises(ValidationError, match="exactly conservative, base and optimistic"):
        StartupScenarioSet(
            scenario_set_id=uuid4(),
            case_id=case_id,
            data_revision=2,
            scenarios={"base": base},
            selected_scenario_key="base",
            rationale="Incomplete scenario set",
            validation_plan="Review after paid pilots",
            acceptance="proposed",
        )


def test_founder_statement_public_benchmark_and_ai_scenario_never_auto_promote_to_source_fact() -> None:
    for provenance in (
        CaseValueKind.FOUNDER_STATEMENT,
        CaseValueKind.PUBLIC_BENCHMARK,
        CaseValueKind.AI_SCENARIO,
    ):
        item = _make_input(
            provenance=provenance,
            source_refs=(uuid4(),) if provenance is not CaseValueKind.AI_SCENARIO else (),
            acceptance="accepted" if provenance is CaseValueKind.FOUNDER_STATEMENT else "proposed",
        )
        assert item.provenance is provenance
        assert item.provenance.value != CaseValueKind.SOURCE_FACT.value


def test_scenario_input_and_metric_support_first_class_period_with_legacy_unit_default_json_projection() -> None:
    legacy_input = _make_input(unit="KZT/month")
    explicit_input = _make_input(unit="KZT", period="month")
    metric = ScenarioMetric(
        case_id=uuid4(),
        data_revision=1,
        metric_key="mrr",
        value_range=ScenarioRange(lower=Decimal("300000"), upper=Decimal("500000")),
        unit="KZT",
        period="month",
        provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
        dependency_refs=(explicit_input.input_id,),
        formula_key="mrr",
        formula_description="Monthly price multiplied by paying customer count",
        confidence="medium",
        rationale="Depends on paid pilots and monthly price",
        validation_plan="Validate after first paid month",
        what_would_confirm="Invoices for the forecast period.",
        acceptance="proposed",
    )

    assert legacy_input.period == "month"
    assert explicit_input.unit == "KZT"
    assert explicit_input.period == "month"
    assert metric.unit == "KZT"
    assert metric.period == "month"
    assert explicit_input.model_dump(mode="json")["period"] == "month"
    assert metric.model_dump(mode="json")["period"] == "month"


def _make_input(
    *,
    case_id: UUID | None = None,
    data_revision: int = 1,
    input_key: str = "monthly_price",
    unit: str = "KZT/month",
    period: str | None = None,
    provenance: CaseValueKind = CaseValueKind.AI_SCENARIO,
    source_refs: tuple[UUID, ...] = (),
    dependency_refs: tuple[UUID, ...] = (),
    acceptance: str = "proposed",
) -> ScenarioInput:
    return ScenarioInput(
        case_id=case_id,
        data_revision=data_revision,
        input_key=input_key,
        value_range=ScenarioRange(lower=Decimal("30000"), upper=Decimal("50000")),
        unit=unit,
        period=period,
        provenance=provenance,
        source_refs=source_refs,
        dependency_refs=dependency_refs,
        confidence="low",
        rationale="Copilot estimate",
        validation_plan="Run five paid pilots",
        acceptance=acceptance,  # type: ignore[arg-type]
    )


def _variant(
    *,
    case_id: UUID,
    data_revision: int,
    scenario_key: str,
) -> StartupScenarioVariant:
    input_item = _make_input(
        case_id=case_id,
        data_revision=data_revision,
        input_key="monthly_price",
    )
    metric = ScenarioMetric(
        case_id=case_id,
        data_revision=data_revision,
        metric_key="mrr",
        value_range=ScenarioRange(lower=Decimal("1400000"), upper=Decimal("2000000")),
        unit="KZT/month",
        provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
        dependency_refs=(input_item.input_id,),
        formula_key="mrr",
        formula_description="Monthly price multiplied by paying customers",
        confidence="medium",
        rationale="Depends on accepted pricing and customer-count planning inputs",
        validation_plan="Validate after the first paid month",
        acceptance="proposed",
    )
    return StartupScenarioVariant(
        scenario_key=scenario_key,  # type: ignore[arg-type]
        inputs={"monthly_price": input_item},
        metrics={"mrr": metric},
        gaps={},
    )

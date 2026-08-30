from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID, uuid5

import pytest

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.application.services.startup_metric_service import StartupMetricService
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.metrics import MetricStatus
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.scenario import ScenarioRange
from due_diligence_agent.domain.metrics.startup import (
    STARTUP_FORMULA_SET_VERSION,
    startup_metric_names,
)


GOLDEN = Path(__file__).parents[2] / "golden" / "startup_synthetic_saas_v1" / "metrics.json"
CASE_ID = UUID("77777777-7777-4777-8777-777777777777")
ARTIFACT_ID = UUID("88888888-8888-4888-8888-888888888888")
FACT_NAMESPACE = UUID("99999999-9999-4999-8999-999999999999")
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def test_all_startup_metric_formulas_match_synthetic_saas_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert golden["schema_version"] == "startup_synthetic_saas_metrics_golden@1"
    assert golden["formula_set"] == STARTUP_FORMULA_SET_VERSION
    assert startup_metric_names() == tuple(case["metric"] for case in golden["cases"])
    assert len(golden["cases"]) == 16

    service = StartupMetricService()
    for case in golden["cases"]:
        facts = tuple(_fact_from_spec(spec) for spec in case["facts"])

        result = service.calculate(
            case["metric"],
            tuple(reversed(facts)),
            assumptions=case.get("assumptions", {}),
        )

        expected = case["expected"]
        assert result.status.value == expected["status"]
        assert result.formula_version == case["formula_version"]
        assert result.value == Decimal(expected["value"])
        assert result.display_value == expected["display"]
        assert result.unit == expected["unit"]
        assert result.period == expected["period"]
        assert result.input_evidence_ids == tuple(_fact_id(alias) for alias in expected["input_aliases"])
        assert result.warnings == tuple(expected["warnings"])


def test_runway_is_calculated_from_cash_and_normalized_monthly_burn() -> None:
    service = StartupMetricService()

    result = service.calculate(
        "runway_months",
        (
            _fact("cash", "cash", "950000", unit="USD", period="2026-07"),
            _fact(
                "monthly_burn",
                "monthly_net_burn",
                "100000",
                unit="USD/month",
                period="2026-07",
            ),
        ),
    )

    assert result.status is MetricStatus.CALCULATED
    assert result.value == Decimal("9.500000")
    assert result.formula_version == "runway_months@1"
    assert result.unit == "months"


def test_ltv_without_explicit_model_is_insufficient_data() -> None:
    result = StartupMetricService().calculate(
        "ltv",
        (
            _fact("arpa", "monthly_arpa", "100", unit="USD/month", period="2026-07"),
            _fact("churn", "logo_churn_rate", "0.05", unit="ratio", period="2026-07"),
        ),
        assumptions={},
    )

    assert result.status is MetricStatus.INSUFFICIENT_DATA
    assert result.warnings == ("assumption.missing:ltv_model",)


def test_fail_closed_for_missing_duplicate_period_unit_denominator_and_conditions() -> None:
    service = StartupMetricService()

    cases = [
        (
            "runway_months",
            (_fact("cash", "cash", "950000", unit="USD", period="2026-07"),),
            {},
            "input.missing:monthly_net_burn",
        ),
        (
            "gross_margin",
            (
                _fact("revenue", "revenue", "100", unit="USD", period="2026-Q2"),
                _fact("cogs1", "cogs", "40", unit="USD", period="2026-Q2"),
                _fact("cogs2", "cogs", "30", unit="USD", period="2026-Q2"),
            ),
            {},
            "input.duplicate:cogs",
        ),
        (
            "gross_margin",
            (
                _fact("revenue", "revenue", "100", unit="USD", period="2026-Q2"),
                _fact("cogs", "cogs", "40", unit="EUR", period="2026-Q2"),
            ),
            {},
            "unit.currency_mismatch",
        ),
        (
            "period_growth",
            (
                _fact("revenue_2026", "revenue", "100", unit="USD", period="2026-Q2"),
                _fact("revenue_2025", "revenue", "40", unit="USD", period="2025"),
            ),
            {},
            "period.mismatch",
        ),
        (
            "cac",
            (
                _fact("sales", "sales_marketing_spend", "50000", unit="USD", period="2026-Q2"),
                _fact("customers", "new_customers", "0", unit="count", period="2026-Q2"),
            ),
            {},
            "denominator.non_positive:new_customers",
        ),
        (
            "rule_of_40",
            (
                _fact("growth", "revenue_growth_rate", "0.25", unit="ratio", period="2026"),
                _fact("margin", "profit_margin", "-0.1", unit="ratio", period="2026"),
            ),
            {"business_model": "marketplace", "stage": "growth"},
            "condition.inapplicable:rule_of_40",
        ),
    ]

    for metric, facts, assumptions, warning in cases:
        result = service.calculate(metric, facts, assumptions=assumptions)
        assert result.status is MetricStatus.INSUFFICIENT_DATA
        assert result.value is None
        assert result.display_value is None
        assert result.warnings == (warning,)


def test_calculate_available_is_deterministic_and_does_not_invent_missing_inputs() -> None:
    facts = (
        _fact("mrr_a", "monthly_recurring_revenue", "10000", unit="USD/month", period="2026-07"),
        _fact("mrr_b", "monthly_recurring_revenue", "5000", unit="USD/month", period="2026-07"),
        _fact("cash", "cash", "300000", unit="USD", period="2026-07"),
        _fact("burn", "monthly_net_burn", "60000", unit="USD/month", period="2026-07"),
    )

    results = StartupMetricService().calculate_available(facts)

    assert tuple(result.metric_name for result in results) == ("mrr", "arr", "runway_months")
    assert [result.value for result in results] == [
        Decimal("15000.000000"),
        Decimal("180000.000000"),
        Decimal("5.000000"),
    ]


def test_calculate_available_handles_metric_specific_period_subsets_without_dropping_current_metrics() -> None:
    facts = (
        _fact("revenue_q1", "revenue", "96000", unit="USD", period="2026-Q1"),
        _fact("revenue_q2", "revenue", "120000", unit="USD", period="2026-Q2"),
        _fact("cogs_q2", "cogs", "36000", unit="USD", period="2026-Q2"),
    )

    results = StartupMetricService().calculate_available(facts)

    assert tuple(result.metric_name for result in results) == ("period_growth", "gross_margin")
    assert results[0].value == Decimal("0.250000")
    assert results[0].input_evidence_ids == (_fact_id("revenue_q2"), _fact_id("revenue_q1"))
    assert results[1].value == Decimal("0.700000")
    assert results[1].input_evidence_ids == (_fact_id("revenue_q2"), _fact_id("cogs_q2"))


def test_calculate_available_keeps_shared_mrr_and_cohort_selection_deterministic() -> None:
    facts = (
        _fact("mrr_a", "monthly_recurring_revenue", "10000", unit="USD/month", period="2026-07"),
        _fact("mrr_b", "monthly_recurring_revenue", "5000", unit="USD/month", period="2026-07"),
        _fact(
            "cohort_start",
            "starting_cohort_customers",
            "100",
            unit="count",
            period="2026-01",
            metadata={"cohort_id": "jan", "cohort_start_period": "2026-01"},
        ),
        _fact(
            "cohort_end",
            "ending_cohort_customers",
            "80",
            unit="count",
            period="2026-07",
            metadata={"cohort_id": "jan", "cohort_start_period": "2026-01"},
        ),
    )

    results = StartupMetricService().calculate_available(tuple(reversed(facts)))

    assert tuple(result.metric_name for result in results) == ("mrr", "arr", "cohort_retention")
    assert results[0].input_evidence_ids == (_fact_id("mrr_b"), _fact_id("mrr_a"))
    assert results[1].input_evidence_ids == (_fact_id("mrr_b"), _fact_id("mrr_a"))
    assert results[2].input_evidence_ids == (_fact_id("cohort_start"), _fact_id("cohort_end"))


def test_calculate_available_selects_latest_complete_matching_cohort_pair() -> None:
    facts = (
        _fact(
            "jan_start",
            "starting_cohort_customers",
            "100",
            unit="count",
            period="2026-01",
            metadata={"cohort_id": "jan", "cohort_start_period": "2026-01"},
        ),
        _fact(
            "jan_end",
            "ending_cohort_customers",
            "80",
            unit="count",
            period="2026-07",
            metadata={"cohort_id": "jan", "cohort_start_period": "2026-01"},
        ),
        _fact(
            "feb_end_incomplete",
            "ending_cohort_customers",
            "70",
            unit="count",
            period="2026-08",
            metadata={"cohort_id": "feb", "cohort_start_period": "2026-02"},
        ),
    )

    results = StartupMetricService().calculate_available(facts)

    assert tuple(result.metric_name for result in results) == ("cohort_retention",)
    assert results[0].value == Decimal("0.800000")
    assert results[0].input_evidence_ids == (_fact_id("jan_start"), _fact_id("jan_end"))


def test_startup_metric_edge_cases_are_explicit_and_fail_closed() -> None:
    service = StartupMetricService()

    unsupported_ltv_model = service.calculate(
        "ltv",
        (
            _fact("arpa", "monthly_arpa", "100", unit="USD/month", period="2026-07"),
            _fact("gm", "gross_margin_rate", "0.70", unit="ratio", period="2026-07"),
            _fact("churn", "logo_churn_rate", "0.05", unit="ratio", period="2026-07"),
        ),
        assumptions={"ltv_model": "revenue_multiple"},
    )
    assert unsupported_ltv_model.warnings == ("assumption.unsupported:ltv_model",)

    nrr = service.calculate(
        "nrr",
        (
            _fact("opening", "opening_mrr", "100000", unit="USD/month", period="2026-Q2"),
            _fact("expansion", "expansion_mrr", "20000", unit="USD/month", period="2026-Q2"),
            _fact("contraction", "contraction_mrr", "5000", unit="USD/month", period="2026-Q2"),
            _fact("churned", "churned_mrr", "10000", unit="USD/month", period="2026-Q2"),
        ),
    )
    assert nrr.value == Decimal("1.050000")

    burn_multiple = service.calculate(
        "burn_multiple",
        (
            _fact("burn", "net_burn", "60000", unit="USD", period="2026-Q2"),
            _fact("net_new_arr", "net_new_arr", "0", unit="USD", period="2026-Q2"),
        ),
    )
    assert burn_multiple.warnings == ("denominator.non_positive:net_new_arr",)

    non_monthly_burn = service.calculate(
        "runway_months",
        (
            _fact("cash", "cash", "300000", unit="USD", period="2026-Q2"),
            _fact("burn", "monthly_net_burn", "60000", unit="USD", period="2026-Q2"),
        ),
    )
    assert non_monthly_burn.warnings == ("unit.mismatch:monthly_net_burn",)

    unexpected = service.calculate(
        "runway_months",
        (
            _fact("cash", "cash", "300000", unit="USD", period="2026-07"),
            _fact("burn", "monthly_net_burn", "60000", unit="USD/month", period="2026-07"),
            _fact("extra", "revenue", "1", unit="USD", period="2026-07"),
        ),
    )
    assert unexpected.warnings == ("input.unexpected",)

    mrr = service.calculate(
        "mrr",
        (
            _fact("mrr_a", "monthly_recurring_revenue", "10000", unit="USD/month", period="2026-07"),
            _fact("mrr_b", "monthly_recurring_revenue", "5000", unit="USD/month", period="2026-07"),
        ),
    )
    assert mrr.value == Decimal("15000.000000")

    mixed_fx = service.calculate(
        "mrr",
        (
            _fact("mrr_usd", "monthly_recurring_revenue", "10000", unit="USD/month", period="2026-07"),
            _fact("mrr_eur", "monthly_recurring_revenue", "5000", unit="EUR/month", period="2026-07"),
        ),
    )
    assert mixed_fx.warnings == ("unit.currency_mismatch",)

    invalid_units = [
        ("bananas", "unit.unsupported:cash"),
        ("", "unit.unsupported:cash"),
        ("/month", "unit.unsupported:monthly_net_burn"),
        ("ABC", "unit.unsupported:cash"),
        ("ABC/month", "unit.unsupported:monthly_net_burn"),
    ]
    for unit, warning in invalid_units:
        metric = "runway_months"
        facts = (
            _fact_with_possible_empty_unit(
                "cash_bad",
                "cash",
                "300000",
                unit=unit if not unit.endswith("/month") else "USD",
                period="2026-07",
            ),
            _fact_with_possible_empty_unit(
                "burn_bad",
                "monthly_net_burn",
                "60000",
                unit=unit if unit.endswith("/month") else "USD/month",
                period="2026-07",
            ),
        )
        assert service.calculate(metric, facts).warnings == (warning,)

    cohort_mismatch = service.calculate(
        "cohort_retention",
        (
            _fact(
                "start",
                "starting_cohort_customers",
                "100",
                unit="count",
                period="2026-01",
                metadata={"cohort_id": "jan", "cohort_start_period": "2026-01"},
            ),
            _fact(
                "end",
                "ending_cohort_customers",
                "80",
                unit="count",
                period="2026-07",
                metadata={"cohort_id": "feb", "cohort_start_period": "2026-02"},
            ),
        ),
    )
    assert cohort_mismatch.warnings == ("cohort.mismatch",)


def test_service_persists_only_calculated_results_with_stable_id_and_highest_sensitivity() -> None:
    facts = [
        _fact("cash", "cash", "300000", unit="USD", period="2026-07"),
        _fact(
            "burn",
            "monthly_net_burn",
            "60000",
            unit="USD/month",
            period="2026-07",
            sensitivity=SensitivityClass.CONFIDENTIAL,
        ),
    ]
    repo = _CalculationRepo()
    service = StartupMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=repo,
        clock=lambda: NOW,
    )

    result = service.calculate_for_case(
        CASE_ID,
        "runway_months",
        evidence_fact_ids=tuple(fact.id for fact in facts),
    )
    second = service.calculate_for_case(
        CASE_ID,
        "runway_months",
        evidence_fact_ids=tuple(reversed([fact.id for fact in facts])),
    )
    insufficient = service.calculate_for_case(CASE_ID, "runway_months", evidence_fact_ids=(facts[0].id,))

    assert result.calculation_id == second.calculation_id
    assert insufficient.status is MetricStatus.INSUFFICIENT_DATA
    assert len(repo.saved) == 1
    assert repo.saved[0].id == result.calculation_id
    assert repo.saved[0].sensitivity is SensitivityClass.CONFIDENTIAL
    assert repo.saved[0].input_fact_ids == (_fact_id("cash"), _fact_id("burn"))


def test_case_service_rejects_bad_ids_non_utc_clock_and_conflicting_existing_calculation() -> None:
    facts = [
        _fact("cash", "cash", "300000", unit="USD", period="2026-07"),
        _fact("burn", "monthly_net_burn", "60000", unit="USD/month", period="2026-07"),
    ]
    service = StartupMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=_CalculationRepo(),
        clock=lambda: NOW,
    )

    with pytest.raises(ValueError, match=f"evidence_fact_id.duplicate:{facts[0].id}"):
        service.calculate_for_case(
            CASE_ID,
            "runway_months",
            evidence_fact_ids=(facts[0].id, facts[0].id),
        )
    missing_id = UUID("00000000-0000-4000-8000-000000000001")
    with pytest.raises(ValueError, match=f"evidence_fact_id.not_in_case:{missing_id}"):
        service.calculate_for_case(CASE_ID, "runway_months", evidence_fact_ids=(missing_id,))

    non_utc = StartupMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=_CalculationRepo(),
        clock=lambda: datetime(2026, 8, 9, 12, 0),
    )
    with pytest.raises(ValueError, match="timestamp must be timezone-aware UTC"):
        non_utc.calculate_for_case(
            CASE_ID,
            "runway_months",
            evidence_fact_ids=tuple(fact.id for fact in facts),
        )

    repo = _CalculationRepo()
    ok = StartupMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=repo,
        clock=lambda: NOW,
    )
    ok.calculate_for_case(CASE_ID, "runway_months", evidence_fact_ids=tuple(fact.id for fact in facts))
    repo.saved[0] = repo.saved[0].model_copy(update={"value": Decimal("6.000000")})
    with pytest.raises(ValueError, match="calculation_id_conflict"):
        ok.calculate_for_case(CASE_ID, "runway_months", evidence_fact_ids=tuple(fact.id for fact in facts))


def test_scenario_mrr_and_arr_use_decimal_ranges_and_metric_dependency_ids() -> None:
    service = StartupMetricService()

    mrr = service.calculate_scenario(
        "mrr",
        {
            "monthly_price": ScenarioRange(lower=Decimal("35000"), upper=Decimal("40000")),
            "paying_customers": ScenarioRange(lower=Decimal("40"), upper=Decimal("50")),
        },
    )
    assert mrr.value_range is not None
    arr = service.calculate_scenario("arr", {"mrr": mrr.value_range})

    assert mrr.value_range == ScenarioRange(lower=Decimal("1400000"), upper=Decimal("2000000"))
    assert mrr.provenance is CaseValueKind.DETERMINISTIC_CALCULATION
    assert mrr.formula_key == "mrr"
    assert mrr.dependency_refs
    assert mrr.what_would_confirm == "Signed paid customers and invoices for the forecast month."
    assert arr.value_range == ScenarioRange(lower=Decimal("16800000"), upper=Decimal("24000000"))
    assert arr.dependency_refs == (mrr.metric_id,)


def test_scenario_formula_edges_fail_closed_without_unexplained_zeroes_or_fabricated_negative_ranges() -> None:
    service = StartupMetricService()

    gross_margin = service.calculate_scenario(
        "gross_margin",
        {
            "revenue": ScenarioRange(lower=Decimal("100"), upper=Decimal("200")),
            "cogs": ScenarioRange(lower=Decimal("30"), upper=Decimal("80")),
        },
    )
    net_burn_gap = service.calculate_scenario(
        "net_burn",
        {
            "monthly_operating_expenses": ScenarioRange(lower=Decimal("100"), upper=Decimal("120")),
            "monthly_revenue": ScenarioRange(lower=Decimal("150"), upper=Decimal("200")),
        },
    )
    runway_gap = service.calculate_scenario(
        "runway_months",
        {
            "cash_balance": ScenarioRange(lower=Decimal("1000"), upper=Decimal("1200")),
            "net_burn": ScenarioRange(lower=Decimal("0"), upper=Decimal("0")),
        },
    )
    ltv = service.calculate_scenario(
        "ltv",
        {
            "arpa": ScenarioRange(lower=Decimal("100"), upper=Decimal("120")),
            "gross_margin": ScenarioRange(lower=Decimal("0.60"), upper=Decimal("0.80")),
            "churn": ScenarioRange(lower=Decimal("0.04"), upper=Decimal("0.05")),
        },
    )
    ltv_missing_churn = service.calculate_scenario(
        "ltv",
        {
            "arpa": ScenarioRange(lower=Decimal("100"), upper=Decimal("120")),
            "gross_margin": ScenarioRange(lower=Decimal("0.60"), upper=Decimal("0.80")),
        },
    )
    cac_zero_customers = service.calculate_scenario(
        "cac",
        {
            "acquisition_spend": ScenarioRange(lower=Decimal("1000"), upper=Decimal("1200")),
            "acquired_customers": ScenarioRange(lower=Decimal("0"), upper=Decimal("0")),
        },
    )

    assert gross_margin.value_range == ScenarioRange(lower=Decimal("0.20"), upper=Decimal("0.85"))
    assert net_burn_gap.value_range is None
    assert net_burn_gap.gaps == ("ineligible.net_burn:revenue_exceeds_expenses",)
    assert runway_gap.value_range is None
    assert runway_gap.gaps == ("denominator.non_positive:net_burn",)
    assert ltv.value_range == ScenarioRange(lower=Decimal("1200.00"), upper=Decimal("2400.00"))
    assert ltv_missing_churn.value_range is None
    assert ltv_missing_churn.gaps == ("input.missing:churn",)
    assert cac_zero_customers.value_range is None
    assert cac_zero_customers.gaps == ("denominator.non_positive:acquired_customers",)


def test_scenario_gross_margin_negative_ranges_fail_closed_without_validation_error() -> None:
    service = StartupMetricService()

    fully_negative = service.calculate_scenario(
        "gross_margin",
        {
            "revenue": ScenarioRange(lower=Decimal("100"), upper=Decimal("120")),
            "cogs": ScenarioRange(lower=Decimal("130"), upper=Decimal("150")),
        },
    )
    partially_negative = service.calculate_scenario(
        "gross_margin",
        {
            "revenue": ScenarioRange(lower=Decimal("100"), upper=Decimal("200")),
            "cogs": ScenarioRange(lower=Decimal("80"), upper=Decimal("250")),
        },
    )

    assert fully_negative.value_range is None
    assert fully_negative.gaps == ("ineligible.gross_margin:cogs_exceeds_revenue",)
    assert fully_negative.validation_plan
    assert fully_negative.what_would_confirm
    assert partially_negative.value_range is None
    assert partially_negative.gaps == ("ineligible.gross_margin:range_crosses_negative_margin",)
    assert partially_negative.validation_plan
    assert partially_negative.what_would_confirm


def _fact_from_spec(spec: dict[str, object]) -> EvidenceFact:
    raw_metadata = spec.get("metadata", {})
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    return _fact(
        str(spec["alias"]),
        str(spec["name"]),
        str(spec["value"]),
        unit=str(spec["unit"]),
        period=str(spec["period"]),
        sensitivity=SensitivityClass(str(spec.get("sensitivity", "public"))),
        metadata={str(key): str(value) for key, value in metadata.items()},
    )


def _fact(
    alias: str,
    name: str,
    value: str,
    *,
    unit: str,
    period: str,
    sensitivity: SensitivityClass = SensitivityClass.PUBLIC,
    metadata: dict[str, str] | None = None,
) -> EvidenceFact:
    return EvidenceFact(
        id=_fact_id(alias),
        artifact_id=ARTIFACT_ID,
        name=name,
        value=Decimal(value),
        value_type="decimal",
        unit=unit,
        period=period,
        locator=SourceLocator(kind="signed_document", value=name, artifact_id=ARTIFACT_ID),
        sensitivity=sensitivity,
        confidence=Decimal("0.95"),
        source_priority=SourcePriority.OFFICIAL_OR_SIGNED,
        extraction_method="fixture",
        supporting_text_hash="d" * 64,
        source_freshness_at=NOW,
        retrieved_at=NOW,
        metadata=metadata or {},
    )


def _fact_with_possible_empty_unit(
    alias: str,
    name: str,
    value: str,
    *,
    unit: str,
    period: str,
) -> EvidenceFact:
    if unit:
        return _fact(alias, name, value, unit=unit, period=period)
    return EvidenceFact.model_construct(
        id=_fact_id(alias),
        artifact_id=ARTIFACT_ID,
        name=name,
        value=Decimal(value),
        value_type="decimal",
        unit=unit,
        period=period,
        locator=SourceLocator(kind="signed_document", value=name, artifact_id=ARTIFACT_ID),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.95"),
        source_priority=SourcePriority.OFFICIAL_OR_SIGNED,
        extraction_method="fixture",
        supporting_text_hash="d" * 64,
        source_freshness_at=NOW,
        retrieved_at=NOW,
        metadata={},
        version=1,
    )


def _fact_id(alias: str) -> UUID:
    return uuid5(FACT_NAMESPACE, alias)


class _EvidenceRepo:
    def __init__(self, facts_by_case: dict[UUID, list[EvidenceFact]]) -> None:
        self._facts_by_case = facts_by_case

    def add(self, fact: EvidenceFact) -> None:
        raise NotImplementedError

    def list_for_case(self, case_id: UUID) -> list[EvidenceFact]:
        return list(self._facts_by_case.get(case_id, ()))


class _CalculationRepo:
    def __init__(self) -> None:
        self.saved: list[Calculation] = []

    def add(self, calculation: Calculation) -> None:
        if any(existing.id == calculation.id for existing in self.saved):
            raise ValueError("calculation_already_exists")
        self.saved.append(calculation)

    def list_for_case(self, case_id: UUID) -> list[Calculation]:
        return [item for item in self.saved if item.case_id == case_id]

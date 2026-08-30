from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.application.services.public_metric_service import PublicMetricService
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.metrics import (
    MetricCalculationResult,
    MetricEngine,
    MetricStatus,
    public_metric_names,
)
from due_diligence_agent.domain.metrics.definitions import FORMULA_SET_VERSION


GOLDEN = Path(__file__).parents[2] / "golden" / "public_us_frozen_v1" / "metrics.json"
CASE_ID = UUID("11111111-1111-4111-8111-111111111111")
ARTIFACT_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
FACT_NAMESPACE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_all_13_public_metric_formulas_match_rich_frozen_golden_file() -> None:
    golden = _golden()

    assert golden["schema_version"] == "public_us_frozen_metrics_golden@1"
    assert golden["formula_set"] == FORMULA_SET_VERSION
    assert public_metric_names() == tuple(case["metric"] for case in golden["cases"])
    assert len(golden["cases"]) == 13

    engine = MetricEngine()
    for case in golden["cases"]:
        facts = tuple(_fact_from_spec(spec) for spec in case["facts"])
        as_of = _parse_as_of(case.get("as_of"))

        result = engine.calculate(case["metric"], tuple(reversed(facts)), as_of=as_of)

        expected = case["expected"]
        assert result.status.value == expected["status"]
        assert result.formula_version == case["formula_version"]
        assert result.value == Decimal(expected["value"])
        assert result.display_value == expected["display"]
        assert result.unit == expected["unit"]
        assert result.period == expected["period"]
        assert result.input_evidence_ids == tuple(_fact_id(alias) for alias in expected["input_aliases"])
        assert result.warnings == tuple(expected["warnings"])


def test_engine_rejects_unrelated_explicit_facts_and_keeps_current_prior_order_caller_independent() -> None:
    facts = (
        _fact("prior", "revenue", "100", period="2024-Q4"),
        _fact("current", "revenue", "125", period="2025-Q4"),
    )
    result = MetricEngine().calculate("revenue_growth", tuple(reversed(facts)))
    assert result.value == Decimal("0.250000")
    assert result.input_evidence_ids == (_fact_id("current"), _fact_id("prior"))

    extra = facts + (_fact("extra", "net_income", "1", period="2025-Q4"),)
    rejected = MetricEngine().calculate("revenue_growth", extra)
    assert rejected.status is MetricStatus.INSUFFICIENT_DATA
    assert rejected.warnings == ("input.unexpected",)


def test_engine_accepts_non_consecutive_earlier_same_kind_prior_period() -> None:
    result = MetricEngine().calculate(
        "revenue_growth",
        (
            _fact("cur", "revenue", "150", period="2025"),
            _fact("pri", "revenue", "100", period="2023"),
        ),
    )

    assert result.status is MetricStatus.CALCULATED
    assert result.value == Decimal("0.500000")


def test_engine_accepts_quarterly_prior_earlier_than_current_independent_of_caller_order() -> None:
    result = MetricEngine().calculate(
        "revenue_growth",
        (
            _fact("q3", "revenue", "100", period="2025-Q3"),
            _fact("q4", "revenue", "125", period="2025-Q4"),
        ),
    )

    assert result.status is MetricStatus.CALCULATED
    assert result.value == Decimal("0.250000")
    assert result.input_evidence_ids == (_fact_id("q4"), _fact_id("q3"))


def test_engine_classifies_same_kind_single_period_disagreement_as_period_mismatch() -> None:
    result = MetricEngine().calculate(
        "gross_margin",
        (
            _fact("gp", "gross_profit", "40", period="2025"),
            _fact("rev", "revenue", "100", period="2024"),
        ),
    )

    assert result.status is MetricStatus.INSUFFICIENT_DATA
    assert result.warnings == ("period.mismatch",)


def test_engine_classifies_split_same_kind_prior_group_as_period_mismatch() -> None:
    result = MetricEngine().calculate(
        "working_capital_trend",
        (
            _fact("assets-current", "current_assets", "200", period="2025"),
            _fact("liabilities-current", "current_liabilities", "80", period="2025"),
            _fact("assets-prior", "current_assets", "150", period="2024"),
            _fact("liabilities-prior", "current_liabilities", "70", period="2023"),
        ),
    )

    assert result.status is MetricStatus.INSUFFICIENT_DATA
    assert result.warnings == ("period.mismatch",)


def test_engine_keeps_unprovided_shared_name_slot_as_input_missing() -> None:
    result = MetricEngine().calculate(
        "revenue_growth",
        (_fact("current", "revenue", "125", period="2025"),),
    )

    assert result.status is MetricStatus.INSUFFICIENT_DATA
    assert result.warnings == ("input.missing:prior_revenue",)


def test_engine_enforces_valuation_as_of_without_application_source_priority() -> None:
    facts = (
        _fact("mc", "market_cap", "3000", period="2026-08-09", source="market"),
        _fact("debt", "total_debt", "250"),
        _fact("cash", "cash_and_equivalents", "100"),
        _fact("rev", "revenue", "500"),
    )

    assert MetricEngine().calculate("ev_sales", facts).warnings == ("as_of.required",)
    assert MetricEngine().calculate(
        "ev_sales", facts, as_of=datetime(2026, 8, 8, tzinfo=UTC)
    ).warnings == ("as_of.mismatch:market_cap",)
    assert MetricEngine().calculate(
        "ev_sales", facts, as_of=datetime(2026, 8, 9, tzinfo=UTC)
    ).status is MetricStatus.CALCULATED


def test_engine_same_count_unrelated_facts_are_unexpected_and_iso_date_financial_periods_invalid() -> None:
    unexpected = MetricEngine().calculate(
        "gross_margin",
        (_fact("gp", "gross_profit", "1"), _fact("ni", "net_income", "2")),
    )
    assert unexpected.warnings == ("input.unexpected",)

    invalid_period = MetricEngine().calculate(
        "gross_margin",
        (_fact("gp", "gross_profit", "1", period="2026-08-09"), _fact("rev", "revenue", "2")),
    )
    assert invalid_period.warnings == ("period.invalid",)

    extra_mixed_unrelated = MetricEngine().calculate(
        "gross_margin",
        (
            _fact("gp", "gross_profit", "1"),
            _fact("rev", "revenue", "2"),
            _fact("extra", "net_income", "1", period="2025-Q4"),
        ),
    )
    assert extra_mixed_unrelated.warnings == ("input.unexpected",)


def test_engine_fails_closed_with_stable_warning_codes() -> None:
    cases = [
        ("gross_margin", (_fact("gp", "gross_profit", "1"),), "input.missing:revenue"),
        ("gross_margin", (_fact("gp", "gross_profit", "1"), _fact("rev", "revenue", "0")), "denominator.non_positive:revenue"),
        ("free_cash_flow", (_fact("ocf", "operating_cash_flow", "1"), _fact("capex", "capital_expenditures", "-1")), "capex.negative"),
        ("net_margin", (_fact("ni", "net_income", "1", unit="EUR"), _fact("rev", "revenue", "2", unit="USD")), "unit.mismatch"),
        ("dilution", (_fact("cur", "weighted_average_diluted_shares", "1", unit="shares", period="2025"), _fact("pri", "weighted_average_diluted_shares", "1", unit="USD", period="2024")), "unit.mismatch"),
        ("revenue_growth", (_fact("cur", "revenue", "1", period="2025"), _fact("pri", "revenue", "1", period="2024-Q4")), "period.mismatch"),
        ("gross_margin", (_fact("gp", "gross_profit", "1", period="FY2025"), _fact("rev", "revenue", "2", period="FY2025")), "period.invalid"),
    ]
    for metric, facts, warning in cases:
        result = MetricEngine().calculate(metric, facts)

        assert result.status is MetricStatus.INSUFFICIENT_DATA
        assert result.value is None
        assert result.display_value is None
        assert result.warnings == (warning,)


def test_engine_rejects_duplicate_same_name_period_and_non_decimal_values() -> None:
    duplicate = (
        _fact("gp", "gross_profit", "1"),
        _fact("rev1", "revenue", "2"),
        _fact("rev2", "revenue", "3"),
    )
    assert MetricEngine().calculate("gross_margin", duplicate).warnings == ("input.duplicate:revenue",)

    current_duplicate = (
        _fact("cur1", "revenue", "2", period="2025"),
        _fact("cur2", "revenue", "3", period="2025"),
        _fact("pri", "revenue", "1", period="2024"),
    )
    assert MetricEngine().calculate("revenue_growth", current_duplicate).warnings == (
        "input.duplicate:current_revenue",
    )

    prior_duplicate = (
        _fact("cur", "revenue", "2", period="2025"),
        _fact("pri1", "revenue", "1", period="2024"),
        _fact("pri2", "revenue", "1", period="2024"),
    )
    assert MetricEngine().calculate("revenue_growth", prior_duplicate).warnings == (
        "input.duplicate:prior_revenue",
    )

    non_numeric = (
        _fact("ni", "net_income", "1").model_copy(update={"value": "not-number"}),
        _fact("rev", "revenue", "2"),
    )
    assert MetricEngine().calculate("net_margin", non_numeric).warnings == ("input.non_numeric:net_income",)

    with pytest.raises(KeyError, match="unknown_metric:not_a_metric"):
        MetricEngine().calculate("not_a_metric", ())


def test_engine_preserves_valid_negative_outputs_and_canonical_negative_zero_display() -> None:
    engine = MetricEngine()
    assert engine.calculate("gross_margin", (_fact("gp", "gross_profit", "-10"), _fact("rev", "revenue", "500"))).value == Decimal("-0.020000")
    assert engine.calculate("free_cash_flow", (_fact("ocf", "operating_cash_flow", "5"), _fact("capex", "capital_expenditures", "20"))).value == Decimal("-15.000000")
    assert engine.calculate("net_debt", (_fact("debt", "total_debt", "50"), _fact("cash", "cash_and_equivalents", "300"))).value == Decimal("-250.000000")
    assert engine.calculate("interest_coverage", (_fact("ebit", "ebit", "-40"), _fact("int", "interest_expense", "50"))).value == Decimal("-0.800000")
    near_zero = engine.calculate("gross_margin", (_fact("gp", "gross_profit", "-0.0000001"), _fact("rev", "revenue", "1")))
    assert near_zero.value == Decimal("0.000000")
    assert near_zero.display_value == "0.0000"


def test_service_enforces_official_sources_market_as_of_and_explicit_case_ids() -> None:
    repo = _EvidenceRepo({CASE_ID: [_fact("gp", "gross_profit", "200", source="market"), _fact("rev", "revenue", "500")]})
    service = PublicMetricService(evidence_repository=repo, calculation_repository=_CalculationRepo(), clock=lambda: NOW)

    result = service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=(_fact_id("gp"), _fact_id("rev")))
    assert result.warnings == ("source.ineligible:gross_profit",)

    market = _fact("mc", "market_cap", "3000", period="2026-08-09", source="market")
    official = [_fact("debt", "total_debt", "250"), _fact("cash", "cash_and_equivalents", "100"), _fact("rev", "revenue", "500")]
    service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: [market, *official]}),
        calculation_repository=_CalculationRepo(),
        clock=lambda: NOW,
    )
    ids = tuple(f.id for f in [market, *official])
    assert service.calculate(CASE_ID, "ev_sales", evidence_fact_ids=ids).warnings == ("as_of.required",)
    assert service.calculate(CASE_ID, "ev_sales", evidence_fact_ids=ids, as_of=datetime(2026, 8, 8, tzinfo=UTC)).warnings == ("as_of.mismatch:market_cap",)
    assert service.calculate(CASE_ID, "ev_sales", evidence_fact_ids=ids, as_of=datetime(2026, 8, 9, tzinfo=UTC)).status is MetricStatus.CALCULATED


def test_service_source_governance_is_slot_ordered_for_reversed_current_prior_inputs() -> None:
    current = _fact("cur", "revenue", "500", period="2025")
    prior = _fact("pri", "revenue", "400", period="2024", source="model")
    service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: [current, prior]}),
        calculation_repository=_CalculationRepo(),
        clock=lambda: NOW,
    )

    result = service.calculate(
        CASE_ID,
        "revenue_growth",
        evidence_fact_ids=(prior.id, current.id),
    )

    assert result.warnings == ("source.ineligible:prior_revenue",)


def test_service_rejects_news_and_model_locator_kinds_even_with_official_numeric_priority() -> None:
    current = _fact("cur", "revenue", "500", period="2025")
    prior = _fact("pri", "revenue", "400", period="2024", locator_kind="news_metadata")
    model_prior = _fact("model_pri", "revenue", "400", period="2024", locator_kind="model_inference")
    service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: [current, prior, model_prior]}),
        calculation_repository=_CalculationRepo(),
        clock=lambda: NOW,
    )

    assert service.calculate(
        CASE_ID,
        "revenue_growth",
        evidence_fact_ids=(prior.id, current.id),
    ).warnings == ("source.ineligible:prior_revenue",)
    assert service.calculate(
        CASE_ID,
        "revenue_growth",
        evidence_fact_ids=(model_prior.id, current.id),
    ).warnings == ("source.ineligible:prior_revenue",)


def test_service_allows_signed_document_official_financial_evidence() -> None:
    facts = (
        _fact("gp", "gross_profit", "200", locator_kind="signed_document"),
        _fact("rev", "revenue", "500", locator_kind="signed_document"),
    )
    service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: list(facts)}),
        calculation_repository=_CalculationRepo(),
        clock=lambda: NOW,
    )

    result = service.calculate(
        CASE_ID,
        "gross_margin",
        evidence_fact_ids=tuple(fact.id for fact in facts),
    )

    assert result.status is MetricStatus.CALCULATED
    assert result.value == Decimal("0.400000")


def test_service_rejects_duplicate_missing_case_fact_ids_and_persists_only_calculated_results() -> None:
    facts = [_fact("gp", "gross_profit", "200"), _fact("rev", "revenue", "500")]
    calculation_repo = _CalculationRepo()
    service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=calculation_repo,
        clock=lambda: NOW,
    )

    with pytest.raises(ValueError, match=f"evidence_fact_id.duplicate:{facts[0].id}"):
        service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=(facts[0].id, facts[0].id))
    missing_id = uuid4()
    with pytest.raises(ValueError, match=f"evidence_fact_id.not_in_case:{missing_id}"):
        service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=(missing_id,))

    insufficient = service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=(facts[0].id,))
    assert insufficient.status is MetricStatus.INSUFFICIENT_DATA
    assert calculation_repo.saved == []


def test_service_idempotence_excludes_calculated_at_and_does_not_call_clock_on_repeat() -> None:
    facts = [_fact("gp", "gross_profit", "200", sensitivity=SensitivityClass.CONFIDENTIAL), _fact("rev", "revenue", "500")]
    clock_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return NOW

    calculation_repo = _CalculationRepo()
    service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=calculation_repo,
        clock=clock,
    )
    ids = tuple(reversed([fact.id for fact in facts]))

    first = service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=ids)
    second = service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=ids)

    assert first == second
    assert clock_calls == 1
    assert len(calculation_repo.saved) == 1
    saved = calculation_repo.saved[0]
    assert saved.calculated_at == NOW
    assert saved.sensitivity is SensitivityClass.CONFIDENTIAL
    assert saved.input_fact_ids == (_fact_id("gp"), _fact_id("rev"))


def test_service_rejects_non_utc_clock_and_conflicting_existing_deterministic_calculation() -> None:
    facts = [_fact("gp", "gross_profit", "200"), _fact("rev", "revenue", "500")]
    service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=_CalculationRepo(),
        clock=lambda: datetime(2026, 8, 9, 12, 0),
    )
    with pytest.raises(ValueError, match="timestamp must be timezone-aware UTC"):
        service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=tuple(f.id for f in facts))

    repo = _CalculationRepo()
    ok_service = PublicMetricService(
        evidence_repository=_EvidenceRepo({CASE_ID: facts}),
        calculation_repository=repo,
        clock=lambda: NOW,
    )
    ok_service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=tuple(f.id for f in facts))
    repo.saved[0] = repo.saved[0].model_copy(update={"value": Decimal("0.410000")})

    with pytest.raises(ValueError, match="calculation_id_conflict"):
        ok_service.calculate(CASE_ID, "gross_margin", evidence_fact_ids=tuple(f.id for f in facts))


def test_result_contract_is_immutable_forbids_extra_fields_and_non_finite_values() -> None:
    result = MetricEngine().calculate("gross_margin", (_fact("gp", "gross_profit", "200"), _fact("rev", "revenue", "500")))
    with pytest.raises(ValidationError):
        MetricCalculationResult.model_validate({**result.model_dump(), "extra": "field"})
    with pytest.raises(ValidationError):
        MetricCalculationResult.model_validate({**result.model_dump(), "value": Decimal("NaN")})
    with pytest.raises(ValidationError):
        MetricCalculationResult.model_validate({**result.model_dump(), "value": Decimal("Infinity")})
    with pytest.raises(ValidationError):
        MetricCalculationResult.model_validate({**result.model_dump(), "value": 1.0})
    with pytest.raises(ValidationError):
        result.metric_name = "changed"  # type: ignore[misc]


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _parse_as_of(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _fact_from_spec(spec: dict[str, str]) -> EvidenceFact:
    return _fact(
        spec["alias"],
        spec["name"],
        spec["value"],
        unit=spec["unit"],
        period=spec["period"],
        source=spec["source"],
    )


def _fact(
    alias: str,
    name: str,
    value: str,
    *,
    unit: str = "USD",
    period: str = "2025",
    source: str = "official",
    locator_kind: str | None = None,
    sensitivity: SensitivityClass = SensitivityClass.PUBLIC,
) -> EvidenceFact:
    return EvidenceFact(
        id=_fact_id(alias),
        artifact_id=ARTIFACT_ID,
        name=name,
        value=Decimal(value),
        value_type="decimal",
        unit=unit,
        period=period,
        locator=SourceLocator(
            kind=locator_kind or ("market_data" if source == "market" else "sec_fact"),
            value=name,
            artifact_id=ARTIFACT_ID,
        ),
        sensitivity=sensitivity,
        confidence=Decimal("0.95"),
        source_priority={
            "official": SourcePriority.OFFICIAL_OR_SIGNED,
            "market": SourcePriority.SECONDARY_AGGREGATOR,
            "model": SourcePriority.MODEL_INFERENCE,
        }[source],
        extraction_method="fixture",
        supporting_text_hash="c" * 64,
        source_freshness_at=NOW,
        retrieved_at=NOW,
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

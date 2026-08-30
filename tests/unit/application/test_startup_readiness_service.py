from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.application.services.startup_readiness_service import StartupReadinessService
from due_diligence_agent.domain.metrics import MetricCalculationResult, MetricStatus
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.readiness import StartupReadinessDimensionStatus
from due_diligence_agent.domain.startup.scenario import (
    ScenarioInput,
    ScenarioMetric,
    ScenarioRange,
    StartupScenarioVariant,
)


_BUILT_AT = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)


def test_metric_pack_selects_subscription_saas_allowlist_and_ignores_text_order() -> None:
    profile_a = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("B2B subscription SaaS",),
            ),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: _field(
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
                ("monthly recurring subscription",),
            ),
            StartupProfileFieldName.STAGE: _field(StartupProfileFieldName.STAGE, ("growth",)),
            StartupProfileFieldName.METRIC_PACK_CANDIDATES: _field(
                StartupProfileFieldName.METRIC_PACK_CANDIDATES,
                ("arr", "unsupported_founder_metric", "logo_churn"),
            ),
        },
        data_revision=3,
    )
    profile_b = _profile(
        {
            StartupProfileFieldName.METRIC_PACK_CANDIDATES: _field(
                StartupProfileFieldName.METRIC_PACK_CANDIDATES,
                ("unsupported_founder_metric", "logo_churn", "arr"),
            ),
            StartupProfileFieldName.STAGE: _field(StartupProfileFieldName.STAGE, ("growth",)),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: _field(
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
                ("monthly recurring subscription",),
            ),
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("B2B subscription SaaS",),
            ),
        },
        data_revision=3,
    )

    pack_a = StartupReadinessService(clock=lambda: _BUILT_AT).select_metric_pack(profile_a)
    pack_b = StartupReadinessService(clock=lambda: _BUILT_AT).select_metric_pack(profile_b)

    assert pack_a.metric_ids == (
        "arr",
        "burn_multiple",
        "cac",
        "cac_payback_months",
        "gross_margin",
        "logo_churn",
        "ltv",
        "ltv_cac",
        "mrr",
        "net_burn",
        "nrr",
        "period_growth",
        "revenue_churn",
        "runway_months",
    )
    assert pack_a.pack_hash == pack_b.pack_hash
    assert pack_a.dimensions[0].reason_code == "pack.selected:saas"
    assert {dimension.reason_code for dimension in pack_a.dimensions} >= {
        "metric_candidate.ignored"
    }


def test_metric_pack_selects_marketplace_and_pre_revenue_without_arbitrary_metric_text() -> None:
    service = StartupReadinessService(clock=lambda: _BUILT_AT)
    marketplace = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("managed transaction marketplace",),
            ),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: _field(
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
                ("take rate per transaction",),
            ),
            StartupProfileFieldName.METRIC_PACK_CANDIDATES: _field(
                StartupProfileFieldName.METRIC_PACK_CANDIDATES,
                ("gross_margin", "path:/private.csv", "mrr"),
            ),
        }
    )
    pre_revenue = _profile(
        {
            StartupProfileFieldName.STAGE: _field(
                StartupProfileFieldName.STAGE,
                ("idea and pre-revenue pilot stage",),
            ),
        }
    )

    assert service.select_metric_pack(marketplace).metric_ids == (
        "burn_multiple",
        "cac",
        "gross_margin",
        "net_burn",
        "period_growth",
        "runway_months",
    )
    assert service.select_metric_pack(pre_revenue).metric_ids == (
        "cac",
        "gross_margin",
        "net_burn",
        "runway_months",
    )


def test_metric_pack_unknown_model_uses_conservative_default() -> None:
    pack = StartupReadinessService(clock=lambda: _BUILT_AT).select_metric_pack(_profile({}))

    assert pack.metric_ids == ("gross_margin", "net_burn", "period_growth", "runway_months")
    assert pack.dimensions[0].status is StartupReadinessDimensionStatus.PROVISIONAL
    assert pack.dimensions[0].reason_code == "pack.selected:default"


def test_readiness_is_not_made_ready_by_confidence_only() -> None:
    profile = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("SaaS subscription",),
                confidence=Decimal("1"),
            ),
            StartupProfileFieldName.TRACTION: _field(
                StartupProfileFieldName.TRACTION,
                ("strong traction claimed",),
                confidence=Decimal("1"),
            ),
        }
    )

    snapshot = StartupReadinessService(clock=lambda: _BUILT_AT).evaluate(profile, (), calculation_ids=())

    statuses = {dimension.metric_id: dimension.status for dimension in snapshot.metric_pack.dimensions}
    assert statuses["mrr"] is StartupReadinessDimensionStatus.BLOCKED
    assert statuses["net_burn"] is StartupReadinessDimensionStatus.BLOCKED
    assert all(metric.value is None for metric in _insufficient_metrics(snapshot.metric_pack.metric_ids))


def test_readiness_includes_six_explicit_business_dimensions_with_method_codes() -> None:
    profile = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("SaaS subscription",),
            ),
            StartupProfileFieldName.TRACTION: _field(
                StartupProfileFieldName.TRACTION,
                ("20 active pilots",),
            ),
            StartupProfileFieldName.CHANNELS_GTM: _field(
                StartupProfileFieldName.CHANNELS_GTM,
                ("Founder-led outbound",),
            ),
            StartupProfileFieldName.ASSUMPTIONS: _field(
                StartupProfileFieldName.ASSUMPTIONS,
                ("Gross margin depends on usage costs",),
            ),
        }
    )

    snapshot = StartupReadinessService(clock=lambda: _BUILT_AT).evaluate(profile, (), calculation_ids=())
    by_dimension = {dimension.metric_id: dimension for dimension in snapshot.metric_pack.dimensions}

    assert {
        "business_model",
        "traction",
        "unit_economics",
        "market_evidence",
        "gtm_evidence",
        "risk_disclosure",
    }.issubset(by_dimension)
    assert by_dimension["business_model"].reason_code == "method.profile_field:business_model"
    assert by_dimension["traction"].reason_code == "method.profile_field:traction"
    assert by_dimension["unit_economics"].reason_code == "method.metric_diagnostics:unit_economics"
    assert by_dimension["market_evidence"].reason_code == "method.profile_field:market_evidence"
    assert by_dimension["gtm_evidence"].reason_code == "method.profile_field:gtm_evidence"
    assert by_dimension["risk_disclosure"].reason_code == "method.profile_field:risk_disclosure"


def test_readiness_blocks_contradictions_even_when_metrics_calculated() -> None:
    calculation_id = _uuid("calc:mrr")
    profile = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("SaaS", "marketplace"),
                status=StartupProfileFieldStatus.CONTRADICTION,
                reason_code="competing_models",
            ),
        },
        contradiction_ids=(_uuid("contradiction:business-model"),),
    )
    diagnostic = _calculated_metric("mrr", calculation_id=calculation_id)

    snapshot = StartupReadinessService(clock=lambda: _BUILT_AT).evaluate(
        profile,
        (diagnostic,),
        calculation_ids=(calculation_id,),
    )

    assert snapshot.calculation_ids == (calculation_id,)
    assert any(
        dimension.metric_id == "mrr"
        and dimension.status is StartupReadinessDimensionStatus.BLOCKED
        and dimension.reason_code == "profile.contradiction:business_model"
        for dimension in snapshot.metric_pack.dimensions
    )


def test_readiness_preserves_calculation_lineage_and_missing_inputs_do_not_create_values() -> None:
    calculation_id = _uuid("calc:arr")
    service = StartupReadinessService(clock=lambda: _BUILT_AT)
    profile = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("SaaS subscription",),
            ),
            StartupProfileFieldName.STAGE: _field(StartupProfileFieldName.STAGE, ("growth",)),
        }
    )

    snapshot = service.evaluate(
        profile,
        (
            _calculated_metric("arr", calculation_id=calculation_id),
            _insufficient_metric("ltv", warning="input.missing:monthly_arpa"),
        ),
        calculation_ids=(calculation_id,),
    )

    assert snapshot.calculation_ids == (calculation_id,)
    arr_dimension = next(dimension for dimension in snapshot.metric_pack.dimensions if dimension.metric_id == "arr")
    ltv_dimension = next(dimension for dimension in snapshot.metric_pack.dimensions if dimension.metric_id == "ltv")
    assert arr_dimension.status is StartupReadinessDimensionStatus.READY
    assert arr_dimension.reason_code == "metric.calculated:arr@1"
    assert ltv_dimension.status is StartupReadinessDimensionStatus.BLOCKED
    assert ltv_dimension.reason_code == "input.missing:monthly_arpa"


def test_readiness_accepts_real_workflow_metric_diagnostic_shape_without_formula_version() -> None:
    calculation_id = _uuid("calc:workflow-gross-margin")
    profile = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("marketplace transaction model",),
            ),
        }
    )

    snapshot = StartupReadinessService(clock=lambda: _BUILT_AT).evaluate(
        profile,
        (
            {
                "metric_name": "gross_margin",
                "status": "calculated",
                "warnings": [],
                "input_evidence_ids": [str(_uuid("input:workflow-gross-margin"))],
                "calculation_id": str(calculation_id),
            },
        ),
        calculation_ids=(calculation_id,),
    )

    gross_margin = next(dimension for dimension in snapshot.metric_pack.dimensions if dimension.metric_id == "gross_margin")
    assert gross_margin.status is StartupReadinessDimensionStatus.READY
    assert gross_margin.reason_code == "metric.calculated:gross_margin@workflow"


def test_invalid_metric_candidates_do_not_leak_private_content_to_dimensions_or_questions() -> None:
    private_candidate = r"C:\Users\Akana\OneDrive\secret-founder-model.xlsx https://drive.google.com/private.csv"
    profile = _profile(
        {
            StartupProfileFieldName.METRIC_PACK_CANDIDATES: _field(
                StartupProfileFieldName.METRIC_PACK_CANDIDATES,
                (private_candidate,),
            ),
        }
    )
    service = StartupReadinessService(clock=lambda: _BUILT_AT)

    pack = service.select_metric_pack(profile)
    snapshot = service.evaluate(profile, (), calculation_ids=())
    questions = service.priority_questions(snapshot)

    serialized = " ".join(
        str(item)
        for item in (
            *(dimension.reason_code for dimension in pack.dimensions),
            *(dimension.notes for dimension in pack.dimensions),
            *(question.question_code for question in questions),
            *(question.text for question in questions),
        )
    ).casefold()
    for sentinel in ("akana", "onedrive", "secret-founder-model", "drive.google", "private.csv", "https", "users"):
        assert sentinel not in serialized
    assert "metric_candidate.ignored" in serialized


def test_priority_questions_are_bounded_deduplicated_stable_and_safe() -> None:
    service = StartupReadinessService(clock=lambda: _BUILT_AT)
    profile = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("SaaS subscription",),
            ),
        },
        gap_codes=(
            "input.missing:monthly_recurring_revenue",
            "input.missing:monthly_recurring_revenue",
            "input.missing:cash",
            "input.missing:monthly_net_burn",
            "input.missing:gross_margin_rate",
        ),
    )
    snapshot = service.evaluate(
        profile,
        (
            _insufficient_metric("mrr", warning="input.missing:monthly_recurring_revenue"),
            _insufficient_metric("runway_months", warning="input.missing:cash"),
            _insufficient_metric("gross_margin", warning="input.missing:revenue"),
            _insufficient_metric("ltv", warning="input.missing:gross_margin_rate"),
        ),
        calculation_ids=(),
    )

    questions = service.priority_questions(snapshot)

    assert tuple(question.question_code for question in questions) == (
        "input.missing:monthly_recurring_revenue",
        "input.missing:cash",
        "input.missing:revenue",
    )
    assert len(questions) == 3
    assert all("file:" not in question.text and "\\" not in question.text and "/" not in question.text for question in questions)
    assert snapshot.metric_pack.model_copy(update={"adaptive_questions": questions}).adaptive_questions == questions


def test_priority_questions_use_semantic_tie_break_across_case_ids_and_restarts() -> None:
    service = StartupReadinessService(clock=lambda: _BUILT_AT)
    diagnostics = (
        _insufficient_metric("mrr", warning="input.missing:monthly_recurring_revenue"),
        _insufficient_metric("arr", warning="input.missing:monthly_recurring_revenue"),
        _insufficient_metric("runway_months", warning="input.missing:cash"),
        _insufficient_metric("gross_margin", warning="input.missing:revenue"),
    )
    question_sets: list[tuple[tuple[str, str, int], ...]] = []
    for index in range(16):
        profile = _profile(
            {
                StartupProfileFieldName.BUSINESS_MODEL: _field(
                    StartupProfileFieldName.BUSINESS_MODEL,
                    ("SaaS subscription",),
                ),
            },
            case_seed=f"case:readiness-tie-break:{index}",
        )
        ordered_diagnostics = diagnostics if index % 2 == 0 else tuple(reversed(diagnostics))
        snapshot = service.evaluate(profile, ordered_diagnostics, calculation_ids=())
        questions = service.priority_questions(snapshot)
        question_sets.append(
            tuple((question.question_code, question.text, question.weight) for question in questions)
        )

    assert len(set(question_sets)) == 1
    assert question_sets[0] == (
        (
            "input.missing:monthly_recurring_revenue",
            "Provide monthly recurring revenue so the arr metric and readiness dimension can be assessed.",
            10,
        ),
        (
            "input.missing:cash",
            "Provide current cash balance so the runway_months metric and readiness dimension can be assessed.",
            20,
        ),
        (
            "input.missing:revenue",
            "Provide revenue for the target period so the gross_margin metric and readiness dimension can be assessed.",
            30,
        ),
    )


def test_priority_questions_include_contradiction_resolution_before_metric_gaps() -> None:
    service = StartupReadinessService(clock=lambda: _BUILT_AT)
    profile = _profile(
        {
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("SaaS", "marketplace"),
                status=StartupProfileFieldStatus.CONTRADICTION,
                reason_code="competing_models",
            ),
        },
        contradiction_ids=(_uuid("contradiction:model"),),
    )

    snapshot = service.evaluate(
        profile,
        (
            _insufficient_metric("mrr", warning="input.missing:monthly_recurring_revenue"),
            _insufficient_metric("runway_months", warning="input.missing:cash"),
        ),
        calculation_ids=(),
    )

    questions = service.priority_questions(snapshot)

    assert questions[0].question_code == "profile.contradiction:business_model"
    assert "business model" in questions[0].text.casefold()
    assert len({question.question_id for question in questions}) == len(questions)


def test_scenario_completeness_is_separate_from_evidence_based_readiness_for_idea_cases() -> None:
    service = StartupReadinessService(clock=lambda: _BUILT_AT)
    idea_profile = _profile({})
    snapshot = service.evaluate(idea_profile, (), calculation_ids=())
    scenario = _scenario_variant_with_one_executable_formula(idea_profile.case_id, idea_profile.data_revision)

    completeness = service.scenario_completeness(scenario)

    blocked = {
        dimension.metric_id
        for dimension in snapshot.metric_pack.dimensions
        if dimension.status is StartupReadinessDimensionStatus.BLOCKED
    }
    assert {"traction", "market_evidence", "gtm_evidence"}.issubset(blocked)
    assert completeness.percent == 50
    assert completeness.executable_formula_keys == ("mrr",)
    assert completeness.missing_input_keys == ("churn",)


def _profile(
    overrides: dict[StartupProfileFieldName, StartupProfileField],
    *,
    data_revision: int = 1,
    gap_codes: tuple[str, ...] = (),
    contradiction_ids: tuple[UUID, ...] = (),
    case_seed: str = "case:startup-readiness",
) -> StartupProfile:
    fields = {
        name: overrides.get(
            name,
            StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal("0"),
            ),
        )
        for name in StartupProfileFieldName
    }
    fields_by_key = {name.value: field for name, field in fields.items()}
    return StartupProfile.build(
        case_id=_uuid(case_seed),
        schema_version="startup_profile@1",
        profile_version="primary@1",
        extractor_version="test@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes={"upload": "sha256:" + ("a" * 64)},
        parse_outcomes={"upload": "parsed"},
        fields=fields_by_key,
        gap_codes=gap_codes,
        contradiction_ids=contradiction_ids,
        case_revision_at=_BUILT_AT,
    )


def _field(
    name: StartupProfileFieldName,
    values: tuple[str, ...],
    *,
    status: StartupProfileFieldStatus = StartupProfileFieldStatus.SOURCE_FACT,
    confidence: Decimal = Decimal("0.82"),
    reason_code: str | None = None,
) -> StartupProfileField:
    refs = (
        _evidence_ref(name, "a"),
        _evidence_ref(name, "b"),
    )
    return StartupProfileField(
        name=name,
        status=status,
        values=values,
        confidence=confidence,
        evidence_refs=refs if status in {StartupProfileFieldStatus.SOURCE_FACT, StartupProfileFieldStatus.CONTRADICTION} else (),
        reason_code=reason_code,
    )


def _evidence_ref(name: StartupProfileFieldName, suffix: str) -> StartupProfileEvidenceRef:
    return StartupProfileEvidenceRef(
        evidence_id=_uuid(f"evidence:{name.value}:{suffix}"),
        fragment_id=_uuid(f"fragment:{name.value}:{suffix}"),
        artifact_id=_uuid(f"artifact:{name.value}:{suffix}"),
        artifact_hash="sha256:" + ("b" * 64),
        locator_hash="sha256:" + ("c" * 64),
        field_name=name,
        confidence=Decimal("0.8"),
    )


def _calculated_metric(metric_name: str, *, calculation_id: UUID) -> MetricCalculationResult:
    return MetricCalculationResult(
        status=MetricStatus.CALCULATED,
        metric_name=metric_name,
        formula_version=f"{metric_name}@1",
        value=Decimal("12.340000"),
        display_value="12.34",
        unit="currency",
        period="2026",
        input_evidence_ids=(_uuid(f"input:{metric_name}"),),
        calculation_id=calculation_id,
    )


def _insufficient_metric(metric_name: str, *, warning: str) -> MetricCalculationResult:
    return MetricCalculationResult(
        status=MetricStatus.INSUFFICIENT_DATA,
        metric_name=metric_name,
        formula_version=f"{metric_name}@1",
        value=None,
        display_value=None,
        unit="currency",
        period="",
        input_evidence_ids=(),
        warnings=(warning,),
    )


def _insufficient_metrics(metric_ids: tuple[str, ...]) -> tuple[MetricCalculationResult, ...]:
    return tuple(_insufficient_metric(metric_id, warning="input.missing:test") for metric_id in metric_ids)


def _uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)


def _scenario_variant_with_one_executable_formula(
    case_id: UUID,
    data_revision: int,
) -> StartupScenarioVariant:
    price = ScenarioInput(
        case_id=case_id,
        data_revision=data_revision,
        input_key="monthly_price",
        value_range=ScenarioRange(lower=Decimal("35000"), upper=Decimal("40000")),
        unit="KZT/month",
        provenance=CaseValueKind.FOUNDER_STATEMENT,
        source_refs=(_uuid("statement:price"),),
        confidence="medium",
        rationale="Founder supplied pricing",
        validation_plan="Confirm paid invoices",
        acceptance="accepted",
    )
    customers = ScenarioInput(
        case_id=case_id,
        data_revision=data_revision,
        input_key="paying_customers",
        value_range=ScenarioRange(lower=Decimal("40"), upper=Decimal("50")),
        unit="count/month",
        provenance=CaseValueKind.AI_SCENARIO,
        source_refs=(),
        confidence="low",
        rationale="Planning assumption",
        validation_plan="Validate paid pilots",
        acceptance="proposed",
    )
    mrr = ScenarioMetric(
        case_id=case_id,
        data_revision=data_revision,
        metric_key="mrr",
        value_range=ScenarioRange(lower=Decimal("1400000"), upper=Decimal("2000000")),
        unit="KZT/month",
        provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
        dependency_refs=(price.input_id, customers.input_id),
        formula_key="mrr",
        formula_description="Monthly price multiplied by paying customers",
        confidence="medium",
        rationale="Scenario calculation",
        validation_plan="Confirm paid customers and price",
        acceptance="proposed",
    )
    ltv_gap = ScenarioMetric(
        case_id=case_id,
        data_revision=data_revision,
        metric_key="ltv",
        value_range=None,
        unit="KZT/customer",
        provenance=CaseValueKind.DETERMINISTIC_CALCULATION,
        dependency_refs=(price.input_id,),
        formula_key="ltv",
        formula_description="ARPA multiplied by gross margin divided by churn",
        confidence="low",
        rationale="Churn is not available for an idea-stage case",
        validation_plan="Collect cohort churn",
        acceptance="proposed",
        gaps=("input.missing:churn",),
    )
    return StartupScenarioVariant(
        scenario_key="base",
        inputs={"monthly_price": price, "paying_customers": customers},
        metrics={"mrr": mrr, "ltv": ltv_gap},
        gaps={"churn": "Observed cohort churn is required"},
    )

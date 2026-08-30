from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from due_diligence_agent.application.services.startup_market_research_service import (
    StartupMarketResearchService,
    StartupMarketSizingInputs,
)
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchSentiment,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
    StartupSentimentSignal,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)


_BUILT_AT = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)
_AS_OF = date(2026, 8, 1)


def test_research_plan_uses_only_allowlisted_profile_fields_and_is_stable() -> None:
    profile_a = _profile(
        {
            StartupProfileFieldName.SOLUTION: _field(StartupProfileFieldName.SOLUTION, ("AI due diligence copilot",)),
            StartupProfileFieldName.ICP: _field(StartupProfileFieldName.ICP, ("seed-stage founders",)),
            StartupProfileFieldName.USERS: _field(StartupProfileFieldName.USERS, ("startup operators",)),
            StartupProfileFieldName.BUYERS: _field(StartupProfileFieldName.BUYERS, ("accelerators",)),
            StartupProfileFieldName.GEOGRAPHY: _field(StartupProfileFieldName.GEOGRAPHY, ("United States",)),
            StartupProfileFieldName.BUSINESS_MODEL: _field(StartupProfileFieldName.BUSINESS_MODEL, ("B2B SaaS",)),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: _field(
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
                ("subscription",),
            ),
            StartupProfileFieldName.COMPETITORS_MENTIONED: _field(
                StartupProfileFieldName.COMPETITORS_MENTIONED,
                ("Visible Alpha", "AlphaSense"),
            ),
            StartupProfileFieldName.ASSUMPTIONS: _field(
                StartupProfileFieldName.ASSUMPTIONS,
                ("private file C:/Users/Akana/secret.xlsx",),
            ),
        }
    )
    profile_b = _profile(
        {
            StartupProfileFieldName.COMPETITORS_MENTIONED: _field(
                StartupProfileFieldName.COMPETITORS_MENTIONED,
                ("AlphaSense", "Visible Alpha"),
            ),
            StartupProfileFieldName.PRICING_REVENUE_MODEL: _field(
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
                ("subscription",),
            ),
            StartupProfileFieldName.BUSINESS_MODEL: _field(StartupProfileFieldName.BUSINESS_MODEL, ("B2B SaaS",)),
            StartupProfileFieldName.GEOGRAPHY: _field(StartupProfileFieldName.GEOGRAPHY, ("United States",)),
            StartupProfileFieldName.BUYERS: _field(StartupProfileFieldName.BUYERS, ("accelerators",)),
            StartupProfileFieldName.USERS: _field(StartupProfileFieldName.USERS, ("startup operators",)),
            StartupProfileFieldName.ICP: _field(StartupProfileFieldName.ICP, ("seed-stage founders",)),
            StartupProfileFieldName.SOLUTION: _field(StartupProfileFieldName.SOLUTION, ("AI due diligence copilot",)),
            StartupProfileFieldName.PROBLEM: _field(StartupProfileFieldName.PROBLEM, ("ignored problem text",)),
        }
    )

    result_a = StartupMarketResearchService(clock=lambda: _BUILT_AT).build_research_plan(profile_a)
    result_b = StartupMarketResearchService(clock=lambda: _BUILT_AT).build_research_plan(profile_b)

    assert result_a.plan == result_b.plan
    assert result_a.plan.case_id == profile_a.case_id
    assert 1 <= len(result_a.plan.queries) <= result_a.plan.max_queries
    assert result_a.plan.queries == tuple(sorted(result_a.plan.queries))
    assert all(len(query) <= 120 for query in result_a.plan.queries)
    assert all("secret" not in query.casefold() and "c:/users" not in query.casefold() for query in result_a.plan.queries)
    assert any("AI due diligence copilot" in query for query in result_a.plan.queries)
    assert any("AlphaSense competitors" in query for query in result_a.plan.queries)


def test_research_plan_marks_missing_contradictory_and_private_values_without_inventing_queries() -> None:
    profile = _profile(
        {
            StartupProfileFieldName.SOLUTION: _field(
                StartupProfileFieldName.SOLUTION,
                ("file:///private/idea.md",),
                status=StartupProfileFieldStatus.INFERENCE,
                reason_code="unsafe_source",
                dependency_refs=(_uuid("dep:solution"),),
            ),
            StartupProfileFieldName.BUSINESS_MODEL: _field(
                StartupProfileFieldName.BUSINESS_MODEL,
                ("SaaS", "marketplace"),
                status=StartupProfileFieldStatus.CONTRADICTION,
                reason_code="competing_models",
            ),
        }
    )

    result = StartupMarketResearchService(clock=lambda: _BUILT_AT).build_research_plan(profile)

    assert result.plan.queries == ()
    assert result.gap_codes == (
        "research_plan.private_value:solution",
        "research_plan.missing:icp",
        "research_plan.missing:geography",
        "research_plan.contradiction:business_model",
    )
    assert result.omitted_values == ("private_value:solution",)


def test_research_plan_omitted_values_are_safe_metadata_not_raw_private_values() -> None:
    private_path = "C:/Users/Akana/private/product-plan.md"
    raw_token = "api_key=sk-test-secret-token"
    profile = _profile(
        {
            StartupProfileFieldName.SOLUTION: _field(
                StartupProfileFieldName.SOLUTION,
                (private_path, raw_token),
                status=StartupProfileFieldStatus.INFERENCE,
                reason_code="unsafe_source",
                dependency_refs=(_uuid("dep:private-solution"),),
            ),
        }
    )

    result = StartupMarketResearchService(clock=lambda: _BUILT_AT).build_research_plan(profile)
    dumped = repr(result)

    assert result.omitted_values == ("private_value:solution",)
    assert private_path not in dumped
    assert raw_token not in dumped
    assert "Akana" not in dumped
    assert "sk-test-secret-token" not in dumped


def test_live_research_plan_omits_financing_milestone_profile_noise() -> None:
    profile = _profile(
        {
            StartupProfileFieldName.SOLUTION: _field(
                StartupProfileFieldName.SOLUTION,
                ("Платформу стоит финансировать как staged commercial validation на 35,2 млн ₸",),
            ),
            StartupProfileFieldName.GEOGRAPHY: _field(
                StartupProfileFieldName.GEOGRAPHY,
                ("Казахстан; жильё - Алматы",),
            ),
        }
    )

    result = StartupMarketResearchService(clock=lambda: _BUILT_AT).build_research_plan(
        profile,
        source_mode=StartupResearchSourceMode.LIVE,
        public_focus="public_pricing_analogs",
        public_topic="public pricing analogs",
    )

    serialized = " ".join(result.plan.queries).casefold()
    assert "break-even" not in serialized
    assert "финансировать" not in serialized
    assert "commercial validation" not in serialized
    assert "35,2 млн" not in serialized
    assert result.gap_codes == ("live_research.missing:solution", "live_research.missing:icp")


def test_live_research_plan_for_smart_university_keeps_education_context_and_drops_finance_noise() -> None:
    profile = _profile(
        {
            StartupProfileFieldName.SOLUTION: _field(
                StartupProfileFieldName.SOLUTION,
                (
                    "Платформа поступления, независимый рейтинг подготовки и студенческого жилья",
                    "платформы break-even",
                ),
            ),
            StartupProfileFieldName.ICP: _field(
                StartupProfileFieldName.ICP,
                ("Абитуриенты, родители и университеты",),
            ),
            StartupProfileFieldName.GEOGRAPHY: _field(
                StartupProfileFieldName.GEOGRAPHY,
                ("Казахстан; жильё — Алматы",),
            ),
            StartupProfileFieldName.ASSUMPTIONS: _field(
                StartupProfileFieldName.ASSUMPTIONS,
                ("Раунд 35,2 млн ₸",),
            ),
        }
    )

    result = StartupMarketResearchService(clock=lambda: _BUILT_AT).build_research_plan(
        profile,
        source_mode=StartupResearchSourceMode.LIVE,
        public_focus="public_market_research",
        public_topic="рынок образовательных платформ",
    )

    serialized = " ".join(result.plan.queries).casefold()
    assert result.plan.source_mode is StartupResearchSourceMode.LIVE
    assert result.plan.queries
    assert "поступления" in serialized
    assert "рейтинг" in serialized
    assert "университет" in serialized
    assert "казахстан" in serialized
    assert "жильё — алматы" not in serialized
    assert "жилье - алматы" not in serialized
    assert "break-even" not in serialized
    assert "35,2" not in serialized
    assert "формат для обсуждения" not in serialized
    assert "live_research.missing:solution" not in result.gap_codes
    assert "live_research.missing:icp" not in result.gap_codes


def test_market_sizing_top_down_preserves_assumption_lineage_and_hierarchy() -> None:
    source_id = _uuid("source:market-report")
    result = StartupMarketResearchService(clock=lambda: _BUILT_AT).calculate_market_sizing(
        StartupMarketSizingInputs(
            source_ids=(source_id,),
            as_of=_AS_OF,
            currency="USD",
            unit="annual_revenue",
            tam_amount=Decimal("100000000"),
            sam_share=Decimal("0.25"),
            som_share=Decimal("0.10"),
        )
    )
    sizing = result.sizing

    assert sizing.tam.value == Decimal("100000000.000000")
    assert sizing.sam.value == Decimal("25000000.000000")
    assert sizing.som.value == Decimal("2500000.000000")
    assert sizing.tam.source_refs == (source_id,)
    assert sizing.sam.assumption_refs
    assert sizing.som.assumption_refs
    assert {assumption.assumption_id for assumption in result.assumptions} == set(
        sizing.sam.assumption_refs + sizing.som.assumption_refs
    )
    assert sizing.tam.formula_version == "market_sizing.top_down@1"


def test_market_sizing_result_builds_valid_snapshot_without_reconstructing_assumptions() -> None:
    source = _source("source:market-report")
    result = StartupMarketResearchService(clock=lambda: _BUILT_AT).calculate_market_sizing(
        StartupMarketSizingInputs(
            source_ids=(source.source_id,),
            as_of=_AS_OF,
            currency="USD",
            unit="annual_revenue",
            tam_amount=Decimal("100000000"),
            sam_share=Decimal("0.25"),
            som_share=Decimal("0.10"),
        )
    )

    snapshot = StartupMarketResearchSnapshot.build(
        case_id=_uuid("case:market-service"),
        as_of=_BUILT_AT,
        source_mode=StartupResearchSourceMode.FROZEN,
        research_id=_uuid("research:market-service"),
        competitors=(),
        sources=(source,),
        sentiment_signals=(),
        assumptions=result.assumptions,
        sizing=result.sizing,
        labels=("unit",),
        data_revision=1,
    )

    assert snapshot.sizing == result.sizing
    assert snapshot.assumptions == result.assumptions


def test_market_sizing_bottom_up_requires_explicit_numeric_inputs() -> None:
    source_id = _uuid("source:customer-model")
    service = StartupMarketResearchService(clock=lambda: _BUILT_AT)

    result = service.calculate_market_sizing(
        StartupMarketSizingInputs(
            source_ids=(source_id,),
            as_of=_AS_OF,
            currency="USD",
            unit="annual_revenue",
            total_accounts=Decimal("10000"),
            addressable_share=Decimal("0.50"),
            obtainable_share=Decimal("0.10"),
            annual_revenue_per_account=Decimal("1200"),
        )
    )
    insufficient_result = service.calculate_market_sizing(
        StartupMarketSizingInputs(
            source_ids=(source_id,),
            as_of=_AS_OF,
            currency="USD",
            unit="annual_revenue",
            total_accounts=Decimal("10000"),
            addressable_share=Decimal("0.50"),
            annual_revenue_per_account=Decimal("1200"),
        )
    )
    sizing = result.sizing
    insufficient = insufficient_result.sizing

    assert sizing.tam.value == Decimal("12000000.000000")
    assert sizing.sam.value == Decimal("6000000.000000")
    assert sizing.som.value == Decimal("600000.000000")
    assert {assumption.assumption_id for assumption in result.assumptions} == set(
        sizing.tam.assumption_refs + sizing.sam.assumption_refs + sizing.som.assumption_refs
    )
    assert insufficient.som.value is None
    assert insufficient.som.level is StartupResearchSourceStatus.INSUFFICIENT_DATA


def test_market_sizing_rejects_mismatch_invalid_hierarchy_and_narrative_values() -> None:
    source_id = _uuid("source:bad-market")
    service = StartupMarketResearchService(clock=lambda: _BUILT_AT)

    with pytest.raises(ValueError, match="share must be between"):
        service.calculate_market_sizing(
            StartupMarketSizingInputs(
                source_ids=(source_id,),
                as_of=_AS_OF,
                tam_amount=Decimal("100"),
                sam_share=Decimal("1.20"),
                som_share=Decimal("0.10"),
            )
        )

    with pytest.raises(ValueError, match="currency mismatch"):
        service.calculate_market_sizing(
            StartupMarketSizingInputs(
                source_ids=(source_id,),
                as_of=_AS_OF,
                currency="USD",
                unit="annual_revenue",
                tam_amount=Decimal("100"),
                sam_share=Decimal("0.10"),
                som_share=Decimal("0.10"),
                sam_currency="EUR",
            )
        )

    with pytest.raises(ValueError, match="narrative"):
        service.calculate_market_sizing(
            StartupMarketSizingInputs(
                source_ids=(source_id,),
                as_of=_AS_OF,
                narrative_market_size="huge market",
            )
        )


def test_sentiment_aggregation_is_dated_bounded_secondary_only_and_flags_stale() -> None:
    source = _source("source:news")
    stale_source = _source("source:old-news", as_of=date(2025, 1, 1), stale=True)
    service = StartupMarketResearchService(clock=lambda: _BUILT_AT)

    aggregate = service.aggregate_sentiment(
        (
            _signal("sig:pos", StartupResearchSentiment.POSITIVE, source.source_id, _BUILT_AT - timedelta(days=2)),
            _signal("sig:neg", StartupResearchSentiment.NEGATIVE, source.source_id, _BUILT_AT - timedelta(days=1)),
            _signal("sig:old", StartupResearchSentiment.NEUTRAL, stale_source.source_id, _BUILT_AT - timedelta(days=250)),
        ),
        sources=(source, stale_source),
        max_age_days=90,
    )

    assert aggregate.counts == {"negative": 1, "neutral": 1, "positive": 1}
    assert aggregate.source_ids == tuple(sorted((source.source_id, stale_source.source_id)))
    assert aggregate.stale is True
    assert aggregate.supports_primary_financial_metrics is False
    assert aggregate.window_start == (_BUILT_AT - timedelta(days=250))
    assert aggregate.window_end == (_BUILT_AT - timedelta(days=1))


def test_sentiment_rejects_unknown_sources_and_primary_financial_support() -> None:
    source = _source("source:news")
    service = StartupMarketResearchService(clock=lambda: _BUILT_AT)

    with pytest.raises(ValueError, match="source"):
        service.aggregate_sentiment(
            (_signal("sig:missing", StartupResearchSentiment.NEUTRAL, _uuid("source:missing"), _BUILT_AT),),
            sources=(source,),
        )

    with pytest.raises(ValueError, match="primary financial"):
        StartupSentimentSignal(
            signal_id=_uuid("sig:bad"),
            sentiment=StartupResearchSentiment.POSITIVE,
            subject="market",
            as_of=_BUILT_AT,
            source_id=source.source_id,
            source_mode=StartupResearchSourceMode.FROZEN,
            supports_primary_financial_metrics=True,
        )


def _profile(overrides: dict[StartupProfileFieldName, StartupProfileField]) -> StartupProfile:
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
    return StartupProfile.build(
        case_id=_uuid("case:market-service"),
        schema_version="startup_profile@1",
        profile_version="primary@1",
        extractor_version="test@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=1,
        source_hashes={"upload": "sha256:" + ("a" * 64)},
        parse_outcomes={"upload": "parsed"},
        fields={name.value: field for name, field in fields.items()},
        case_revision_at=_BUILT_AT,
    )


def _field(
    name: StartupProfileFieldName,
    values: tuple[str, ...],
    *,
    status: StartupProfileFieldStatus = StartupProfileFieldStatus.SOURCE_FACT,
    reason_code: str | None = None,
    dependency_refs: tuple[UUID, ...] = (),
) -> StartupProfileField:
    return StartupProfileField(
        name=name,
        status=status,
        values=values,
        confidence=Decimal("0.82"),
        evidence_refs=(
            _evidence_ref(name, "a"),
            _evidence_ref(name, "b"),
        )
        if status in {StartupProfileFieldStatus.SOURCE_FACT, StartupProfileFieldStatus.CONTRADICTION}
        else (),
        dependency_refs=dependency_refs,
        reason_code=reason_code,
    )


def _evidence_ref(name: StartupProfileFieldName, suffix: str) -> StartupProfileEvidenceRef:
    return StartupProfileEvidenceRef(
        evidence_id=_uuid(f"evidence:{name.value}:{suffix}"),
        artifact_id=_uuid(f"artifact:{name.value}:{suffix}"),
        artifact_hash="sha256:" + ("b" * 64),
        locator_hash="sha256:" + ("c" * 64),
        field_name=name,
        confidence=Decimal("0.8"),
    )


def _source(seed: str, *, as_of: date = _AS_OF, stale: bool = False) -> StartupResearchSource:
    return StartupResearchSource.model_validate(
        {
            "source_id": _uuid(seed),
            "source_mode": StartupResearchSourceMode.FROZEN,
            "source_hash": "sha256:" + ("d" * 64),
            "source_url": "https://example.com/news",
            "source_label": "Example News",
            "as_of": as_of,
            "retrieved_at": _BUILT_AT,
            "query": "market signal",
            "provenance": "fixture",
            "stale": stale,
        }
    )


def _signal(
    seed: str,
    sentiment: StartupResearchSentiment,
    source_id: UUID,
    as_of: datetime,
) -> StartupSentimentSignal:
    return StartupSentimentSignal(
        signal_id=_uuid(seed),
        sentiment=sentiment,
        subject="market",
        as_of=as_of,
        source_id=source_id,
        source_mode=StartupResearchSourceMode.FROZEN,
        supports_event_narrative_claims=True,
    )


def _uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)

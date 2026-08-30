from __future__ import annotations

from datetime import UTC, datetime, date
from decimal import Decimal
from inspect import signature
from uuid import UUID, uuid4

from pydantic import HttpUrl, ValidationError
import pytest

from due_diligence_agent.domain.startup.market import (
    MarketSizingAssumption,
    MarketSizingEstimate,
    StartupCompetitor,
    StartupCompetitorCategory,
    StartupMarketResearchSnapshot,
    StartupMarketSizing,
    StartupPublicBenchmarkCandidate,
    StartupResearchPlan,
    StartupResearchSchema,
    StartupResearchSentiment,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
    StartupSentimentSignal,
)
from due_diligence_agent.ports.startup_research import StartupResearchPort


def test_startup_market_research_schema_version_is_expected_constant() -> None:
    assert StartupResearchSchema.VERSION == "startup_market_research@1"


def test_competitor_category_contains_all_five_types() -> None:
    expected = {
        "direct",
        "indirect",
        "substitute",
        "do_nothing",
        "potential_entrant",
    }
    assert {item.value for item in StartupCompetitorCategory} == expected


def test_research_source_rejects_sensitive_url_and_validates_hash_url() -> None:
    source_id = uuid4()
    with pytest.raises(ValidationError, match="credentials"):
        StartupResearchSource(
            source_id=source_id,
            source_mode=StartupResearchSourceMode.FROZEN,
            source_hash="sha256:" + ("a" * 64),
            source_url=HttpUrl("https://user:pass@example.com/source"),
            source_label="market data",
            as_of=date(2026, 8, 10),
            retrieved_at=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
            query="seed startup market",
            provenance="manifest:public-v1",
        )
    with pytest.raises(ValidationError, match="fragment"):
        StartupResearchSource(
            source_id=source_id,
            source_mode=StartupResearchSourceMode.FROZEN,
            source_hash="sha256:" + ("a" * 64),
            source_url=HttpUrl("https://example.com/source#bad"),
            source_label="market data",
            as_of=date(2026, 8, 10),
            retrieved_at=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
            query="seed startup market",
            provenance="manifest:public-v1",
        )
    with pytest.raises(ValidationError, match="sensitive"):
        StartupResearchSource(
            source_id=source_id,
            source_mode=StartupResearchSourceMode.FROZEN,
            source_hash="sha256:" + ("a" * 64),
            source_url=HttpUrl("https://example.com/source?token=bad"),
            source_label="market data",
            as_of=date(2026, 8, 10),
            retrieved_at=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
            query="seed startup market",
            provenance="manifest:public-v1",
        )


def test_research_plan_binds_query_boundaries() -> None:
    with pytest.raises(ValidationError, match="too many queries"):
        StartupResearchPlan(
            case_id=uuid4(),
            source_mode=StartupResearchSourceMode.FROZEN,
            queries=tuple(f"q{i}" for i in range(9)),
        )

    with pytest.raises(ValidationError, match="query"):
        StartupResearchPlan(
            case_id=uuid4(),
            source_mode=StartupResearchSourceMode.LIVE,
            queries=("   ",),
        )


def test_snapshot_hash_and_id_are_recomputed_on_model_validation() -> None:
    snapshot = _base_snapshot()
    tampered = snapshot.model_dump(mode="python")
    tampered["snapshot_hash"] = "sha256:" + ("1" * 64)
    with pytest.raises(ValidationError, match="recomputed from payload"):
        StartupMarketResearchSnapshot.model_validate(tampered)

    tampered = snapshot.model_dump(mode="python")
    tampered["snapshot_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="derived from case id"):
        StartupMarketResearchSnapshot.model_validate(tampered)


def test_snapshot_graph_validates_all_refs_between_competitors_sources_assumptions_and_sizing() -> None:
    source = _make_source(source_id=uuid4())
    missing_source_id = uuid4()
    assumption = MarketSizingAssumption(
        assumption_id=uuid4(),
        text="Growth trajectory from public filings",
        status=StartupResearchSourceStatus.INFERENCE,
        confidence=Decimal("0.6"),
        as_of=date(2026, 8, 10),
        source_mode=StartupResearchSourceMode.FROZEN,
        source_ids=(source.source_id,),
        lineage=tuple(),
        reason_code="market_method",
    )

    with pytest.raises(ValidationError, match="competitor source id missing"):
        StartupMarketResearchSnapshot.build(
            case_id=uuid4(),
            as_of=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            source_mode=StartupResearchSourceMode.FROZEN,
            research_id=uuid4(),
            competitors=(
                StartupCompetitor(
                    name="Competitor One",
                    category=StartupCompetitorCategory.DIRECT,
                    confidence=Decimal("0.8"),
                    source_ids=(missing_source_id,),
                ),
            ),
            sources=(source,),
            sentiment_signals=tuple(),
            assumptions=(assumption,),
            sizing=StartupMarketSizing(
                tam=_tam_estimate(source_id=source.source_id, value=Decimal("1000")),
                sam=_sam_estimate(
                    source_id=source.source_id,
                    value=Decimal("100"),
                    assumption_refs=(assumption.assumption_id,),
                ),
                som=_som_estimate(
                    source_id=source.source_id,
                    value=Decimal("10"),
                    assumption_refs=(assumption.assumption_id,),
                ),
            ),
            labels=("x",),
            data_revision=1,
        )

    with pytest.raises(ValidationError, match="assumption lineage id missing"):
        StartupMarketResearchSnapshot.build(
            case_id=uuid4(),
            as_of=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            source_mode=StartupResearchSourceMode.FROZEN,
            research_id=uuid4(),
            competitors=tuple(),
            sources=(source,),
            sentiment_signals=tuple(),
            assumptions=(
                _make_assumption_with_reason(
                    assumption_id=uuid4(),
                    source_id=source.source_id,
                    lineage=(uuid4(),),
                ),
            ),
            sizing=None,
            labels=("x",),
            data_revision=1,
        )

    with pytest.raises(ValidationError, match="frozen snapshot requires frozen sources"):
        StartupMarketResearchSnapshot.build(
            case_id=uuid4(),
            as_of=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            source_mode=StartupResearchSourceMode.FROZEN,
            research_id=uuid4(),
            competitors=tuple(),
            sources=(
                _make_source(
                    source_id=uuid4(),
                    source_mode=StartupResearchSourceMode.LIVE,
                ),
            ),
            sentiment_signals=tuple(),
            assumptions=tuple(),
            sizing=None,
            labels=("x",),
            data_revision=1,
        )

    with pytest.raises(ValidationError, match="assumption source id missing"):
        missing_assumption_id = uuid4()
        StartupMarketResearchSnapshot.build(
            case_id=uuid4(),
            as_of=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            source_mode=StartupResearchSourceMode.FROZEN,
            research_id=uuid4(),
            competitors=(
                StartupCompetitor(
                    name="Competitor One",
                    category=StartupCompetitorCategory.DIRECT,
                    confidence=Decimal("0.8"),
                    source_ids=(source.source_id,),
                ),
            ),
            sources=(source,),
            sentiment_signals=tuple(),
            assumptions=(
                MarketSizingAssumption(
                    assumption_id=missing_assumption_id,
                    text="growth from filings",
                    status=StartupResearchSourceStatus.SOURCE_FACT,
                    confidence=Decimal("0.6"),
                    as_of=date(2026, 8, 10),
                    source_mode=StartupResearchSourceMode.FROZEN,
                    source_ids=(uuid4(),),
                    lineage=tuple(),
                ),
            ),
            sizing=StartupMarketSizing(
                tam=_tam_estimate(source_id=source.source_id, value=Decimal("1000")),
                sam=_sam_estimate(
                    source_id=source.source_id,
                    value=Decimal("100"),
                    assumption_refs=(missing_assumption_id,),
                ),
                som=_som_estimate(
                    source_id=source.source_id,
                    value=Decimal("10"),
                    assumption_refs=(missing_assumption_id,),
                ),
            ),
            labels=("x",),
            data_revision=1,
        )

    with pytest.raises(ValidationError, match="sizing source ref missing"):
        StartupMarketResearchSnapshot.build(
            case_id=uuid4(),
            as_of=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            source_mode=StartupResearchSourceMode.FROZEN,
            research_id=uuid4(),
            competitors=(
                StartupCompetitor(
                    name="Competitor One",
                    category=StartupCompetitorCategory.DIRECT,
                    confidence=Decimal("0.8"),
                    source_ids=(source.source_id,),
                ),
            ),
            sources=(source,),
            sentiment_signals=tuple(),
            assumptions=(assumption,),
            sizing=StartupMarketSizing(
                tam=MarketSizingEstimate(
                    estimate_id=uuid4(),
                    level=StartupResearchSourceStatus.SOURCE_FACT,
                    value=Decimal("1000"),
                    unit="usd",
                    currency="usd",
                    as_of=date(2026, 8, 12),
                    source_mode=StartupResearchSourceMode.FROZEN,
                    formula_version="formula@1",
                    source_refs=(uuid4(),),
                ),
                sam=_sam_estimate(
                    source_id=source.source_id,
                    value=Decimal("100"),
                    assumption_refs=(assumption.assumption_id,),
                ),
                som=_som_estimate(
                    source_id=source.source_id,
                    value=Decimal("10"),
                    assumption_refs=(assumption.assumption_id,),
                ),
            ),
            labels=("x",),
            data_revision=1,
        )


def test_collect_port_signature_uses_plan_only() -> None:
    sig = signature(StartupResearchPort.collect)
    params = list(sig.parameters.values())
    assert len(params) == 2
    assert params[0].name == "self"
    assert params[1].name == "plan"
    assert str(params[1].annotation).endswith("StartupResearchPlan")


def test_sensitive_markers_rejected_in_persisted_text_query_and_provenance_fields() -> None:
    with pytest.raises(ValidationError, match="contains sensitive material"):
        _make_source(
            source_id=uuid4(),
            label="api_key_leak",
        )

    with pytest.raises(ValidationError, match="contains sensitive material"):
        _make_assumption_with_reason(
            assumption_id=uuid4(),
            source_id=uuid4(),
            reason_code="api_key",
        )

    with pytest.raises(ValidationError, match="contains private path token"):
        StartupCompetitor(
            name="Competitor One",
            category=StartupCompetitorCategory.DIRECT,
            confidence=Decimal("0.8"),
            reason_code="/tmp/path",
        )

    with pytest.raises(ValidationError, match="contains sensitive query key"):
        _make_source(
            source_id=uuid4(),
            label="market source",
            url="https://example.com/source",
            query="auth_token=abc",
        )

    with pytest.raises(ValidationError, match="contains private path token"):
        _make_source(
            source_id=uuid4(),
            label="market source",
            url="https://example.com/source",
            query="/etc/config",
        )

    with pytest.raises(ValidationError, match="contains sensitive material"):
        _make_source(
            source_id=uuid4(),
            label="market data",
            provenance="bearer:token",
        )


@pytest.mark.parametrize(
    "private_path",
    (
        "C:\\Users\\Akana\\Documents\\pitch.pdf",
        "C:/Users/Akana/Documents/pitch.pdf",
        "\\\\fileserver\\founder\\pitch.pdf",
        "/Users/Akana/Documents/pitch.pdf",
    ),
)
def test_local_windows_unc_and_user_paths_are_rejected_in_persisted_text(private_path: str) -> None:
    with pytest.raises(ValidationError, match="contains private path token"):
        _make_source(
            source_id=uuid4(),
            label="market source",
            query=f"market evidence from {private_path}",
        )


def test_tam_sam_som_allow_insufficient_no_values_without_invented_amount() -> None:
    sizing = StartupMarketSizing(
        tam=MarketSizingEstimate(
            estimate_id=uuid4(),
            level=StartupResearchSourceStatus.INSUFFICIENT_DATA,
            value=None,
            unit="usd",
            currency="usd",
            as_of=date(2026, 8, 12),
            source_mode=StartupResearchSourceMode.FROZEN,
            formula_version="formula@1",
            source_refs=tuple(),
        ),
        sam=MarketSizingEstimate(
            estimate_id=uuid4(),
            level=StartupResearchSourceStatus.INSUFFICIENT_DATA,
            value=None,
            unit="usd",
            currency="usd",
            as_of=date(2026, 8, 12),
            source_mode=StartupResearchSourceMode.FROZEN,
            formula_version="formula@1",
            source_refs=tuple(),
        ),
        som=MarketSizingEstimate(
            estimate_id=uuid4(),
            level=StartupResearchSourceStatus.INSUFFICIENT_DATA,
            value=None,
            unit="usd",
            currency="usd",
            as_of=date(2026, 8, 12),
            source_mode=StartupResearchSourceMode.FROZEN,
            formula_version="formula@1",
            source_refs=tuple(),
        ),
    )
    assert sizing.tam.value is None
    assert sizing.sam.value is None
    assert sizing.som.value is None


def test_tam_sam_som_reject_downstream_value_when_middle_layer_missing() -> None:
    source_id = uuid4()
    assumption_id = uuid4()
    with pytest.raises(ValidationError, match="sam is required when som has value"):
        StartupMarketSizing(
            tam=_tam_estimate(source_id, Decimal("1000")),
            sam=_insufficient_estimate(),
            som=_som_estimate(
                source_id,
                Decimal("10"),
                assumption_refs=(assumption_id,),
            ),
        )


def test_tam_sam_som_validates_present_partial_values_without_requiring_all_layers() -> None:
    source_id = uuid4()
    assumption_id = uuid4()
    sizing = StartupMarketSizing(
        tam=_tam_estimate(source_id, Decimal("1000")),
        sam=_sam_estimate(
            source_id,
            Decimal("100"),
            assumption_refs=(assumption_id,),
        ),
        som=_insufficient_estimate(),
    )
    assert sizing.tam.value == Decimal("1000")
    assert sizing.sam.value == Decimal("100")
    assert sizing.som.value is None

    with pytest.raises(ValidationError, match="sam cannot exceed tam"):
        StartupMarketSizing(
            tam=_tam_estimate(source_id, Decimal("100")),
            sam=_sam_estimate(
                source_id,
                Decimal("1000"),
                assumption_refs=(assumption_id,),
            ),
            som=_insufficient_estimate(),
        )


def test_snapshot_reorders_every_logical_collection_for_stable_hash_and_id() -> None:
    source_a = _make_source(source_id=uuid4(), label="zeta", url="https://example.com/zeta")
    source_b = _make_source(source_id=uuid4(), label="alpha", url="https://example.com/alpha")
    assump_a = _make_assumption(assumption_id=uuid4(), source_id=source_a.source_id)
    assump_b = _make_assumption(assumption_id=uuid4(), source_id=source_b.source_id)
    sentiment_id = uuid4()
    sizing_tam_id = uuid4()
    sizing_sam_id = uuid4()
    sizing_som_id = uuid4()
    sizing_tam = MarketSizingEstimate(
        estimate_id=sizing_tam_id,
        level=StartupResearchSourceStatus.SOURCE_FACT,
        value=Decimal("1200"),
        unit="usd",
        currency="usd",
        as_of=date(2026, 8, 12),
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version="formula@1",
        source_refs=(source_a.source_id,),
    )
    sizing_sam = MarketSizingEstimate(
        estimate_id=sizing_sam_id,
        level=StartupResearchSourceStatus.INFERENCE,
        value=Decimal("120"),
        unit="usd",
        currency="usd",
        as_of=date(2026, 8, 12),
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version="formula@1",
        assumption_refs=(assump_a.assumption_id,),
        confidence=Decimal("0.4"),
        source_refs=(source_a.source_id,),
    )
    sizing_som = MarketSizingEstimate(
        estimate_id=sizing_som_id,
        level=StartupResearchSourceStatus.INFERENCE,
        value=Decimal("12"),
        unit="usd",
        currency="usd",
        as_of=date(2026, 8, 12),
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version="formula@1",
        assumption_refs=(assump_a.assumption_id,),
        confidence=Decimal("0.5"),
        source_refs=(source_a.source_id,),
    )
    sizing = StartupMarketSizing(tam=sizing_tam, sam=sizing_sam, som=sizing_som)

    base = StartupMarketResearchSnapshot.build(
        case_id=uuid4(),
        as_of=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.FROZEN,
        research_id=uuid4(),
        competitors=(
            StartupCompetitor(
                name="Zed",
                category=StartupCompetitorCategory.DIRECT,
                confidence=Decimal("0.7"),
                source_ids=(source_a.source_id,),
            ),
            StartupCompetitor(
                name="Ari",
                category=StartupCompetitorCategory.SUBSTITUTE,
                confidence=Decimal("0.6"),
                source_ids=(source_b.source_id,),
            ),
        ),
        sources=(source_a, source_b),
        sentiment_signals=(
            StartupSentimentSignal(
                signal_id=sentiment_id,
                sentiment=StartupResearchSentiment.NEUTRAL,
                subject="Market sentiment neutral",
                as_of=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
                source_id=source_a.source_id,
                source_mode=StartupResearchSourceMode.FROZEN,
            ),
        ),
        assumptions=(assump_a, assump_b),
            sizing=sizing,
        labels=("beta", "alpha"),
        data_revision=1,
    )

    reordered = StartupMarketResearchSnapshot.build(
        case_id=base.case_id,
        as_of=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.FROZEN,
        research_id=base.research_id,
        competitors=tuple(reversed((
            StartupCompetitor(
                name="Zed",
                category=StartupCompetitorCategory.DIRECT,
                confidence=Decimal("0.7"),
                source_ids=(source_a.source_id,),
            ),
            StartupCompetitor(
                name="Ari",
                category=StartupCompetitorCategory.SUBSTITUTE,
                confidence=Decimal("0.6"),
                source_ids=(source_b.source_id,),
            ),
        ))),
        sources=tuple(reversed((source_a, source_b))),
        sentiment_signals=(
            StartupSentimentSignal(
                signal_id=sentiment_id,
                sentiment=StartupResearchSentiment.NEUTRAL,
                subject="Market sentiment neutral",
                as_of=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
                source_id=source_a.source_id,
                source_mode=StartupResearchSourceMode.FROZEN,
            ),
        ),
        assumptions=(assump_b, assump_a),
            sizing=sizing,
        labels=("alpha", "beta"),
        data_revision=1,
    )

    assert base.snapshot_hash == reordered.snapshot_hash
    assert base.snapshot_id == reordered.snapshot_id


def test_public_benchmark_candidates_are_frozen_validated_and_hash_stable() -> None:
    source = _make_source(
        source_id=uuid4(),
        url="https://example.com/",
        source_mode=StartupResearchSourceMode.LIVE,
    )
    candidate_a = StartupPublicBenchmarkCandidate(
        input_key="arpa",
        source_url="https://example.com",
        publisher="Example Research",
        publication_date="2026-08-01",
        retrieval_date="2026-08-22",
        as_of="2026-08-01",
        source_class="industry_report",
        confidence="medium",
        range_low="18500",
        range_high="32500",
        unit="KZT",
        period="month",
        formula="reported public KZT ARPA benchmark range",
        dependencies=("public comparable companies",),
        validation_plan="Use only as external context until case evidence confirms fit.",
        source_ref=source.source_id,
        rationale="Cited public range for comparable SaaS ARPA.",
    )
    candidate_b = StartupPublicBenchmarkCandidate(
        input_key="monthly_price",
        source_url="https://example.com/",
        publisher="Example Research",
        publication_date="2026-08-01",
        retrieval_date="2026-08-22",
        as_of="2026-08-01",
        source_class="pricing_page",
        confidence="medium",
        value="9000",
        unit="KZT",
        period="month",
        formula="reported public KZT monthly price",
        dependencies=("public pricing page",),
        validation_plan="Use only as external context until case evidence confirms fit.",
        source_ref=source.source_id,
        rationale="Cited public monthly price for comparable SaaS.",
    )

    base = StartupMarketResearchSnapshot.build(
        case_id=uuid4(),
        as_of=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=uuid4(),
        competitors=(),
        sources=(source,),
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=("live_public_research",),
        data_revision=1,
        public_benchmark_candidates=(candidate_b, candidate_a),
    )
    reordered = StartupMarketResearchSnapshot.build(
        case_id=base.case_id,
        as_of=base.as_of,
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=base.research_id,
        competitors=(),
        sources=(source,),
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=("live_public_research",),
        data_revision=1,
        public_benchmark_candidates=(candidate_a, candidate_b),
    )
    without_candidates = StartupMarketResearchSnapshot.build(
        case_id=base.case_id,
        as_of=base.as_of,
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=base.research_id,
        competitors=(),
        sources=(source,),
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=("live_public_research",),
        data_revision=1,
    )

    assert base.snapshot_hash == reordered.snapshot_hash
    assert base.snapshot_id == reordered.snapshot_id
    assert base.snapshot_hash != without_candidates.snapshot_hash
    assert base.public_benchmark_candidates[0].input_key == "arpa"


def test_public_benchmark_candidate_rejects_private_currency_period_and_precision() -> None:
    source_id = uuid4()
    payload = {
        "input_key": "arpa",
        "source_url": "https://example.com/benchmark",
        "publisher": "Example Research",
        "publication_date": "2026-08-01",
        "retrieval_date": "2026-08-22",
        "as_of": "2026-08-01",
        "source_class": "industry_report",
        "confidence": "medium",
        "value": "1000",
        "unit": "KZT",
        "period": "month",
        "formula": "reported public KZT monthly benchmark",
        "dependencies": ("public comparable companies",),
        "validation_plan": "Use only as external context until case evidence confirms fit.",
        "source_ref": source_id,
        "rationale": "Cited public benchmark.",
    }

    for override in (
        {"input_key": "mrr"},
        {"unit": "USD"},
        {"period": "year"},
        {"value": "10.123"},
        {"provenance": "source_fact"},
    ):
        with pytest.raises(ValidationError):
            StartupPublicBenchmarkCandidate(**{**payload, **override})


def _base_snapshot() -> StartupMarketResearchSnapshot:
    source = _make_source(uuid4())
    assumption = _make_assumption(uuid4(), source.source_id)
    return StartupMarketResearchSnapshot.build(
        case_id=uuid4(),
        as_of=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.FROZEN,
        research_id=uuid4(),
        competitors=(
            StartupCompetitor(
                name="Competitor One",
                category=StartupCompetitorCategory.DIRECT,
                confidence=Decimal("0.8"),
                source_ids=(source.source_id,),
            ),
        ),
        sources=(source,),
        sentiment_signals=tuple(),
        assumptions=(assumption,),
        sizing=StartupMarketSizing(
            tam=_tam_estimate(source.source_id, Decimal("1000")),
            sam=_sam_estimate(
                source.source_id,
                Decimal("100"),
                assumption_refs=(assumption.assumption_id,),
            ),
            som=_som_estimate(
                source.source_id,
                Decimal("10"),
                assumption_refs=(assumption.assumption_id,),
            ),
        ),
        labels=("market",),
        data_revision=1,
    )


def _make_source(
    source_id: UUID,
    label: str = "market data",
    url: str = "https://example.com/source",
    source_mode: StartupResearchSourceMode = StartupResearchSourceMode.FROZEN,
    query: str = "seed startup market",
    provenance: str = "manifest:public-v1",
) -> StartupResearchSource:
    return StartupResearchSource(
        source_id=source_id,
        source_mode=source_mode,
        source_hash="sha256:" + ("a" * 64),
        source_url=HttpUrl(url),
        source_label=label,
        as_of=date(2026, 8, 10),
        retrieved_at=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
        query=query,
        provenance=provenance,
    )


def _make_assumption(assumption_id: UUID, source_id: UUID) -> MarketSizingAssumption:
    return _make_assumption_with_reason(
        assumption_id=assumption_id,
        source_id=source_id,
    )


def _make_assumption_with_reason(
    assumption_id: UUID,
    source_id: UUID,
    text: str = "Comparable growth assumption",
    reason_code: str = "top_down",
    lineage: tuple[UUID, ...] | None = None,
) -> MarketSizingAssumption:
    return MarketSizingAssumption(
        assumption_id=assumption_id,
        text=text,
        status=StartupResearchSourceStatus.INFERENCE,
        confidence=Decimal("0.7"),
        as_of=date(2026, 8, 11),
        source_mode=StartupResearchSourceMode.FROZEN,
        source_ids=(source_id,),
        lineage=tuple() if lineage is None else lineage,
        reason_code=reason_code,
    )


def _tam_estimate(source_id: UUID, value: Decimal, assumption_refs: tuple[UUID, ...] | None = None) -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=uuid4(),
        level=StartupResearchSourceStatus.SOURCE_FACT,
        value=value,
        unit="usd",
        currency="usd",
        as_of=date(2026, 8, 12),
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version="formula@1",
        source_refs=(source_id,),
        assumption_refs=tuple() if assumption_refs is None else assumption_refs,
    )


def _sam_estimate(source_id: UUID, value: Decimal, assumption_refs: tuple[UUID, ...] | None = None) -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=uuid4(),
        level=StartupResearchSourceStatus.INFERENCE,
        value=value,
        unit="usd",
        currency="usd",
        as_of=date(2026, 8, 12),
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version="formula@1",
        assumption_refs=tuple() if assumption_refs is None else assumption_refs,
        confidence=Decimal("0.4"),
        source_refs=(source_id,),
    )


def _som_estimate(source_id: UUID, value: Decimal, assumption_refs: tuple[UUID, ...] | None = None) -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=uuid4(),
        level=StartupResearchSourceStatus.INFERENCE,
        value=value,
        unit="usd",
        currency="usd",
        as_of=date(2026, 8, 12),
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version="formula@1",
        assumption_refs=tuple() if assumption_refs is None else assumption_refs,
        confidence=Decimal("0.5"),
        source_refs=(source_id,),
    )


def _insufficient_estimate() -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=uuid4(),
        level=StartupResearchSourceStatus.INSUFFICIENT_DATA,
        value=None,
        unit="usd",
        currency="usd",
        as_of=date(2026, 8, 12),
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version="formula@1",
        source_refs=tuple(),
    )

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import HttpUrl
import pytest

from due_diligence_agent.application.services.startup_gtm_service import (
    StartupGtmService,
)
from due_diligence_agent.application.services.startup_product_validation_service import (
    StartupProductValidationService,
)
from due_diligence_agent.domain.startup.gtm import (
    StartupGtmDimension,
    StartupGtmDimensionName,
    StartupGtmDimensionStatus,
    StartupGtmExperimentCode,
    StartupGtmHorizon,
    StartupGtmSnapshot,
    StartupGtmStatus,
)
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchSource,
    StartupResearchSourceMode,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.roles import (
    StartupProductValidationDimension,
    StartupProductValidationDimensionName,
    StartupProductValidationDimensionStatus,
    StartupProductValidationSnapshot,
    StartupProductValidationStatus,
)


_BUILT_AT = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)


def test_gtm_snapshot_is_deterministic_bounded_and_reference_only() -> None:
    profile = _profile(
        {
            name: _field(name)
            for name in (
                StartupProfileFieldName.PROBLEM,
                StartupProfileFieldName.ICP,
                StartupProfileFieldName.USERS,
                StartupProfileFieldName.BUYERS,
                StartupProfileFieldName.GEOGRAPHY,
                StartupProfileFieldName.BUSINESS_MODEL,
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
                StartupProfileFieldName.TRACTION,
                StartupProfileFieldName.CHANNELS_GTM,
                StartupProfileFieldName.COMPETITORS_MENTIONED,
                StartupProfileFieldName.WEAKNESSES,
            )
        }
    )
    evidence_ids = _evidence_ids(profile)
    product_validation = StartupProductValidationService().evaluate(
        profile,
        evidence_fact_ids=evidence_ids,
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )
    market_research = _market_research(profile)
    service = StartupGtmService()

    first = service.evaluate(
        profile,
        product_validation=product_validation,
        market_research=market_research,
        evidence_fact_ids=evidence_ids,
        finding_ids=(str(_uuid("finding:market")), str(_uuid("finding:risk"))),
        contradiction_ids=(),
    )
    second = service.evaluate(
        profile,
        product_validation=product_validation,
        market_research=market_research,
        evidence_fact_ids=tuple(reversed(evidence_ids)),
        finding_ids=(str(_uuid("finding:risk")), str(_uuid("finding:market"))),
        contradiction_ids=(),
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_hash == second.snapshot_hash
    assert tuple(item.name for item in first.dimensions) == tuple(StartupGtmDimensionName)
    assert tuple(item.horizon for item in first.launch_plan) == tuple(StartupGtmHorizon)
    assert first.status is StartupGtmStatus.PARTIAL
    channels = _dimension(first, StartupGtmDimensionName.CHANNELS)
    assert channels.status is StartupGtmDimensionStatus.SUPPORTED
    assert channels.evidence_fact_ids
    market = _dimension(first, StartupGtmDimensionName.MARKET_CONTEXT)
    assert market.market_source_ids == (str(_uuid("source:gtm-market")),)
    experiment_codes = {
        code for phase in first.launch_plan for code in phase.experiment_codes
    }
    assert StartupGtmExperimentCode.MEASURE_CHANNEL_SIGNAL in experiment_codes
    assert StartupGtmExperimentCode.REVIEW_LAUNCH_EVIDENCE in experiment_codes
    dumped = first.model_dump_json()
    assert "private founder channel" not in dumped
    assert "https://research.example/market" not in dumped
    assert "content_sha256" not in dumped
    assert "score" not in dumped
    assert "target" not in dumped


def test_gtm_plan_converts_missing_proof_into_bounded_validation_work() -> None:
    profile = _profile({})
    product_validation = StartupProductValidationService().evaluate(
        profile,
        evidence_fact_ids=(),
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )
    snapshot = StartupGtmService().evaluate(
        profile,
        product_validation=product_validation,
        market_research=_market_research(profile, with_source=False),
        evidence_fact_ids=(),
        finding_ids=(),
        contradiction_ids=(),
    )

    assert snapshot.status is StartupGtmStatus.INSUFFICIENT
    assert all(
        dimension.status is StartupGtmDimensionStatus.MISSING
        for dimension in snapshot.dimensions
    )
    by_horizon = {phase.horizon: phase for phase in snapshot.launch_plan}
    assert StartupGtmExperimentCode.CLARIFY_AUDIENCE in by_horizon[
        StartupGtmHorizon.DAY_7
    ].experiment_codes
    assert StartupGtmExperimentCode.VALIDATE_CHANNEL in by_horizon[
        StartupGtmHorizon.DAY_30
    ].experiment_codes
    assert StartupGtmExperimentCode.VALIDATE_OFFER in by_horizon[
        StartupGtmHorizon.DAY_60
    ].experiment_codes
    assert by_horizon[StartupGtmHorizon.DAY_90].experiment_codes == (
        StartupGtmExperimentCode.REVIEW_LAUNCH_EVIDENCE,
    )
    dumped = snapshot.model_dump_json()
    for invented in ("linkedin", "paid search", "cac target", "conversion target"):
        assert invented not in dumped.casefold()


def test_gtm_snapshot_downgrades_excluded_channel_evidence() -> None:
    channel = _field(StartupProfileFieldName.CHANNELS_GTM)
    profile = _profile({StartupProfileFieldName.CHANNELS_GTM: channel})
    allowed_evidence_ids = tuple(str(ref.evidence_id) for ref in channel.evidence_refs)
    product_validation = StartupProductValidationService().evaluate(
        profile,
        evidence_fact_ids=allowed_evidence_ids,
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )
    market_research = _market_research(profile, with_source=False)
    service = StartupGtmService()

    before = service.evaluate(
        profile,
        product_validation=product_validation,
        market_research=market_research,
        evidence_fact_ids=allowed_evidence_ids,
        finding_ids=(),
        contradiction_ids=(),
    )
    after = service.evaluate(
        profile,
        product_validation=product_validation,
        market_research=market_research,
        evidence_fact_ids=(),
        finding_ids=(),
        contradiction_ids=(),
    )

    before_channels = _dimension(before, StartupGtmDimensionName.CHANNELS)
    after_channels = _dimension(after, StartupGtmDimensionName.CHANNELS)
    assert before_channels.status is StartupGtmDimensionStatus.SUPPORTED
    assert after_channels.status is StartupGtmDimensionStatus.MISSING
    assert after_channels.evidence_fact_ids == ()
    assert StartupGtmExperimentCode.VALIDATE_CHANNEL in {
        code for phase in after.launch_plan for code in phase.experiment_codes
    }
    assert before.snapshot_hash != after.snapshot_hash


def test_gtm_snapshot_never_promotes_contradicted_product_signal() -> None:
    profile = _profile(
        {
            name: _field(name)
            for name in (
                StartupProfileFieldName.ICP,
                StartupProfileFieldName.GEOGRAPHY,
                StartupProfileFieldName.BUSINESS_MODEL,
                StartupProfileFieldName.PRICING_REVENUE_MODEL,
                StartupProfileFieldName.TRACTION,
                StartupProfileFieldName.CHANNELS_GTM,
                StartupProfileFieldName.COMPETITORS_MENTIONED,
                StartupProfileFieldName.WEAKNESSES,
            )
        }
    )
    evidence_ids = _evidence_ids(profile)
    product_validation = StartupProductValidationService().evaluate(
        profile,
        evidence_fact_ids=evidence_ids,
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )
    product_validation = _with_product_dimension_status(
        product_validation,
        name=StartupProductValidationDimensionName.WILLINGNESS_TO_PAY,
        status=StartupProductValidationDimensionStatus.CONTRADICTED,
    )

    snapshot = StartupGtmService().evaluate(
        profile,
        product_validation=product_validation,
        market_research=_market_research(profile),
        evidence_fact_ids=evidence_ids,
        finding_ids=(),
        contradiction_ids=(),
    )

    offer = _dimension(snapshot, StartupGtmDimensionName.OFFER)
    assert offer.status is StartupGtmDimensionStatus.PARTIAL
    assert offer.reason_code == "gtm.partial:offer"


def test_gtm_snapshot_rejects_stale_product_validation_lineage() -> None:
    old_profile = _profile({}, revision=3)
    current_profile = _profile({}, revision=4)
    product_validation = StartupProductValidationService().evaluate(
        old_profile,
        evidence_fact_ids=(),
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )

    with pytest.raises(ValueError, match="gtm_product_validation_lineage_mismatch"):
        StartupGtmService().evaluate(
            current_profile,
            product_validation=product_validation,
            market_research=_market_research(current_profile),
            evidence_fact_ids=(),
            finding_ids=(),
            contradiction_ids=(),
        )


def test_gtm_snapshot_rejects_stale_market_research_lineage() -> None:
    old_profile = _profile({}, revision=3)
    current_profile = _profile({}, revision=4)
    product_validation = StartupProductValidationService().evaluate(
        current_profile,
        evidence_fact_ids=(),
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )

    with pytest.raises(ValueError, match="gtm_market_research_lineage_mismatch"):
        StartupGtmService().evaluate(
            current_profile,
            product_validation=product_validation,
            market_research=_market_research(old_profile),
            evidence_fact_ids=(),
            finding_ids=(),
            contradiction_ids=(),
        )


def _dimension(
    snapshot: StartupGtmSnapshot,
    name: StartupGtmDimensionName,
) -> StartupGtmDimension:
    return next(item for item in snapshot.dimensions if item.name is name)


def _profile(
    overrides: dict[StartupProfileFieldName, StartupProfileField],
    *,
    revision: int = 4,
) -> StartupProfile:
    fields = {
        name.value: overrides.get(
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
        case_id=_uuid("case:gtm"),
        schema_version="startup_profile@1",
        profile_version="enriched@1",
        extractor_version="test@1",
        analysis_stage=StartupProfileAnalysisStage.ENRICHED,
        parent_profile_id=_uuid("profile:gtm-primary"),
        data_revision=revision,
        source_hashes={"upload": "sha256:" + ("a" * 64)},
        parse_outcomes={"upload": "parsed"},
        fields=fields,
        gap_codes=(),
        contradiction_ids=(),
        case_revision_at=_BUILT_AT,
    )


def _field(name: StartupProfileFieldName) -> StartupProfileField:
    return StartupProfileField(
        name=name,
        status=StartupProfileFieldStatus.SOURCE_FACT,
        values=("private founder channel",),
        confidence=Decimal("0.82"),
        evidence_refs=(
            _evidence_ref(name, "a"),
            _evidence_ref(name, "b"),
        ),
    )


def _evidence_ref(
    name: StartupProfileFieldName,
    suffix: str,
) -> StartupProfileEvidenceRef:
    return StartupProfileEvidenceRef(
        evidence_id=_uuid(f"evidence:{name.value}:{suffix}"),
        fragment_id=_uuid(f"fragment:{name.value}:{suffix}"),
        artifact_id=_uuid(f"artifact:{name.value}:{suffix}"),
        artifact_hash="sha256:" + ("b" * 64),
        locator_hash="sha256:" + ("c" * 64),
        field_name=name,
        confidence=Decimal("0.8"),
    )


def _evidence_ids(profile: StartupProfile) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(reference.evidence_id)
                for field in profile.fields.values()
                for reference in field.evidence_refs
            }
        )
    )


def _market_research(
    profile: StartupProfile,
    *,
    with_source: bool = True,
) -> StartupMarketResearchSnapshot:
    sources = (
        (
            StartupResearchSource(
                source_id=_uuid("source:gtm-market"),
                source_mode=StartupResearchSourceMode.FROZEN,
                source_hash="sha256:" + ("d" * 64),
                source_url=HttpUrl("https://research.example/market"),
                source_label="Frozen GTM market source",
                as_of=date(2026, 8, 1),
                retrieved_at=_BUILT_AT,
                query="gtm market evidence",
                provenance="frozen_fixture",
            ),
        )
        if with_source
        else ()
    )
    return StartupMarketResearchSnapshot.build(
        case_id=profile.case_id,
        as_of=_BUILT_AT,
        source_mode=StartupResearchSourceMode.FROZEN,
        research_id=_uuid("research:gtm-market"),
        competitors=(),
        sources=sources,
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=(),
        data_revision=profile.data_revision,
    )


def _uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)


def _with_product_dimension_status(
    snapshot: StartupProductValidationSnapshot,
    *,
    name: StartupProductValidationDimensionName,
    status: StartupProductValidationDimensionStatus,
) -> StartupProductValidationSnapshot:
    dimensions = tuple(
        StartupProductValidationDimension(
            name=item.name,
            status=status if item.name is name else item.status,
            evidence_fact_ids=item.evidence_fact_ids,
            startup_claim_ids=item.startup_claim_ids,
            contradiction_ids=item.contradiction_ids,
            reason_code=(
                f"product_validation.{status.value}:{item.name.value}"
                if item.name is name
                else item.reason_code
            ),
            gap_code=None if item.name is name else item.gap_code,
        )
        for item in snapshot.dimensions
    )
    return StartupProductValidationSnapshot.build(
        case_id=snapshot.case_id,
        profile_id=snapshot.profile_id,
        profile_hash=snapshot.profile_hash,
        profile_revision=snapshot.profile_revision,
        status=StartupProductValidationStatus.CONTRADICTED,
        dimensions=dimensions,
        built_at=snapshot.built_at,
    )

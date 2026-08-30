from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TypedDict
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from pydantic import ValidationError

from due_diligence_agent.application.services.startup_improvement_service import (
    StartupImprovementService,
    StartupImprovementValidationError,
)
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    ContradictionStatus,
    FindingSeverity,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import Calculation
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
from due_diligence_agent.domain.startup.advisor import (
    StartupImprovementEvidenceKind,
    StartupImprovementEvidenceRef,
    StartupImprovementProposal,
    StartupImprovementTargetArea,
)
from due_diligence_agent.domain.startup.gtm import (
    StartupGtmDimension,
    StartupGtmDimensionName,
    StartupGtmDimensionStatus,
    StartupGtmHorizon,
    StartupGtmLaunchPhase,
    StartupGtmSnapshot,
    StartupGtmStatus,
)
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.readiness import (
    StartupMetricPack,
    StartupReadinessDimension,
    StartupReadinessDimensionStatus,
    StartupReadinessSnapshot,
)


AS_OF = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
CASE_ID = uuid5(NAMESPACE_URL, "startup-improvement-case")
OTHER_CASE_ID = uuid5(NAMESPACE_URL, "startup-improvement-other-case")
ARTIFACT_ID = uuid5(NAMESPACE_URL, "startup-improvement-artifact")
CALCULATION_ID = uuid5(NAMESPACE_URL, "startup-improvement-calculation")
CONTRADICTION_ID = uuid5(NAMESPACE_URL, "startup-improvement-contradiction")
PUBLIC_SOURCE_ID = uuid5(NAMESPACE_URL, "startup-improvement-public-source")


class _Context(TypedDict):
    case: DueDiligenceCase
    base_report_snapshot: ReportSnapshot
    startup_profile: StartupProfile
    startup_readiness: StartupReadinessSnapshot
    startup_gtm: StartupGtmSnapshot
    contradictions: tuple[Contradiction, ...]
    startup_market_research: StartupMarketResearchSnapshot
    calculations: tuple[Calculation, ...]


def test_generates_six_deterministic_russian_proposals_with_typed_evidence() -> None:
    context = _context()
    service = StartupImprovementService()

    first = _generate(service, context, improvement_version=3)
    reordered = _generate(
        service,
        context,
        improvement_version=3,
        contradictions=tuple(reversed(context["contradictions"])),
        calculations=tuple(reversed(context["calculations"])),
    )

    assert tuple(proposal.target_area for proposal in first) == tuple(
        StartupImprovementTargetArea
    )
    assert first == reordered
    assert len({proposal.proposal_id for proposal in first}) == 6
    assert all(proposal.proposal_id.version == 5 for proposal in first)
    assert all(proposal.case_id == CASE_ID for proposal in first)
    assert all(proposal.base_report_snapshot_id == context["base_report_snapshot"].id for proposal in first)
    assert all(proposal.base_report_snapshot_hash == context["base_report_snapshot"].report_hash for proposal in first)
    assert all(proposal.base_case_revision == context["case"].data_revision for proposal in first)
    assert all(proposal.improvement_version == 3 for proposal in first)
    assert all(Decimal("0") <= proposal.confidence <= Decimal("1") for proposal in first)
    assert all(
        re.search(r"[А-Яа-яЁё]", text)
        for proposal in first
        for text in (
            proposal.recommendation_ru,
            proposal.rationale_ru,
            proposal.expected_effect_ru,
        )
    )

    evidence = {
        (reference.kind, reference.ref_id)
        for proposal in first
        for reference in proposal.evidence_refs
    }
    assert (StartupImprovementEvidenceKind.PUBLIC_FACT, PUBLIC_SOURCE_ID) in evidence
    assert (StartupImprovementEvidenceKind.LOCAL_CALCULATION, CALCULATION_ID) in evidence
    assert (
        StartupImprovementEvidenceKind.LIVE_INFERENCE,
        context["startup_market_research"].snapshot_id,
    ) in evidence


def test_live_inference_is_never_relabelled_as_public_fact() -> None:
    context = _context()

    proposals = _generate(StartupImprovementService(), context, improvement_version=1)
    public_fact_ids = {
        reference.ref_id
        for proposal in proposals
        for reference in proposal.evidence_refs
        if reference.kind is StartupImprovementEvidenceKind.PUBLIC_FACT
    }
    live_inference_ids = {
        reference.ref_id
        for proposal in proposals
        for reference in proposal.evidence_refs
        if reference.kind is StartupImprovementEvidenceKind.LIVE_INFERENCE
    }

    assert public_fact_ids == {PUBLIC_SOURCE_ID}
    assert live_inference_ids == {context["startup_market_research"].snapshot_id}
    assert live_inference_ids.isdisjoint(public_fact_ids)


def test_decision_advances_only_for_acceptance_and_records_sorted_immutable_delta() -> None:
    context = _context()
    service = StartupImprovementService()
    proposals = _generate(service, context, improvement_version=7)
    accepted = (
        _proposal_id(proposals, StartupImprovementTargetArea.RISK_REDUCTION),
        _proposal_id(proposals, StartupImprovementTargetArea.GTM),
    )
    rejected = (
        _proposal_id(proposals, StartupImprovementTargetArea.METRICS),
    )
    report_before = context["base_report_snapshot"].model_dump(mode="json")

    accepted_delta = service.apply_decision(
        case=context["case"],
        base_report_snapshot=context["base_report_snapshot"],
        proposals=proposals,
        previous_version=7,
        accepted_proposal_ids=accepted,
        rejected_proposal_ids=rejected,
    )
    rejected_only_delta = service.apply_decision(
        case=context["case"],
        base_report_snapshot=context["base_report_snapshot"],
        proposals=proposals,
        previous_version=7,
        accepted_proposal_ids=(),
        rejected_proposal_ids=rejected,
    )

    assert accepted_delta.case_id == CASE_ID
    assert accepted_delta.base_report_snapshot_id == context["base_report_snapshot"].id
    assert accepted_delta.base_report_snapshot_hash == context["base_report_snapshot"].report_hash
    assert accepted_delta.base_case_revision == context["case"].data_revision
    assert accepted_delta.previous_version == 7
    assert accepted_delta.new_version == 8
    assert accepted_delta.accepted_proposal_ids == tuple(sorted(accepted, key=str))
    assert accepted_delta.rejected_proposal_ids == tuple(sorted(rejected, key=str))
    assert accepted_delta.changed_fields == ("gtm", "risk_reduction")
    assert rejected_only_delta.previous_version == 7
    assert rejected_only_delta.new_version == 7
    assert rejected_only_delta.changed_fields == ()
    assert context["base_report_snapshot"].version == 99
    assert context["base_report_snapshot"].model_dump(mode="json") == report_before
    with pytest.raises(ValidationError):
        accepted_delta.new_version = 9


@pytest.mark.parametrize("invalid_kind", ["unknown", "duplicate", "overlap"])
def test_decision_rejects_unknown_duplicate_or_overlapping_ids(invalid_kind: str) -> None:
    context = _context()
    service = StartupImprovementService()
    proposals = _generate(service, context, improvement_version=1)
    known = proposals[0].proposal_id
    unknown = uuid5(NAMESPACE_URL, "unknown-improvement-proposal")
    accepted: tuple[UUID, ...]
    rejected: tuple[UUID, ...]
    if invalid_kind == "unknown":
        accepted, rejected = (unknown,), ()
    elif invalid_kind == "duplicate":
        accepted, rejected = (known, known), ()
    else:
        accepted, rejected = (known,), (known,)

    with pytest.raises(StartupImprovementValidationError, match=invalid_kind):
        service.apply_decision(
            case=context["case"],
            base_report_snapshot=context["base_report_snapshot"],
            proposals=proposals,
            previous_version=1,
            accepted_proposal_ids=accepted,
            rejected_proposal_ids=rejected,
        )


def test_decision_rejects_cross_case_and_stale_report_lineage() -> None:
    service = StartupImprovementService()
    context = _context()
    proposals = _generate(service, context, improvement_version=2)
    other_context = _context(case_id=OTHER_CASE_ID)
    other_proposals = _generate(service, other_context, improvement_version=2)

    with pytest.raises(StartupImprovementValidationError, match="cross_case"):
        service.apply_decision(
            case=context["case"],
            base_report_snapshot=context["base_report_snapshot"],
            proposals=other_proposals,
            previous_version=2,
            accepted_proposal_ids=(other_proposals[0].proposal_id,),
            rejected_proposal_ids=(),
        )

    stale_report = _report(case_id=CASE_ID, data_revision=1, hash_seed="stale")
    with pytest.raises(StartupImprovementValidationError, match="stale_hash"):
        service.apply_decision(
            case=context["case"],
            base_report_snapshot=stale_report,
            proposals=proposals,
            previous_version=2,
            accepted_proposal_ids=(proposals[0].proposal_id,),
            rejected_proposal_ids=(),
        )

    revised_case = _case(case_id=CASE_ID, data_revision=2)
    with pytest.raises(StartupImprovementValidationError, match="stale_revision"):
        service.apply_decision(
            case=revised_case,
            base_report_snapshot=context["base_report_snapshot"],
            proposals=proposals,
            previous_version=2,
            accepted_proposal_ids=(proposals[0].proposal_id,),
            rejected_proposal_ids=(),
        )


def test_proposals_reject_stale_or_cross_case_canonical_inputs() -> None:
    context = _context()
    service = StartupImprovementService()

    with pytest.raises(StartupImprovementValidationError, match="cross_case_calculation"):
        _generate(
            service,
            context,
            improvement_version=1,
            calculations=(_calculation(case_id=OTHER_CASE_ID),),
        )

    with pytest.raises(StartupImprovementValidationError, match="stale_revision_report"):
        _generate(
            service,
            context,
            improvement_version=1,
            base_report_snapshot=_report(
                case_id=CASE_ID,
                data_revision=2,
                hash_seed="revision-2",
            ),
        )


def test_evidence_refs_require_uuid_identifiers_and_bounded_decimal_confidence() -> None:
    with pytest.raises(ValidationError):
        StartupImprovementEvidenceRef.model_validate(
            {
                "kind": StartupImprovementEvidenceKind.PUBLIC_FACT,
                "ref_id": "not-an-id",
                "confidence": Decimal("0.8"),
            }
        )
    with pytest.raises(ValidationError):
        StartupImprovementEvidenceRef(
            kind=StartupImprovementEvidenceKind.PUBLIC_FACT,
            ref_id=PUBLIC_SOURCE_ID,
            confidence=Decimal("1.01"),
        )


def test_proposal_text_must_be_russian_and_proposal_identity_is_validated() -> None:
    context = _context()
    proposal = _generate(StartupImprovementService(), context, improvement_version=1)[0]

    with pytest.raises(ValueError, match="Cyrillic"):
        StartupImprovementProposal.create(
            case_id=proposal.case_id,
            base_report_snapshot_id=proposal.base_report_snapshot_id,
            base_report_snapshot_hash=proposal.base_report_snapshot_hash,
            base_case_revision=proposal.base_case_revision,
            improvement_version=proposal.improvement_version,
            target_area=proposal.target_area,
            recommendation_ru="Improve positioning",
            rationale_ru=proposal.rationale_ru,
            expected_effect_ru=proposal.expected_effect_ru,
            evidence_refs=proposal.evidence_refs,
            confidence=proposal.confidence,
        )

    with pytest.raises(ValidationError, match="invalid proposal id"):
        StartupImprovementProposal(
            **{
                **proposal.model_dump(mode="python", exclude={"proposal_id"}),
                "proposal_id": uuid5(NAMESPACE_URL, "wrong-proposal-id"),
            }
        )


def _context(*, case_id: UUID = CASE_ID) -> _Context:
    case = _case(case_id=case_id)
    profile = _profile(case_id=case_id)
    readiness = _readiness(profile)
    market = _market(case_id=case_id)
    gtm = _gtm(profile, market)
    return {
        "case": case,
        "base_report_snapshot": _report(case_id=case_id),
        "startup_profile": profile,
        "startup_readiness": readiness,
        "startup_gtm": gtm,
        "contradictions": (_contradiction(case_id=case_id),),
        "startup_market_research": market,
        "calculations": (_calculation(case_id=case_id),),
    }


def _generate(
    service: StartupImprovementService,
    context: _Context,
    *,
    improvement_version: int,
    base_report_snapshot: ReportSnapshot | None = None,
    contradictions: tuple[Contradiction, ...] | None = None,
    calculations: tuple[Calculation, ...] | None = None,
) -> tuple[StartupImprovementProposal, ...]:
    return service.generate_proposals(
        case=context["case"],
        base_report_snapshot=base_report_snapshot or context["base_report_snapshot"],
        startup_profile=context["startup_profile"],
        startup_readiness=context["startup_readiness"],
        startup_gtm=context["startup_gtm"],
        contradictions=(
            context["contradictions"] if contradictions is None else contradictions
        ),
        startup_market_research=context["startup_market_research"],
        calculations=context["calculations"] if calculations is None else calculations,
        improvement_version=improvement_version,
    )


def _case(*, case_id: UUID, data_revision: int = 1) -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=case_id,
        mode=AnalysisMode.STARTUP,
        entity_name="FounderCo",
        entity_identifier="founderco",
        jurisdiction="KZ",
        scope=("startup",),
        as_of=AS_OF,
        base_currency="KZT",
        privacy_policy="startup-local@1",
        budget_policy="offline",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
        updated_at=AS_OF,
        workflow_version="startup-graph@1",
        data_revision=data_revision,
    )


def _profile(*, case_id: UUID) -> StartupProfile:
    supported = {
        StartupProfileFieldName.PROBLEM,
        StartupProfileFieldName.SOLUTION,
        StartupProfileFieldName.ICP,
        StartupProfileFieldName.GEOGRAPHY,
        StartupProfileFieldName.BUSINESS_MODEL,
        StartupProfileFieldName.CHANNELS_GTM,
    }
    fields = {
        name.value: (
            _supported_profile_field(name)
            if name in supported
            else StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal("0"),
                reason_code=f"{name.value}_missing",
            )
        )
        for name in StartupProfileFieldName
    }
    return StartupProfile.build(
        case_id=case_id,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@42",
        extractor_version="deterministic-profile@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=1,
        source_hashes={"pitch-deck": "sha256:" + "a" * 64},
        parse_outcomes={"pitch-deck": "parsed"},
        fields=fields,
        gap_codes=("traction_missing",),
        case_revision_at=AS_OF,
    )


def _supported_profile_field(name: StartupProfileFieldName) -> StartupProfileField:
    return StartupProfileField(
        name=name,
        status=StartupProfileFieldStatus.SOURCE_FACT,
        values=(f"Canonical {name.value}",),
        confidence=Decimal("0.85"),
        evidence_refs=(
            StartupProfileEvidenceRef(
                evidence_id=uuid5(NAMESPACE_URL, f"startup-improvement:{name.value}"),
                artifact_id=ARTIFACT_ID,
                artifact_hash="sha256:" + "a" * 64,
                locator_hash="sha256:" + "b" * 64,
                field_name=name,
                confidence=Decimal("0.85"),
            ),
        ),
    )


def _readiness(profile: StartupProfile) -> StartupReadinessSnapshot:
    dimension = StartupReadinessDimension(
        dimension_id=uuid5(NAMESPACE_URL, "startup-improvement-readiness-dimension"),
        metric_id="gross_margin",
        status=StartupReadinessDimensionStatus.PROVISIONAL,
        reason_code="metric_provisional",
    )
    pack = StartupMetricPack.build(
        profile_id=profile.profile_id,
        profile_hash=profile.profile_hash,
        profile_revision=profile.data_revision,
        metric_ids=("gross_margin",),
        dimensions=(dimension,),
        built_at=AS_OF,
    )
    return StartupReadinessSnapshot.build(
        profile_id=profile.profile_id,
        profile_hash=profile.profile_hash,
        profile_revision=profile.data_revision,
        metric_pack=pack,
        calculation_ids=(CALCULATION_ID,),
        built_at=AS_OF,
    )


def _market(*, case_id: UUID) -> StartupMarketResearchSnapshot:
    source = StartupResearchSource.model_validate(
        {
            "source_id": (
                PUBLIC_SOURCE_ID
                if case_id == CASE_ID
                else uuid5(case_id, "public-source")
            ),
            "source_mode": StartupResearchSourceMode.LIVE,
            "source_hash": "sha256:" + "c" * 64,
            "source_url": "https://example.com/public-market",
            "source_label": "Public market source",
            "as_of": date(2026, 8, 10),
            "retrieved_at": AS_OF,
            "query": "public diligence market",
            "provenance": "live_public_research",
            "confidence": Decimal("0.74"),
            "status": StartupResearchSourceStatus.SOURCE_FACT,
        }
    )
    return StartupMarketResearchSnapshot.build(
        case_id=case_id,
        as_of=AS_OF,
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=uuid5(case_id, "startup-improvement-research"),
        competitors=(),
        sources=(source,),
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=("live_inference", "live_public_research"),
        data_revision=1,
    )


def _gtm(profile: StartupProfile, market: StartupMarketResearchSnapshot) -> StartupGtmSnapshot:
    return StartupGtmSnapshot.build(
        case_id=profile.case_id,
        profile_id=profile.profile_id,
        product_validation_snapshot_id=uuid5(profile.case_id, "product-validation"),
        market_research_snapshot_id=market.snapshot_id,
        data_revision=profile.data_revision,
        status=StartupGtmStatus.PARTIAL,
        dimensions=tuple(
            StartupGtmDimension(
                name=name,
                status=StartupGtmDimensionStatus.MISSING,
                reason_code="evidence_missing",
                gap_code=f"{name.value}_missing",
            )
            for name in StartupGtmDimensionName
        ),
        launch_plan=tuple(StartupGtmLaunchPhase(horizon=horizon) for horizon in StartupGtmHorizon),
        built_at=AS_OF,
    )


def _calculation(*, case_id: UUID) -> Calculation:
    return Calculation(
        id=CALCULATION_ID if case_id == CASE_ID else uuid5(case_id, "calculation"),
        case_id=case_id,
        metric_name="gross_margin",
        formula_version="startup-gross-margin@1",
        input_fact_ids=(),
        value=Decimal("0.72"),
        unit="ratio",
        period="2026-Q2",
        calculated_at=AS_OF,
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )


def _contradiction(*, case_id: UUID) -> Contradiction:
    return Contradiction(
        id=CONTRADICTION_ID if case_id == CASE_ID else uuid5(case_id, "contradiction"),
        case_id=case_id,
        conflict_type="metric_vs_claim",
        explanation="Canonical contradiction",
        severity=FindingSeverity.HIGH,
        status=ContradictionStatus.OPEN,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        detected_at=AS_OF,
    )


def _report(
    *,
    case_id: UUID,
    data_revision: int = 1,
    hash_seed: str = "base",
) -> ReportSnapshot:
    report_hash = "sha256:" + uuid5(case_id, hash_seed).hex * 2
    return ReportSnapshot(
        id=uuid5(case_id, f"report:{hash_seed}:{data_revision}"),
        case_id=case_id,
        report_hash=report_hash,
        case_snapshot_hash="sha256:" + "d" * 64,
        source_hashes={},
        as_of=AS_OF,
        graph_version="startup@1",
        prompt_versions={"report": "startup-report@1"},
        formula_versions={"gross_margin": "startup-gross-margin@1"},
        model_versions={"analysis": "offline"},
        sections={"summary": {"status": "PARTIAL"}},
        data_revision=data_revision,
        json_artifact_ref="sha256:" + "e" * 64,
        content_hashes={"json": "sha256:" + "e" * 64},
        reproducibility=ReproducibilityManifest(
            code_commit="test",
            build_id="test",
            dependency_lock_hash="sha256:" + "f" * 64,
            python_version="3.13",
            package_versions={},
            provider_model_id="offline",
            model_alias_snapshot="offline",
            reasoning_parameters={},
            adapter_versions={},
            parser_versions={},
            redaction_policy_version="test",
            locale="ru-KZ",
            timezone="UTC",
            deterministic_seeds={},
            configuration_hash="sha256:" + "1" * 64,
        ),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
        version=99,
    )


def _proposal_id(
    proposals: tuple[StartupImprovementProposal, ...],
    target: StartupImprovementTargetArea,
) -> UUID:
    return next(proposal.proposal_id for proposal in proposals if proposal.target_area is target)

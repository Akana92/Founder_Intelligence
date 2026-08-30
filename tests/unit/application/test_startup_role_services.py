from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from due_diligence_agent.application.services.startup_document_intelligence_service import (
    StartupDocumentIntelligenceService,
)
from due_diligence_agent.application.services.startup_product_validation_service import (
    StartupProductValidationService,
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
    StartupDocumentIntelligenceStatus,
    StartupProductValidationDimensionName,
    StartupProductValidationDimensionStatus,
)


_BUILT_AT = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)


def test_document_intelligence_is_deterministic_bounded_and_reference_only() -> None:
    service = StartupDocumentIntelligenceService()

    snapshot_a = service.analyze(
        case_id=_uuid("case:document-intelligence"),
        data_revision=3,
        inventory_id="inventory-003",
        source_document_ids=("doc-0002", "doc-0001"),
        artifact_ids=("artifact-b", "artifact-a"),
        parsed_artifact_ids=("artifact-a",),
        evidence_fact_ids=(str(_uuid("fact:b")), str(_uuid("fact:a"))),
        startup_claim_ids=(str(_uuid("claim:b")), str(_uuid("claim:a"))),
        quarantine_reason_codes=("archive.entry_unsafe",),
    )
    snapshot_b = service.analyze(
        case_id=_uuid("case:document-intelligence"),
        data_revision=3,
        inventory_id="inventory-003",
        source_document_ids=("doc-0001", "doc-0002"),
        artifact_ids=("artifact-a", "artifact-b"),
        parsed_artifact_ids=("artifact-a",),
        evidence_fact_ids=(str(_uuid("fact:a")), str(_uuid("fact:b"))),
        startup_claim_ids=(str(_uuid("claim:a")), str(_uuid("claim:b"))),
        quarantine_reason_codes=("archive.entry_unsafe",),
    )

    assert snapshot_a.snapshot_id == snapshot_b.snapshot_id
    assert snapshot_a.snapshot_hash == snapshot_b.snapshot_hash
    assert snapshot_a.status is StartupDocumentIntelligenceStatus.PARTIAL
    assert snapshot_a.gap_codes == (
        "document_intelligence.parse_coverage_partial",
        "document_intelligence.quarantine_present",
    )
    assert snapshot_a.source_document_ids == ("doc-0001", "doc-0002")
    assert snapshot_a.accepted_artifact_count == 2
    assert snapshot_a.parsed_artifact_count == 1
    dumped = snapshot_a.model_dump_json()
    assert "private_name" not in dumped
    assert "content_sha256" not in dumped


def test_document_intelligence_rejects_raw_paths_in_reference_fields() -> None:
    with pytest.raises(ValueError, match="safe reference"):
        StartupDocumentIntelligenceService().analyze(
            case_id=_uuid("case:document-intelligence-unsafe"),
            data_revision=1,
            inventory_id=r"C:\private\pitch.pdf",
            source_document_ids=("doc-0001",),
            artifact_ids=("artifact-a",),
            parsed_artifact_ids=("artifact-a",),
            evidence_fact_ids=(),
            startup_claim_ids=(),
            quarantine_reason_codes=(),
        )


def test_document_intelligence_accepts_large_bounded_evidence_ref_sets() -> None:
    evidence_fact_ids = tuple(str(_uuid(f"fact:large:{index}")) for index in range(700))

    snapshot = StartupDocumentIntelligenceService().analyze(
        case_id=_uuid("case:document-intelligence-large"),
        data_revision=1,
        inventory_id="inventory-large",
        source_document_ids=("doc-0001",),
        artifact_ids=("artifact-large",),
        parsed_artifact_ids=("artifact-large",),
        evidence_fact_ids=evidence_fact_ids,
        startup_claim_ids=(str(_uuid("claim:large")),),
        quarantine_reason_codes=(),
    )

    assert snapshot.evidence_fact_count == 700
    assert set(snapshot.evidence_fact_ids) == set(evidence_fact_ids)
    assert snapshot.status is StartupDocumentIntelligenceStatus.COMPLETE


def test_product_validation_maps_evidence_and_contradictions_without_scores() -> None:
    problem = _field(StartupProfileFieldName.PROBLEM, ("manual reconciliation",))
    icp = _field(
        StartupProfileFieldName.ICP,
        ("mid-market finance teams", "enterprise controllers"),
        status=StartupProfileFieldStatus.CONTRADICTION,
        reason_code="profile.contradiction:icp",
        contradiction_ids=(_uuid("contradiction:icp"),),
    )
    pricing = _field(
        StartupProfileFieldName.PRICING_REVENUE_MODEL,
        ("annual subscription",),
    )
    weaknesses = _field(
        StartupProfileFieldName.WEAKNESSES,
        ("migration effort",),
    )
    profile = _profile(
        {
            StartupProfileFieldName.PROBLEM: problem,
            StartupProfileFieldName.ICP: icp,
            StartupProfileFieldName.PRICING_REVENUE_MODEL: pricing,
            StartupProfileFieldName.WEAKNESSES: weaknesses,
        }
    )
    allowed = tuple(
        str(ref.evidence_id)
        for field in (problem, icp, pricing, weaknesses)
        for ref in field.evidence_refs
    )

    snapshot = StartupProductValidationService().evaluate(
        profile,
        evidence_fact_ids=allowed,
        startup_claim_ids=(str(_uuid("claim:verified")), str(_uuid("claim:contradicted"))),
        claim_status_by_id={
            str(_uuid("claim:verified")): "verified",
            str(_uuid("claim:contradicted")): "contradicted",
        },
        contradiction_ids=(str(_uuid("contradiction:icp")),),
    )

    by_name = {dimension.name: dimension for dimension in snapshot.dimensions}
    assert tuple(by_name) == tuple(StartupProductValidationDimensionName)
    assert by_name[StartupProductValidationDimensionName.PROBLEM_CLARITY].status is (
        StartupProductValidationDimensionStatus.SUPPORTED
    )
    assert by_name[StartupProductValidationDimensionName.ICP_PRECISION].status is (
        StartupProductValidationDimensionStatus.CONTRADICTED
    )
    assert by_name[StartupProductValidationDimensionName.WILLINGNESS_TO_PAY].status is (
        StartupProductValidationDimensionStatus.PARTIAL
    )
    assert by_name[StartupProductValidationDimensionName.VALIDATION_EVIDENCE].status is (
        StartupProductValidationDimensionStatus.CONTRADICTED
    )
    dumped = snapshot.model_dump_json()
    assert "manual reconciliation" not in dumped
    assert "annual subscription" not in dumped
    assert "score" not in dumped


def test_product_validation_downgrades_excluded_profile_evidence_deterministically() -> None:
    problem = _field(StartupProfileFieldName.PROBLEM, ("manual reconciliation",))
    icp = _field(
        StartupProfileFieldName.ICP,
        ("mid-market finance teams", "enterprise controllers"),
        status=StartupProfileFieldStatus.CONTRADICTION,
        reason_code="profile.contradiction:icp",
        contradiction_ids=(_uuid("contradiction:icp:excluded"),),
    )
    profile = _profile(
        {
            StartupProfileFieldName.PROBLEM: problem,
            StartupProfileFieldName.ICP: icp,
        }
    )
    fact_ids = tuple(str(ref.evidence_id) for ref in problem.evidence_refs)
    service = StartupProductValidationService()

    before = service.evaluate(
        profile,
        evidence_fact_ids=fact_ids,
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )
    after = service.evaluate(
        profile,
        evidence_fact_ids=(),
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )

    before_problem = next(
        item
        for item in before.dimensions
        if item.name is StartupProductValidationDimensionName.PROBLEM_CLARITY
    )
    after_problem = next(
        item
        for item in after.dimensions
        if item.name is StartupProductValidationDimensionName.PROBLEM_CLARITY
    )
    assert before_problem.status is StartupProductValidationDimensionStatus.SUPPORTED
    assert after_problem.status is StartupProductValidationDimensionStatus.MISSING
    assert after_problem.gap_code == "product_validation.missing:problem_clarity"
    after_icp = next(
        item
        for item in after.dimensions
        if item.name is StartupProductValidationDimensionName.ICP_PRECISION
    )
    assert after_icp.status is StartupProductValidationDimensionStatus.MISSING
    assert after_icp.contradiction_ids == ()
    assert before.snapshot_hash != after.snapshot_hash


def test_product_validation_does_not_reintroduce_excluded_contradiction_ids() -> None:
    excluded_contradiction_id = _uuid("contradiction:icp:excluded-with-evidence")
    icp = _field(
        StartupProfileFieldName.ICP,
        ("mid-market finance teams", "enterprise controllers"),
        status=StartupProfileFieldStatus.CONTRADICTION,
        reason_code="profile.contradiction:icp",
        contradiction_ids=(excluded_contradiction_id,),
    )
    profile = _profile({StartupProfileFieldName.ICP: icp})
    allowed_evidence_ids = tuple(str(ref.evidence_id) for ref in icp.evidence_refs)

    snapshot = StartupProductValidationService().evaluate(
        profile,
        evidence_fact_ids=allowed_evidence_ids,
        startup_claim_ids=(),
        claim_status_by_id={},
        contradiction_ids=(),
    )

    dimension = next(
        item
        for item in snapshot.dimensions
        if item.name is StartupProductValidationDimensionName.ICP_PRECISION
    )
    assert dimension.status is StartupProductValidationDimensionStatus.CONTRADICTED
    assert dimension.contradiction_ids == ()


def _profile(
    overrides: dict[StartupProfileFieldName, StartupProfileField],
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
        case_id=_uuid("case:product-validation"),
        schema_version="startup_profile@1",
        profile_version="enriched@1",
        extractor_version="test@1",
        analysis_stage=StartupProfileAnalysisStage.ENRICHED,
        parent_profile_id=_uuid("profile:primary"),
        data_revision=4,
        source_hashes={"upload": "sha256:" + ("a" * 64)},
        parse_outcomes={"upload": "parsed"},
        fields=fields,
        gap_codes=(),
        contradiction_ids=(),
        case_revision_at=_BUILT_AT,
    )


def _field(
    name: StartupProfileFieldName,
    values: tuple[str, ...],
    *,
    status: StartupProfileFieldStatus = StartupProfileFieldStatus.SOURCE_FACT,
    reason_code: str | None = None,
    contradiction_ids: tuple[UUID, ...] = (),
) -> StartupProfileField:
    refs = (
        _evidence_ref(name, "a"),
        _evidence_ref(name, "b"),
    )
    return StartupProfileField(
        name=name,
        status=status,
        values=values,
        confidence=Decimal("0.82"),
        evidence_refs=refs,
        reason_code=reason_code,
        contradiction_ids=contradiction_ids,
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


def _uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)

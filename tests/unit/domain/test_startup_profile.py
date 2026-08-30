from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)


def test_startup_profile_field_requires_the_expected_invariants() -> None:
    evidence_ref = _make_evidence_ref()

    with pytest.raises(ValidationError, match="evidence refs"):
        StartupProfileField(
            name=StartupProfileFieldName.STARTUP_NAME,
            status=StartupProfileFieldStatus.SOURCE_FACT,
            values=("Acme",),
            confidence=Decimal("0.9"),
        )

    with pytest.raises(ValidationError, match="dependency refs"):
        StartupProfileField(
            name=StartupProfileFieldName.PROBLEM,
            status=StartupProfileFieldStatus.INFERENCE,
            values=("manual reconciliation",),
            confidence=Decimal("0.8"),
            evidence_refs=(evidence_ref,),
            reason_code="derived",
        )

    with pytest.raises(ValidationError, match="must not invent values"):
        StartupProfileField(
            name=StartupProfileFieldName.SOLUTION,
            status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
            values=("should not appear",),
            confidence=Decimal("0.2"),
        )

    with pytest.raises(ValidationError, match="competing refs"):
        StartupProfileField(
            name=StartupProfileFieldName.STAGE,
            status=StartupProfileFieldStatus.CONTRADICTION,
            values=("pre-seed", "seed"),
            confidence=Decimal("0.4"),
            evidence_refs=(evidence_ref,),
            reason_code="conflict",
        )


def test_startup_profile_evidence_ref_rejects_raw_locator_leaks() -> None:
    base = _make_evidence_ref().model_dump()

    with pytest.raises(ValidationError, match="extra_forbidden"):
        StartupProfileEvidenceRef.model_validate({**base, "locator_value": "secret"})

    with pytest.raises(ValidationError, match="extra_forbidden"):
        StartupProfileEvidenceRef.model_validate({**base, "locator_path": "secret/path"})

    with pytest.raises(ValidationError, match="safe reference"):
        StartupProfileEvidenceRef(
            evidence_id=uuid4(),
            fragment_id=uuid4(),
            artifact_id=uuid4(),
            artifact_hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            locator_hash="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            page=1,
            table="Revenue/Table",
            cell="a1@example.com",
            field_name=StartupProfileFieldName.STARTUP_NAME,
            confidence=Decimal("0.91"),
        )


def test_startup_profile_requires_all_fields_and_derived_identity_is_stable() -> None:
    case_id = uuid4()
    case_revision_at = datetime(2026, 8, 13, 10, 30, tzinfo=UTC)
    shared_refs: dict[StartupProfileFieldName, tuple[StartupProfileEvidenceRef, ...]] = {
        name: (_make_evidence_ref(field_name=name),)
        for name in StartupProfileFieldName
        if name is not StartupProfileFieldName.COMPETITORS_MENTIONED
    }
    competitor_refs: tuple[StartupProfileEvidenceRef, StartupProfileEvidenceRef] = (
        _make_evidence_ref(field_name=StartupProfileFieldName.COMPETITORS_MENTIONED),
        _make_evidence_ref(field_name=StartupProfileFieldName.COMPETITORS_MENTIONED),
    )

    profile_a = StartupProfile.build(
        case_id=case_id,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="extractor@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=3,
        source_hashes={
            "artifact-b": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "artifact-a": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        },
        parse_outcomes={
            "artifact-b": "parsed",
            "artifact-a": "partial",
        },
        fields=_make_profile_fields(order="forward", shared_refs=shared_refs, competitor_refs=competitor_refs),
        gap_codes=("market_size", "team"),
        contradiction_ids=(uuid4(), uuid4()),
        case_revision_at=case_revision_at,
    )

    profile_b = StartupProfile.build(
        case_id=case_id,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="extractor@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=3,
        source_hashes={
            "artifact-a": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "artifact-b": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        },
        parse_outcomes={
            "artifact-a": "partial",
            "artifact-b": "parsed",
        },
        fields=_make_profile_fields(order="reverse", shared_refs=shared_refs, competitor_refs=competitor_refs),
        gap_codes=("team", "market_size"),
        contradiction_ids=tuple(reversed(profile_a.contradiction_ids)),
        case_revision_at=case_revision_at,
    )

    assert profile_a.profile_id == profile_b.profile_id
    assert profile_a.profile_hash == profile_b.profile_hash
    assert profile_a.built_at == case_revision_at
    assert profile_a.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    assert profile_a.parent_profile_id is None
    assert set(profile_a.fields) == {field.value for field in StartupProfileFieldName}


def test_startup_profile_enforces_stage_lineage() -> None:
    with pytest.raises(ValidationError, match="primary profiles must not reference a parent profile"):
        StartupProfile.build(
            case_id=uuid4(),
            schema_version="startup-profile-schema@1",
            profile_version="startup-profile@1",
            extractor_version="extractor@1",
            analysis_stage=StartupProfileAnalysisStage.PRIMARY,
            parent_profile_id=uuid4(),
            data_revision=2,
            source_hashes={
                "artifact-a": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
            parse_outcomes={"artifact-a": "parsed"},
            fields=_make_profile_fields(),
            gap_codes=(),
            contradiction_ids=(),
            case_revision_at=datetime(2026, 8, 13, 10, 32, tzinfo=UTC),
        )

    with pytest.raises(ValidationError, match="enriched profiles require a parent profile"):
        StartupProfile.build(
            case_id=uuid4(),
            schema_version="startup-profile-schema@1",
            profile_version="startup-profile@1",
            extractor_version="extractor@1",
            analysis_stage=StartupProfileAnalysisStage.ENRICHED,
            parent_profile_id=None,
            data_revision=2,
            source_hashes={
                "artifact-a": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
            parse_outcomes={"artifact-a": "parsed"},
            fields=_make_profile_fields(),
            gap_codes=(),
            contradiction_ids=(),
            case_revision_at=datetime(2026, 8, 13, 10, 32, tzinfo=UTC),
        )


def test_startup_profile_rejects_missing_required_fields() -> None:
    fields = _make_profile_fields()
    fields.pop(StartupProfileFieldName.WEAKNESSES.value)

    with pytest.raises(ValidationError, match="required fields"):
        StartupProfile.build(
            case_id=uuid4(),
            schema_version="startup-profile-schema@1",
            profile_version="startup-profile@1",
            extractor_version="extractor@1",
            analysis_stage=StartupProfileAnalysisStage.ENRICHED,
            parent_profile_id=uuid4(),
            data_revision=2,
            source_hashes={
                "artifact-a": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
            parse_outcomes={"artifact-a": "parsed"},
            fields=fields,
            gap_codes=(),
            contradiction_ids=(),
            case_revision_at=datetime(2026, 8, 13, 10, 31, tzinfo=UTC),
        )


def test_startup_profile_field_normalizes_text_values() -> None:
    field = StartupProfileField(
        name=StartupProfileFieldName.ONE_LINE_DESCRIPTION,
        status=StartupProfileFieldStatus.SOURCE_FACT,
        values=("  AI for SMB lending  ", " AI for SMB lending "),
        confidence=Decimal("0.95"),
        evidence_refs=(_make_evidence_ref(),),
    )

    assert field.values == ("AI for SMB lending",)


def _make_profile_fields(
    *,
    order: str = "forward",
    shared_refs: dict[StartupProfileFieldName, tuple[StartupProfileEvidenceRef, ...]] | None = None,
    competitor_refs: tuple[StartupProfileEvidenceRef, StartupProfileEvidenceRef] | None = None,
) -> dict[str, StartupProfileField]:
    names = [field for field in StartupProfileFieldName]
    if order == "reverse":
        names = list(reversed(names))

    return {
        name.value: _make_profile_field(
            name=name,
            order=order,
            shared_refs=shared_refs,
            competitor_refs=competitor_refs,
        )
        for name in names
    }


def _make_profile_field(
    *,
    name: StartupProfileFieldName,
    order: str = "forward",
    shared_refs: dict[StartupProfileFieldName, tuple[StartupProfileEvidenceRef, ...]] | None = None,
    competitor_refs: tuple[StartupProfileEvidenceRef, StartupProfileEvidenceRef] | None = None,
) -> StartupProfileField:
    values: tuple[str, ...]
    evidence_refs: tuple[StartupProfileEvidenceRef, ...]
    if name is StartupProfileFieldName.COMPETITORS_MENTIONED:
        values = ("TriageAI", "ModelForge")
        if competitor_refs is None:
            competitor_refs = (
                _make_evidence_ref(field_name=name),
                _make_evidence_ref(field_name=name),
            )
        evidence_refs = competitor_refs
        if order == "reverse":
            values = tuple(reversed(values))
            evidence_refs = tuple(reversed(evidence_refs))
    else:
        values = (f"{name.value.replace('_', ' ')}",)
        if shared_refs is not None and name in shared_refs:
            evidence_refs = shared_refs[name]
        else:
            evidence_refs = (_make_evidence_ref(field_name=name),)

    return StartupProfileField(
        name=name,
        status=StartupProfileFieldStatus.SOURCE_FACT,
        values=values,
        confidence=Decimal("0.9"),
        evidence_refs=evidence_refs,
    )


def _make_evidence_ref(*, field_name: StartupProfileFieldName | None = None) -> StartupProfileEvidenceRef:
    return StartupProfileEvidenceRef(
        evidence_id=uuid4(),
        fragment_id=uuid4(),
        artifact_id=uuid4(),
        artifact_hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        locator_hash="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        page=1,
        table="summary",
        cell="A1",
        field_name=field_name,
        confidence=Decimal("0.91"),
    )

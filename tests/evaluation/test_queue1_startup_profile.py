from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.adapters.local_storage.repositories import (
    LocalArtifactRepository,
    LocalCaseRepository,
    LocalContradictionRepository,
    LocalEvidenceRepository,
    LocalParsedStartupArtifactRepository,
    LocalStartupClaimRepository,
    LocalStartupProfileRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.adapters.startup.deterministic_profile_extractor import (
    DeterministicStartupProfileExtractor,
)
from due_diligence_agent.application.services.startup_profile_service import StartupProfileService
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    ArtifactParsingStatus,
    CaseStatus,
    ContradictionStatus,
    FindingSeverity,
    SensitivityClass,
)
from due_diligence_agent.domain.documents.models import ParsedDocument
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.documents.tabular import SpreadsheetParseResult
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.ports.startup_profile_extraction import StartupProfileBoundedFragment
from due_diligence_agent.ports.startup_profile_extraction import (
    StartupProfileExtractionRequest,
    StartupProfileExtractionResponse,
)


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "startup_profile_v1"
EXPECTED_FORMATS = {"pdf", "docx", "png", "jpeg", "csv", "xlsx", "safe_zip"}


def test_queue1_fixture_manifest_freezes_the_required_synthetic_matrix() -> None:
    manifest = _load_json("manifest.json")

    assert manifest["schema"] == "startup_profile_fixture_manifest.v1"
    assert manifest["network_policy"] == "no_external_network"
    assert manifest["fixture_layer"] == "normalized_synthetic_inputs"
    assert set(manifest["active_format_matrix"]) == EXPECTED_FORMATS
    assert {scenario["key"] for scenario in manifest["scenarios"]} == {
        "normal_mixed_pitch",
        "spreadsheet_heavy_missing_narrative",
        "contradictory_arr",
        "safe_mixed_zip",
        "damaged_unsupported_sibling",
        "privacy_sentinel",
    }
    for document in manifest["documents"]:
        fixture_path = FIXTURE_ROOT / document["path"]
        assert fixture_path.is_file()
        assert _sha256(fixture_path.read_bytes()) == document["sha256"]


def test_queue1_profile_matches_frozen_snapshot_and_is_restart_equivalent(tmp_path: Path) -> None:
    database_path = tmp_path / "queue1.sqlite3"
    first, external_calls = _build_profile(database_path, seed=True)
    restarted, restarted_external_calls = _build_profile(database_path, seed=False)
    expected = _load_json("expected_profile.json")

    assert _profile_projection(first) == expected
    assert _profile_projection(restarted) == expected
    assert first.profile_id == restarted.profile_id
    assert first.profile_hash == restarted.profile_hash
    assert first.profile_hash == first.derived_profile_hash()
    assert external_calls == restarted_external_calls == 0


def test_queue1_profile_retains_competing_arr_and_partial_parse_without_private_material(
    tmp_path: Path,
) -> None:
    manifest = _load_json("manifest.json")
    profile, _external_calls = _build_profile(tmp_path / "queue1.sqlite3", seed=True)
    traction = profile.fields[StartupProfileFieldName.TRACTION.value]
    privacy_source = next(
        item for item in manifest["documents"] if item["role"] == "privacy_sentinel"
    )
    privacy_artifact_id = UUID(privacy_source["artifact_id"])
    privacy_fragment = next(
        (
            fragment
            for fragment in _fragments(manifest, _artifacts(manifest))
            if fragment.artifact_id == privacy_artifact_id
        ),
        None,
    )
    private_sentinels = {
        line.split("=", 1)[1].strip()
        for line in (FIXTURE_ROOT / "documents" / "privacy_sentinel.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if "=" in line
    }
    serialized = profile.model_dump_json()

    assert traction.values == ("ARR: 120000 USD 2026", "ARR: 150000 USD 2026")
    assert len(traction.evidence_refs) == 2
    assert profile.contradiction_ids == (UUID("90000000-0000-4000-8000-000000000001"),)
    assert "partial" in profile.parse_outcomes.values()
    assert "damaged" in profile.parse_outcomes.values()
    assert privacy_fragment is not None
    assert all(sentinel not in privacy_fragment.text for sentinel in private_sentinels)
    assert all(
        f"[REDACTED:{label}:" in privacy_fragment.text
        for label in ("email", "token", "windows_path", "unix_path")
    )
    assert "[REDACTED:" in privacy_fragment.text
    assert private_sentinels
    assert all(sentinel not in serialized for sentinel in private_sentinels)
    assert set(field.status for field in profile.fields.values()) <= set(StartupProfileFieldStatus)
    assert set(profile.fields) == {field.value for field in StartupProfileFieldName}


def test_queue1_spreadsheet_only_fixture_keeps_numeric_facts_and_marks_narrative_gaps(
    tmp_path: Path,
) -> None:
    profile = _build_spreadsheet_only_profile(tmp_path / "spreadsheet-only.sqlite3")
    traction = profile.fields[StartupProfileFieldName.TRACTION.value]

    assert set(traction.values) == {
        "Gross Margin: 72 percent 2026-H1",
        "MRR: 12000 USD 2026-07",
    }
    assert traction.status is StartupProfileFieldStatus.SOURCE_FACT
    assert profile.fields[StartupProfileFieldName.PROBLEM.value].status is (
        StartupProfileFieldStatus.INSUFFICIENT_DATA
    )
    assert profile.fields[StartupProfileFieldName.SOLUTION.value].status is (
        StartupProfileFieldStatus.INSUFFICIENT_DATA
    )


class _FixtureFragmentInventory:
    def __init__(self, fragments: tuple[StartupProfileBoundedFragment, ...]) -> None:
        self._fragments = fragments

    def list_for_case_revision(
        self,
        case_id: UUID,
        data_revision: int,
    ) -> tuple[StartupProfileBoundedFragment, ...]:
        assert case_id == UUID("10000000-0000-4000-8000-000000000001")
        assert data_revision == 1
        return self._fragments


class _ForbiddenExternalExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse:
        del request, disclosure_scope
        self.calls += 1
        raise AssertionError("Queue 1 primary fixture must not call an external provider")


def _build_profile(database_path: Path, *, seed: bool) -> tuple[StartupProfile, int]:
    db = SQLiteDatabase(database_path)
    manifest = _load_json("manifest.json")
    case = _case(manifest)
    artifacts = _artifacts(manifest)
    parsed = _parse_results(manifest, artifacts)
    facts = _spreadsheet_facts(manifest, artifacts)
    contradiction = _contradiction(case.case_id, facts)

    case_repository = LocalCaseRepository(db)
    artifact_repository = LocalArtifactRepository(db)
    parsed_repository = LocalParsedStartupArtifactRepository(db)
    evidence_repository = LocalEvidenceRepository(db)
    contradiction_repository = LocalContradictionRepository(db)
    profile_repository = LocalStartupProfileRepository(db)
    if seed:
        case_repository.add(case)
        for artifact in artifacts:
            artifact_repository.add(artifact)
        for item in parsed:
            parsed_repository.add(item)
        for fact in facts:
            evidence_repository.add(fact)
        contradiction_repository.add(contradiction)

    external = _ForbiddenExternalExtractor()
    service = StartupProfileService(
        case_repository=case_repository,
        artifact_repository=artifact_repository,
        parsed_artifact_repository=parsed_repository,
        evidence_repository=evidence_repository,
        startup_claim_repository=LocalStartupClaimRepository(db),
        contradiction_repository=contradiction_repository,
        startup_profile_repository=profile_repository,
        deterministic_extractor=DeterministicStartupProfileExtractor(),
        external_extractor=external,
        fragment_inventory=_FixtureFragmentInventory(_fragments(manifest, artifacts)),
    )
    profile = service.build_primary(case.case_id)
    db.close()

    reopened = SQLiteDatabase(database_path)
    restored = LocalStartupProfileRepository(reopened).get(profile.profile_id)
    reopened.close()
    assert restored == profile
    return profile, external.calls


def _build_spreadsheet_only_profile(database_path: Path) -> StartupProfile:
    db = SQLiteDatabase(database_path)
    manifest = _load_json("manifest.json")
    case = _case(manifest)
    source = next(
        item for item in manifest["documents"] if item["role"] == "spreadsheet_only"
    )
    artifact = next(
        item for item in _artifacts(manifest) if str(item.id) == source["artifact_id"]
    )
    parsed = next(
        item
        for item in _parse_results(manifest, (artifact,))
        if item.artifact_id == artifact.id
    )
    facts = _facts_from_source(
        source,
        artifact,
        id_start=10,
        locator_stem="spreadsheet-only",
    )

    case_repository = LocalCaseRepository(db)
    case_repository.add(case)
    LocalArtifactRepository(db).add(artifact)
    LocalParsedStartupArtifactRepository(db).add(parsed)
    evidence_repository = LocalEvidenceRepository(db)
    for fact in facts:
        evidence_repository.add(fact)
    external = _ForbiddenExternalExtractor()
    profile = StartupProfileService(
        case_repository=case_repository,
        artifact_repository=LocalArtifactRepository(db),
        parsed_artifact_repository=LocalParsedStartupArtifactRepository(db),
        evidence_repository=evidence_repository,
        startup_claim_repository=LocalStartupClaimRepository(db),
        contradiction_repository=LocalContradictionRepository(db),
        startup_profile_repository=LocalStartupProfileRepository(db),
        deterministic_extractor=DeterministicStartupProfileExtractor(),
        external_extractor=external,
        fragment_inventory=_FixtureFragmentInventory(()),
    ).build_primary(case.case_id)
    db.close()
    assert external.calls == 0
    return profile


def _case(manifest: dict[str, Any]) -> DueDiligenceCase:
    instant = datetime.fromisoformat(manifest["case_revision_at"].replace("Z", "+00:00"))
    assert instant.tzinfo == UTC
    return DueDiligenceCase(
        case_id=UUID(manifest["case_id"]),
        mode=AnalysisMode.STARTUP,
        entity_name="QueueOne Synthetic",
        entity_identifier="queue-one-synthetic",
        jurisdiction="US",
        scope=("startup",),
        as_of=instant,
        base_currency="USD",
        privacy_policy="startup@1",
        budget_policy="startup@1",
        status=CaseStatus.RUNNING,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=instant,
        updated_at=instant,
        workflow_version="startup@1",
        data_revision=1,
    )


def _artifacts(manifest: dict[str, Any]) -> tuple[Artifact, ...]:
    instant = datetime.fromisoformat(manifest["case_revision_at"].replace("Z", "+00:00"))
    return tuple(
        Artifact(
            id=UUID(item["artifact_id"]),
            case_id=UUID(manifest["case_id"]),
            content_hash=item["sha256"],
            mime_type=item["mime_type"],
            source="startup_upload",
            retrieved_at=instant,
            source_snapshot_hash=item["sha256"],
            parsing_status=(
                ArtifactParsingStatus.PARTIAL
                if item["parse_status"] == "partial"
                else ArtifactParsingStatus.FAILED
                if item["parse_status"] == "damaged"
                else ArtifactParsingStatus.PARSED
            ),
            sensitivity=SensitivityClass.PUBLIC,
        )
        for item in manifest["documents"]
    )


def _parse_results(
    manifest: dict[str, Any], artifacts: tuple[Artifact, ...]
) -> tuple[ParsedStartupArtifact, ...]:
    by_id = {str(artifact.id): artifact for artifact in artifacts}
    results: list[ParsedStartupArtifact] = []
    for item in manifest["documents"]:
        if item["artifact_id"] not in by_id:
            continue
        artifact = by_id[item["artifact_id"]]
        status = item["parse_status"]
        if item["format"] in {"csv", "xlsx"}:
            result = SpreadsheetParseResult(
                artifact_id=artifact.id,
                status="parsed" if status == "parsed" else "partial",
            )
            results.append(
                ParsedStartupArtifact.from_spreadsheet(
                    result,
                    case_id=artifact.case_id,
                    detected_mime_type=artifact.mime_type,
                    parser_name="queue1-fixture",
                    parser_version="queue1-fixture@1",
                )
            )
        elif status in {"parsed", "partial"}:
            document = ParsedDocument(
                artifact_id=artifact.id,
                detected_mime_type=artifact.mime_type,
                parser_name="queue1-fixture",
                parser_version="queue1-fixture@1",
                confidence=Decimal("1"),
                status=status,
            )
            results.append(ParsedStartupArtifact.from_document(document, case_id=artifact.case_id))
        else:
            results.append(
                ParsedStartupArtifact.outcome(
                    artifact_id=artifact.id,
                    case_id=artifact.case_id,
                    kind="unsupported",
                    detected_mime_type=artifact.mime_type,
                    parser_name="queue1-fixture",
                    parser_version="queue1-fixture@1",
                    status="damaged",
                    error_code="synthetic_damaged_sibling",
                )
            )
    return tuple(results)


def _spreadsheet_facts(
    manifest: dict[str, Any], artifacts: tuple[Artifact, ...]
) -> tuple[EvidenceFact, ...]:
    facts: list[EvidenceFact] = []
    arr_sources = [item for item in manifest["documents"] if item["role"] == "arr_source"]
    for index, source in enumerate(arr_sources, start=1):
        artifact = next(item for item in artifacts if str(item.id) == source["artifact_id"])
        facts.extend(
            _facts_from_source(
                source,
                artifact,
                id_start=index,
                locator_stem=f"arr-{index}",
            )
        )
    return tuple(facts)


def _facts_from_source(
    source: dict[str, Any],
    artifact: Artifact,
    *,
    id_start: int,
    locator_stem: str,
) -> tuple[EvidenceFact, ...]:
    rows = csv.DictReader(
        io.StringIO((FIXTURE_ROOT / source["path"]).read_text(encoding="utf-8"))
    )
    facts: list[EvidenceFact] = []
    for offset, row in enumerate(rows):
        sequence = id_start + offset
        facts.append(
            EvidenceFact(
                id=UUID(f"80000000-0000-4000-8000-{sequence:012d}"),
                artifact_id=artifact.id,
                name=row["metric"],
                value=Decimal(row["value"]),
                value_type="decimal",
                unit=row["unit"],
                period=row["period"],
                locator=SourceLocator(
                    kind="cell",
                    value=(
                        f"C:\\synthetic-private\\{locator_stem}.csv#B{offset + 2}"
                    ),
                    artifact_id=artifact.id,
                    table="metrics",
                    cell=f"B{offset + 2}",
                ),
                sensitivity=SensitivityClass.PUBLIC,
                confidence=Decimal("0.95"),
            )
        )
    return tuple(facts)


def _contradiction(case_id: UUID, facts: tuple[EvidenceFact, ...]) -> Contradiction:
    instant = datetime(2026, 8, 13, 9, tzinfo=UTC)
    return Contradiction(
        id=UUID("90000000-0000-4000-8000-000000000001"),
        case_id=case_id,
        conflict_type="arr_value_conflict",
        fact_ids=tuple(fact.id for fact in facts),
        explanation="Synthetic ARR sources disagree.",
        severity=FindingSeverity.HIGH,
        status=ContradictionStatus.OPEN,
        recommended_resolution="request_audited_arr_schedule",
        sensitivity=SensitivityClass.PUBLIC,
        detected_at=instant,
    )


def _fragments(
    manifest: dict[str, Any], artifacts: tuple[Artifact, ...]
) -> tuple[StartupProfileBoundedFragment, ...]:
    normal_item = next(item for item in manifest["documents"] if item["role"] == "normal_pitch")
    normal_artifact = next(item for item in artifacts if str(item.id) == normal_item["artifact_id"])
    text = (FIXTURE_ROOT / normal_item["path"]).read_text(encoding="utf-8")
    privacy_item = next(
        item for item in manifest["documents"] if item["role"] == "privacy_sentinel"
    )
    privacy_artifact = next(
        item for item in artifacts if str(item.id) == privacy_item["artifact_id"]
    )
    privacy_text = _redacted_privacy_fragment_text(privacy_item)
    return (
        StartupProfileBoundedFragment(
            fragment_id=UUID("70000000-0000-4000-8000-000000000001"),
            artifact_id=normal_artifact.id,
            text=text,
            text_hash=f"sha256:{_sha256(text.encode('utf-8'))}",
            artifact_hash=f"sha256:{normal_artifact.source_snapshot_hash}",
            locator_hash=f"sha256:{'7' * 64}",
            sensitivity=SensitivityClass.PUBLIC,
            redacted=True,
            minimized=True,
            redaction_policy_version="rules-redactor@1",
        ),
        StartupProfileBoundedFragment(
            fragment_id=UUID("70000000-0000-4000-8000-000000000002"),
            artifact_id=privacy_artifact.id,
            text=privacy_text,
            text_hash=f"sha256:{_sha256(privacy_text.encode('utf-8'))}",
            artifact_hash=f"sha256:{privacy_artifact.source_snapshot_hash}",
            locator_hash=f"sha256:{'8' * 64}",
            sensitivity=SensitivityClass.PUBLIC,
            redacted=True,
            minimized=True,
            redaction_policy_version="rules-redactor@1",
        ),
    )


def _redacted_privacy_fragment_text(source: dict[str, Any]) -> str:
    values = {
        key: value
        for key, value in (
            line.split("=", 1)
            for line in (FIXTURE_ROOT / source["path"])
            .read_text(encoding="utf-8")
            .splitlines()
            if "=" in line
        )
    }
    return "\n".join(
        [
            "Privacy Sentinel: bounded redaction audit",
            *(f"{key}=[REDACTED:{key}:{len(value.strip())}]" for key, value in values.items()),
        ]
    )


def _load_json(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return cast(dict[str, Any], value)


def _profile_projection(profile: StartupProfile) -> dict[str, Any]:
    return {
        "schema": "startup_profile_expected.v1",
        "profile_id": str(profile.profile_id),
        "profile_hash": profile.profile_hash,
        "case_id": str(profile.case_id),
        "analysis_stage": profile.analysis_stage.value,
        "data_revision": profile.data_revision,
        "built_at": profile.built_at.isoformat().replace("+00:00", "Z"),
        "source_hashes": dict(profile.source_hashes),
        "parse_outcomes": dict(profile.parse_outcomes),
        "fields": {
            name: {
                "status": field.status.value,
                "values": list(field.values),
                "evidence_ref_count": len(field.evidence_refs),
            }
            for name, field in profile.fields.items()
        },
        "gap_codes": list(profile.gap_codes),
        "contradiction_ids": [str(item) for item in profile.contradiction_ids],
    }


def _sha256(payload: bytes) -> str:
    return sha256(payload).hexdigest()

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
import os
from pathlib import Path
import sqlite3
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.local_storage.repositories import (
    LocalApprovalRepository,
    LocalArtifactRepository,
    LocalCaseRepository,
    LocalCalculationRepository,
    LocalContradictionRepository,
    LocalEvidenceRepository,
    LocalFindingRepository,
    LocalParsedStartupArtifactRepository,
    LocalReportRepository,
    LocalStartupClaimRepository,
    LocalStartupProfileRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.application.services.case_service import CaseService
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    ArtifactParsingStatus,
    CaseStatus,
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.approvals.models import Approval
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.documents.tabular import SpreadsheetParseResult
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import (
    ClaimCategory,
    ClaimCriticality,
    StartupClaim,
)
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)


def test_artifact_store_is_content_addressed_and_immutable(tmp_path: Path):
    store = LocalArtifactStore(tmp_path)

    first = store.put_bytes(b"same filing", media_type="text/html")
    second = store.put_bytes(b"same filing", media_type="text/html")

    assert first.content_hash == second.content_hash
    assert first.storage_ref == second.storage_ref
    assert Path(first.storage_ref).read_bytes() == b"same filing"


def test_artifact_store_defaults_to_restricted_metadata_and_reads_by_hash(tmp_path: Path):
    store = LocalArtifactStore(tmp_path)

    stored = store.put_bytes(b"restricted filing", media_type="text/html")

    assert stored.artifact_id == UUID("1aac5b83-e7d2-5fdd-945c-9dd2b717f3f5")
    assert stored.source_snapshot_hash == stored.content_hash
    assert stored.sensitivity is SensitivityClass.RESTRICTED
    assert stored.byte_size == len(b"restricted filing")
    assert stored.stored_at.tzinfo == UTC
    assert store.read_bytes(stored.content_hash) == b"restricted filing"


def test_artifact_store_rejects_invalid_hashes_and_traversal(tmp_path: Path):
    store = LocalArtifactStore(tmp_path)
    stored = store.put_bytes(b"filing", media_type="text/plain")

    with pytest.raises(ValueError, match="invalid content_hash"):
        store.read_bytes("../secrets")

    with pytest.raises(ValueError, match="invalid content_hash"):
        store.read_bytes(stored.content_hash.upper())

    target = Path(stored.storage_ref)
    target.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="content hash mismatch"):
        store.read_bytes(stored.content_hash)


def test_artifact_store_failed_publish_does_not_leave_partial_canonical_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = LocalArtifactStore(tmp_path)

    def fail_publish(source: str | bytes | os.PathLike[str], target: str | bytes | os.PathLike[str]) -> None:
        Path(target).write_bytes(b"part")
        raise OSError("simulated interrupted publish")

    monkeypatch.setattr(os, "replace", fail_publish)

    with pytest.raises(OSError, match="simulated interrupted publish"):
        store.put_bytes(b"atomic filing", media_type="text/plain")

    canonical = (
        tmp_path
        / "objects"
        / "92"
        / "929ac2a80e9fd34470ff9d06abb29bb2f10539be1ec7dd88fee0fec46bca55c6"
    )
    assert not canonical.exists()


def test_sqlite_database_creates_required_schema(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")

    tables = set(db.table_names())

    assert {
        "cases",
        "artifacts",
        "evidence_facts",
        "calculations",
        "findings",
        "contradictions",
        "approvals",
        "report_snapshots",
        "startup_parse_results",
        "startup_profiles",
        "workflow_checkpoints",
    }.issubset(tables)


def test_sqlite_database_context_manager_closes_windows_file_handle(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"

    with SQLiteDatabase(db_path) as db:
        assert "cases" in db.table_names()

    db_path.unlink()
    assert not db_path.exists()


def test_case_bound_orphan_inserts_fail_with_foreign_keys(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    orphan_case_id = uuid4()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO artifacts (id, case_id, payload) VALUES (?, ?, ?)",
            (str(uuid4()), str(orphan_case_id), "{}"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO calculations (id, case_id, sort_key, payload) VALUES (?, ?, ?, ?)",
            (str(uuid4()), str(orphan_case_id), "metric", "{}"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO findings (id, case_id, sort_key, payload) VALUES (?, ?, ?, ?)",
            (str(uuid4()), str(orphan_case_id), "risk", "{}"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO contradictions (id, case_id, sort_key, payload) VALUES (?, ?, ?, ?)",
            (str(uuid4()), str(orphan_case_id), "conflict", "{}"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO approvals (id, case_id, sort_key, payload) VALUES (?, ?, ?, ?)",
            (str(uuid4()), str(orphan_case_id), "gate", "{}"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO report_snapshots (id, case_id, created_at, payload) VALUES (?, ?, ?, ?)",
            (str(uuid4()), str(orphan_case_id), datetime(2026, 8, 9, tzinfo=UTC).isoformat(), "{}"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO workflow_checkpoints (id, case_id, node_name, created_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                str(orphan_case_id),
                "node",
                datetime(2026, 8, 9, tzinfo=UTC).isoformat(),
                "{}",
            ),
        )


def test_evidence_fact_orphan_artifact_insert_fails_with_foreign_key(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    LocalCaseRepository(db).add(case)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO evidence_facts (id, artifact_id, case_id, sort_key, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), str(uuid4()), str(case.case_id), "orphan", "{}"),
        )


def test_direct_sql_evidence_rejects_artifact_case_mismatch(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    artifact_case = _make_case()
    evidence_case = _make_case(ticker="MSFT")
    artifact = _make_artifact(artifact_case.case_id)
    LocalCaseRepository(db).add(artifact_case)
    LocalCaseRepository(db).add(evidence_case)
    LocalArtifactRepository(db).add(artifact)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO evidence_facts (id, artifact_id, case_id, sort_key, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), str(artifact.id), str(evidence_case.case_id), "cross-case", "{}"),
        )


def test_repositories_report_missing_parent_as_referential_integrity_violation(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    missing_case_id = uuid4()

    missing_parent_operations = [
        (LocalArtifactRepository(db).add, _make_artifact(missing_case_id)),
        (LocalCalculationRepository(db).add, _make_calculation(missing_case_id)),
        (LocalFindingRepository(db).add, _make_finding(missing_case_id)),
        (LocalContradictionRepository(db).add, _make_contradiction(missing_case_id)),
        (LocalApprovalRepository(db).add, _make_approval(missing_case_id)),
        (LocalReportRepository(db).add_snapshot, _make_report_snapshot(missing_case_id)),
    ]

    for add, model in missing_parent_operations:
        with pytest.raises(ValueError, match="referential_integrity_violation"):
            add(model)


def test_evidence_repository_reports_missing_artifact_before_insert(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    repo = LocalEvidenceRepository(db)

    with pytest.raises(ValueError, match="referential_integrity_violation"):
        repo.add(_make_fact(uuid4()))


def test_evidence_repository_persists_under_artifact_case_not_locator_case(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    artifact_case = _make_case()
    unrelated_case = _make_case(ticker="MSFT")
    artifact = _make_artifact(artifact_case.case_id)
    fact = _make_fact(artifact.id).model_copy(
        update={"locator": SourceLocator(kind="sec_fact", value="revenue", artifact_id=uuid4())}
    )
    LocalCaseRepository(db).add(artifact_case)
    LocalCaseRepository(db).add(unrelated_case)
    LocalArtifactRepository(db).add(artifact)

    LocalEvidenceRepository(db).add(fact)

    assert LocalEvidenceRepository(db).list_for_case(artifact_case.case_id) == [fact]
    assert LocalEvidenceRepository(db).list_for_case(unrelated_case.case_id) == []


def test_startup_claim_repository_round_trips_orders_isolates_and_reopens(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    db = SQLiteDatabase(db_path)
    case = _make_case()
    other_case = _make_case(ticker="MSFT")
    artifact = _make_artifact(case.case_id)
    other_artifact = _make_artifact(other_case.case_id)
    first = _make_startup_claim(case.case_id, artifact.id, normalized_name="arr")
    second = _make_startup_claim(case.case_id, artifact.id, normalized_name="runway")
    other = _make_startup_claim(other_case.case_id, other_artifact.id, normalized_name="ignored")
    repo = LocalStartupClaimRepository(db)
    LocalCaseRepository(db).add(case)
    LocalCaseRepository(db).add(other_case)
    LocalArtifactRepository(db).add(artifact)
    LocalArtifactRepository(db).add(other_artifact)

    repo.add(second)
    repo.add(other)
    repo.add(first)

    reopened = SQLiteDatabase(db_path)
    reopened_repo = LocalStartupClaimRepository(reopened)

    assert reopened_repo.get(first.id) == first
    assert reopened_repo.list_for_case(case.case_id) == [first, second]
    assert reopened_repo.list_for_case(other_case.case_id) == [other]
    assert reopened_repo.get(first.id).normalized_value == Decimal("1200000")


def test_direct_sql_startup_claim_rejects_artifact_case_mismatch(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    artifact_case = _make_case()
    claim_case = _make_case(ticker="MSFT")
    artifact = _make_artifact(artifact_case.case_id)
    LocalCaseRepository(db).add(artifact_case)
    LocalCaseRepository(db).add(claim_case)
    LocalArtifactRepository(db).add(artifact)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO startup_claims (id, case_id, source_artifact_id, sort_key, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), str(claim_case.case_id), str(artifact.id), "cross-case", "{}"),
        )


def test_startup_claim_repository_reports_missing_artifact_before_insert(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    LocalCaseRepository(db).add(case)

    with pytest.raises(ValueError, match="referential_integrity_violation"):
        LocalStartupClaimRepository(db).add(_make_startup_claim(case.case_id, uuid4()))


def test_parsed_startup_artifact_repository_round_trips_idempotently_and_reopens(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    db = SQLiteDatabase(db_path)
    case = _make_case()
    artifact = _make_artifact(case.case_id)
    parsed = _make_parsed_startup_artifact(case.case_id, artifact.id)
    repo = LocalParsedStartupArtifactRepository(db)
    LocalCaseRepository(db).add(case)
    LocalArtifactRepository(db).add(artifact)

    repo.add(parsed)
    repo.add(parsed)

    reopened_repo = LocalParsedStartupArtifactRepository(SQLiteDatabase(db_path))
    assert reopened_repo.get_for_case(case.case_id, parsed.artifact_id) == parsed
    assert reopened_repo.list_for_case(case.case_id) == [parsed]
    with pytest.raises(KeyError, match="parsed_startup_artifact_not_found"):
        reopened_repo.get_for_case(uuid4(), parsed.artifact_id)


def test_parsed_startup_artifact_repository_rejects_conflict_and_missing_parent(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    artifact = _make_artifact(case.case_id)
    parsed = _make_parsed_startup_artifact(case.case_id, artifact.id)
    LocalCaseRepository(db).add(case)
    LocalArtifactRepository(db).add(artifact)
    repo = LocalParsedStartupArtifactRepository(db)

    repo.add(parsed)

    conflicting = ParsedStartupArtifact.outcome(
        artifact_id=parsed.artifact_id,
        case_id=case.case_id,
        kind="unsupported",
        detected_mime_type="application/octet-stream",
        parser_name="none",
        parser_version="1",
        status="unsupported",
        error_code="unsupported_media_type",
    )
    with pytest.raises(ValueError, match="parsed_startup_artifact_conflict"):
        repo.add(conflicting)
    with pytest.raises(ValueError, match="referential_integrity_violation"):
        LocalParsedStartupArtifactRepository(db).add(_make_parsed_startup_artifact(case.case_id, uuid4()))


def test_startup_profile_repository_round_trips_current_revision_and_stage_precedence(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    db = SQLiteDatabase(db_path)
    case = _make_case().model_copy(update={"data_revision": 2})
    old_case = case.model_copy(update={"data_revision": 1})
    artifact = _make_artifact(case.case_id)
    primary_old = _make_startup_profile(old_case, artifact, StartupProfileAnalysisStage.PRIMARY)
    primary = _make_startup_profile(case, artifact, StartupProfileAnalysisStage.PRIMARY)
    enriched = _make_startup_profile(
        case,
        artifact,
        StartupProfileAnalysisStage.ENRICHED,
        parent_profile_id=primary.profile_id,
    )
    repo = LocalStartupProfileRepository(db)
    LocalCaseRepository(db).add(case)

    repo.add(primary_old)
    repo.add(primary)
    repo.add(enriched)
    repo.add(enriched)

    reopened = LocalStartupProfileRepository(SQLiteDatabase(db_path))
    assert reopened.get(enriched.profile_id) == enriched
    assert reopened.get_for_stage(case.case_id, 2, StartupProfileAnalysisStage.PRIMARY) == primary
    assert reopened.get_current(case.case_id) == enriched
    assert reopened.list_for_case(case.case_id) == [primary_old, primary, enriched]


def test_startup_profile_idempotent_replay_releases_sqlite_write_lock(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    first_db = SQLiteDatabase(db_path)
    case = _make_case()
    artifact = _make_artifact(case.case_id)
    profile = _make_startup_profile(case, artifact, StartupProfileAnalysisStage.PRIMARY)
    first_repo = LocalStartupProfileRepository(first_db)
    LocalCaseRepository(first_db).add(case)

    first_repo.add(profile)
    first_repo.add(profile)

    second_db = SQLiteDatabase(db_path)
    updated_case = case.model_copy(update={"data_revision": case.data_revision + 1})
    assert LocalCaseRepository(second_db).advance_data_revision(
        case.case_id,
        expected_revision=case.data_revision,
        updated_case=updated_case,
    ) == updated_case


def test_startup_profile_repository_rejects_conflict_and_missing_case(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    artifact = _make_artifact(case.case_id)
    profile = _make_startup_profile(case, artifact, StartupProfileAnalysisStage.PRIMARY)
    repo = LocalStartupProfileRepository(db)
    LocalCaseRepository(db).add(case)

    repo.add(profile)

    conflicting = profile.model_copy(update={"extractor_version": "other@1"})
    with pytest.raises(ValueError, match="startup_profile_conflict"):
        repo.add(conflicting)
    with pytest.raises(ValueError, match="referential_integrity_violation"):
        LocalStartupProfileRepository(db).add(
            _make_startup_profile(_make_case(), artifact, StartupProfileAnalysisStage.PRIMARY)
        )


def test_repositories_save_and_reload_case_artifact_evidence_and_report(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    db = SQLiteDatabase(db_path)
    case = _make_case()
    artifact = _make_artifact(case.case_id)
    fact = _make_fact(artifact.id)
    snapshot = _make_report_snapshot(case.case_id)

    LocalCaseRepository(db).add(case)
    LocalArtifactRepository(db).add(artifact)
    LocalEvidenceRepository(db).add(fact)
    LocalReportRepository(db).add_snapshot(snapshot)

    reopened = SQLiteDatabase(db_path)

    assert LocalCaseRepository(reopened).get(case.case_id) == case
    assert LocalArtifactRepository(reopened).get(artifact.id) == artifact
    assert LocalEvidenceRepository(reopened).list_for_case(case.case_id) == [fact]
    restored_snapshot = LocalReportRepository(reopened).get_snapshot(snapshot.id)
    assert restored_snapshot == snapshot
    assert isinstance(restored_snapshot.source_hashes, MappingProxyType)
    with pytest.raises(TypeError):
        restored_snapshot.source_hashes["10-k"] = "sha256:mutated"


def test_list_for_case_is_isolated_and_deterministically_ordered(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    other_case = _make_case(ticker="MSFT")
    artifact = _make_artifact(case.case_id)
    other_artifact = _make_artifact(other_case.case_id)
    first = _make_fact(artifact.id, name="assets")
    second = _make_fact(artifact.id, name="revenue")
    other = _make_fact(other_artifact.id, name="ignored")
    repo = LocalEvidenceRepository(db)
    LocalCaseRepository(db).add(case)
    LocalCaseRepository(db).add(other_case)
    LocalArtifactRepository(db).add(artifact)
    LocalArtifactRepository(db).add(other_artifact)

    repo.add(second)
    repo.add(other)
    repo.add(first)

    assert repo.list_for_case(case.case_id) == [first, second]


def test_duplicate_report_snapshot_id_is_rejected(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    repo = LocalReportRepository(db)
    case = _make_case()
    LocalCaseRepository(db).add(case)
    snapshot = _make_report_snapshot(case.case_id)

    repo.add_snapshot(snapshot)

    with pytest.raises(ValueError, match="report_snapshot_already_exists"):
        repo.add_snapshot(snapshot)


def test_calculation_repository_round_trips_orders_isolates_and_rejects_duplicates(
    tmp_path: Path,
):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    other_case = _make_case(ticker="MSFT")
    LocalCaseRepository(db).add(case)
    LocalCaseRepository(db).add(other_case)
    repo = LocalCalculationRepository(db)
    first = _make_calculation(case.case_id, metric_name="assets")
    second = _make_calculation(case.case_id, metric_name="revenue")
    other = _make_calculation(other_case.case_id, metric_name="ignored")

    repo.add(second)
    repo.add(other)
    repo.add(first)

    reopened = LocalCalculationRepository(SQLiteDatabase(db.path))
    assert reopened.list_for_case(case.case_id) == [first, second]
    assert reopened.list_for_case(other_case.case_id) == [other]
    with pytest.raises(ValueError, match="calculation_already_exists"):
        reopened.add(first)
    with pytest.raises(ValueError, match="calculation_already_exists"):
        reopened.add(_make_calculation(case_id=uuid4(), calculation_id=first.id))


def test_finding_repository_round_trips_orders_isolates_and_rejects_duplicates(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    other_case = _make_case(ticker="MSFT")
    LocalCaseRepository(db).add(case)
    LocalCaseRepository(db).add(other_case)
    repo = LocalFindingRepository(db)
    first = _make_finding(case.case_id, category="capital")
    second = _make_finding(case.case_id, category="risk")
    other = _make_finding(other_case.case_id, category="ignored")

    repo.add(second)
    repo.add(other)
    repo.add(first)

    reopened = LocalFindingRepository(SQLiteDatabase(db.path))
    assert reopened.list_for_case(case.case_id) == [first, second]
    assert reopened.list_for_case(other_case.case_id) == [other]
    with pytest.raises(ValueError, match="finding_already_exists"):
        reopened.add(first)
    with pytest.raises(ValueError, match="finding_already_exists"):
        reopened.add(_make_finding(case_id=uuid4(), finding_id=first.id))


def test_contradiction_repository_round_trips_orders_isolates_and_rejects_duplicates(
    tmp_path: Path,
):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    other_case = _make_case(ticker="MSFT")
    LocalCaseRepository(db).add(case)
    LocalCaseRepository(db).add(other_case)
    repo = LocalContradictionRepository(db)
    first = _make_contradiction(case.case_id, conflict_type="filing")
    second = _make_contradiction(case.case_id, conflict_type="metric")
    other = _make_contradiction(other_case.case_id, conflict_type="ignored")

    repo.add(second)
    repo.add(other)
    repo.add(first)

    reopened = LocalContradictionRepository(SQLiteDatabase(db.path))
    assert reopened.list_for_case(case.case_id) == [first, second]
    assert reopened.list_for_case(other_case.case_id) == [other]
    with pytest.raises(ValueError, match="contradiction_already_exists"):
        reopened.add(first)
    with pytest.raises(ValueError, match="contradiction_already_exists"):
        reopened.add(_make_contradiction(case_id=uuid4(), contradiction_id=first.id))


def test_approval_repository_round_trips_orders_isolates_and_rejects_duplicates(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case = _make_case()
    other_case = _make_case(ticker="MSFT")
    LocalCaseRepository(db).add(case)
    LocalCaseRepository(db).add(other_case)
    repo = LocalApprovalRepository(db)
    first = _make_approval(case.case_id, gate="a_scope")
    second = _make_approval(case.case_id, gate="b_report")
    other = _make_approval(other_case.case_id, gate="ignored")

    repo.add(second)
    repo.add(other)
    repo.add(first)

    reopened = LocalApprovalRepository(SQLiteDatabase(db.path))
    assert reopened.list_for_case(case.case_id) == [first, second]
    assert reopened.list_for_case(other_case.case_id) == [other]
    with pytest.raises(ValueError, match="approval_already_exists"):
        reopened.add(first)
    with pytest.raises(ValueError, match="approval_already_exists"):
        reopened.add(_make_approval(case_id=uuid4(), approval_id=first.id))


def test_case_service_normalizes_and_persists_public_sec_case(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "cases.sqlite3")
    case_repo = LocalCaseRepository(db)
    service = CaseService(case_repo)

    created = service.create_public_case(
        ticker=" aapl ",
        entity_name="Apple Inc.",
        jurisdiction="US_SEC",
        as_of=datetime(2026, 8, 9, tzinfo=UTC),
        base_currency="usd",
    )

    assert created.entity_identifier == "AAPL"
    assert created.mode is AnalysisMode.PUBLIC_COMPANY
    assert created.jurisdiction == "US_SEC"
    assert created.status is CaseStatus.CREATED
    assert case_repo.get(created.case_id) == created


def test_case_service_rejects_empty_ticker_and_unsupported_mode_or_jurisdiction(tmp_path: Path):
    service = CaseService(LocalCaseRepository(SQLiteDatabase(tmp_path / "cases.sqlite3")))

    with pytest.raises(ValueError, match="ticker_required"):
        service.create_public_case(ticker=" ", entity_name="Apple Inc.")

    with pytest.raises(ValueError, match="unsupported_mode"):
        service.create_public_case(
            ticker="AAPL",
            entity_name="Apple Inc.",
            mode=AnalysisMode.STARTUP,
        )

    with pytest.raises(ValueError, match="unsupported_jurisdiction"):
        service.create_public_case(
            ticker="AAPL",
            entity_name="Apple Inc.",
            jurisdiction="US",
        )


def test_case_repository_advances_data_revision_atomically_and_rejects_stale_updates(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    db = SQLiteDatabase(db_path)
    repo = LocalCaseRepository(db)
    case = _make_case()
    repo.add(case)
    updated = case.model_copy(
        update={
            "data_revision": 2,
            "updated_at": datetime(2026, 8, 10, tzinfo=UTC),
        }
    )

    result = repo.advance_data_revision(
        case.case_id,
        expected_revision=1,
        updated_case=updated,
    )

    reopened = LocalCaseRepository(SQLiteDatabase(db_path))
    assert result == updated
    assert reopened.get(case.case_id) == updated
    with pytest.raises(ValueError, match="case_data_revision_conflict"):
        reopened.advance_data_revision(
            case.case_id,
            expected_revision=1,
            updated_case=updated.model_copy(
                update={
                    "data_revision": 2,
                    "updated_at": datetime(2026, 8, 11, tzinfo=UTC),
                }
            ),
        )
    with pytest.raises(ValueError, match="case_data_revision_must_advance_by_one"):
        reopened.advance_data_revision(
            case.case_id,
            expected_revision=2,
            updated_case=updated.model_copy(update={"data_revision": 4}),
        )


def test_case_repository_concurrent_revision_advance_is_single_winner(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    seed_repo = LocalCaseRepository(SQLiteDatabase(db_path))
    case = _make_case()
    seed_repo.add(case)
    candidates = [
        case.model_copy(
            update={
                "data_revision": 2,
                "updated_at": datetime(2026, 8, 10, hour=idx, tzinfo=UTC),
                "entity_name": f"winner-{idx}",
            }
        )
        for idx in (1, 2)
    ]

    def attempt(updated_case: DueDiligenceCase) -> DueDiligenceCase | str:
        repo = LocalCaseRepository(SQLiteDatabase(db_path))
        try:
            return repo.advance_data_revision(
                case.case_id,
                expected_revision=1,
                updated_case=updated_case,
            )
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, candidates))

    winners = [result for result in results if isinstance(result, DueDiligenceCase)]
    conflicts = [result for result in results if result == "case_data_revision_conflict"]
    assert len(winners) == 1
    assert len(conflicts) == 1
    assert LocalCaseRepository(SQLiteDatabase(db_path)).get(case.case_id) == winners[0]


def _make_case(ticker: str = "AAPL") -> DueDiligenceCase:
    now = datetime(2026, 8, 9, tzinfo=UTC)
    return DueDiligenceCase(
        case_id=uuid4(),
        mode=AnalysisMode.PUBLIC_COMPANY,
        entity_name=f"{ticker} Inc.",
        entity_identifier=ticker,
        jurisdiction="US_SEC",
        scope=("public_company_stage1a",),
        period_start=None,
        period_end=None,
        as_of=now,
        base_currency="USD",
        privacy_policy="public-company-local@1",
        budget_policy="stage1a-local@1",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=now,
        updated_at=now,
        workflow_version="public-company-local@1",
        data_revision=1,
    )


def _make_artifact(case_id: UUID) -> Artifact:
    return Artifact(
        id=uuid4(),
        case_id=case_id,
        content_hash="a" * 64,
        mime_type="text/html",
        source="sec-edgar",
        source_url="https://www.sec.gov/example",
        normalized_query=(("ticker", "AAPL"),),
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
        published_at=None,
        filing_acceptance_at=None,
        effective_at=None,
        source_snapshot_hash="b" * 64,
        storage_ref="artifact://filing",
        parsing_status=ArtifactParsingStatus.PARSED,
        sensitivity=SensitivityClass.PUBLIC,
        parent_artifact_id=None,
        version=1,
    )


def _make_fact(artifact_id: UUID, name: str = "revenue") -> EvidenceFact:
    return EvidenceFact(
        id=uuid4(),
        artifact_id=artifact_id,
        name=name,
        value=Decimal("100.25"),
        value_type="decimal",
        unit="USD",
        period="FY2025",
        locator=SourceLocator(kind="sec_fact", value=name, artifact_id=artifact_id),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.95"),
        source_priority=1,
        extraction_method="xbrl",
        supporting_text_hash="c" * 64,
        source_freshness_at=datetime(2026, 8, 8, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
        version=1,
    )


def _make_parsed_startup_artifact(case_id: UUID, artifact_id: UUID) -> ParsedStartupArtifact:
    return ParsedStartupArtifact.from_spreadsheet(
        SpreadsheetParseResult(artifact_id=artifact_id, status="parsed"),
        case_id=case_id,
        detected_mime_type="text/csv",
        parser_name="unit",
        parser_version="unit@1",
    )


def _make_startup_profile(
    case: DueDiligenceCase,
    artifact: Artifact,
    stage: StartupProfileAnalysisStage,
    *,
    parent_profile_id: UUID | None = None,
) -> StartupProfile:
    fields = {
        name.value: StartupProfileField(
            name=name,
            status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
            confidence=Decimal("0"),
        )
        for name in StartupProfileFieldName
    }
    fields[StartupProfileFieldName.STARTUP_NAME.value] = StartupProfileField(
        name=StartupProfileFieldName.STARTUP_NAME,
        status=StartupProfileFieldStatus.INFERENCE,
        values=(case.entity_name,),
        confidence=Decimal("0.70"),
        dependency_refs=(artifact.id,),
        reason_code="case_entity_name",
    )
    return StartupProfile.build(
        case_id=case.case_id,
        schema_version="startup-profile-schema@1",
        profile_version=f"{stage.value}@1",
        extractor_version="unit@1",
        analysis_stage=stage,
        parent_profile_id=parent_profile_id,
        data_revision=case.data_revision,
        source_hashes={f"artifact-{artifact.id.hex}": f"sha256:{artifact.source_snapshot_hash}"},
        parse_outcomes={f"artifact-{artifact.id.hex}": "parsed"},
        fields=fields,
        case_revision_at=case.updated_at,
    )


def _make_startup_claim(
    case_id: UUID,
    artifact_id: UUID,
    normalized_name: str = "arr",
) -> StartupClaim:
    return StartupClaim.from_raw_text(
        raw_text=f"{normalized_name} is $1.2M ARR in FY2026",
        id=uuid4(),
        case_id=case_id,
        category=ClaimCategory.ARR if normalized_name == "arr" else ClaimCategory.OTHER,
        source_artifact_id=artifact_id,
        locator=SourceLocator(kind="document_text", value=normalized_name, artifact_id=artifact_id),
        criticality=ClaimCriticality.HIGH,
        normalized_name=normalized_name,
        normalized_value=Decimal("1200000"),
        unit="USD",
        period="FY2026",
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.90"),
        extracted_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


def _make_calculation(
    case_id: UUID, metric_name: str = "revenue", calculation_id: UUID | None = None
) -> Calculation:
    return Calculation(
        id=calculation_id or uuid4(),
        case_id=case_id,
        metric_name=metric_name,
        formula_version="metric@1",
        input_fact_ids=(uuid4(),),
        value=Decimal("10.5"),
        unit="USD",
        period="FY2025",
        warnings=(),
        calculated_at=datetime(2026, 8, 9, tzinfo=UTC),
        sensitivity=SensitivityClass.PUBLIC,
    )


def _make_finding(
    case_id: UUID, category: str = "risk", finding_id: UUID | None = None
) -> Finding:
    return Finding(
        id=finding_id or uuid4(),
        case_id=case_id,
        category=category,
        severity=FindingSeverity.HIGH,
        claim=f"{category} claim",
        evidence_fact_ids=(),
        calculation_ids=(),
        confidence=Decimal("0.80"),
        status=FindingStatus.VERIFIED,
        counter_evidence_fact_ids=(),
        author_node="risk_node",
        author_model=None,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


def _make_contradiction(
    case_id: UUID, conflict_type: str = "metric", contradiction_id: UUID | None = None
) -> Contradiction:
    return Contradiction(
        id=contradiction_id or uuid4(),
        case_id=case_id,
        conflict_type=conflict_type,
        fact_ids=(),
        finding_ids=(),
        explanation=f"{conflict_type} conflict",
        severity=FindingSeverity.MEDIUM,
        status=ContradictionStatus.OPEN,
        recommended_resolution=None,
        resolved_by_approval_id=None,
        sensitivity=SensitivityClass.PUBLIC,
        detected_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


def _make_approval(case_id: UUID, gate: str = "scope", approval_id: UUID | None = None) -> Approval:
    return Approval(
        id=approval_id or uuid4(),
        case_id=case_id,
        gate=gate,
        action="approved",
        actor="analyst",
        comment=None,
        decided_at=datetime(2026, 8, 9, tzinfo=UTC),
        data_revision=1,
    )


def _make_report_snapshot(case_id: UUID) -> ReportSnapshot:
    manifest = ReproducibilityManifest(
        code_commit="abc123",
        build_id="local",
        dependency_lock_hash="sha256:lock",
        python_version="3.12.0",
        package_versions={"pydantic": "2.13.4"},
        provider_model_id="openai/gpt-5.5",
        model_alias_snapshot="public-analysis@1",
        reasoning_parameters={"effort": "medium"},
        adapter_versions={"sec": "sec-adapter@1"},
        parser_versions={"xbrl": "xbrl-parser@1"},
        embedding_model_version="sentence-transformers/all-MiniLM-L6-v2",
        index_version="faiss@1",
        redaction_policy_version="egress@1",
        locale="en-US",
        timezone="UTC",
        fx_source="none",
        deterministic_seeds={"report": 1},
        configuration_hash="sha256:config",
    )
    return ReportSnapshot(
        id=uuid4(),
        case_id=case_id,
        report_hash="sha256:report",
        case_snapshot_hash="sha256:case",
        source_hashes={"10-k": "sha256:filing"},
        as_of=datetime(2026, 8, 9, tzinfo=UTC),
        graph_version="public-graph@1",
        prompt_versions={"synthesis": "prompt@1"},
        formula_versions={"revenue_growth": "formula@1"},
        model_versions={"analysis": "openai/gpt-5.5"},
        trace_ids=("trace-1",),
        json_artifact_ref="artifact://json",
        html_artifact_ref="artifact://html",
        pdf_artifact_ref=None,
        content_hashes={"json": "sha256:json", "html": "sha256:html"},
        reproducibility=manifest,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
        version=1,
    )

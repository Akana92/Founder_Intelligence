from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import json
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from due_diligence_agent.adapters.local_storage.repositories import (
    LocalApprovalRepository,
    LocalArtifactRepository,
    LocalCalculationRepository,
    LocalContradictionDecisionRepository,
    LocalCaseRepository,
    LocalContradictionRepository,
    LocalEvidenceRepository,
    LocalFindingRepository,
    LocalReportRepository,
    LocalStartupClaimRepository,
    LocalStartupProfileRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.reports.html_renderer import HtmlRenderer
from due_diligence_agent.bootstrap.container import build_startup_report_port
from due_diligence_agent.domain.approvals.models import Approval, ContradictionDecision
from due_diligence_agent.application.services.report_service import (
    ReportService,
)
from due_diligence_agent.application.services.startup_report_service import (
    STARTUP_REPORT_SECTION_KEYS,
    StartupReportSnapshotBuilder,
)
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
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import (
    ClaimCategory,
    ClaimCriticality,
    StartupClaim,
)
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.workflows.startup.ports import StartupReportRepositoryAdapter


AS_OF = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
CASE_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-case")
ARTIFACT_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-artifact")
CLAIM_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-claim")
FACT_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-fact")
CALCULATION_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-calculation")
FINDING_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-finding")
CONTRADICTION_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-contradiction")
CONTRADICTION_APPROVAL_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-contradiction-approval")
CONTRADICTION_DECISION_ID = uuid5(NAMESPACE_URL, "e2e-startup-report-contradiction-decision")
PRIVATE_SENTINEL = "C:\\Users\\Akana\\secret\\pitch.pdf founder@example.com sk-live-secret"
TRACE_RUN_ID = "startup-e2e-report-run"
TRACE_CORRELATION_ID = "case-e2e-startup-report"
TRACE_CHECKPOINT_IDS = (
    "startup-profile-111111111111",
    "startup-evidence-222222222222",
)


def test_startup_report_builds_one_persisted_canonical_snapshot_from_local_repositories(
    seeded_context: SeededContext,
) -> None:
    adapter = seeded_context.adapter()

    built = _build_report(adapter)
    snapshot = seeded_context.repositories.report_repository.get_snapshot(
        UUID(str(built["report_snapshot_id"]))
    )
    canonical = json.loads(adapter.canonical_json_bytes(str(CASE_ID)))
    html = adapter.html(str(CASE_ID))

    assert built == {
        "report_snapshot_id": str(snapshot.id),
        "report_snapshot_hash": snapshot.report_hash,
        "report_snapshot_revision": snapshot.data_revision,
    }
    assert tuple(canonical["sections"])[:12] == STARTUP_REPORT_SECTION_KEYS
    assert _html_section_order(html)[:12] == STARTUP_REPORT_SECTION_KEYS
    assert canonical["schema"] == "startup_report_snapshot.v1"
    assert canonical["id"] == str(snapshot.id)
    assert canonical["report_hash"] == snapshot.report_hash
    assert canonical["data_revision"] == 1
    assert canonical["reproducibility"]["dependency_lock_hash"].startswith("sha256:")
    assert snapshot.content_hashes["json"] == snapshot.json_artifact_ref
    assert snapshot.html_artifact_ref == f"sha256:{_sha256(seeded_context.html_path(snapshot.id))}"
    assert '<html lang="ru">' in html
    assert "Отчёт для основателя" in html
    assert "Что уже известно" in html
    assert "Что добавить" in html
    assert "Что это откроет" in html
    assert "Предложения ИИ по улучшению" in html
    assert "Техническая методология и источники" in html
    assert "MISSING" not in html
    assert "document_text_block" not in html
    assert "Provide primary support" not in html
    assert "evidence_refs=" not in html
    assert "calculation_ref=" not in html
    assert snapshot.report_hash not in html
    assert str(snapshot.id) not in html
    assert PRIVATE_SENTINEL not in json.dumps(canonical, sort_keys=True)
    assert PRIVATE_SENTINEL not in html
    assert "FAKE_TAM_999" not in html


def test_startup_report_rejects_missing_stale_or_mismatched_profile_tuple(
    seeded_context: SeededContext,
) -> None:
    adapter = seeded_context.adapter()
    profile = seeded_context.repositories.startup_profile_repository.get_current(CASE_ID)

    with pytest.raises(ValueError, match="startup_report_profile_not_found"):
        _build_report(
            adapter,
            profile_id=uuid5(NAMESPACE_URL, "missing-startup-report-profile"),
        )
    with pytest.raises(ValueError, match="startup_report_profile_hash_mismatch"):
        _build_report(adapter, profile_hash="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="startup_report_profile_revision_mismatch"):
        _build_report(adapter, profile_revision=profile.data_revision + 1)
    case = seeded_context.repositories.case_repository.get(CASE_ID)
    seeded_context.repositories.case_repository.advance_data_revision(
        CASE_ID,
        expected_revision=case.data_revision,
        updated_case=case.model_copy(
            update={
                "data_revision": case.data_revision + 1,
                "updated_at": case.updated_at + timedelta(seconds=1),
            }
        ),
    )
    with pytest.raises(ValueError, match="startup_report_profile_stale"):
        _build_report(adapter)


def test_startup_report_rejects_a_persisted_profile_that_is_not_current(
    seeded_context: SeededContext,
) -> None:
    adapter = seeded_context.adapter()
    primary = seeded_context.repositories.startup_profile_repository.get_current(CASE_ID)
    enriched = _profile(
        analysis_stage=StartupProfileAnalysisStage.ENRICHED,
        parent_profile_id=primary.profile_id,
        fields={
            **_profile_fields(),
            StartupProfileFieldName.STRENGTHS.value: _profile_field(
                StartupProfileFieldName.STRENGTHS,
                "Verified enriched differentiation",
            ),
        },
    )
    seeded_context.repositories.startup_profile_repository.add(enriched)

    with pytest.raises(ValueError, match="startup_report_profile_not_current"):
        _build_report(
            adapter,
            profile_id=primary.profile_id,
            profile_hash=primary.profile_hash,
            profile_revision=primary.data_revision,
        )

    built = _build_report(
        adapter,
        profile_id=enriched.profile_id,
        profile_hash=enriched.profile_hash,
        profile_revision=enriched.data_revision,
    )
    snapshot = seeded_context.repositories.report_repository.get_snapshot(
        UUID(str(built["report_snapshot_id"]))
    )
    assert "Verified enriched differentiation" in str(snapshot.sections["moat"])


def test_startup_report_reopens_local_repositories_and_serves_same_canonical_artifacts(
    seeded_context: SeededContext,
) -> None:
    first_adapter = seeded_context.adapter()
    built = _build_report(first_adapter)
    json_before = first_adapter.canonical_json_bytes(str(CASE_ID))
    html_before = first_adapter.html(str(CASE_ID))
    seeded_context.close()
    reopened = seeded_context.reopen()

    current = reopened.adapter().current_snapshot(str(CASE_ID))
    json_after = reopened.adapter().canonical_json_bytes(str(CASE_ID))
    html_after = reopened.adapter().html(str(CASE_ID))

    assert current.snapshot_id == built["report_snapshot_id"]
    assert current.snapshot_hash == built["report_snapshot_hash"]
    assert current.snapshot_revision == built["report_snapshot_revision"]
    assert json_after == json_before
    assert html_after == html_before
    assert tuple(json.loads(json_after)["sections"])[:12] == STARTUP_REPORT_SECTION_KEYS
    assert _html_section_order(html_after)[:12] == STARTUP_REPORT_SECTION_KEYS


def test_reopened_startup_report_rerender_preserves_section_order(
    seeded_context: SeededContext,
) -> None:
    first_adapter = seeded_context.adapter()
    built = _build_report(first_adapter)
    snapshot_id = UUID(str(built["report_snapshot_id"]))
    snapshot_before = seeded_context.repositories.report_repository.get_snapshot(snapshot_id)
    html_before = first_adapter.html(str(CASE_ID))
    canonical_path = seeded_context.report_dir / f"{snapshot_id}.report.json"
    canonical_bytes_before = canonical_path.read_bytes()
    lineage_before = (
        snapshot_before.case_id,
        snapshot_before.id,
        snapshot_before.report_hash,
        snapshot_before.data_revision,
        snapshot_before.json_artifact_ref,
    )
    seeded_context.close()
    reopened = seeded_context.reopen()
    reopened.html_path(snapshot_id).unlink()

    rerendered = reopened.adapter().html(str(CASE_ID))
    snapshot_after = reopened.repositories.report_repository.get_snapshot(snapshot_id)

    assert _html_section_order(rerendered)[:12] == STARTUP_REPORT_SECTION_KEYS
    assert rerendered == html_before
    assert canonical_path.read_bytes() == canonical_bytes_before
    assert (
        snapshot_after.case_id,
        snapshot_after.id,
        snapshot_after.report_hash,
        snapshot_after.data_revision,
        snapshot_after.json_artifact_ref,
    ) == lineage_before


def test_latest_exact_gate4_rejection_blocks_pdf_until_later_exact_approval(
    seeded_context: SeededContext,
) -> None:
    adapter = seeded_context.adapter()
    built = _build_report(adapter)

    rejected = adapter.decide_gate4(
        str(CASE_ID),
        decision="rejected",
        snapshot_hash=str(built["report_snapshot_hash"]),
        snapshot_revision=int(built["report_snapshot_revision"]),
        reason="needs founder evidence",
    )

    assert rejected.snapshot_hash == built["report_snapshot_hash"]
    assert adapter.freeze_status(str(CASE_ID)) == "required"
    assert adapter.pdf_status(str(CASE_ID)) == "freeze_required"
    with pytest.raises(RuntimeError, match="gate_4_freeze_required"):
        adapter.pdf(str(CASE_ID))

    approved = adapter.decide_gate4(
        str(CASE_ID),
        decision="approved",
        snapshot_hash=str(built["report_snapshot_hash"]),
        snapshot_revision=int(built["report_snapshot_revision"]),
        reason="approved after rejection",
    )
    pdf = adapter.pdf(str(CASE_ID))

    assert approved.snapshot_hash == built["report_snapshot_hash"]
    assert adapter.freeze_status(str(CASE_ID)) == "approved"
    assert adapter.pdf_status(str(CASE_ID)) == "ready"
    assert pdf.startswith(b"%PDF-1.4\n% deterministic startup report\n")


def test_gate4_wrong_hash_and_stale_revision_are_blocked_without_persisting_decision(
    seeded_context: SeededContext,
) -> None:
    adapter = seeded_context.adapter()
    built = _build_report(adapter)

    with pytest.raises(ValueError, match="gate_4_snapshot_mismatch"):
        adapter.decide_gate4(
            str(CASE_ID),
            decision="approved",
            snapshot_hash="sha256:" + "0" * 64,
            snapshot_revision=int(built["report_snapshot_revision"]),
        )
    with pytest.raises(ValueError, match="gate_4_snapshot_mismatch"):
        adapter.decide_gate4(
            str(CASE_ID),
            decision="approved",
            snapshot_hash=str(built["report_snapshot_hash"]),
            snapshot_revision=0,
        )
    seeded_context.current_revision = 2
    with pytest.raises(ValueError, match="gate_4_snapshot_mismatch"):
        adapter.decide_gate4(
            str(CASE_ID),
            decision="approved",
            snapshot_hash=str(built["report_snapshot_hash"]),
            snapshot_revision=int(built["report_snapshot_revision"]),
        )

    assert seeded_context.repositories.approval_repository.list_for_case(CASE_ID) == []


def test_pdf_is_rendered_from_approved_persisted_snapshot_after_repository_reopen(
    seeded_context: SeededContext,
) -> None:
    first_adapter = seeded_context.adapter()
    built = _build_report(first_adapter)
    first_adapter.decide_gate4(
        str(CASE_ID),
        decision="approved",
        snapshot_hash=str(built["report_snapshot_hash"]),
        snapshot_revision=int(built["report_snapshot_revision"]),
    )
    seeded_context.close()
    reopened = seeded_context.reopen()
    snapshot = reopened.repositories.report_repository.get_snapshot(UUID(str(built["report_snapshot_id"])))

    pdf = reopened.adapter().pdf(str(CASE_ID))

    assert pdf == b"%PDF-1.4\n% deterministic startup report\n"
    assert snapshot.report_hash.encode("utf-8") not in pdf
    assert reopened.pdf_path(snapshot.id).read_bytes() == pdf


def test_startup_report_uses_canonical_case_revision_not_review_decision_revision(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "canonical-startup-report"
    db = SQLiteDatabase(data_dir / "startup-metadata.sqlite3")
    repositories = Repositories.from_db(db)
    _seed_startup_data(repositories)
    repositories.contradiction_repository.add(_contradiction())
    repositories.approval_repository.add(_contradiction_approval())
    LocalContradictionDecisionRepository(db).add(_contradiction_decision(data_revision=2))
    _seed_startup_audit_spool(data_dir / "startup-audit-spool")
    db.close()
    adapter = build_startup_report_port(data_dir)

    built = _build_report(adapter)
    current = adapter.current_snapshot(str(CASE_ID))
    approved = adapter.decide_gate4(
        str(CASE_ID),
        decision="approved",
        snapshot_hash=str(built["report_snapshot_hash"]),
        snapshot_revision=int(built["report_snapshot_revision"]),
    )

    assert built["report_snapshot_revision"] == 1
    assert current.snapshot_revision == 1
    assert approved.snapshot_revision == 1
    assert adapter.freeze_status(str(CASE_ID)) == "approved"
    assert adapter.pdf_status(str(CASE_ID)) == "ready"

    db = SQLiteDatabase(data_dir / "startup-metadata.sqlite3")
    case_repository = LocalCaseRepository(db)
    original = case_repository.get(CASE_ID)
    case_repository.advance_data_revision(
        CASE_ID,
        expected_revision=1,
        updated_case=original.model_copy(
            update={"data_revision": 2, "updated_at": original.updated_at + timedelta(seconds=1)}
        ),
    )
    db.close()

    assert adapter.freeze_status(str(CASE_ID)) == "required"
    assert adapter.pdf_status(str(CASE_ID)) == "freeze_required"
    with pytest.raises(KeyError, match="report_snapshot_not_found"):
        adapter.current_snapshot(str(CASE_ID))


@pytest.fixture
def seeded_context(tmp_path: Path) -> SeededContext:
    context = SeededContext(tmp_path / "startup-report-e2e")
    _seed_startup_data(context.repositories)
    context.seed_audit_spool()
    return context


@dataclass
class SeededContext:
    root: Path
    current_revision: int = 1
    _db: SQLiteDatabase | None = None
    _repositories: Repositories | None = None

    @property
    def db_path(self) -> Path:
        return self.root / "startup-metadata.sqlite3"

    @property
    def report_dir(self) -> Path:
        return self.root / "startup-reports"

    @property
    def repositories(self) -> Repositories:
        if self._repositories is None:
            self._db = SQLiteDatabase(self.db_path)
            self._repositories = Repositories.from_db(self._db)
        return self._repositories

    def adapter(self) -> StartupReportRepositoryAdapter:
        repos = self.repositories
        return StartupReportRepositoryAdapter(
            case_repository=repos.case_repository,
            startup_claim_repository=repos.startup_claim_repository,
            startup_profile_repository=repos.startup_profile_repository,
            evidence_repository=repos.evidence_repository,
            calculation_repository=repos.calculation_repository,
            finding_repository=repos.finding_repository,
            contradiction_repository=repos.contradiction_repository,
            report_repository=repos.report_repository,
            approval_repository=repos.approval_repository,
            current_data_revision=lambda _case_id: self.current_revision,
            report_service=ReportService(
                html_renderer=HtmlRenderer(),
                pdf_renderer=DeterministicPdfRenderer(),
                approval_repository=repos.approval_repository,
                current_data_revision=lambda _case_id: self.current_revision,
                report_repository=repos.report_repository,
            ),
            output_dir=self.report_dir,
            audit_spool=self.audit_spool,
            builder=StartupReportSnapshotBuilder(project_root=Path.cwd()),
            clock=IncrementingClock(),
        )

    def reopen(self) -> SeededContext:
        return SeededContext(self.root, current_revision=self.current_revision)

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
        self._db = None
        self._repositories = None

    def html_path(self, snapshot_id: UUID) -> Path:
        return self.report_dir / f"{snapshot_id}.report.html"

    def pdf_path(self, snapshot_id: UUID) -> Path:
        return self.report_dir / f"{snapshot_id}.report.pdf"

    @property
    def audit_spool(self) -> JsonlAuditSpool:
        return JsonlAuditSpool(self.root / "startup-audit-spool")

    def seed_audit_spool(self) -> None:
        _seed_startup_audit_spool(self.root / "startup-audit-spool")


@dataclass(frozen=True)
class Repositories:
    case_repository: LocalCaseRepository
    artifact_repository: LocalArtifactRepository
    evidence_repository: LocalEvidenceRepository
    calculation_repository: LocalCalculationRepository
    finding_repository: LocalFindingRepository
    contradiction_repository: LocalContradictionRepository
    startup_claim_repository: LocalStartupClaimRepository
    startup_profile_repository: LocalStartupProfileRepository
    approval_repository: LocalApprovalRepository
    report_repository: LocalReportRepository

    @classmethod
    def from_db(cls, db: SQLiteDatabase) -> Repositories:
        return cls(
            case_repository=LocalCaseRepository(db),
            artifact_repository=LocalArtifactRepository(db),
            evidence_repository=LocalEvidenceRepository(db),
            calculation_repository=LocalCalculationRepository(db),
            finding_repository=LocalFindingRepository(db),
            contradiction_repository=LocalContradictionRepository(db),
            startup_claim_repository=LocalStartupClaimRepository(db),
            startup_profile_repository=LocalStartupProfileRepository(db),
            approval_repository=LocalApprovalRepository(db),
            report_repository=LocalReportRepository(db),
        )


class DeterministicPdfRenderer:
    def render(self, html: str, output_path: Path) -> None:
        assert "startup_report_snapshot.v1" in html
        assert "Отчёт для основателя" in html
        assert "MISSING" not in html
        output_path.write_bytes(b"%PDF-1.4\n% deterministic startup report\n")


class IncrementingClock:
    def __init__(self) -> None:
        self._next = AS_OF

    def __call__(self) -> datetime:
        current = self._next
        self._next = current + timedelta(seconds=1)
        return current


def _seed_startup_audit_spool(root: Path) -> None:
    spool = JsonlAuditSpool(root)
    for index, checkpoint_id in enumerate(TRACE_CHECKPOINT_IDS, start=1):
        node_name = checkpoint_id.removeprefix("startup-").rsplit("-", 1)[0]
        spool.append(
            AuditEvent(
                schema_version="audit_event@1",
                event_id=f"startup-e2e-report-event-{index}",
                timestamp_utc=(AS_OF + timedelta(seconds=index)).isoformat().replace("+00:00", "Z"),
                run_id=TRACE_RUN_ID,
                correlation_id=TRACE_CORRELATION_ID,
                span_name="analysis.module",
                event_type="span",
                attributes={
                    "schema_version": "startup_node_audit@1",
                    "case_id": str(CASE_ID),
                    "node_name": node_name,
                    "status": "succeeded",
                    "evidence_count": 1,
                    "attempt": 1,
                    "retry_count": 0,
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_hash": _sha256_hex(f"{CASE_ID}:{checkpoint_id}"),
                    "tool": "offline",
                },
            )
        )


def _seed_startup_data(repositories: Repositories) -> None:
    repositories.case_repository.add(_case())
    repositories.artifact_repository.add(_artifact())
    repositories.startup_claim_repository.add(_claim())
    repositories.evidence_repository.add(_fact())
    repositories.calculation_repository.add(_calculation())
    repositories.finding_repository.add(_finding())
    repositories.startup_profile_repository.add(_profile())


def _contradiction() -> Contradiction:
    return Contradiction(
        id=CONTRADICTION_ID,
        case_id=CASE_ID,
        conflict_type="metric_vs_claim",
        fact_ids=(FACT_ID,),
        finding_ids=(FINDING_ID,),
        explanation="ARR and risk finding need reviewer decision.",
        severity=FindingSeverity.HIGH,
        status=ContradictionStatus.OPEN,
        recommended_resolution="Use canonical case revision for report freshness.",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        detected_at=AS_OF,
    )


def _contradiction_approval() -> Approval:
    return Approval(
        id=CONTRADICTION_APPROVAL_ID,
        case_id=CASE_ID,
        gate="contradiction_review",
        action="accepted",
        actor="reviewer",
        comment="decision used to test review repository revision divergence",
        decided_at=AS_OF + timedelta(minutes=1),
        data_revision=2,
        subject_id=CONTRADICTION_ID,
    )


def _contradiction_decision(*, data_revision: int) -> ContradictionDecision:
    return ContradictionDecision(
        id=CONTRADICTION_DECISION_ID,
        case_id=CASE_ID,
        contradiction_id=CONTRADICTION_ID,
        approval_id=CONTRADICTION_APPROVAL_ID,
        action="accept_source",
        status=ContradictionStatus.ACCEPTED_SOURCE,
        data_revision=data_revision,
        decided_at=AS_OF + timedelta(minutes=1),
    )


def _build_report(
    adapter: StartupReportRepositoryAdapter,
    *,
    profile_id: UUID | None = None,
    profile_hash: str | None = None,
    profile_revision: int | None = None,
) -> dict[str, str | int]:
    profile = _profile()
    return adapter.build(
        case_id=str(CASE_ID),
        profile_id=str(profile_id or profile.profile_id),
        profile_hash=profile_hash or profile.profile_hash,
        profile_revision=profile_revision if profile_revision is not None else profile.data_revision,
        startup_claim_ids=[str(CLAIM_ID)],
        evidence_fact_ids=[str(FACT_ID)],
        calculation_ids=[str(CALCULATION_ID)],
        finding_ids=[str(FINDING_ID)],
        contradiction_ids=[],
    )


def _profile(
    *,
    analysis_stage: StartupProfileAnalysisStage = StartupProfileAnalysisStage.PRIMARY,
    parent_profile_id: UUID | None = None,
    fields: dict[str, StartupProfileField] | None = None,
) -> StartupProfile:
    return StartupProfile.build(
        case_id=CASE_ID,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="deterministic-profile@1",
        analysis_stage=analysis_stage,
        parent_profile_id=parent_profile_id,
        data_revision=1,
        source_hashes={"pitch-deck": "sha256:" + "a" * 64},
        parse_outcomes={"pitch-deck": "parsed"},
        fields=fields or _profile_fields(),
        gap_codes=("market_size_missing",),
        contradiction_ids=(),
        case_revision_at=AS_OF,
    )


def _profile_fields() -> dict[str, StartupProfileField]:
    values = {
        StartupProfileFieldName.PROBLEM: "Manual diligence takes weeks",
        StartupProfileFieldName.SOLUTION: "Automated evidence-backed diligence",
        StartupProfileFieldName.COMPETITORS_MENTIONED: "Legacy advisory firms",
        StartupProfileFieldName.STRENGTHS: "Deterministic evidence lineage",
        StartupProfileFieldName.WEAKNESSES: "Early distribution",
        StartupProfileFieldName.ASSUMPTIONS: "Founder supplies primary evidence",
    }
    return {
        name.value: (
            _profile_field(name, values[name])
            if name in values
            else StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                values=(),
                confidence=Decimal("0"),
                reason_code=f"{name.value}_missing",
            )
        )
        for name in StartupProfileFieldName
    }


def _profile_field(name: StartupProfileFieldName, value: str) -> StartupProfileField:
    return StartupProfileField(
        name=name,
        status=StartupProfileFieldStatus.SOURCE_FACT,
        values=(value,),
        confidence=Decimal("0.91"),
        evidence_refs=(
            StartupProfileEvidenceRef(
                evidence_id=uuid5(NAMESPACE_URL, f"e2e-startup-report-profile:{name.value}"),
                artifact_id=ARTIFACT_ID,
                artifact_hash="sha256:" + "a" * 64,
                locator_hash="sha256:" + "f" * 64,
                field_name=name,
                confidence=Decimal("0.91"),
            ),
        ),
    )


def _case() -> DueDiligenceCase:
    return DueDiligenceCase(
        case_id=CASE_ID,
        mode=AnalysisMode.STARTUP,
        entity_name="FounderCo",
        entity_identifier="founderco",
        jurisdiction="US",
        scope=("startup",),
        as_of=AS_OF,
        base_currency="USD",
        privacy_policy="startup-local@1",
        budget_policy="offline",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
        updated_at=AS_OF,
        workflow_version="startup-graph@1",
        data_revision=1,
    )


def _artifact() -> Artifact:
    return Artifact(
        id=ARTIFACT_ID,
        case_id=CASE_ID,
        content_hash="a" * 64,
        mime_type="text/plain",
        source="startup-upload",
        source_url=None,
        normalized_query=(("upload", "redacted"),),
        retrieved_at=AS_OF,
        published_at=None,
        filing_acceptance_at=None,
        effective_at=None,
        source_snapshot_hash="b" * 64,
        storage_ref="artifact://redacted",
        parsing_status=ArtifactParsingStatus.PARSED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        parent_artifact_id=None,
        version=1,
    )


def _claim() -> StartupClaim:
    return StartupClaim(
        id=CLAIM_ID,
        case_id=CASE_ID,
        text_ref="c" * 64,
        text_hash="c" * 64,
        category=ClaimCategory.ARR,
        source_artifact_id=ARTIFACT_ID,
        locator=SourceLocator(kind="startup_claim", value="arr", artifact_id=ARTIFACT_ID),
        criticality=ClaimCriticality.CRITICAL,
        evidence_query="arr q2 2026",
        normalized_name="arr",
        normalized_value=Decimal("1200000"),
        unit="USD",
        period="Q2 2026",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.82"),
        extracted_at=AS_OF,
    )


def _fact() -> EvidenceFact:
    return EvidenceFact(
        id=FACT_ID,
        artifact_id=ARTIFACT_ID,
        name="arr",
        value=Decimal("1200000"),
        value_type="decimal",
        unit="USD",
        period="Q2 2026",
        locator=SourceLocator(kind="startup_fact", value="arr", artifact_id=ARTIFACT_ID),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.82"),
        source_priority=1,
        extraction_method="startup-parser",
        supporting_text_hash="sha256:" + "d" * 64,
        source_freshness_at=AS_OF,
        retrieved_at=AS_OF,
        metadata={"startup_claim_id": str(CLAIM_ID), "private_raw": PRIVATE_SENTINEL},
    )


def _calculation() -> Calculation:
    return Calculation(
        id=CALCULATION_ID,
        case_id=CASE_ID,
        metric_name="gross_margin",
        formula_version="startup-gross-margin@1",
        input_fact_ids=(FACT_ID,),
        value=Decimal("0.72"),
        unit="ratio",
        period="Q2 2026",
        warnings=(),
        calculated_at=AS_OF,
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )


def _finding() -> Finding:
    return Finding(
        id=FINDING_ID,
        case_id=CASE_ID,
        category="risk",
        severity=FindingSeverity.MEDIUM,
        claim=PRIVATE_SENTINEL,
        evidence_fact_ids=(FACT_ID,),
        calculation_ids=(CALCULATION_ID,),
        confidence=Decimal("0.55"),
        status=FindingStatus.REQUIRES_REVIEW,
        author_node="risk_analysis",
        author_model="startup-provider@fixture",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=AS_OF,
    )


def _sha256(path: Path) -> str:
    from hashlib import sha256

    return sha256(path.read_bytes()).hexdigest()


def _sha256_hex(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode("utf-8")).hexdigest()


def _html_section_order(html: str) -> tuple[str, ...]:
    return tuple(
        segment.split('"', 1)[0]
        for segment in html.split('<section id="')[1:]
    )

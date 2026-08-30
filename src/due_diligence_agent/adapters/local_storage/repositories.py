from json import dumps
import sqlite3
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.domain.approvals.models import Approval, ContradictionDecision
from due_diligence_agent.domain.artifacts.models import Artifact
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import StartupClaim
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot
from due_diligence_agent.domain.startup.profile import StartupProfile, StartupProfileAnalysisStage


ModelT = TypeVar("ModelT", bound=BaseModel)


def _canonical_json(model: BaseModel) -> str:
    return dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _startup_claim_json(claim: StartupClaim) -> str:
    payload = claim.model_dump(mode="json")
    payload["normalized_value"] = (
        str(claim.normalized_value) if claim.normalized_value is not None else None
    )
    return dumps(payload, sort_keys=True, separators=(",", ":"))


def _load_model(model_type: type[ModelT], payload: str) -> ModelT:
    return model_type.model_validate_json(payload)


def _insert(db: SQLiteDatabase, sql: str, parameters: tuple[str, ...], duplicate: str) -> None:
    try:
        db.execute(sql, parameters)
    except sqlite3.IntegrityError as exc:
        message = str(exc).lower()
        if "foreign key constraint failed" in message:
            raise ValueError("referential_integrity_violation") from exc
        if "unique constraint failed" in message or "primary key" in message:
            raise ValueError(duplicate) from exc
        raise


class LocalCaseRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, case: DueDiligenceCase) -> None:
        _insert(
            self._db,
            "INSERT INTO cases (id, payload) VALUES (?, ?)",
            (str(case.case_id), _canonical_json(case)),
            "case_already_exists",
        )

    def get(self, case_id: UUID) -> DueDiligenceCase:
        row = self._db.fetch_one("SELECT payload FROM cases WHERE id = ?", (str(case_id),))
        if row is None:
            raise KeyError(f"case_not_found:{case_id}")
        return _load_model(DueDiligenceCase, str(row["payload"]))

    def advance_data_revision(
        self,
        case_id: UUID,
        *,
        expected_revision: int,
        updated_case: DueDiligenceCase,
    ) -> DueDiligenceCase:
        if updated_case.case_id != case_id:
            raise ValueError("case_id_mismatch")
        if updated_case.data_revision != expected_revision + 1:
            raise ValueError("case_data_revision_must_advance_by_one")
        current = self.get(case_id)
        if current.data_revision != expected_revision:
            raise ValueError("case_data_revision_conflict")
        if updated_case.created_at != current.created_at:
            raise ValueError("case_created_at_mismatch")
        updated = self._db.compare_and_swap_payload(
            table="cases",
            id_column="id",
            id_value=str(case_id),
            expected_json_path="$.data_revision",
            expected_value=expected_revision,
            new_payload=_canonical_json(updated_case),
        )
        if not updated:
            raise ValueError("case_data_revision_conflict")
        return updated_case

    def restore_data_revision(
        self,
        case_id: UUID,
        *,
        expected_revision: int,
        restored_case: DueDiligenceCase,
    ) -> DueDiligenceCase:
        if restored_case.case_id != case_id:
            raise ValueError("case_id_mismatch")
        current = self.get(case_id)
        if current.data_revision != expected_revision:
            raise ValueError("case_data_revision_conflict")
        if restored_case.data_revision >= expected_revision:
            raise ValueError("case_data_revision_restore_must_decrease")
        if restored_case.created_at != current.created_at:
            raise ValueError("case_created_at_mismatch")
        updated = self._db.compare_and_swap_payload(
            table="cases",
            id_column="id",
            id_value=str(case_id),
            expected_json_path="$.data_revision",
            expected_value=expected_revision,
            new_payload=_canonical_json(restored_case),
        )
        if not updated:
            raise ValueError("case_data_revision_conflict")
        return restored_case


class LocalArtifactRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, artifact: Artifact) -> None:
        _insert(
            self._db,
            "INSERT INTO artifacts (id, case_id, payload) VALUES (?, ?, ?)",
            (str(artifact.id), str(artifact.case_id), _canonical_json(artifact)),
            "artifact_already_exists",
        )

    def get(self, artifact_id: UUID) -> Artifact:
        row = self._db.fetch_one("SELECT payload FROM artifacts WHERE id = ?", (str(artifact_id),))
        if row is None:
            raise KeyError(f"artifact_not_found:{artifact_id}")
        return _load_model(Artifact, str(row["payload"]))

    def case_id_for_artifact(self, artifact_id: UUID) -> UUID:
        row = self._db.fetch_one("SELECT case_id FROM artifacts WHERE id = ?", (str(artifact_id),))
        if row is None:
            raise KeyError(f"artifact_not_found:{artifact_id}")
        return UUID(str(row["case_id"]))

    def list_for_case(self, case_id: UUID) -> list[Artifact]:
        rows = self._db.fetch_all(
            "SELECT payload FROM artifacts WHERE case_id = ? ORDER BY id",
            (str(case_id),),
        )
        return [_load_model(Artifact, str(row["payload"])) for row in rows]


class LocalEvidenceRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, fact: EvidenceFact) -> None:
        try:
            case_id = LocalArtifactRepository(self._db).case_id_for_artifact(fact.artifact_id)
        except KeyError as exc:
            raise ValueError("referential_integrity_violation") from exc
        _insert(
            self._db,
            """
            INSERT INTO evidence_facts (id, artifact_id, case_id, sort_key, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(fact.id),
                str(fact.artifact_id),
                str(case_id),
                fact.name,
                _canonical_json(fact),
            ),
            "evidence_fact_already_exists",
        )

    def list_for_case(self, case_id: UUID) -> list[EvidenceFact]:
        rows = self._db.fetch_all(
            """
            SELECT payload FROM evidence_facts
            WHERE case_id = ?
            ORDER BY sort_key, id
            """,
            (str(case_id),),
        )
        return [_load_model(EvidenceFact, str(row["payload"])) for row in rows]

    def list_for_artifact(self, artifact_id: UUID) -> list[EvidenceFact]:
        rows = self._db.fetch_all(
            """
            SELECT payload FROM evidence_facts
            WHERE artifact_id = ?
            ORDER BY sort_key, id
            """,
            (str(artifact_id),),
        )
        return [_load_model(EvidenceFact, str(row["payload"])) for row in rows]


class LocalCalculationRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, calculation: Calculation) -> None:
        _insert(
            self._db,
            """
            INSERT INTO calculations (id, case_id, sort_key, payload)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(calculation.id),
                str(calculation.case_id),
                calculation.metric_name,
                _canonical_json(calculation),
            ),
            "calculation_already_exists",
        )

    def list_for_case(self, case_id: UUID) -> list[Calculation]:
        rows = self._db.fetch_all(
            "SELECT payload FROM calculations WHERE case_id = ? ORDER BY sort_key, id",
            (str(case_id),),
        )
        return [_load_model(Calculation, str(row["payload"])) for row in rows]


class LocalFindingRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, finding: Finding) -> None:
        _insert(
            self._db,
            "INSERT INTO findings (id, case_id, sort_key, payload) VALUES (?, ?, ?, ?)",
            (str(finding.id), str(finding.case_id), finding.category, _canonical_json(finding)),
            "finding_already_exists",
        )

    def list_for_case(self, case_id: UUID) -> list[Finding]:
        rows = self._db.fetch_all(
            "SELECT payload FROM findings WHERE case_id = ? ORDER BY sort_key, id",
            (str(case_id),),
        )
        return [_load_model(Finding, str(row["payload"])) for row in rows]


class LocalStartupClaimRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, claim: StartupClaim) -> None:
        _insert(
            self._db,
            """
            INSERT INTO startup_claims (id, case_id, source_artifact_id, sort_key, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(claim.id),
                str(claim.case_id),
                str(claim.source_artifact_id),
                claim.normalized_name,
                _startup_claim_json(claim),
            ),
            "startup_claim_already_exists",
        )

    def get(self, claim_id: UUID) -> StartupClaim | None:
        row = self._db.fetch_one("SELECT payload FROM startup_claims WHERE id = ?", (str(claim_id),))
        if row is None:
            return None
        return _load_model(StartupClaim, str(row["payload"]))

    def list_for_case(self, case_id: UUID) -> list[StartupClaim]:
        rows = self._db.fetch_all(
            """
            SELECT payload FROM startup_claims
            WHERE case_id = ?
            ORDER BY sort_key, id
            """,
            (str(case_id),),
        )
        return [_load_model(StartupClaim, str(row["payload"])) for row in rows]


class LocalParsedStartupArtifactRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, parsed_artifact: ParsedStartupArtifact) -> None:
        payload = _canonical_json(parsed_artifact)
        try:
            self._db.execute(
                """
                INSERT INTO startup_parse_results
                    (artifact_id, case_id, kind, status, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(parsed_artifact.artifact_id),
                    str(parsed_artifact.case_id),
                    str(parsed_artifact.kind),
                    str(parsed_artifact.status),
                    payload,
                ),
            )
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "foreign key constraint failed" in message:
                raise ValueError("referential_integrity_violation") from exc
            existing = self._db.fetch_one(
                "SELECT payload FROM startup_parse_results WHERE artifact_id = ?",
                (str(parsed_artifact.artifact_id),),
            )
            if existing is not None and str(existing["payload"]) == payload:
                return
            raise ValueError("parsed_startup_artifact_conflict") from exc

    def get_for_case(self, case_id: UUID, artifact_id: UUID) -> ParsedStartupArtifact:
        row = self._db.fetch_one(
            """
            SELECT payload FROM startup_parse_results
            WHERE case_id = ? AND artifact_id = ?
            """,
            (str(case_id), str(artifact_id)),
        )
        if row is None:
            raise KeyError(f"parsed_startup_artifact_not_found:{case_id}:{artifact_id}")
        return _load_model(ParsedStartupArtifact, str(row["payload"]))

    def list_for_case(self, case_id: UUID) -> list[ParsedStartupArtifact]:
        rows = self._db.fetch_all(
            """
            SELECT payload FROM startup_parse_results
            WHERE case_id = ?
            ORDER BY artifact_id
            """,
            (str(case_id),),
        )
        return [_load_model(ParsedStartupArtifact, str(row["payload"])) for row in rows]


class LocalStartupProfileRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, profile: StartupProfile) -> None:
        payload = _canonical_json(profile)
        try:
            self._db.execute(
                """
                INSERT INTO startup_profiles
                    (id, case_id, data_revision, analysis_stage, profile_hash, built_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(profile.profile_id),
                    str(profile.case_id),
                    str(profile.data_revision),
                    str(profile.analysis_stage),
                    profile.profile_hash,
                    profile.built_at.isoformat(),
                    payload,
                ),
            )
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "foreign key constraint failed" in message:
                raise ValueError("referential_integrity_violation") from exc
            existing = self._db.fetch_one(
                "SELECT payload FROM startup_profiles WHERE id = ?",
                (str(profile.profile_id),),
            )
            if existing is not None and str(existing["payload"]) == payload:
                return
            raise ValueError("startup_profile_conflict") from exc

    def get(self, profile_id: UUID) -> StartupProfile:
        row = self._db.fetch_one(
            "SELECT payload FROM startup_profiles WHERE id = ?",
            (str(profile_id),),
        )
        if row is None:
            raise KeyError(f"startup_profile_not_found:{profile_id}")
        return _load_model(StartupProfile, str(row["payload"]))

    def list_for_case(self, case_id: UUID) -> list[StartupProfile]:
        rows = self._db.fetch_all(
            """
            SELECT payload FROM startup_profiles
            WHERE case_id = ?
            ORDER BY
                data_revision,
                CASE analysis_stage WHEN 'primary' THEN 0 WHEN 'enriched' THEN 1 ELSE 2 END,
                built_at,
                id
            """,
            (str(case_id),),
        )
        return [_load_model(StartupProfile, str(row["payload"])) for row in rows]

    def get_for_stage(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile:
        row = self._db.fetch_one(
            """
            SELECT payload FROM startup_profiles
            WHERE case_id = ? AND data_revision = ? AND analysis_stage = ?
            ORDER BY built_at DESC, id DESC
            LIMIT 1
            """,
            (str(case_id), str(data_revision), str(stage)),
        )
        if row is None:
            raise KeyError(f"startup_profile_stage_not_found:{case_id}:{data_revision}:{stage}")
        return _load_model(StartupProfile, str(row["payload"]))

    def get_current(self, case_id: UUID) -> StartupProfile:
        case = LocalCaseRepository(self._db).get(case_id)
        enriched = self._maybe_get_for_stage(
            case_id,
            case.data_revision,
            StartupProfileAnalysisStage.ENRICHED,
        )
        if enriched is not None:
            return enriched
        return self.get_for_stage(case_id, case.data_revision, StartupProfileAnalysisStage.PRIMARY)

    def _maybe_get_for_stage(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile | None:
        try:
            return self.get_for_stage(case_id, data_revision, stage)
        except KeyError:
            return None


class LocalContradictionRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, contradiction: Contradiction) -> None:
        _insert(
            self._db,
            """
            INSERT INTO contradictions (id, case_id, sort_key, payload)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(contradiction.id),
                str(contradiction.case_id),
                contradiction.conflict_type,
                _canonical_json(contradiction),
            ),
            "contradiction_already_exists",
        )

    def replace(self, contradiction: Contradiction) -> None:
        cursor = self._db.execute(
            """
            UPDATE contradictions
            SET sort_key = ?, payload = ?
            WHERE id = ? AND case_id = ?
            """,
            (
                contradiction.conflict_type,
                _canonical_json(contradiction),
                str(contradiction.id),
                str(contradiction.case_id),
            ),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"contradiction_not_found:{contradiction.id}")

    def list_for_case(self, case_id: UUID) -> list[Contradiction]:
        rows = self._db.fetch_all(
            "SELECT payload FROM contradictions WHERE case_id = ? ORDER BY sort_key, id",
            (str(case_id),),
        )
        return [_load_model(Contradiction, str(row["payload"])) for row in rows]

    def get(self, contradiction_id: UUID) -> Contradiction:
        row = self._db.fetch_one(
            "SELECT payload FROM contradictions WHERE id = ?", (str(contradiction_id),)
        )
        if row is None:
            raise KeyError(f"contradiction_not_found:{contradiction_id}")
        return _load_model(Contradiction, str(row["payload"]))


class LocalApprovalRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, approval: Approval) -> None:
        _insert(
            self._db,
            "INSERT INTO approvals (id, case_id, sort_key, payload) VALUES (?, ?, ?, ?)",
            (str(approval.id), str(approval.case_id), approval.gate, _canonical_json(approval)),
            "approval_already_exists",
        )

    def list_for_case(self, case_id: UUID) -> list[Approval]:
        rows = self._db.fetch_all(
            "SELECT payload FROM approvals WHERE case_id = ? ORDER BY sort_key, id",
            (str(case_id),),
        )
        return [_load_model(Approval, str(row["payload"])) for row in rows]


class LocalContradictionDecisionRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add(self, decision: ContradictionDecision) -> None:
        payload = _canonical_json(decision)
        try:
            self._db.execute(
                """
                INSERT INTO contradiction_decisions
                    (id, case_id, contradiction_id, approval_id, action, data_revision, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(decision.id),
                    str(decision.case_id),
                    str(decision.contradiction_id),
                    str(decision.approval_id),
                    decision.action,
                    decision.data_revision,
                    payload,
                ),
            )
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "foreign key constraint failed" in message:
                raise ValueError("referential_integrity_violation") from exc
            existing = self._db.fetch_one(
                "SELECT payload FROM contradiction_decisions WHERE id = ?", (str(decision.id),)
            )
            if existing is not None and str(existing["payload"]) == payload:
                return
            raise ValueError("contradiction_decision_conflict") from exc

    def list_for_case(self, case_id: UUID) -> list[ContradictionDecision]:
        rows = self._db.fetch_all(
            """
            SELECT payload FROM contradiction_decisions
            WHERE case_id = ?
            ORDER BY data_revision, id
            """,
            (str(case_id),),
        )
        return [_load_model(ContradictionDecision, str(row["payload"])) for row in rows]


class LocalReportRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def add_snapshot(self, snapshot: ReportSnapshot) -> None:
        _insert(
            self._db,
            """
            INSERT INTO report_snapshots (id, case_id, created_at, payload)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(snapshot.id),
                str(snapshot.case_id),
                snapshot.created_at.isoformat(),
                _canonical_json(snapshot),
            ),
            "report_snapshot_already_exists",
        )

    def get_snapshot(self, snapshot_id: UUID) -> ReportSnapshot:
        row = self._db.fetch_one(
            "SELECT payload FROM report_snapshots WHERE id = ?", (str(snapshot_id),)
        )
        if row is None:
            raise KeyError(f"report_snapshot_not_found:{snapshot_id}")
        return _load_model(ReportSnapshot, str(row["payload"]))

    def list_for_case(self, case_id: UUID) -> list[ReportSnapshot]:
        rows = self._db.fetch_all(
            """
            SELECT payload FROM report_snapshots
            WHERE case_id = ?
            ORDER BY created_at, id
            """,
            (str(case_id),),
        )
        return [_load_model(ReportSnapshot, str(row["payload"])) for row in rows]

    def get_current_draft(self, case_id: UUID) -> ReportSnapshot | None:
        snapshots = self.list_for_case(case_id)
        drafts = [snapshot for snapshot in snapshots if snapshot.pdf_artifact_ref is None]
        return drafts[-1] if drafts else None


class LocalReviewRepository:
    def __init__(
        self,
        *,
        artifact_repository: LocalArtifactRepository,
        evidence_repository: LocalEvidenceRepository,
        calculation_repository: LocalCalculationRepository,
        finding_repository: LocalFindingRepository,
        contradiction_repository: LocalContradictionRepository,
        report_repository: LocalReportRepository,
        approval_repository: LocalApprovalRepository,
        decision_repository: LocalContradictionDecisionRepository,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.evidence_repository = evidence_repository
        self.calculation_repository = calculation_repository
        self.finding_repository = finding_repository
        self.contradiction_repository = contradiction_repository
        self.report_repository = report_repository
        self.approval_repository = approval_repository
        self.decision_repository = decision_repository

    def list_facts_for_artifact(self, artifact_id: UUID) -> list[EvidenceFact]:
        return self.evidence_repository.list_for_artifact(artifact_id)

    def list_calculations_for_facts(self, fact_ids: set[UUID]) -> list[Calculation]:
        if not fact_ids:
            return []
        case_id = self._case_id_from_facts(fact_ids)
        return [
            calculation
            for calculation in self.calculation_repository.list_for_case(case_id)
            if set(calculation.input_fact_ids) & fact_ids
        ]

    def list_findings_for_dependencies(
        self, fact_ids: set[UUID], calculation_ids: set[UUID]
    ) -> list[Finding]:
        case_id = self._case_id_from_dependencies(fact_ids, calculation_ids)
        return [
            finding
            for finding in self.finding_repository.list_for_case(case_id)
            if set(finding.evidence_fact_ids) & fact_ids
            or set(finding.calculation_ids) & calculation_ids
            or set(finding.counter_evidence_fact_ids) & fact_ids
        ]

    def list_contradictions_for_dependencies(
        self, fact_ids: set[UUID], finding_ids: set[UUID]
    ) -> list[Contradiction]:
        case_id = self._case_id_from_dependencies(fact_ids, set())
        return [
            contradiction
            for contradiction in self.contradiction_repository.list_for_case(case_id)
            if set(contradiction.fact_ids) & fact_ids
            or set(contradiction.finding_ids) & finding_ids
        ]

    def list_report_snapshots_for_case(self, case_id: UUID) -> list[ReportSnapshot]:
        return self.report_repository.list_for_case(case_id)

    def get_snapshot(self, snapshot_id: UUID) -> ReportSnapshot:
        return self.report_repository.get_snapshot(snapshot_id)

    def get_current_draft(self, case_id: UUID) -> ReportSnapshot | None:
        return self.report_repository.get_current_draft(case_id)

    def get_contradiction(self, contradiction_id: UUID) -> Contradiction:
        return self.contradiction_repository.get(contradiction_id)

    def add_approval(self, approval: Approval) -> None:
        try:
            self.approval_repository.add(approval)
        except ValueError as exc:
            if str(exc) != "approval_already_exists":
                raise

    def add_decision(self, decision: ContradictionDecision) -> None:
        self.decision_repository.add(decision)

    def current_data_revision(self, case_id: UUID | None = None) -> int:
        if case_id is None:
            return 1
        decisions = self.decision_repository.list_for_case(case_id)
        if not decisions:
            return 1
        return max(decision.data_revision for decision in decisions)

    def next_data_revision(self, case_id: UUID) -> int:
        return self.current_data_revision(case_id) + 1

    def _case_id_from_facts(self, fact_ids: set[UUID]) -> UUID:
        for fact_id in fact_ids:
            row = self.evidence_repository._db.fetch_one(
                "SELECT case_id FROM evidence_facts WHERE id = ?", (str(fact_id),)
            )
            if row is not None:
                return UUID(str(row["case_id"]))
        raise KeyError("fact_not_found")

    def _case_id_from_dependencies(self, fact_ids: set[UUID], calculation_ids: set[UUID]) -> UUID:
        if fact_ids:
            return self._case_id_from_facts(fact_ids)
        for calculation_id in calculation_ids:
            row = self.calculation_repository._db.fetch_one(
                "SELECT case_id FROM calculations WHERE id = ?", (str(calculation_id),)
            )
            if row is not None:
                return UUID(str(row["case_id"]))
        raise KeyError("dependency_not_found")

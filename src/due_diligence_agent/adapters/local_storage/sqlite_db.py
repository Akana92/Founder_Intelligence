from collections.abc import Iterable
from pathlib import Path
import sqlite3
from threading import RLock
from types import TracebackType
from typing import Any, Self, cast


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                cursor = self._connection.execute(sql, tuple(parameters))
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
            return cursor

    def fetch_one(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return cast(
                sqlite3.Row | None, self._connection.execute(sql, tuple(parameters)).fetchone()
            )

    def fetch_all(self, sql: str, parameters: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._connection.execute(sql, tuple(parameters)).fetchall())

    def compare_and_swap_payload(
        self,
        *,
        table: str,
        id_column: str,
        id_value: str,
        expected_json_path: str,
        expected_value: Any,
        new_payload: str,
    ) -> bool:
        if table != "cases" or id_column != "id" or expected_json_path != "$.data_revision":
            raise ValueError("unsupported_compare_and_swap")
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE cases
                SET payload = ?
                WHERE id = ? AND json_extract(payload, '$.data_revision') = ?
                """,
                (new_payload, id_value, expected_value),
            )
            if cursor.rowcount == 1:
                self._connection.commit()
                return True
            self._connection.rollback()
            return False

    def table_names(self) -> list[str]:
        rows = self.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        return [str(row["name"]) for row in rows]

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                payload TEXT NOT NULL,
                UNIQUE (id, case_id)
            );
            CREATE INDEX IF NOT EXISTS idx_artifacts_case_id ON artifacts(case_id, id);

            CREATE TABLE IF NOT EXISTS evidence_facts (
                id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                sort_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                FOREIGN KEY (artifact_id, case_id)
                    REFERENCES artifacts(id, case_id) ON DELETE RESTRICT,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_facts_case_id
                ON evidence_facts(case_id, sort_key, id);

            CREATE TABLE IF NOT EXISTS calculations (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                sort_key TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_calculations_case_id
                ON calculations(case_id, sort_key, id);

            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                sort_key TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_findings_case_id ON findings(case_id, sort_key, id);

            CREATE TABLE IF NOT EXISTS startup_claims (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                source_artifact_id TEXT NOT NULL,
                sort_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                FOREIGN KEY (source_artifact_id, case_id)
                    REFERENCES artifacts(id, case_id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_startup_claims_case_id
                ON startup_claims(case_id, sort_key, id);

            CREATE TABLE IF NOT EXISTS startup_parse_results (
                artifact_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                FOREIGN KEY (artifact_id, case_id)
                    REFERENCES artifacts(id, case_id) ON DELETE RESTRICT,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_startup_parse_results_case_id
                ON startup_parse_results(case_id, artifact_id);

            CREATE TABLE IF NOT EXISTS startup_profiles (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                data_revision INTEGER NOT NULL,
                analysis_stage TEXT NOT NULL,
                profile_hash TEXT NOT NULL,
                built_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (case_id, data_revision, analysis_stage, profile_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_startup_profiles_case_revision_stage
                ON startup_profiles(case_id, data_revision, analysis_stage, built_at, id);

            CREATE TABLE IF NOT EXISTS contradictions (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                sort_key TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_contradictions_case_id
                ON contradictions(case_id, sort_key, id);

            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                sort_key TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_approvals_case_id ON approvals(case_id, sort_key, id);

            CREATE TABLE IF NOT EXISTS contradiction_decisions (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                contradiction_id TEXT NOT NULL REFERENCES contradictions(id) ON DELETE RESTRICT,
                approval_id TEXT NOT NULL REFERENCES approvals(id) ON DELETE RESTRICT,
                action TEXT NOT NULL,
                data_revision INTEGER NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (case_id, contradiction_id, action, data_revision)
            );
            CREATE INDEX IF NOT EXISTS idx_contradiction_decisions_case_id
                ON contradiction_decisions(case_id, data_revision, id);

            CREATE TABLE IF NOT EXISTS report_snapshots (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_report_snapshots_case_id
                ON report_snapshots(case_id, created_at, id);

            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
                node_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_case_id
                ON workflow_checkpoints(case_id, created_at, id);
            """
        )
        self._connection.commit()

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from json import dumps, loads
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel

from due_diligence_agent.domain.startup.assets import CaseAssetDraft
from due_diligence_agent.domain.startup.case_intake import FounderStatement
from due_diligence_agent.domain.startup.copilot import CopilotThread
from due_diligence_agent.domain.startup.scenario import ScenarioInput, ScenarioSelectionRecord, StartupScenarioSet
from due_diligence_agent.ports.repositories import CaseResearchJob, CaseResearchPlan


ModelT = TypeVar("ModelT", bound=BaseModel)


class CaseScopeError(KeyError):
    pass


class CaseStaleRevisionError(ValueError):
    pass


class _JsonCaseRepository(Generic[ModelT]):
    _schema_version = "case_copilot_repository@1"

    def __init__(
        self,
        root: Path,
        *,
        file_name: str,
        model_type: type[ModelT],
        id_field: str,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        self._root = root
        self._path = root / "case-copilot" / f"{file_name}.json"
        self._model_type = model_type
        self._id_field = id_field
        self._current_revision = current_revision

    def save(
        self,
        value: ModelT,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> ModelT:
        case_id = _case_id(value)
        normalized_idempotency_key = _idempotency_key(case_id, idempotency_key)
        state = self._read_state()
        replay_key = state["idempotency"].get(normalized_idempotency_key)
        if replay_key is not None:
            if not isinstance(replay_key, str):
                raise ValueError(f"{self._path.stem}_invalid_store")
            return self._load_record(state, replay_key)

        self._validate_revision(case_id, _data_revision(value), expected_revision)
        record_key = _record_key(case_id, _record_id(value, self._id_field))
        state["records"][record_key] = value.model_dump(mode="json")
        state["current_by_case"][str(case_id)] = record_key
        state["idempotency"][normalized_idempotency_key] = record_key
        self._write_state(state)
        return value

    def get_current(self, case_id: UUID) -> ModelT:
        state = self._read_state()
        record_key = state["current_by_case"].get(str(case_id))
        if record_key is None:
            raise KeyError(f"{self._path.stem}_current_not_found:{case_id}")
        if not isinstance(record_key, str):
            raise ValueError(f"{self._path.stem}_invalid_store")
        return self._load_record(state, record_key)

    def get_for_case(self, case_id: UUID, record_id: UUID) -> ModelT:
        state = self._read_state()
        record_key = _record_key(case_id, record_id)
        if record_key in state["records"]:
            return self._load_record(state, record_key)
        foreign_key_suffix = f":{record_id}"
        if any(key.endswith(foreign_key_suffix) for key in state["records"]):
            raise CaseScopeError(f"{self._path.stem}_scope_mismatch:{case_id}:{record_id}")
        raise KeyError(f"{self._path.stem}_not_found:{case_id}:{record_id}")

    def get_by_idempotency(self, case_id: UUID, idempotency_key: str) -> ModelT | None:
        state = self._read_state()
        normalized_idempotency_key = _idempotency_key(case_id, idempotency_key)
        record_key = state["idempotency"].get(normalized_idempotency_key)
        if record_key is None:
            return None
        if not isinstance(record_key, str):
            raise ValueError(f"{self._path.stem}_invalid_store")
        return self._load_record(state, record_key)

    def list_for_case(self, case_id: UUID) -> tuple[ModelT, ...]:
        state = self._read_state()
        prefix = f"{case_id}:"
        return tuple(
            self._model_type.model_validate(payload)
            for key, payload in sorted(state["records"].items())
            if key.startswith(prefix)
        )

    def list_all(self) -> tuple[ModelT, ...]:
        state = self._read_state()
        return tuple(
            self._model_type.model_validate(payload)
            for _key, payload in sorted(state["records"].items())
        )

    def delete_for_case(self, case_id: UUID, record_id: UUID) -> None:
        state = self._read_state()
        record_key = _record_key(case_id, record_id)
        if record_key not in state["records"]:
            raise KeyError(f"{self._path.stem}_not_found:{case_id}:{record_id}")
        del state["records"][record_key]
        for key, value in list(state["idempotency"].items()):
            if value == record_key:
                del state["idempotency"][key]
        if state["current_by_case"].get(str(case_id)) == record_key:
            prefix = f"{case_id}:"
            remaining = sorted(key for key in state["records"] if key.startswith(prefix))
            if remaining:
                state["current_by_case"][str(case_id)] = remaining[-1]
            else:
                state["current_by_case"].pop(str(case_id), None)
        self._write_state(state)

    def _validate_revision(
        self,
        case_id: UUID,
        value_revision: int,
        expected_revision: int,
    ) -> None:
        if expected_revision < 1:
            raise CaseStaleRevisionError("case_revision_conflict")
        current_revision = (
            self._current_revision(case_id)
            if self._current_revision is not None
            else expected_revision
        )
        if current_revision != expected_revision or value_revision != expected_revision:
            raise CaseStaleRevisionError("case_revision_conflict")

    def _read_state(self) -> dict[str, dict[str, object]]:
        if not self._path.exists():
            return {
                "records": {},
                "current_by_case": {},
                "idempotency": {},
            }
        loaded = loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or loaded.get("schema_version") != self._schema_version:
            raise ValueError(f"{self._path.stem}_invalid_store")
        records = loaded.get("records")
        current_by_case = loaded.get("current_by_case")
        idempotency = loaded.get("idempotency")
        if not isinstance(records, dict) or not isinstance(current_by_case, dict) or not isinstance(idempotency, dict):
            raise ValueError(f"{self._path.stem}_invalid_store")
        return {
            "records": dict(records),
            "current_by_case": dict(current_by_case),
            "idempotency": dict(idempotency),
        }

    def _write_state(self, state: dict[str, dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = dumps(
            {
                "schema_version": self._schema_version,
                **state,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                "wb",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, self._path)
            _fsync_directory(self._path.parent)
            temp_path = None
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _load_record(self, state: dict[str, dict[str, object]], record_key: str) -> ModelT:
        payload = state["records"].get(record_key)
        if payload is None:
            raise ValueError(f"{self._path.stem}_idempotency_record_missing")
        return self._model_type.model_validate(payload)


class LocalCaseAssumptionRepository(_JsonCaseRepository[FounderStatement]):
    def __init__(
        self,
        root: Path,
        *,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        super().__init__(
            root,
            file_name="founder-statements",
            model_type=FounderStatement,
            id_field="statement_id",
            current_revision=current_revision,
        )

    def get_current(self, case_id: UUID) -> tuple[FounderStatement, ...]:  # type: ignore[override]
        return self.list_for_case(case_id)


LocalFounderStatementRepository = LocalCaseAssumptionRepository


class LocalCaseScenarioRepository(_JsonCaseRepository[StartupScenarioSet]):
    def __init__(
        self,
        root: Path,
        *,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        super().__init__(
            root,
            file_name="scenarios",
            model_type=StartupScenarioSet,
            id_field="scenario_set_id",
            current_revision=current_revision,
        )
        self._selection_records: _JsonCaseRepository[ScenarioSelectionRecord] = _JsonCaseRepository(
            root,
            file_name="scenario-selections",
            model_type=ScenarioSelectionRecord,
            id_field="selection_id",
            current_revision=current_revision,
        )

    def get_selection_by_idempotency(
        self,
        case_id: UUID,
        idempotency_key: str,
    ) -> ScenarioSelectionRecord | None:
        return self._selection_records.get_by_idempotency(case_id, idempotency_key)

    def save_selection(
        self,
        value: ScenarioSelectionRecord,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> ScenarioSelectionRecord:
        return self._selection_records.save(
            value,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )


class LocalCaseCopilotThreadRepository(_JsonCaseRepository[CopilotThread]):
    def __init__(
        self,
        root: Path,
        *,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        super().__init__(
            root,
            file_name="copilot-threads",
            model_type=CopilotThread,
            id_field="thread_id",
            current_revision=current_revision,
        )


class LocalCaseResearchJobRepository(_JsonCaseRepository[CaseResearchJob]):
    def __init__(
        self,
        root: Path,
        *,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        super().__init__(
            root,
            file_name="research-jobs",
            model_type=CaseResearchJob,
            id_field="job_id",
            current_revision=current_revision,
        )
        self._defer_interrupted_running_jobs()

    def _defer_interrupted_running_jobs(self) -> None:
        state = self._read_state()
        changed = False
        now = datetime.now(UTC).isoformat()
        for key, payload in list(state["records"].items()):
            if not isinstance(payload, dict) or payload.get("status") != "running":
                continue
            state["records"][key] = {
                **payload,
                "status": "deferred",
                "reason": "research_interrupted",
                "updated_at": now,
            }
            changed = True
        if changed:
            self._write_state(state)


class LocalCaseResearchPlanRepository(_JsonCaseRepository[CaseResearchPlan]):
    def __init__(
        self,
        root: Path,
        *,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        super().__init__(
            root,
            file_name="research-plans",
            model_type=CaseResearchPlan,
            id_field="plan_id",
            current_revision=current_revision,
        )


class LocalPublicBenchmarkRepository(_JsonCaseRepository[ScenarioInput]):
    def __init__(
        self,
        root: Path,
        *,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        super().__init__(
            root,
            file_name="public-benchmarks",
            model_type=ScenarioInput,
            id_field="input_id",
            current_revision=current_revision,
        )

    def get_current(self, case_id: UUID) -> tuple[ScenarioInput, ...]:  # type: ignore[override]
        return self.list_for_case(case_id)


class LocalCaseAssetRepository(_JsonCaseRepository[CaseAssetDraft]):
    def __init__(
        self,
        root: Path,
        *,
        current_revision: Callable[[UUID], int] | None = None,
    ) -> None:
        super().__init__(
            root,
            file_name="asset-drafts",
            model_type=CaseAssetDraft,
            id_field="draft_id",
            current_revision=current_revision,
        )


def _case_id(value: BaseModel) -> UUID:
    return UUID(str(getattr(value, "case_id")))


def _data_revision(value: BaseModel) -> int:
    revision = getattr(value, "data_revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise ValueError("case_data_revision_invalid")
    return revision


def _record_id(value: BaseModel, id_field: str) -> UUID:
    return UUID(str(getattr(value, id_field)))


def _record_key(case_id: UUID, record_id: UUID) -> str:
    return f"{case_id}:{record_id}"


def _idempotency_key(case_id: UUID, idempotency_key: str) -> str:
    normalized = idempotency_key.strip()
    if not normalized:
        raise ValueError("idempotency_key_required")
    return f"{case_id}:{normalized}"


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


__all__ = [
    "CaseScopeError",
    "CaseStaleRevisionError",
    "LocalCaseAssetRepository",
    "LocalCaseAssumptionRepository",
    "LocalCaseCopilotThreadRepository",
    "LocalCaseResearchJobRepository",
    "LocalCaseResearchPlanRepository",
    "LocalCaseScenarioRepository",
    "LocalFounderStatementRepository",
    "LocalPublicBenchmarkRepository",
]

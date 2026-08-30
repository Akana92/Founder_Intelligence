from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib import import_module
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
from time import sleep
from typing import Any, Protocol, cast
from uuid import uuid4

from pydantic import BaseModel

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.domain.approvals.startup_disclosure import ClassifiedDisclosureSnapshot

DELETE_RUNTIME_VALUE = object()
_WINDOWS_REPLACE_RETRY_WINERRORS = frozenset({5, 32})
_WINDOWS_REPLACE_RETRY_DELAYS_SECONDS = (0.01, 0.02, 0.04, 0.08)


class StartupWorkflowRuntimeStore(Protocol):
    def load(self, case_id: str) -> dict[str, Any]: ...

    def save(self, case_id: str, values: dict[str, Any]) -> None: ...

    def update(
        self,
        case_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]: ...

    def consume_resume_token(self, case_id: str, *, gate: str, expected_digest: str) -> bool: ...


class InMemoryStartupWorkflowRuntimeStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def load(self, case_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._records.get(case_id, {}))

    def save(self, case_id: str, values: dict[str, Any]) -> None:
        self.update(case_id, lambda _current: values)

    def update(
        self,
        case_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._lock:
            current = dict(self._records.get(case_id, {}))
            _apply_runtime_update(current, mutator(dict(current)))
            self._records[case_id] = current
            return dict(current)

    def consume_resume_token(self, case_id: str, *, gate: str, expected_digest: str) -> bool:
        digest_key = f"{gate}_resume_token_digest"
        used_key = f"{gate}_resume_token_used"
        with self._lock:
            current = dict(self._records.get(case_id, {}))
            digest = current.get(digest_key)
            if (
                not isinstance(digest, str)
                or current.get(used_key)
                or digest != expected_digest
            ):
                return False
            current[digest_key] = None
            current[used_key] = True
            self._records[case_id] = current
            return True


class JsonFileStartupWorkflowRuntimeStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock_path = path.with_suffix(f"{path.suffix}.lock")
        self._lock = Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, case_id: str) -> dict[str, Any]:
        with self._lock, _exclusive_file_lock(self._lock_path):
            records = self._read_all()
        raw = records.get(case_id, {})
        if not isinstance(raw, dict):
            return {}
        return {str(key): _decode_json_safe(value) for key, value in raw.items()}

    def save(self, case_id: str, values: dict[str, Any]) -> None:
        self.update(case_id, lambda _current: values)

    def update(
        self,
        case_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._lock, _exclusive_file_lock(self._lock_path):
            records = self._read_all()
            raw_current = records.get(case_id, {})
            current = _decode_runtime_record(raw_current)
            values = mutator(dict(current))
            _apply_runtime_update(current, values)
            records[case_id] = {
                key: _encode_json_safe(value) for key, value in current.items()
            }
            self._write_all(records)
            return dict(current)

    def consume_resume_token(self, case_id: str, *, gate: str, expected_digest: str) -> bool:
        digest_key = f"{gate}_resume_token_digest"
        used_key = f"{gate}_resume_token_used"
        with self._lock, _exclusive_file_lock(self._lock_path):
            records = self._read_all()
            current = records.get(case_id, {})
            if not isinstance(current, dict):
                return False
            digest = current.get(digest_key)
            if (
                not isinstance(digest, str)
                or current.get(used_key)
                or digest != expected_digest
            ):
                return False
            current[digest_key] = None
            current[used_key] = True
            records[case_id] = current
            self._write_all(records)
            return True

    def _read_all(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("startup_runtime_store_invalid")
        return data

    def _write_all(self, records: dict[str, Any]) -> None:
        temp = self._path.with_name(f"{self._path.name}.{uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(records, sort_keys=True), encoding="utf-8")
            _replace_with_transient_windows_retry(temp, self._path)
        finally:
            temp.unlink(missing_ok=True)


def _replace_with_transient_windows_retry(source: Path, target: Path) -> None:
    # Windows scanners and indexers can briefly hold a freshly written temp file. Retry only
    # access/share violations; every other filesystem error still fails closed immediately.
    for delay_seconds in _WINDOWS_REPLACE_RETRY_DELAYS_SECONDS:
        try:
            source.replace(target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in _WINDOWS_REPLACE_RETRY_WINERRORS:
                raise
            sleep(delay_seconds)
    source.replace(target)


class SQLiteStartupWorkflowRuntimeStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS startup_workflow_runtime (
                    case_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def load(self, case_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM startup_workflow_runtime WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if row is None:
            return {}
        raw = json.loads(str(row[0]))
        if not isinstance(raw, dict):
            raise ValueError("startup_runtime_store_invalid")
        return {str(key): _decode_json_safe(value) for key, value in raw.items()}

    def save(self, case_id: str, values: dict[str, Any]) -> None:
        self.update(case_id, lambda _current: values)

    def update(
        self,
        case_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM startup_workflow_runtime WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            current = {}
            if row is not None:
                current = _decode_runtime_record(json.loads(str(row[0])))
            values = mutator(dict(current))
            _apply_runtime_update(current, values)
            encoded = {str(key): _encode_json_safe(value) for key, value in current.items()}
            connection.execute(
                """
                INSERT INTO startup_workflow_runtime (case_id, payload)
                VALUES (?, ?)
                ON CONFLICT(case_id) DO UPDATE SET payload = excluded.payload
                """,
                (case_id, json.dumps(encoded, sort_keys=True)),
            )
            connection.commit()
            return dict(current)

    def consume_resume_token(self, case_id: str, *, gate: str, expected_digest: str) -> bool:
        digest_key = f"{gate}_resume_token_digest"
        used_key = f"{gate}_resume_token_used"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM startup_workflow_runtime WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            current = json.loads(str(row[0]))
            if not isinstance(current, dict):
                connection.rollback()
                raise ValueError("startup_runtime_store_invalid")
            digest = current.get(digest_key)
            if (
                not isinstance(digest, str)
                or current.get(used_key)
                or digest != expected_digest
            ):
                connection.rollback()
                return False
            current[digest_key] = None
            current[used_key] = True
            encoded = {str(key): _encode_json_safe(value) for key, value in current.items()}
            connection.execute(
                "UPDATE startup_workflow_runtime SET payload = ? WHERE case_id = ?",
                (json.dumps(encoded, sort_keys=True), case_id),
            )
            connection.commit()
            return True

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=30, isolation_level=None)


def ensure_runtime(dependencies: Any) -> None:
    if not hasattr(dependencies, "_startup_runtime"):
        setattr(dependencies, "_startup_runtime", {})
    if not hasattr(dependencies, "workflow_store"):
        raise ValueError("startup_workflow_runtime_store_required")
    if not hasattr(dependencies, "_startup_disclosure_scope"):
        setattr(dependencies, "_startup_disclosure_scope", None)


def runtime_for(dependencies: Any, case_id: str) -> dict[str, Any]:
    ensure_runtime(dependencies)
    runtime_map = cast(dict[str, dict[str, Any]], getattr(dependencies, "_startup_runtime"))
    if case_id not in runtime_map:
        store = cast(StartupWorkflowRuntimeStore, getattr(dependencies, "workflow_store"))
        runtime_map[case_id] = store.load(case_id)
    return runtime_map[case_id]


def save_runtime(dependencies: Any, case_id: str, values: dict[str, Any]) -> dict[str, Any]:
    runtime = runtime_for(dependencies, case_id)
    runtime.update(values)
    store = cast(StartupWorkflowRuntimeStore, getattr(dependencies, "workflow_store"))
    store.save(case_id, values)
    return runtime


def _encode_json_safe(value: Any) -> Any:
    if isinstance(value, ClassifiedDisclosureSnapshot):
        return {
            "__model__": "startup_disclosure_snapshot",
            "payload": value.model_dump(mode="json"),
        }
    if isinstance(value, DisclosureScope):
        return {"__model__": "startup_disclosure_scope", "payload": value.model_dump(mode="json")}
    if isinstance(value, BaseModel):
        raise TypeError(f"unsupported_runtime_model:{type(value).__name__}")
    if isinstance(value, dict):
        return {str(key): _encode_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_encode_json_safe(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"unsupported_runtime_value:{type(value).__name__}")


def _decode_json_safe(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__model__") == "startup_disclosure_snapshot":
        payload = value.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("startup_runtime_snapshot_invalid")
        return ClassifiedDisclosureSnapshot.model_validate(payload)
    if isinstance(value, dict) and value.get("__model__") == "startup_disclosure_scope":
        payload = value.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("startup_runtime_scope_invalid")
        return DisclosureScope.model_validate(payload)
    if isinstance(value, dict):
        return {str(key): _decode_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_json_safe(item) for item in value]
    return value


def _apply_runtime_update(current: dict[str, Any], values: dict[str, Any]) -> None:
    for key, value in values.items():
        if value is DELETE_RUNTIME_VALUE:
            current.pop(key, None)
        else:
            current[key] = value


def _decode_runtime_record(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): _decode_json_safe(value) for key, value in raw.items()}


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl: Any = import_module("fcntl")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

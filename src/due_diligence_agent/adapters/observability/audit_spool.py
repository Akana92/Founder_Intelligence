from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Final

from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.ports.tracing import AuditEvent, TraceSanitizer

_RUN_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}[A-Za-z0-9]$")
_WINDOWS_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
_ALLOWED_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "span",
        "disclosure",
        "startup_disclosure.previewed",
        "startup_disclosure.approved",
        "startup_disclosure.denied",
        "startup_disclosure.invalidated",
        "startup_report.canonical",
        "startup_report.canonical_snapshot",
        "startup_report.gate4_completed",
        "observability.exporter_degraded",
        "observability.langsmith_status",
    }
)
_ALLOWED_SPAN_NAMES: Final[frozenset[str]] = frozenset(
    {
        "workflow.invoke",
        "sec.fetch",
        "document.ingest",
        "chunk.create",
        "embedding.create",
        "retrieval.search",
        "llm.call",
        "analysis.module",
        "report.generate",
        "startup.disclosure_gate",
        "startup.advisor_public_research",
        "startup.public_research",
    }
)
_STARTUP_DISCLOSURE_ATTRIBUTE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "case_id",
        "decision",
        "reason",
        "approval_id",
        "data_revision",
        "content_hash",
        "overall_class",
        "detected_class_count",
        "artifact_count",
        "fragment_count",
        "redaction_policy_version",
        "egress_policy_version",
        "destination",
    }
)
_STARTUP_REPORT_ATTRIBUTE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "case_id",
        "status",
        "report_status",
        "report_id",
        "report_revision",
        "report_checksum",
        "gate4_status",
        "decision",
    }
)
_EXPORTER_DEGRADATION_ATTRIBUTES: Final[dict[str, str]] = {
    "status": "degraded",
    "error_code": "external_export_failed",
    "fallback_used": "local_audit",
}
_LANGSMITH_STATUS_ERROR_CODES: Final[dict[str, frozenset[str]]] = {
    "disabled": frozenset({"tracing_disabled"}),
    "blocked_missing_credential": frozenset({"missing_credential"}),
    "healthy": frozenset({"none"}),
    "degraded": frozenset({"external_export_failed", "telemetry_privacy_rejected"}),
}
_SAFE_STATUS_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_SAFE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_SAFE_HASH_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Fa-f0-9]{32,128}$")
_SAFE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SENSITIVE_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)([\w.+-]+@[\w.-]+\.[a-z]{2,}|bearer[\s_-]*\S+|sk-[\w-]+|"
    r"api[_ -]?key|secret|prompt|output|system\s+instructions|runtimeerror)"
)


class JsonlAuditSpool:
    def __init__(
        self,
        root: Path,
        *,
        max_mb: float = 256,
        sanitizer: TraceSanitizer | None = None,
    ) -> None:
        self.root = root
        self.max_bytes = max(1, int(max_mb * 1024 * 1024))
        self._sanitizer = sanitizer or StrictTraceSanitizer()
        self._lock = RLock()

    def append(self, event: AuditEvent) -> str:
        safe_event = self._validate_event(event)
        line = self._canonical_json(safe_event).encode("utf-8") + b"\n"
        with self._lock:
            path = self._path_for(safe_event)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size + len(line) > self.max_bytes:
                path = self._rotated_path(path, len(line))
            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                self._write_all(fd, line)
                # fsync covers the file bytes on Windows and POSIX. Directory-entry fsync is
                # intentionally not attempted because Windows does not expose a portable variant.
                os.fsync(fd)
            finally:
                os.close(fd)
            return path.as_posix()

    def read_batch(self, limit: int = 100) -> list[AuditEvent]:
        with self._lock:
            if limit < 1:
                return []
            events: list[AuditEvent] = []
            for path in sorted(self.root.rglob("*.jsonl")):
                with path.open("r", encoding="utf-8") as file:
                    for line in file:
                        if not line.strip():
                            continue
                        events.append(AuditEvent(**json.loads(line)))
                        if len(events) >= limit:
                            return events
            return events

    def read_bounded(
        self,
        *,
        max_events: int = 100,
        max_files: int = 128,
        max_bytes: int = 1_048_576,
        max_line_chars: int = 8192,
        newest_first: bool = False,
    ) -> list[AuditEvent]:
        with self._lock:
            if max_events < 1 or max_files < 1 or max_bytes < 1 or max_line_chars < 1:
                return []
            events: list[AuditEvent] = []
            files_seen = 0
            bytes_seen = 0
            for path in self._bounded_jsonl_paths(
                max_files=max_files,
                newest_first=newest_first,
            ):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size <= 0:
                    continue
                if bytes_seen + stat.st_size > max_bytes:
                    break
                bytes_seen += stat.st_size
                files_seen += 1
                with path.open("r", encoding="utf-8") as file:
                    lines: Iterable[str] = reversed(file.readlines()) if newest_first else file
                    for line in lines:
                        if len(line) > max_line_chars:
                            break
                        if not line.strip():
                            continue
                        try:
                            events.append(AuditEvent(**json.loads(line)))
                        except (TypeError, ValueError, json.JSONDecodeError):
                            continue
                        if len(events) >= max_events:
                            return events
                if files_seen >= max_files:
                    return events
            return events

    def mark_flushed(self, event_ids: Sequence[str]) -> None:
        with self._lock:
            flushed = set(event_ids)
            if not flushed:
                return
            for path in sorted(self.root.rglob("*.jsonl")):
                kept: list[str] = []
                with path.open("r", encoding="utf-8") as file:
                    for line in file:
                        if not line.strip():
                            continue
                        event_id = json.loads(line)["event_id"]
                        if event_id not in flushed:
                            kept.append(line)
                self._replace_lines(path, kept)

    def _path_for(self, event: AuditEvent) -> Path:
        timestamp = self._parse_utc_timestamp(event.timestamp_utc)
        if not self._is_safe_run_id(event.run_id):
            raise ValueError("run_id.invalid")
        year = f"{timestamp.year:04d}"
        month = f"{timestamp.month:02d}"
        day = f"{timestamp.day:02d}"
        candidate = self.root / year / month / day / f"{event.run_id}.jsonl"
        resolved_root = self.root.resolve()
        resolved_parent = candidate.parent.resolve()
        if resolved_root != resolved_parent and resolved_root not in resolved_parent.parents:
            raise ValueError("audit_spool.path_escape")
        return candidate

    def _rotated_path(self, path: Path, line_size: int) -> Path:
        stem = path.stem
        suffix = path.suffix
        for index in range(1, 10_000):
            candidate = path.with_name(f"{stem}-{index:04d}{suffix}")
            if not candidate.exists() or candidate.stat().st_size + line_size <= self.max_bytes:
                return candidate
        raise OSError("audit_spool.rotation_exhausted")

    def _canonical_json(self, event: AuditEvent) -> str:
        return json.dumps(
            asdict(event),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _replace_lines(self, path: Path, lines: list[str]) -> None:
        if not lines:
            path.unlink(missing_ok=True)
            return
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp:
            temp.writelines(lines)
            temp.flush()
            os.fsync(temp.fileno())
            temp_path = Path(temp.name)
        temp_path.replace(path)

    def _bounded_jsonl_paths(
        self,
        *,
        max_files: int,
        newest_first: bool = False,
    ) -> list[Path]:
        if newest_first:
            return self._latest_bounded_jsonl_paths(max_files=max_files)
        resolved_root = self.root.resolve()
        if self.root.is_symlink():
            return []
        pending = [resolved_root]
        files: list[Path] = []
        while pending and len(files) < max_files:
            current = pending.pop(0)
            try:
                entries = sorted(current.iterdir(), key=lambda item: item.name)
            except OSError:
                continue
            for entry in entries:
                try:
                    resolved_entry = entry.resolve()
                except OSError:
                    continue
                if resolved_entry != resolved_root and resolved_root not in resolved_entry.parents:
                    continue
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    pending.append(resolved_entry)
                    continue
                if entry.is_file() and entry.suffix == ".jsonl":
                    files.append(resolved_entry)
                    if len(files) >= max_files:
                        break
        return files

    def _latest_bounded_jsonl_paths(self, *, max_files: int) -> list[Path]:
        resolved_root = self.root.resolve()
        if self.root.is_symlink():
            return []
        pending = [resolved_root]
        files: list[Path] = []
        while pending and len(files) < max_files:
            current = pending.pop()
            try:
                entries = list(current.iterdir())
            except OSError:
                continue
            directories: list[Path] = []
            jsonl_files: list[tuple[int, str, Path]] = []
            for entry in entries:
                try:
                    resolved_entry = entry.resolve()
                    if resolved_entry != resolved_root and resolved_root not in resolved_entry.parents:
                        continue
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        directories.append(resolved_entry)
                        continue
                    if entry.is_file() and entry.suffix == ".jsonl":
                        jsonl_files.append((entry.stat().st_mtime_ns, entry.name, resolved_entry))
                except OSError:
                    continue
            jsonl_files.sort(key=lambda item: (item[0], item[1]), reverse=True)
            files.extend(path for _, _, path in jsonl_files[: max_files - len(files)])
            pending.extend(sorted(directories, key=lambda path: path.name))
        return files

    def _validate_event(self, event: AuditEvent) -> AuditEvent:
        self._parse_utc_timestamp(event.timestamp_utc)
        if event.schema_version != "audit_event@1":
            raise ValueError("audit_event.schema_version.invalid")
        self._validate_top_level_id("event_id", event.event_id)
        self._validate_run_id(event.run_id)
        self._validate_top_level_id("correlation_id", event.correlation_id)
        if event.event_type not in _ALLOWED_EVENT_TYPES:
            raise ValueError("audit_event.event_type.invalid")
        if event.span_name not in _ALLOWED_SPAN_NAMES:
            raise ValueError("audit_event.span_name.invalid")
        if not self._is_safe_run_id(event.run_id):
            raise ValueError("run_id.invalid")
        if event.event_type.startswith("startup_disclosure."):
            attributes = self._sanitize_startup_disclosure_attributes(event.attributes)
        elif event.event_type.startswith("startup_report."):
            attributes = self._sanitize_startup_report_attributes(event.attributes)
        elif event.event_type == "observability.exporter_degraded":
            attributes = self._sanitize_exporter_degradation_attributes(event.attributes)
        elif event.event_type == "observability.langsmith_status":
            attributes = self._sanitize_langsmith_status_attributes(event.attributes)
        else:
            attributes = self._sanitizer.sanitize_attributes(event.attributes)
        return AuditEvent(
            schema_version=event.schema_version,
            event_id=event.event_id,
            timestamp_utc=event.timestamp_utc,
            run_id=event.run_id,
            correlation_id=event.correlation_id,
            span_name=event.span_name,
            event_type=event.event_type,
            attributes=attributes,
        )

    def _sanitize_exporter_degradation_attributes(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        expected_keys = {"case_id", *_EXPORTER_DEGRADATION_ATTRIBUTES}
        if set(attributes) != expected_keys:
            raise ValueError("audit_event.exporter_degradation.invalid")
        sanitized = self._sanitizer.sanitize_attributes(attributes)
        if any(
            sanitized.get(key) != expected
            for key, expected in _EXPORTER_DEGRADATION_ATTRIBUTES.items()
        ):
            raise ValueError("audit_event.exporter_degradation.invalid")
        return sanitized

    def _sanitize_langsmith_status_attributes(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        expected_keys = {
            "case_id",
            "status",
            "error_code",
            "fallback_used",
            "exporter_provider",
        }
        if set(attributes) != expected_keys:
            raise ValueError("audit_event.langsmith_status.invalid")
        sanitized = self._sanitizer.sanitize_attributes(attributes)
        status = sanitized.get("status")
        if not isinstance(status, str):
            raise ValueError("audit_event.langsmith_status.invalid")
        allowed_errors = _LANGSMITH_STATUS_ERROR_CODES.get(status)
        if allowed_errors is None:
            raise ValueError("audit_event.langsmith_status.invalid")
        if sanitized.get("error_code") not in allowed_errors:
            raise ValueError("audit_event.langsmith_status.invalid")
        if sanitized.get("fallback_used") != "local_audit":
            raise ValueError("audit_event.langsmith_status.invalid")
        if sanitized.get("exporter_provider") != "langsmith":
            raise ValueError("audit_event.langsmith_status.invalid")
        return sanitized

    def _sanitize_startup_report_attributes(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        sanitized: dict[str, str | int | float | bool | None] = {}
        for key, value in attributes.items():
            if key not in _STARTUP_REPORT_ATTRIBUTE_KEYS:
                raise ValueError(f"trace_attribute.disallowed:{key}")
            if value is None:
                sanitized[key] = None
                continue
            if key == "report_revision":
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"trace_attribute.value_type:{key}")
                sanitized[key] = value
                continue
            if isinstance(value, bool | int | float) or not isinstance(value, str):
                raise ValueError(f"trace_attribute.value_type:{key}")
            if _SENSITIVE_VALUE_RE.search(value):
                raise ValueError(f"trace_attribute.value_sensitive:{key}")
            if key in {"case_id", "report_id"} and not _SAFE_ID_RE.fullmatch(value):
                raise ValueError(f"trace_attribute.value_format:{key}")
            if key == "report_checksum" and not _SAFE_HASH_RE.fullmatch(value):
                raise ValueError(f"trace_attribute.value_format:{key}")
            if key in {"status", "report_status", "gate4_status", "decision"} and not _SAFE_STATUS_RE.fullmatch(value):
                raise ValueError(f"trace_attribute.value_format:{key}")
            sanitized[key] = value
        return sanitized

    def _sanitize_startup_disclosure_attributes(
        self,
        attributes: Mapping[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        sanitized: dict[str, str | int | float | bool | None] = {}
        for key, value in attributes.items():
            if key not in _STARTUP_DISCLOSURE_ATTRIBUTE_KEYS:
                raise ValueError(f"trace_attribute.disallowed:{key}")
            if value is None:
                sanitized[key] = None
                continue
            if key in {"data_revision", "detected_class_count", "artifact_count", "fragment_count"}:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"trace_attribute.value_type:{key}")
                sanitized[key] = value
                continue
            if isinstance(value, bool | int | float) or not isinstance(value, str):
                raise ValueError(f"trace_attribute.value_type:{key}")
            if _SENSITIVE_VALUE_RE.search(value):
                raise ValueError(f"trace_attribute.value_sensitive:{key}")
            if key in {"case_id", "approval_id"} and not _SAFE_ID_RE.fullmatch(value):
                raise ValueError(f"trace_attribute.value_format:{key}")
            if key == "content_hash" and not _SAFE_HASH_RE.fullmatch(value):
                raise ValueError(f"trace_attribute.value_format:{key}")
            if key in {"decision", "reason", "overall_class"} and not _SAFE_STATUS_RE.fullmatch(value):
                raise ValueError(f"trace_attribute.value_format:{key}")
            if key in {"redaction_policy_version", "egress_policy_version", "destination"} and not _SAFE_TOKEN_RE.fullmatch(value):
                raise ValueError(f"trace_attribute.value_format:{key}")
            sanitized[key] = value
        return sanitized

    def _validate_top_level_id(self, key: str, value: str) -> None:
        try:
            self._sanitizer.sanitize_attributes({key: value})
        except ValueError as exc:
            raise ValueError(f"audit_event.{key}.invalid") from exc

    def _validate_run_id(self, value: str) -> None:
        try:
            self._sanitizer.sanitize_attributes({"run_id": value})
        except ValueError as exc:
            raise ValueError("run_id.invalid") from exc

    def _parse_utc_timestamp(self, value: str) -> datetime:
        if not value.endswith("Z"):
            raise ValueError("timestamp_utc.invalid")
        try:
            parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
        except ValueError as exc:
            raise ValueError("timestamp_utc.invalid") from exc
        if parsed.tzinfo != UTC:
            raise ValueError("timestamp_utc.invalid")
        return parsed

    def _is_safe_run_id(self, value: str) -> bool:
        if not _RUN_ID_RE.match(value):
            return False
        stem = value.split(".", 1)[0].upper()
        return stem not in _WINDOWS_RESERVED_NAMES

    def _write_all(self, fd: int, data: bytes) -> None:
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError("audit_spool.write_failed")
            offset += written

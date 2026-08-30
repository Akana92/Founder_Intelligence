from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path
import re
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from due_diligence_agent.domain.artifacts.models import Artifact
from due_diligence_agent.domain.artifacts.safety import SafetyLimits, SafetyScanResult
from due_diligence_agent.domain.artifacts.startup_inventory import (
    DataRoomInventory,
    QuarantinedArtifact,
)
from due_diligence_agent.domain.common import ArtifactParsingStatus, SensitivityClass
from due_diligence_agent.ports.archive import ArchiveInspectorPort
from due_diligence_agent.ports.repositories import ArtifactRepository, ArtifactStore
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class DataRoomService:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        artifact_repository: ArtifactRepository,
        archive_inspector: ArchiveInspectorPort,
        quarantine_root: Path = Path(".local/quarantine"),
        limits: SafetyLimits | None = None,
        audit_spool: AuditSpool | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._artifact_repository = artifact_repository
        self._archive_inspector = archive_inspector
        self._quarantine_root = quarantine_root.resolve()
        self._limits = limits or SafetyLimits()
        self._audit_spool = audit_spool

    def ingest(self, case_id: str | UUID, sources: Iterable[Path]) -> DataRoomInventory:
        case_text = str(case_id)
        if not _SAFE_CASE_ID.fullmatch(case_text):
            raise ValueError("case_id.invalid")
        case_uuid = self._case_uuid(case_id)
        accepted: list[Artifact] = []
        quarantined: list[QuarantinedArtifact] = []
        scanned_files = 0
        accounted_unpacked_bytes = 0
        unpacked_bytes = 0
        run_id = f"startup-{uuid4().hex}"
        for source in sources:
            result = self._archive_inspector.inspect(
                Path(source),
                remaining_files=self._limits.max_files - scanned_files,
                remaining_unpacked_bytes=(
                    self._limits.max_unpacked_bytes - accounted_unpacked_bytes
                ),
            )
            try:
                if result.reason is not None:
                    item = self._quarantine(case_text, result)
                    quarantined.append(item)
                    self._audit(
                        run_id=run_id,
                        case_id=case_uuid,
                        content_hash=result.source_content_hash,
                        byte_size=item.byte_size,
                        status="quarantined",
                        error_code=item.reason,
                    )
                    continue
                source_artifacts: list[Artifact] = []
                for scanned in result.accepted:
                    payload = self._read_staged(scanned.staged_path, scanned.byte_size)
                    if sha256(payload).hexdigest() != scanned.content_hash:
                        raise ValueError("staged_artifact.content_hash_mismatch")
                    artifact_id = uuid5(
                        NAMESPACE_URL,
                        f"startup:{case_uuid}:{scanned.source.value}:{scanned.content_hash}",
                    )
                    stored = self._artifact_store.put_bytes(
                        payload,
                        media_type=scanned.media_type,
                        artifact_id=artifact_id,
                        source_snapshot_hash=result.source_content_hash,
                        sensitivity=SensitivityClass.RESTRICTED,
                    )
                    artifact = Artifact(
                        id=stored.artifact_id,
                        case_id=case_uuid,
                        content_hash=stored.content_hash,
                        mime_type=stored.media_type,
                        source=scanned.source.value,
                        retrieved_at=datetime.now(UTC),
                        source_snapshot_hash=stored.source_snapshot_hash,
                        storage_ref=stored.storage_ref,
                        parsing_status=ArtifactParsingStatus.PENDING,
                        sensitivity=stored.sensitivity,
                    )
                    self._artifact_repository.add(artifact)
                    source_artifacts.append(artifact)
                accepted.extend(source_artifacts)
                scanned_files += result.file_count
                accounted_unpacked_bytes += result.accounted_unpacked_bytes
                unpacked_bytes += result.unpacked_bytes
                self._audit(
                    run_id=run_id,
                    case_id=case_uuid,
                    content_hash=result.source_content_hash,
                    byte_size=result.unpacked_bytes,
                    status="accepted",
                    error_code=None,
                )
            finally:
                result.close()
        return DataRoomInventory(
            case_id=case_text,
            accepted=accepted,
            quarantined=quarantined,
            scanned_files=scanned_files,
            unpacked_bytes=unpacked_bytes,
        )

    def _quarantine(self, case_id: str, result: SafetyScanResult) -> QuarantinedArtifact:
        case_root = (self._quarantine_root / case_id).resolve()
        if self._quarantine_root != case_root and self._quarantine_root not in case_root.parents:
            raise ValueError("case_id.invalid")
        case_root.mkdir(parents=True, exist_ok=True)
        target = case_root / f"{result.source_content_hash}.quarantine"
        if target.exists():
            if self._hash_path(target) != result.source_content_hash:
                raise ValueError("quarantine.content_hash_mismatch")
        else:
            temp = case_root / f".{result.source_content_hash}.{uuid4().hex}.tmp"
            try:
                digest = sha256()
                byte_size = 0
                with temp.open("xb") as output:
                    if result.source_payload is not None:
                        output.write(result.source_payload)
                        digest.update(result.source_payload)
                        byte_size = len(result.source_payload)
                    else:
                        with Path(result.source.value).open("rb") as input_file:
                            for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                                output.write(chunk)
                                digest.update(chunk)
                                byte_size += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if digest.hexdigest() != result.source_content_hash:
                    raise ValueError("quarantine.source_changed")
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        return QuarantinedArtifact(
            source=result.source,
            content_hash=result.source_content_hash,
            reason=result.reason or "unsafe",
            byte_size=target.stat().st_size,
            quarantine_ref=str(target),
        )

    def _audit(
        self,
        *,
        run_id: str,
        case_id: UUID,
        content_hash: str,
        byte_size: int,
        status: str,
        error_code: str | None,
    ) -> None:
        if self._audit_spool is None:
            return
        attributes: dict[str, str | int | float | bool | None] = {
            "case_id": case_id.hex,
            "workflow_type": "startup",
            "artifact_hash": content_hash,
            "bytes": byte_size,
            "status": status,
        }
        if error_code is not None:
            attributes["error_code"] = error_code
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self._audit_spool.append(
            AuditEvent(
                schema_version="audit_event@1",
                event_id=uuid4().hex,
                timestamp_utc=timestamp,
                run_id=run_id,
                correlation_id=f"case-{case_id.hex}",
                span_name="document.ingest",
                event_type="span",
                attributes=attributes,
            )
        )

    @staticmethod
    def _case_uuid(case_id: str | UUID) -> UUID:
        if isinstance(case_id, UUID):
            return case_id
        try:
            return UUID(case_id)
        except ValueError:
            return uuid5(NAMESPACE_URL, f"startup-case:{case_id}")

    @staticmethod
    def _hash_path(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _read_staged(path: Path, byte_size: int) -> bytes:
        payload = bytearray()
        with path.open("rb") as file:
            while len(payload) < byte_size:
                chunk = file.read(min(1024 * 1024, byte_size - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            if file.read(1):
                raise ValueError("staged_artifact.size_mismatch")
        if len(payload) != byte_size:
            raise ValueError("staged_artifact.size_mismatch")
        return bytes(payload)

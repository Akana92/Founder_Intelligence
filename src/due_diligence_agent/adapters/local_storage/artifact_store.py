from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path
import re
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from due_diligence_agent.domain.artifacts.models import StoredArtifact
from due_diligence_agent.domain.common import SensitivityClass


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put_bytes(
        self,
        payload: bytes,
        *,
        media_type: str,
        artifact_id: UUID | None = None,
        source_snapshot_hash: str | None = None,
        sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> StoredArtifact:
        digest = sha256(payload).hexdigest()
        target = self._path_for_hash(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self._validate_existing_object(target, digest)
        else:
            self._write_and_publish(payload, target, digest)
        return StoredArtifact(
            artifact_id=artifact_id or uuid5(NAMESPACE_URL, digest),
            content_hash=digest,
            source_snapshot_hash=source_snapshot_hash or digest,
            storage_ref=str(target),
            media_type=media_type,
            byte_size=len(payload),
            stored_at=datetime.now(UTC),
            sensitivity=sensitivity,
        )

    def read_bytes(self, content_hash: str) -> bytes:
        target = self._path_for_hash(content_hash)
        payload = target.read_bytes()
        if sha256(payload).hexdigest() != content_hash:
            raise ValueError("content hash mismatch")
        return payload

    def _path_for_hash(self, content_hash: str) -> Path:
        if not _SHA256_HEX.fullmatch(content_hash):
            raise ValueError("invalid content_hash")
        target = self.root / "objects" / content_hash[:2] / content_hash
        resolved = target.resolve()
        if self.root not in resolved.parents:
            raise ValueError("invalid content_hash")
        return resolved

    @staticmethod
    def _validate_existing_object(target: Path, content_hash: str) -> None:
        if sha256(target.read_bytes()).hexdigest() != content_hash:
            raise ValueError("content hash mismatch")

    def _write_and_publish(self, payload: bytes, target: Path, content_hash: str) -> None:
        temp = self._temp_path_for(target)
        try:
            with temp.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._validate_existing_object(temp, content_hash)
            if target.exists():
                self._validate_existing_object(target, content_hash)
                return
            os.replace(temp, target)
            self._validate_existing_object(target, content_hash)
        except FileExistsError:
            if target.exists():
                self._validate_existing_object(target, content_hash)
                return
            raise
        except Exception:
            self._cleanup_failed_publish(temp, target, content_hash)
            raise
        finally:
            if temp.exists():
                temp.unlink()

    @staticmethod
    def _temp_path_for(target: Path) -> Path:
        return target.with_name(f".{target.name}.{os.getpid()}.{uuid4().hex}.tmp")

    @staticmethod
    def _cleanup_failed_publish(temp: Path, target: Path, content_hash: str) -> None:
        if temp.exists():
            temp.unlink()
        if target.exists() and sha256(target.read_bytes()).hexdigest() != content_hash:
            target.unlink()

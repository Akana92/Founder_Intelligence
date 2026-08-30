from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.parse import SplitResult, urlsplit
from uuid import uuid4

from due_diligence_agent.ports.collectors import SourceSnapshot


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class SnapshotCache:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._meta = self.root / "metadata"
        self._payloads = self.root / "payloads"

    def key(self, provider: str, endpoint: str, query: dict[str, str], as_of: date) -> str:
        payload = {
            "provider": provider.strip().lower(),
            "endpoint": endpoint.strip(),
            "query": _normalize_query(query),
            "as_of": as_of.isoformat(),
        }
        return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def get(self, key: str, *, stale: bool = False, primary_failure: str | None = None) -> SourceSnapshot | None:
        snapshot = self._load_snapshot_metadata(key)
        if snapshot is None:
            return None
        self._validate_storage_ref_for_key(snapshot, key)
        self._verify_snapshot_payload(snapshot)
        if stale or primary_failure is not None:
            return snapshot.model_copy(update={"stale": stale, "primary_failure": primary_failure})
        return snapshot

    def get_for_request(
        self,
        key: str,
        *,
        provider: str,
        provider_version: str,
        source_url: str,
        query: dict[str, str],
        as_of: date,
        license_class: str,
        media_type: str | None = None,
        stale: bool = False,
        primary_failure: str | None = None,
    ) -> SourceSnapshot | None:
        snapshot = self._load_snapshot_metadata(key)
        if snapshot is None:
            return None
        self._validate_storage_ref_for_key(snapshot, key)
        self._validate_context(
            snapshot,
            provider=provider,
            provider_version=provider_version,
            source_url=source_url,
            query=query,
            as_of=as_of,
            license_class=license_class,
            media_type=media_type,
        )
        self._verify_snapshot_payload(snapshot)
        if stale or primary_failure is not None:
            return snapshot.model_copy(update={"stale": stale, "primary_failure": primary_failure})
        return snapshot

    def read_bytes(self, snapshot: SourceSnapshot) -> bytes:
        payload_path = self._resolve_storage_ref(snapshot.storage_ref)
        payload = payload_path.read_bytes()
        if sha256(payload).hexdigest() != snapshot.content_hash:
            raise ValueError("content hash mismatch")
        return payload

    def put_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        provider: str,
        provider_version: str,
        source_url: str,
        query: dict[str, str],
        as_of: date,
        media_type: str,
        license_class: str,
        published_at: datetime | None = None,
        retrieved_at: datetime | None = None,
    ) -> SourceSnapshot:
        content_hash = sha256(payload).hexdigest()
        existing = self._load_snapshot_metadata(key)
        if existing is not None:
            self._validate_storage_ref_for_key(existing, key)
            self._validate_context(
                existing,
                provider=provider,
                provider_version=provider_version,
                source_url=source_url,
                query=query,
                as_of=as_of,
                license_class=license_class,
                media_type=media_type,
            )
            if existing.content_hash != content_hash:
                raise ValueError("immutable snapshot key conflict")
            self._verify_snapshot_payload(existing)
            return existing
        self._meta.mkdir(parents=True, exist_ok=True)
        self._payloads.mkdir(parents=True, exist_ok=True)
        payload_path = self._payload_path(key)
        self._atomic_write(payload_path, payload)
        if sha256(payload_path.read_bytes()).hexdigest() != content_hash:
            raise ValueError("content hash mismatch")
        snapshot = SourceSnapshot(
            provider=provider,
            provider_version=provider_version,
            source_url=source_url,
            query=_normalize_query(query),
            as_of=as_of,
            retrieved_at=retrieved_at or datetime.now(UTC),
            published_at=published_at,
            content_hash=content_hash,
            license_class=license_class,
            media_type=media_type,
            storage_ref=payload_path.name,
        )
        self._atomic_write(
            self._metadata_path(key),
            (snapshot.model_dump_json() + "\n").encode("utf-8"),
        )
        return snapshot

    def _load_snapshot_metadata(self, key: str) -> SourceSnapshot | None:
        metadata_path = self._metadata_path(key)
        if metadata_path.is_symlink():
            raise ValueError("cache_metadata_symlink")
        self._validate_resolved_under_root(metadata_path, "invalid cache key")
        if not metadata_path.exists():
            return None
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return SourceSnapshot(**payload)

    def _verify_snapshot_payload(self, snapshot: SourceSnapshot) -> None:
        payload_path = self._resolve_storage_ref(snapshot.storage_ref)
        actual_hash = sha256(payload_path.read_bytes()).hexdigest()
        if actual_hash != snapshot.content_hash:
            raise ValueError("content hash mismatch")

    @staticmethod
    def _validate_storage_ref_for_key(snapshot: SourceSnapshot, key: str) -> None:
        ref = Path(snapshot.storage_ref)
        if ref.is_absolute() or len(ref.parts) != 1 or ref.name != snapshot.storage_ref:
            raise ValueError("invalid storage_ref")
        if snapshot.storage_ref != f"{key}.bin":
            raise ValueError("cache_storage_ref_mismatch")

    def _validate_context(
        self,
        snapshot: SourceSnapshot,
        *,
        provider: str,
        provider_version: str,
        source_url: str,
        query: dict[str, str],
        as_of: date,
        license_class: str,
        media_type: str | None,
    ) -> None:
        checks: tuple[tuple[str, object, object], ...] = (
            ("provider", snapshot.provider.strip().lower(), provider.strip().lower()),
            ("provider_version", snapshot.provider_version, provider_version),
            ("query", dict(snapshot.query), _normalize_query(query)),
            ("as_of", snapshot.as_of, as_of),
            ("license_class", snapshot.license_class, license_class),
        )
        for field, actual, expected in checks:
            if actual != expected:
                raise ValueError(f"cache_context_mismatch:{field}")
        if media_type is not None and snapshot.media_type != media_type:
            raise ValueError("cache_context_mismatch:media_type")
        if not _source_url_compatible(snapshot.source_url, source_url):
            raise ValueError("cache_context_mismatch:source_url")

    def _metadata_path(self, key: str) -> Path:
        self._validate_key(key)
        return self._meta / f"{key}.json"

    def _payload_path(self, key: str) -> Path:
        self._validate_key(key)
        payload_path = self._payloads / f"{key}.bin"
        if payload_path.is_symlink():
            raise ValueError("cache_payload_symlink")
        return self._safe_path(payload_path)

    def _resolve_storage_ref(self, storage_ref: str) -> Path:
        ref = Path(storage_ref)
        if ref.is_absolute() or len(ref.parts) != 1 or ref.name != storage_ref:
            raise ValueError("invalid storage_ref")
        payload_path = self._payloads / ref.name
        if payload_path.is_symlink():
            raise ValueError("cache_payload_symlink")
        resolved = payload_path.resolve()
        payload_root = self._payloads.resolve()
        if self.root not in resolved.parents or payload_root not in resolved.parents:
            raise ValueError("invalid storage_ref")
        return resolved

    def _safe_path(self, path: Path) -> Path:
        resolved = path.resolve()
        self._validate_resolved_under_root(resolved, "invalid cache key")
        return resolved

    def _validate_resolved_under_root(self, path: Path, message: str) -> None:
        resolved = path.resolve()
        if self.root not in resolved.parents:
            raise ValueError(message)

    @staticmethod
    def _validate_key(key: str) -> None:
        if not _SHA256_HEX.fullmatch(key):
            raise ValueError("invalid cache key")

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            with temp.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()


def verify_fixture_manifest(manifest_path: Path) -> dict[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent.resolve()
    verified: dict[str, str] = {}
    for name, entry in manifest["files"].items():
        target = (root / name).resolve()
        if root not in target.parents:
            raise ValueError("fixture path escapes manifest root")
        if name.endswith((".html", ".xml")):
            _validate_filing_manifest_entry(name, entry)
        digest = sha256(target.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"fixture hash mismatch:{name}")
        verified[name] = digest
    return verified


def _validate_filing_manifest_entry(name: str, entry: dict[str, object]) -> None:
    required_fields = {
        "accession_number",
        "filing_acceptance_at",
        "filing_date",
        "report_period_end",
        "effective_at",
    }
    missing = required_fields - set(entry)
    if missing:
        raise ValueError(f"fixture filing metadata missing:{name}:{','.join(sorted(missing))}")
    acceptance = entry["filing_acceptance_at"]
    if not isinstance(acceptance, str) or not acceptance.endswith("Z"):
        raise ValueError(f"invalid filing_acceptance_at:{name}")
    for field_name in ("filing_date", "report_period_end"):
        value = entry[field_name]
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError(f"invalid {field_name}:{name}")


def _normalize_query(query: dict[str, str]) -> dict[str, str]:
    return {str(key).strip(): str(value).strip() for key, value in sorted(query.items())}


def _source_url_compatible(cached_url: str, requested_url: str) -> bool:
    cached = urlsplit(cached_url)
    requested = urlsplit(requested_url)
    cached_port = _effective_port(cached)
    requested_port = _effective_port(requested)
    return (
        cached.scheme.lower() == "https"
        and requested.scheme.lower() == "https"
        and (cached.hostname or "").lower() == (requested.hostname or "").lower()
        and cached_port is not None
        and requested_port is not None
        and cached_port == requested_port
        and cached.path == requested.path
    )


def _effective_port(url: SplitResult) -> int | None:
    try:
        port = url.port
    except ValueError:
        return None
    return 443 if port is None else port


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

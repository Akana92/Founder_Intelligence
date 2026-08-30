from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any, cast

from due_diligence_agent.adapters.http.snapshot_cache import verify_fixture_manifest


def verify_public_context_manifest(
    manifest_path: Path,
    *,
    expected_provider: str,
    expected_as_of: date,
    allowed_license_classes: set[str],
    expected_ticker: str | None = None,
    expected_query: str | None = None,
) -> dict[str, Any]:
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    if manifest.get("provider") != expected_provider:
        raise ValueError("manifest provider mismatch")
    if manifest.get("as_of") != expected_as_of.isoformat():
        raise ValueError("manifest as_of mismatch")
    if manifest.get("license_class") not in allowed_license_classes:
        raise ValueError("manifest license_class mismatch")
    if expected_ticker is not None and manifest.get("ticker") != expected_ticker.upper():
        raise ValueError("manifest ticker mismatch")
    if expected_query is not None and manifest.get("query") != expected_query:
        raise ValueError("manifest query mismatch")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files required")
    for name, entry in files.items():
        if not isinstance(entry, dict):
            raise ValueError(f"manifest file entry invalid:{name}")
        for field in ("provider", "retrieval_url", "as_of", "license_class", "sha256"):
            if field not in entry:
                raise ValueError(f"manifest file metadata missing:{name}:{field}")
        if entry["provider"] != expected_provider:
            raise ValueError(f"manifest provider mismatch:{name}")
        if entry["as_of"] != expected_as_of.isoformat():
            raise ValueError(f"manifest as_of mismatch:{name}")
        if entry["license_class"] not in allowed_license_classes:
            raise ValueError(f"manifest license_class mismatch:{name}")
        if not str(entry["retrieval_url"]).startswith(("https://", "http://")):
            raise ValueError(f"manifest retrieval_url invalid:{name}")

    verified = verify_fixture_manifest(manifest_path)
    for name, digest in verified.items():
        manifest["files"][name]["sha256"] = digest
    return manifest

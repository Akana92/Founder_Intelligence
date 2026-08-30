from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from importlib import import_module
from importlib.util import find_spec
import json
from pathlib import Path
from typing import Any

from due_diligence_agent.adapters.documents.no_network_guard import NoNetworkGuard


class DoclingDocumentParser:
    """Optional parser registration gate; importing this module never imports Docling."""

    parser_name = "docling"
    parser_version = "1"

    def __init__(self, *, model_cache: Path) -> None:
        self.model_cache = model_cache.resolve()

    @classmethod
    def try_create(
        cls,
        *,
        model_cache: Path,
        dependency_probe: Callable[[str], bool] | None = None,
        offline_smoke: Callable[[Path], bool] | None = None,
    ) -> DoclingDocumentParser | None:
        probe = dependency_probe or (lambda name: find_spec(name) is not None)
        if not probe("docling") or not _valid_local_cache(model_cache):
            return None
        smoke = offline_smoke or _default_offline_smoke
        try:
            with NoNetworkGuard():
                if not smoke(model_cache.resolve()):
                    return None
        except Exception:
            return None
        return cls(model_cache=model_cache)


def _valid_local_cache(model_cache: Path) -> bool:
    root = model_cache.resolve()
    manifest_path = root / "model-manifest.json"
    if not root.is_dir() or not manifest_path.is_file() or manifest_path.is_symlink():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if not isinstance(files, list) or not files:
        return False
    for item in files:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("size"), int)
            or isinstance(item.get("size"), bool)
            or not isinstance(item.get("sha256"), str)
        ):
            return False
        relative = Path(item["path"])
        candidate = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or root not in candidate.parents:
            return False
        if not candidate.is_file() or candidate.is_symlink():
            return False
        if candidate.stat().st_size != item["size"]:
            return False
        if _hash_file(candidate) != item["sha256"]:
            return False
    return True


def _default_offline_smoke(model_cache: Path) -> bool:
    module: Any = import_module("docling.document_converter")
    converter: Any = module.DocumentConverter(artifacts_path=model_cache)
    return converter is not None


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

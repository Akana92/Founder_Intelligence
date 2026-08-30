from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from due_diligence_agent.adapters.retrieval.local_embeddings import (
    E5_MULTILINGUAL_BASE_PROFILE,
    build_model_manifest,
    unsafe_model_ignore_patterns,
    verify_model_manifest,
)

try:
    from huggingface_hub import snapshot_download
except ImportError:  # pragma: no cover - exercised only on incomplete optional installs
    snapshot_download = None  # type: ignore[assignment]


def cache_embedding_model(
    *,
    output: Path,
    model: str = E5_MULTILINGUAL_BASE_PROFILE.repo_id,
) -> Path:
    if snapshot_download is None:
        raise RuntimeError("huggingface_hub is required to cache the embedding model")
    if model != E5_MULTILINGUAL_BASE_PROFILE.repo_id:
        raise ValueError("unsupported embedding model")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output.with_name(f".{output.name}.{os.getpid()}.{uuid4().hex}.tmp")
    backup_dir = output.with_name(f".{output.name}.{os.getpid()}.{uuid4().hex}.backup")
    try:
        snapshot_download(
            repo_id=E5_MULTILINGUAL_BASE_PROFILE.repo_id,
            revision=E5_MULTILINGUAL_BASE_PROFILE.revision,
            local_dir=temp_dir,
            local_files_only=False,
            ignore_patterns=unsafe_model_ignore_patterns(),
        )
        _remove_transient_cache(temp_dir)
        manifest = build_model_manifest(temp_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)
        (temp_dir / "model-manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        verify_model_manifest(temp_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)
        backup_created = _publish_directory(temp_dir, output, backup_dir)
        try:
            verify_model_manifest(output, profile=E5_MULTILINGUAL_BASE_PROFILE)
        except Exception:
            if output.exists():
                shutil.rmtree(output)
            if backup_created and backup_dir.exists():
                os.replace(backup_dir, output)
            raise
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        return output
    except Exception:
        if output.exists() and not backup_dir.exists():
            pass
        if backup_dir.exists() and not output.exists():
            os.replace(backup_dir, output)
        raise
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=E5_MULTILINGUAL_BASE_PROFILE.repo_id)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    cache_embedding_model(output=args.output, model=args.model)
    return 0


def _remove_transient_cache(root: Path) -> None:
    for path in sorted(root.rglob(".cache"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _publish_directory(temp_dir: Path, output: Path, backup_dir: Path) -> bool:
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_created = False
    if output.exists():
        os.replace(output, backup_dir)
        backup_created = True
    try:
        os.replace(temp_dir, output)
    except Exception:
        if backup_dir.exists() and not output.exists():
            os.replace(backup_dir, output)
        raise
    return backup_created


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class EmbeddingModelProfile:
    repo_id: str
    revision: str
    license: str
    model_card_url: str
    dimension: int
    max_model_length: int


E5_MULTILINGUAL_BASE_PROFILE = EmbeddingModelProfile(
    repo_id="intfloat/multilingual-e5-base",
    revision="f5bd48cd75e61ca79c4cdffff9185cab1f07f4f0",
    license="MIT",
    model_card_url="https://huggingface.co/intfloat/multilingual-e5-base",
    dimension=768,
    max_model_length=512,
)

UNSAFE_MODEL_FILE_SUFFIXES = (".bin", ".h5", ".ckpt", ".pt", ".pth", ".onnx")


class LocalEmbeddingAdapter:
    dimension = E5_MULTILINGUAL_BASE_PROFILE.dimension
    model_id = E5_MULTILINGUAL_BASE_PROFILE.repo_id
    model_revision = E5_MULTILINGUAL_BASE_PROFILE.revision

    def __init__(
        self,
        model_dir: Path,
        *,
        profile: EmbeddingModelProfile = E5_MULTILINGUAL_BASE_PROFILE,
    ) -> None:
        if profile != E5_MULTILINGUAL_BASE_PROFILE:
            raise ValueError("unsupported embedding profile")
        self.model_dir = model_dir.resolve()
        self.profile = profile
        self._model: Any | None = None

    def embed_passages(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        return self._encode([f"passage: {text}" for text in texts])

    def embed_query(self, text: str) -> npt.NDArray[np.float32]:
        return self._encode([f"query: {text}"])

    def _encode(self, texts: list[str]) -> npt.NDArray[np.float32]:
        self._verify_manifest()
        model = self._load_model()
        encoded = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            precision="float32",
        )
        vectors = np.ascontiguousarray(encoded, dtype=np.float32)
        if vectors.ndim != 2:
            raise ValueError("embedding output rank mismatch")
        if vectors.shape != (len(texts), self.profile.dimension):
            raise ValueError("embedding dimension mismatch")
        if not np.isfinite(vectors).all():
            raise ValueError("embedding vector contains non-finite values")
        return vectors

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                str(self.model_dir),
                device="cpu",
                local_files_only=True,
                trust_remote_code=False,
            )
        return self._model

    def _verify_manifest(self) -> None:
        manifest_path = self.model_dir / "model-manifest.json"
        if manifest_path.is_symlink() or not _is_confined(self.model_dir, manifest_path):
            raise ValueError("unsafe model manifest file")
        if not manifest_path.exists():
            raise ValueError("model manifest missing")
        _validate_no_unsafe_model_paths(self.model_dir)
        manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
        _verify_manifest_profile(manifest, self.profile)
        files = cast(list[dict[str, Any]], manifest.get("files", []))
        seen_paths: set[str] = set()
        for item in files:
            relative = str(item.get("path", ""))
            if not _safe_relative_path(relative):
                raise ValueError("unsafe model manifest path")
            if relative in seen_paths:
                raise ValueError("duplicate model manifest path")
            seen_paths.add(relative)
        if not any(item.get("path") == "model.safetensors" for item in files):
            raise ValueError("model.safetensors is required")
        expected_paths = {str(item["path"]) for item in files}
        actual_paths: set[str] = set()
        for path in _iter_model_files(self.model_dir):
            relative = path.relative_to(self.model_dir).as_posix()
            actual_paths.add(relative)
            if path.is_symlink() or not _is_confined(self.model_dir, path):
                raise ValueError("unsafe model file")
            if relative not in expected_paths:
                raise ValueError("unexpected model file")
        missing = expected_paths - actual_paths
        if missing:
            raise ValueError("missing model file")
        for item in files:
            relative = str(item["path"])
            path = self.model_dir / relative
            if path.is_symlink() or not _is_confined(self.model_dir, path):
                raise ValueError("unsafe model file")
            payload = path.read_bytes()
            if len(payload) != int(item["size"]):
                raise ValueError("model file size mismatch")
            if sha256(payload).hexdigest() != item["sha256"]:
                raise ValueError("model file hash mismatch")
        if _tree_hash(files) != manifest.get("tree_sha256"):
            raise ValueError("model tree hash mismatch")


def build_model_manifest(
    model_dir: Path,
    *,
    profile: EmbeddingModelProfile = E5_MULTILINGUAL_BASE_PROFILE,
) -> dict[str, Any]:
    root = model_dir.resolve()
    _validate_no_unsafe_model_paths(root)
    files: list[dict[str, Any]] = []
    has_safetensors = False
    for path in _iter_model_files(root):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not _is_confined(root, path):
            raise ValueError("unsafe model file")
        if _has_unsafe_model_suffix(path):
            raise ValueError("unsafe model file")
        if relative == "model.safetensors":
            has_safetensors = True
        payload = path.read_bytes()
        files.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": sha256(payload).hexdigest(),
            }
        )
    if not has_safetensors:
        raise ValueError("model.safetensors is required")
    files.sort(key=lambda item: str(item["path"]))
    return {
        "repo_id": profile.repo_id,
        "revision": profile.revision,
        "license": profile.license,
        "model_card_url": profile.model_card_url,
        "dimension": profile.dimension,
        "max_model_length": profile.max_model_length,
        "sentence_transformers_version": _package_version("sentence-transformers"),
        "faiss_version": _package_version("faiss-cpu"),
        "files": files,
        "tree_sha256": _tree_hash(files),
    }


def verify_model_manifest(
    model_dir: Path,
    *,
    profile: EmbeddingModelProfile = E5_MULTILINGUAL_BASE_PROFILE,
) -> dict[str, Any]:
    adapter = LocalEmbeddingAdapter(model_dir, profile=profile)
    adapter._verify_manifest()
    return cast(
        dict[str, Any],
        json.loads((model_dir / "model-manifest.json").read_text(encoding="utf-8")),
    )


def _verify_manifest_profile(manifest: dict[str, Any], profile: EmbeddingModelProfile) -> None:
    if manifest.get("repo_id") != profile.repo_id:
        raise ValueError("model repo mismatch")
    if manifest.get("revision") != profile.revision:
        raise ValueError("model revision mismatch")
    if manifest.get("license") != profile.license:
        raise ValueError("model license mismatch")
    if manifest.get("model_card_url") != profile.model_card_url:
        raise ValueError("model card mismatch")
    if manifest.get("dimension") != profile.dimension:
        raise ValueError("model dimension mismatch")
    if manifest.get("max_model_length") != profile.max_model_length:
        raise ValueError("model max length mismatch")


def _iter_model_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "model-manifest.json" and ".cache" not in path.parts
    )


def _validate_no_unsafe_model_paths(root: Path) -> None:
    for path in root.rglob("*"):
        if ".cache" in path.parts:
            raise ValueError("unexpected model cache")
        if path.name == "model-manifest.json":
            continue
        if _has_unsafe_model_suffix(path):
            raise ValueError("unsafe model file")
        if path.is_symlink() or not _is_confined(root, path):
            raise ValueError("unsafe model file")


def _safe_relative_path(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value.replace("\\", "/") == value


def _is_confined(root: Path, path: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def _tree_hash(files: list[dict[str, Any]]) -> str:
    rows = [
        f"{item['path']}\0{item['size']}\0{item['sha256']}"
        for item in sorted(files, key=lambda entry: str(entry["path"]))
    ]
    return sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _has_unsafe_model_suffix(path: Path) -> bool:
    return path.suffix.lower() in UNSAFE_MODEL_FILE_SUFFIXES


def unsafe_model_ignore_patterns() -> tuple[str, ...]:
    return tuple(f"*{suffix}" for suffix in UNSAFE_MODEL_FILE_SUFFIXES)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"

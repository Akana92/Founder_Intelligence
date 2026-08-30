from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np

from due_diligence_agent.ports.repositories import ArtifactStore
from due_diligence_agent.ports.retrieval import (
    INDEX_VERSION,
    EmbeddingPort,
    EvidenceChunk,
    RetrievalHit,
)


class FaissEvidenceIndex:
    def __init__(self, *, root: Path, embedding: EmbeddingPort, artifact_store: ArtifactStore) -> None:
        self.root = root.resolve()
        self.embedding = embedding
        self.artifact_store = artifact_store

    def index(self, chunks: Sequence[EvidenceChunk]) -> None:
        if not chunks:
            return
        case_ids = {chunk.case_id for chunk in chunks}
        if len(case_ids) != 1:
            raise ValueError("chunks must belong to one case")
        case_id = next(iter(case_ids))
        merged_chunks = self._merge_chunks(case_id, chunks)
        vector_ids = np.array([_vector_id(chunk.chunk_id) for chunk in merged_chunks], dtype=np.int64)
        if len(set(int(vector_id) for vector_id in vector_ids)) != len(vector_ids):
            raise ValueError("duplicate vector id")
        texts = [self.artifact_store.read_bytes(chunk.text_ref).decode("utf-8") for chunk in merged_chunks]
        vectors = self._normalize(self.embedding.embed_passages(texts))
        if vectors.shape != (len(merged_chunks), self.embedding.dimension):
            raise ValueError("embedding dimension mismatch")

        import faiss

        index = faiss.IndexIDMap2(faiss.IndexFlatIP(self.embedding.dimension))
        index.add_with_ids(vectors, vector_ids)

        metadata = {
            "case_id": str(case_id),
            "index_version": INDEX_VERSION,
            "dimension": self.embedding.dimension,
            "count": len(merged_chunks),
            "model_id": self.embedding.model_id,
            "model_revision": self.embedding.model_revision,
            "chunks": [
                {
                    **chunk.model_dump(mode="json"),
                    "vector_id": int(vector_id),
                    "index_version": INDEX_VERSION,
                    "model_id": self.embedding.model_id,
                    "model_revision": self.embedding.model_revision,
                }
                for chunk, vector_id in zip(merged_chunks, vector_ids, strict=True)
            ],
        }
        self.root.mkdir(parents=True, exist_ok=True)
        case_dir = self._case_dir(case_id)
        self._publish(case_dir, index, metadata)

    def search(self, query: str, *, k: int, case_id: UUID) -> list[RetrievalHit]:
        if not query.strip():
            raise ValueError("blank query")
        if k < 1:
            raise ValueError("invalid k")
        case_dir = self._case_dir(case_id)
        if not case_dir.exists():
            return []
        metadata = self._load_and_validate_metadata(case_dir, case_id)
        import faiss

        index = faiss.read_index(str(case_dir / "index.faiss"))
        if int(index.d) != int(metadata["dimension"]):
            raise ValueError("index dimension mismatch")
        if int(index.ntotal) != int(metadata["count"]):
            raise ValueError("index count mismatch")
        query_vector = self._normalize(self.embedding.embed_query(query))
        if query_vector.shape != (1, int(metadata["dimension"])):
            raise ValueError("dimension mismatch")
        scores, vector_ids = index.search(query_vector, min(k, int(metadata["count"])))
        by_vector_id = {int(item["vector_id"]): item for item in metadata["chunks"]}
        hits: list[RetrievalHit] = []
        for score, vector_id in zip(scores[0], vector_ids[0], strict=True):
            if int(vector_id) == -1:
                continue
            item = by_vector_id[int(vector_id)]
            hits.append(
                RetrievalHit(
                    chunk_id=UUID(str(item["chunk_id"])),
                    case_id=case_id,
                    artifact_id=UUID(str(item["artifact_id"])),
                    locator=item["locator"],
                    content_hash=str(item["content_hash"]),
                    sensitivity=item["sensitivity"],
                    text_ref=str(item["text_ref"]),
                    chunk_config_hash=str(item["chunk_config_hash"]),
                    chunk_config_version=str(item["chunk_config_version"]),
                    model_id=str(metadata["model_id"]),
                    model_revision=str(metadata["model_revision"]),
                    index_version=INDEX_VERSION,
                    score=float(score),
                )
            )
        hits.sort(key=lambda hit: (-hit.score, str(hit.chunk_id)))
        return hits[:k]

    def _case_dir(self, case_id: UUID) -> Path:
        target = (self.root / str(case_id)).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("case path escaped index root")
        return target

    def _publish(self, case_dir: Path, index: Any, metadata: dict[str, Any]) -> None:
        import faiss

        temp_dir = self.root / f".{case_dir.name}.{uuid4().hex}.tmp"
        backup_dir = self.root / f".{case_dir.name}.{uuid4().hex}.backup"
        try:
            temp_dir.mkdir(parents=True, exist_ok=False)
            index_path = temp_dir / "index.faiss"
            metadata_path = temp_dir / "metadata.json"
            manifest_path = temp_dir / "manifest.json"
            faiss.write_index(index, str(index_path))
            metadata_path.write_text(
                json.dumps(metadata, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            manifest = {
                "index_sha256": sha256(index_path.read_bytes()).hexdigest(),
                "metadata_sha256": sha256(metadata_path.read_bytes()).hexdigest(),
                "index_version": metadata["index_version"],
                "dimension": metadata["dimension"],
                "count": metadata["count"],
            }
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            self._validate_bundle(temp_dir, UUID(str(metadata["case_id"])))
            if case_dir.exists():
                os.replace(case_dir, backup_dir)
            os.replace(temp_dir, case_dir)
            try:
                self._validate_bundle(case_dir, UUID(str(metadata["case_id"])))
            except Exception:
                if case_dir.exists():
                    shutil.rmtree(case_dir)
                if backup_dir.exists():
                    os.replace(backup_dir, case_dir)
                raise
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if backup_dir.exists() and not case_dir.exists():
                os.replace(backup_dir, case_dir)
            raise
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if backup_dir.exists():
                shutil.rmtree(backup_dir)

    def _load_and_validate_metadata(self, case_dir: Path, case_id: UUID) -> dict[str, Any]:
        index_path = case_dir / "index.faiss"
        metadata_path = case_dir / "metadata.json"
        manifest_path = case_dir / "manifest.json"
        for path in (case_dir, index_path, metadata_path, manifest_path):
            if path.is_symlink() or not _is_confined(self.root, path):
                raise ValueError("unsafe index bundle path")
        if not index_path.exists() or not metadata_path.exists() or not manifest_path.exists():
            raise ValueError("incomplete index")
        manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
        if sha256(index_path.read_bytes()).hexdigest() != manifest.get("index_sha256"):
            raise ValueError("manifest hash mismatch")
        if sha256(metadata_path.read_bytes()).hexdigest() != manifest.get("metadata_sha256"):
            raise ValueError("manifest hash mismatch")
        metadata = cast(dict[str, Any], json.loads(metadata_path.read_text(encoding="utf-8")))
        if metadata.get("case_id") != str(case_id):
            raise ValueError("case mismatch")
        if metadata.get("index_version") != INDEX_VERSION or manifest.get("index_version") != INDEX_VERSION:
            raise ValueError("index version mismatch")
        if metadata.get("dimension") != self.embedding.dimension or manifest.get("dimension") != self.embedding.dimension:
            raise ValueError("dimension mismatch")
        chunks = cast(list[dict[str, Any]], metadata.get("chunks", []))
        if metadata.get("count") != len(chunks) or manifest.get("count") != len(chunks):
            raise ValueError("count mismatch")
        if metadata.get("model_id") != self.embedding.model_id:
            raise ValueError("model mismatch")
        if metadata.get("model_revision") != self.embedding.model_revision:
            raise ValueError("model revision mismatch")
        seen_vector_ids: set[int] = set()
        for item in chunks:
            chunk = EvidenceChunk(
                chunk_id=UUID(str(item["chunk_id"])),
                case_id=UUID(str(item["case_id"])),
                artifact_id=UUID(str(item["artifact_id"])),
                locator=item["locator"],
                content_hash=str(item["content_hash"]),
                sensitivity=item["sensitivity"],
                text_ref=str(item["text_ref"]),
                chunk_config_hash=str(item["chunk_config_hash"]),
                chunk_config_version=str(item["chunk_config_version"]),
            )
            if item.get("case_id") != str(case_id):
                raise ValueError("case mismatch")
            if item.get("index_version") != metadata.get("index_version"):
                raise ValueError("chunk index version mismatch")
            if item.get("model_id") != metadata.get("model_id"):
                raise ValueError("chunk model mismatch")
            if item.get("model_revision") != metadata.get("model_revision"):
                raise ValueError("chunk model revision mismatch")
            vector_id = item.get("vector_id")
            if not isinstance(vector_id, int) or isinstance(vector_id, bool):
                raise ValueError("invalid vector id")
            expected_vector_id = _vector_id(chunk.chunk_id)
            if vector_id != expected_vector_id:
                raise ValueError("vector id mismatch")
            if vector_id in seen_vector_ids:
                raise ValueError("duplicate vector id")
            seen_vector_ids.add(vector_id)
        return metadata

    def _merge_chunks(
        self,
        case_id: UUID,
        new_chunks: Sequence[EvidenceChunk],
    ) -> list[EvidenceChunk]:
        case_dir = self._case_dir(case_id)
        by_id: dict[UUID, EvidenceChunk] = {}
        if case_dir.exists():
            metadata = self._load_and_validate_metadata(case_dir, case_id)
            for item in metadata["chunks"]:
                chunk = EvidenceChunk(
                    chunk_id=UUID(str(item["chunk_id"])),
                    case_id=UUID(str(item["case_id"])),
                    artifact_id=UUID(str(item["artifact_id"])),
                    locator=item["locator"],
                    content_hash=str(item["content_hash"]),
                    sensitivity=item["sensitivity"],
                    text_ref=str(item["text_ref"]),
                    chunk_config_hash=str(item["chunk_config_hash"]),
                    chunk_config_version=str(item["chunk_config_version"]),
                )
                by_id[chunk.chunk_id] = chunk
        for chunk in new_chunks:
            existing = by_id.get(chunk.chunk_id)
            if existing is not None and existing != chunk:
                raise ValueError("chunk metadata conflict")
            by_id[chunk.chunk_id] = chunk
        return sorted(by_id.values(), key=lambda chunk: str(chunk.chunk_id))

    def _validate_bundle(self, case_dir: Path, case_id: UUID) -> None:
        metadata = self._load_and_validate_metadata(case_dir, case_id)
        import faiss

        index = faiss.read_index(str(case_dir / "index.faiss"))
        if int(index.d) != int(metadata["dimension"]):
            raise ValueError("index dimension mismatch")
        if int(index.ntotal) != int(metadata["count"]):
            raise ValueError("index count mismatch")

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        contiguous = np.ascontiguousarray(vectors, dtype=np.float32)
        if contiguous.ndim != 2:
            raise ValueError("embedding output rank mismatch")
        if contiguous.shape[1] <= 0:
            raise ValueError("embedding dimension mismatch")
        if not np.isfinite(contiguous).all():
            raise ValueError("embedding vector contains non-finite values")
        norms = np.linalg.norm(contiguous, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return np.ascontiguousarray(contiguous / norms, dtype=np.float32)


def _vector_id(chunk_id: UUID) -> int:
    digest = sha256(str(chunk_id).encode("ascii")).digest()
    return int.from_bytes(digest[:7], "big", signed=False)


def _is_confined(root: Path, path: Path) -> bool:
    try:
        resolved_root = root.resolve(strict=False)
        resolved_path = path.resolve(strict=False)
    except OSError:
        return False
    return resolved_path == resolved_root or resolved_root in resolved_path.parents

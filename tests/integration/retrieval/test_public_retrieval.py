from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import socket
import sys
from types import ModuleType
from uuid import uuid4, uuid5, NAMESPACE_URL

import numpy as np
import pytest

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.retrieval.faiss_index import FaissEvidenceIndex
from due_diligence_agent.adapters.retrieval.local_embeddings import (
    EmbeddingModelProfile,
    E5_MULTILINGUAL_BASE_PROFILE,
    LocalEmbeddingAdapter,
    UNSAFE_MODEL_FILE_SUFFIXES,
    unsafe_model_ignore_patterns,
    build_model_manifest,
)
from due_diligence_agent.application.services.filing_parsing_service import FilingParsingService
from due_diligence_agent.application.services.retrieval_service import RetrievalService
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.ports.collectors import FilingArtifact, SourceSnapshot
from due_diligence_agent.ports.retrieval import RetrievalAuditEvent

_CACHE_SCRIPT_PATH = Path(__file__).parents[3] / "scripts" / "cache_embedding_model.py"
_CACHE_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "task7_cache_embedding_model", _CACHE_SCRIPT_PATH
)
assert _CACHE_SCRIPT_SPEC is not None and _CACHE_SCRIPT_SPEC.loader is not None
cache_script = importlib.util.module_from_spec(_CACHE_SCRIPT_SPEC)
sys.modules[_CACHE_SCRIPT_SPEC.name] = cache_script
_CACHE_SCRIPT_SPEC.loader.exec_module(cache_script)
cache_embedding_model = cache_script.cache_embedding_model


HTML = b"""
<html>
<head><style>body { color: red; }</style><script>secretQuery()</script></head>
<body>
<h1>Business</h1>
<p>Apple designs phones, personal computers, and services for public customers.</p>
<h2>Risk Factors</h2>
<p>Material liquidity risk can increase when supplier concentration changes quickly.</p>
<p>Customers may defer purchases during macroeconomic uncertainty.</p>
<noscript>do not index this text</noscript>
<h2>Liquidity and Capital Resources</h2>
<p>Liquidity resources include cash, marketable securities, and operating cash flow.</p>
</body>
</html>
"""


@pytest.fixture(autouse=True)
def forbid_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden in retrieval tests")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)


class FakeEmbedding:
    dimension = 4
    model_id = "fake-embedding@1"
    model_revision = "fake-revision"

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._vector(text) for text in texts]).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text).reshape(1, -1).astype(np.float32)

    @staticmethod
    def _vector(text: str) -> np.ndarray:
        lowered = text.lower()
        return _normalized(
            np.array(
                [
                    lowered.count("liquidity") + lowered.count("risk"),
                    lowered.count("business") + lowered.count("customers"),
                    lowered.count("cash") + lowered.count("resources"),
                    1.0,
                ],
                dtype=np.float32,
            )
        )


class ConstantEmbedding(FakeEmbedding):
    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return np.vstack([_normalized(np.ones(4, dtype=np.float32)) for _ in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return _normalized(np.ones(4, dtype=np.float32)).reshape(1, -1)


class AuditSpy:
    def __init__(self) -> None:
        self.events: list[RetrievalAuditEvent] = []

    def record(self, event: RetrievalAuditEvent) -> None:
        self.events.append(event)

    def serialized_payload(self) -> str:
        return "\n".join(event.model_dump_json() for event in self.events)


def test_parser_produces_stable_section_locators_and_chunk_ids() -> None:
    parser = FilingParsingService(max_tokens=8, overlap_tokens=2)
    filing = _filing_artifact(HTML)

    first = parser.parse(case_id=uuid4(), artifact_id=uuid4(), filing=filing)
    second = parser.parse(case_id=uuid4(), artifact_id=uuid4(), filing=filing)

    assert [chunk.locator.value for chunk in first] == [chunk.locator.value for chunk in second]
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert {chunk.locator.value for chunk in first} >= {
        "section:0001:business",
        "section:0002:risk-factors",
        "section:0003:liquidity-and-capital-resources",
    }
    assert all("secretQuery" not in chunk.text for chunk in first)
    assert all("do not index" not in chunk.text for chunk in first)
    assert all(len(chunk.text.split()) <= 8 for chunk in first)


def test_retrieval_stores_and_indexes_metadata_without_raw_text(tmp_path) -> None:
    service, audit, _index = _service(tmp_path)
    case_id = uuid4()
    filing = _filing_artifact(HTML)

    chunks = service.index_filing(
        case_id=case_id, filing=filing, sensitivity=SensitivityClass.PUBLIC
    )
    hits = service.search("material liquidity risk", k=3, case_id=case_id)

    assert hits[0].artifact_id == chunks[0].artifact_id
    assert hits[0].locator.kind == "sec_filing_section"
    assert hits[0].content_hash
    assert hits[0].text_ref
    persisted = json.loads((tmp_path / "index" / str(case_id) / "metadata.json").read_text())
    serialized = (
        json.dumps(persisted)
        + audit.serialized_payload()
        + "\n".join(hit.model_dump_json() for hit in hits)
    )
    assert "Material liquidity risk" not in serialized
    assert "material liquidity risk" not in serialized
    assert "Liquidity resources include cash" not in serialized
    assert all(chunk.text_ref for chunk in chunks)
    assert all("text" not in chunk.model_dump() for chunk in chunks)
    assert all("text" not in chunk.model_json_schema()["properties"] for chunk in chunks)


def test_retrieval_can_index_existing_persisted_artifact_id(tmp_path) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    filing = _filing_artifact(HTML)
    existing_artifact_id = uuid5(NAMESPACE_URL, "existing-sec-artifact")

    chunks = service.index_filing(
        case_id=case_id,
        filing=filing,
        sensitivity=SensitivityClass.PUBLIC,
        artifact_id=existing_artifact_id,
    )
    hits = service.search("material liquidity risk", k=3, case_id=case_id)

    assert chunks
    assert {chunk.artifact_id for chunk in chunks} == {existing_artifact_id}
    assert {hit.artifact_id for hit in hits} == {existing_artifact_id}


def test_retrieval_rejects_filing_bytes_that_do_not_match_snapshot_hash(tmp_path) -> None:
    service, _audit, _index = _service(tmp_path)
    filing = _filing_artifact(HTML).model_copy(
        update={
            "snapshot": _filing_artifact(HTML).snapshot.model_copy(
                update={"content_hash": "f" * 64}
            )
        }
    )

    with pytest.raises(ValueError, match="filing content hash mismatch"):
        service.index_filing(case_id=uuid4(), filing=filing, sensitivity=SensitivityClass.PUBLIC)


def test_search_is_case_isolated_and_tie_ordered(tmp_path) -> None:
    service, _audit, _index = _service(tmp_path, embedding=ConstantEmbedding())
    case_id = uuid4()
    other_case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    service.index_filing(
        case_id=other_case_id,
        filing=_filing_artifact(HTML.replace(b"Business", b"Other Business")),
        sensitivity=SensitivityClass.PUBLIC,
    )

    first = service.search("same score", k=10, case_id=case_id)
    second = service.search("same score", k=10, case_id=case_id)
    other = service.search("same score", k=10, case_id=other_case_id)

    assert [hit.chunk_id for hit in first] == sorted(hit.chunk_id for hit in first)
    assert [hit.chunk_id for hit in first] == [hit.chunk_id for hit in second]
    assert {hit.case_id for hit in first} == {case_id}
    assert {hit.case_id for hit in other} == {other_case_id}


def test_persisted_index_reloads_offline_and_rejects_tampering_before_faiss_read(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _audit, index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )

    reloaded = FaissEvidenceIndex(
        root=tmp_path / "index",
        embedding=FakeEmbedding(),
        artifact_store=index.artifact_store,
    )
    assert reloaded.search("liquidity risk", k=1, case_id=case_id)

    (tmp_path / "index" / str(case_id) / "metadata.json").write_text('{"tampered": true}')
    calls: list[str] = []

    def forbidden_read_index(path: str) -> object:
        calls.append(path)
        raise AssertionError("faiss.read_index must not be called before manifest validation")

    import faiss

    monkeypatch.setattr(faiss, "read_index", forbidden_read_index)
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        reloaded.search("liquidity risk", k=1, case_id=case_id)
    assert calls == []


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda metadata: metadata["chunks"][0].update({"vector_id": "1"}), "invalid vector id"),
        (lambda metadata: metadata["chunks"][0].update({"vector_id": True}), "invalid vector id"),
        (lambda metadata: metadata["chunks"][0].update({"vector_id": 1}), "vector id mismatch"),
        (
            lambda metadata: metadata["chunks"][1].update(
                {
                    "chunk_id": metadata["chunks"][0]["chunk_id"],
                    "vector_id": metadata["chunks"][0]["vector_id"],
                }
            ),
            "duplicate vector id",
        ),
        (
            lambda metadata: metadata["chunks"][0].update({"model_id": "other-model"}),
            "chunk model mismatch",
        ),
        (
            lambda metadata: metadata["chunks"][0].update({"model_revision": "other-revision"}),
            "chunk model revision mismatch",
        ),
        (
            lambda metadata: metadata["chunks"][0].update({"index_version": "other-index"}),
            "chunk index version mismatch",
        ),
    ],
)
def test_tampered_semantic_sidecar_metadata_is_rejected_before_faiss_read(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    message: str,
) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    metadata_path = tmp_path / "index" / str(case_id) / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    mutate(metadata)
    _rewrite_metadata_with_manifest(metadata_path, metadata)
    calls: list[str] = []

    def forbidden_read_index(path: str) -> object:
        calls.append(path)
        raise AssertionError("faiss.read_index must not be called before semantic validation")

    import faiss

    monkeypatch.setattr(faiss, "read_index", forbidden_read_index)

    with pytest.raises(ValueError, match=message):
        service.search("liquidity risk", k=1, case_id=case_id)
    assert calls == []


def test_index_publication_rolls_back_existing_trio_on_mid_publish_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    case_dir = tmp_path / "index" / str(case_id)
    before = {
        "index": (case_dir / "index.faiss").read_bytes(),
        "metadata": (case_dir / "metadata.json").read_bytes(),
        "manifest": (case_dir / "manifest.json").read_bytes(),
    }
    replace_calls = 0
    import due_diligence_agent.adapters.retrieval.faiss_index as faiss_index_module

    real_replace = faiss_index_module.os.replace

    def fail_second_replace(source: str, target: str) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("simulated metadata publish failure")
        real_replace(source, target)

    monkeypatch.setattr(faiss_index_module.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated metadata publish failure"):
        service.index_filing(
            case_id=case_id,
            filing=_filing_artifact(HTML.replace(b"Material liquidity", b"New liquidity")),
            sensitivity=SensitivityClass.PUBLIC,
        )

    assert (case_dir / "index.faiss").read_bytes() == before["index"]
    assert (case_dir / "metadata.json").read_bytes() == before["metadata"]
    assert (case_dir / "manifest.json").read_bytes() == before["manifest"]
    assert service.search("material liquidity risk", k=1, case_id=case_id)


def test_initial_index_publication_failure_leaves_no_case_shard(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()

    import faiss

    def fail_write_index(index, path: str) -> None:
        raise OSError("simulated initial write failure")

    monkeypatch.setattr(faiss, "write_index", fail_write_index)

    with pytest.raises(OSError, match="simulated initial write failure"):
        service.index_filing(
            case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
        )

    assert not (tmp_path / "index" / str(case_id)).exists()


def test_indexing_second_filing_merges_without_erasing_existing_evidence(tmp_path) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    first = service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    second = service.index_filing(
        case_id=case_id,
        filing=_filing_artifact(HTML.replace(b"Business", b"Segment Update")),
        sensitivity=SensitivityClass.PUBLIC,
    )

    hits = service.search("material liquidity risk", k=20, case_id=case_id)

    assert {first[0].artifact_id, second[0].artifact_id}.issubset({hit.artifact_id for hit in hits})


def test_existing_chunk_id_with_different_metadata_fails_closed(tmp_path) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    metadata_path = tmp_path / "index" / str(case_id) / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["chunks"][0]["content_hash"] = "a" * 64
    _rewrite_metadata_with_manifest(metadata_path, metadata)

    with pytest.raises(ValueError, match="chunk metadata conflict"):
        service.index_filing(
            case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
        )


def test_duplicate_vector_ids_are_rejected_before_faiss_add(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _audit, _index = _service(tmp_path)
    import due_diligence_agent.adapters.retrieval.faiss_index as faiss_index_module

    monkeypatch.setattr(faiss_index_module, "_vector_id", lambda chunk_id: 1)

    with pytest.raises(ValueError, match="duplicate vector id"):
        service.index_filing(
            case_id=uuid4(), filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
        )


def test_loaded_faiss_dimension_and_count_are_validated_against_manifest(tmp_path) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    case_dir = tmp_path / "index" / str(case_id)

    import faiss

    faiss.write_index(faiss.IndexFlatIP(3), str(case_dir / "index.faiss"))
    metadata_path = case_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    manifest = {
        "index_sha256": sha256((case_dir / "index.faiss").read_bytes()).hexdigest(),
        "metadata_sha256": sha256(metadata_path.read_bytes()).hexdigest(),
        "index_version": metadata["index_version"],
        "dimension": metadata["dimension"],
        "count": metadata["count"],
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))

    with pytest.raises(ValueError, match="index dimension mismatch"):
        service.search("liquidity", k=1, case_id=case_id)


def test_faiss_bundle_symlink_is_rejected_before_hashing_or_read_index(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    manifest_path = tmp_path / "index" / str(case_id) / "manifest.json"

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == manifest_path:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="unsafe index bundle path"):
        service.search("liquidity", k=1, case_id=case_id)


def test_faiss_embedding_vectors_must_be_rank2_finite_and_expected_dimension(tmp_path) -> None:
    class BadRankEmbedding(FakeEmbedding):
        def embed_passages(self, texts: list[str]) -> np.ndarray:
            return np.ones(4, dtype=np.float32)

    service, _audit, _index = _service(tmp_path, embedding=BadRankEmbedding())
    with pytest.raises(ValueError, match="embedding output rank mismatch"):
        service.index_filing(
            case_id=uuid4(), filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
        )

    class NonFiniteEmbedding(FakeEmbedding):
        def embed_passages(self, texts: list[str]) -> np.ndarray:
            result = np.ones((len(texts), 4), dtype=np.float32)
            result[0, 0] = np.inf
            return result

    service, _audit, _index = _service(tmp_path / "finite", embedding=NonFiniteEmbedding())
    with pytest.raises(ValueError, match="embedding vector contains non-finite values"):
        service.index_filing(
            case_id=uuid4(), filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
        )


def test_wrong_index_dimension_version_or_count_fails_closed(tmp_path) -> None:
    service, _audit, index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )
    metadata_path = tmp_path / "index" / str(case_id) / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["dimension"] = 99
    _rewrite_metadata_with_manifest(metadata_path, metadata)

    with pytest.raises(ValueError, match="dimension mismatch"):
        FaissEvidenceIndex(
            root=tmp_path / "index",
            embedding=FakeEmbedding(),
            artifact_store=index.artifact_store,
        ).search("liquidity", k=1, case_id=case_id)

    metadata["dimension"] = 4
    metadata["index_version"] = "wrong"
    _rewrite_metadata_with_manifest(metadata_path, metadata)
    with pytest.raises(ValueError, match="index version mismatch"):
        FaissEvidenceIndex(
            root=tmp_path / "index",
            embedding=FakeEmbedding(),
            artifact_store=index.artifact_store,
        ).search("liquidity", k=1, case_id=case_id)

    metadata["index_version"] = "faiss-flat-ip@1"
    metadata["count"] = metadata["count"] + 1
    _rewrite_metadata_with_manifest(metadata_path, metadata)
    with pytest.raises(ValueError, match="count mismatch"):
        FaissEvidenceIndex(
            root=tmp_path / "index",
            embedding=FakeEmbedding(),
            artifact_store=index.artifact_store,
        ).search("liquidity", k=1, case_id=case_id)


def test_model_manifest_validation_rejects_missing_tampered_and_unsafe_files_before_import(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"weights")
    manifest = build_model_manifest(model_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)
    (model_dir / "model-manifest.json").write_text(json.dumps(manifest, sort_keys=True))

    sys.modules.pop("sentence_transformers", None)
    LocalEmbeddingAdapter(model_dir)
    assert "sentence_transformers" not in sys.modules

    (model_dir / "model.safetensors").write_bytes(b"weigxyz")
    with pytest.raises(ValueError, match="model file hash mismatch"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    (model_dir / "model.safetensors").write_bytes(b"weights")
    extra = model_dir / "extra.txt"
    extra.write_text("extra")
    with pytest.raises(ValueError, match="unexpected model file"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    extra.unlink()
    cache_extra = model_dir / ".cache" / "hub.json"
    cache_extra.parent.mkdir()
    cache_extra.write_text("transient")
    with pytest.raises(ValueError, match="unexpected model cache"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules
    cache_extra.unlink()
    cache_extra.parent.rmdir()

    (model_dir / "model-manifest.json").write_text(
        json.dumps({**manifest, "files": [{"path": "../escape", "size": 1, "sha256": "0" * 64}]})
    )
    with pytest.raises(ValueError, match="unsafe model manifest path"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    (model_dir / "model-manifest.json").write_text(json.dumps({**manifest, "repo_id": "other"}))
    with pytest.raises(ValueError, match="model repo mismatch"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    (model_dir / "model-manifest.json").write_text(json.dumps({**manifest, "revision": "short"}))
    with pytest.raises(ValueError, match="model revision mismatch"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    (model_dir / "model-manifest.json").write_text(json.dumps({**manifest, "license": "apache"}))
    with pytest.raises(ValueError, match="model license mismatch"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    (model_dir / "model-manifest.json").write_text(json.dumps({**manifest, "dimension": 384}))
    with pytest.raises(ValueError, match="model dimension mismatch"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    duplicate_files = [manifest["files"][0], manifest["files"][0]]
    (model_dir / "model-manifest.json").write_text(
        json.dumps({**manifest, "files": duplicate_files})
    )
    with pytest.raises(ValueError, match="duplicate model manifest path"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    manifest_path = model_dir / "model-manifest.json"
    original_is_symlink = Path.is_symlink

    def fake_manifest_is_symlink(path: Path) -> bool:
        if path == manifest_path:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_manifest_is_symlink)
    with pytest.raises(ValueError, match="unsafe model manifest file"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules
    monkeypatch.setattr(Path, "is_symlink", original_is_symlink)

    (model_dir / "model.safetensors").unlink()
    (model_dir / "model-manifest.json").write_text(json.dumps({**manifest, "files": []}))
    with pytest.raises(ValueError, match="model.safetensors is required"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules

    (model_dir / "model.safetensors").write_bytes(b"weights")
    symlink_manifest = build_model_manifest(model_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)
    (model_dir / "model-manifest.json").write_text(json.dumps(symlink_manifest, sort_keys=True))

    def fake_weight_is_symlink(path: Path) -> bool:
        if path == model_dir / "model.safetensors":
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_weight_is_symlink)
    with pytest.raises(ValueError, match="unsafe model file"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules


@pytest.mark.parametrize("suffix", sorted(UNSAFE_MODEL_FILE_SUFFIXES))
def test_unsafe_model_weight_suffixes_fail_build_and_runtime_before_import(
    tmp_path,
    suffix: str,
) -> None:
    model_dir = tmp_path / f"model-{suffix.strip('.')}"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"weights")
    unsafe_file = model_dir / f"unsafe{suffix.upper()}"
    unsafe_file.write_bytes(b"unsafe")

    with pytest.raises(ValueError, match="unsafe model file"):
        build_model_manifest(model_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)

    unsafe_file.unlink()
    manifest = build_model_manifest(model_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)
    (model_dir / "model-manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    unsafe_file.write_bytes(b"unsafe")
    sys.modules.pop("sentence_transformers", None)

    with pytest.raises(ValueError, match="unsafe model file"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")
    assert "sentence_transformers" not in sys.modules


def test_local_embedding_adapter_uses_cpu_local_only_no_remote_code_and_e5_prefixes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"weights")
    manifest = build_model_manifest(model_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)
    (model_dir / "model-manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    calls: dict[str, object] = {}

    class FakeSentenceTransformer:
        def __init__(self, path: str, **kwargs: object) -> None:
            calls["path"] = path
            calls["kwargs"] = kwargs

        def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
            calls.setdefault("texts", []).extend(texts)
            calls["encode_kwargs"] = kwargs
            return np.ones((len(texts), 768), dtype=np.float32)

    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    adapter = LocalEmbeddingAdapter(model_dir)
    passages = adapter.embed_passages(["section text"])
    query = adapter.embed_query("search text")

    assert calls["path"] == str(model_dir)
    assert calls["kwargs"] == {
        "device": "cpu",
        "local_files_only": True,
        "trust_remote_code": False,
    }
    assert calls["texts"] == ["passage: section text", "query: search text"]
    assert calls["encode_kwargs"] == {
        "normalize_embeddings": True,
        "convert_to_numpy": True,
        "show_progress_bar": False,
        "precision": "float32",
    }
    assert passages.dtype == np.float32
    assert query.dtype == np.float32


def test_local_embedding_adapter_rejects_non_allowlisted_profile_and_bad_vectors(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"weights")
    manifest = build_model_manifest(model_dir, profile=E5_MULTILINGUAL_BASE_PROFILE)
    (model_dir / "model-manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    unsupported = EmbeddingModelProfile(
        repo_id="other/repo",
        revision="f5bd48cd75e61ca79c4cdffff9185cab1f07f4f0",
        license="MIT",
        model_card_url="https://example.test/model",
        dimension=768,
        max_model_length=512,
    )

    with pytest.raises(ValueError, match="unsupported embedding profile"):
        LocalEmbeddingAdapter(model_dir, profile=unsupported)

    class WrongDimensionSentenceTransformer:
        def __init__(self, path: str, **kwargs: object) -> None:
            pass

        def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
            return np.ones((len(texts), 2), dtype=np.float32)

    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = WrongDimensionSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    with pytest.raises(ValueError, match="embedding dimension mismatch"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")

    class NonFiniteSentenceTransformer(WrongDimensionSentenceTransformer):
        def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
            result = np.ones((len(texts), 768), dtype=np.float32)
            result[0, 0] = np.nan
            return result

    module.SentenceTransformer = NonFiniteSentenceTransformer
    with pytest.raises(ValueError, match="embedding vector contains non-finite values"):
        LocalEmbeddingAdapter(model_dir).embed_query("hello")


def test_blank_query_invalid_k_and_malformed_html_fail_deterministically(tmp_path) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )

    with pytest.raises(ValueError, match="blank query"):
        service.search(" ", k=1, case_id=case_id)
    with pytest.raises(ValueError, match="invalid k"):
        service.search("liquidity", k=0, case_id=case_id)
    with pytest.raises(ValueError, match="malformed html"):
        service.index_filing(
            case_id=uuid4(),
            filing=_filing_artifact(b"<html><head><title>missing body</title></head></html>"),
            sensitivity=SensitivityClass.PUBLIC,
        )


def test_focused_retrieval_path_opens_no_sockets(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, _audit, _index = _service(tmp_path)
    case_id = uuid4()
    service.index_filing(
        case_id=case_id, filing=_filing_artifact(HTML), sensitivity=SensitivityClass.PUBLIC
    )

    assert service.search("liquidity risk", k=1, case_id=case_id)
    with pytest.raises(AssertionError, match="network access is forbidden"):
        socket.create_connection(("example.com", 443))


def test_cache_embedding_model_uses_pinned_allowlisted_snapshot_and_safe_publication(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}

    def fake_snapshot_download(**kwargs: object) -> str:
        calls.update(kwargs)
        target = kwargs["local_dir"]
        assert not isinstance(target, bool)
        local_dir = target
        local_dir.mkdir(parents=True)
        (local_dir / "model.safetensors").write_bytes(b"weights")
        (local_dir / "config.json").write_text("{}")
        return str(local_dir)

    monkeypatch.setattr(cache_script, "snapshot_download", fake_snapshot_download)

    output = tmp_path / "published-model"
    cache_embedding_model(output=output)

    assert calls["repo_id"] == "intfloat/multilingual-e5-base"
    assert calls["revision"] == E5_MULTILINGUAL_BASE_PROFILE.revision
    assert calls["ignore_patterns"] == unsafe_model_ignore_patterns()
    assert (output / "model.safetensors").exists()
    assert (output / "model-manifest.json").exists()
    assert not any(path.name.startswith(".cache") for path in output.rglob("*"))


def test_cache_embedding_model_rejects_pickle_weights_missing_safetensors_and_rolls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = tmp_path / "published-model"
    existing.mkdir()
    (existing / "model.safetensors").write_bytes(b"old")

    def fake_snapshot_download(**kwargs: object) -> str:
        target = kwargs["local_dir"]
        assert not isinstance(target, bool)
        target.mkdir(parents=True)
        (target / "pytorch_model.bin").write_bytes(b"unsafe")
        return str(target)

    monkeypatch.setattr(cache_script, "snapshot_download", fake_snapshot_download)

    with pytest.raises(ValueError, match="unsafe model file"):
        cache_embedding_model(output=existing)

    assert (existing / "model.safetensors").read_bytes() == b"old"


def test_cache_embedding_model_rolls_back_if_post_publish_verification_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = tmp_path / "published-model"
    existing.mkdir()
    (existing / "model.safetensors").write_bytes(b"old")
    old_manifest = build_model_manifest(existing, profile=E5_MULTILINGUAL_BASE_PROFILE)
    (existing / "model-manifest.json").write_text(json.dumps(old_manifest, sort_keys=True))

    def fake_snapshot_download(**kwargs: object) -> str:
        target = kwargs["local_dir"]
        assert not isinstance(target, bool)
        target.mkdir(parents=True)
        (target / "model.safetensors").write_bytes(b"new")
        return str(target)

    calls = 0

    def fail_on_output(path, *, profile=E5_MULTILINGUAL_BASE_PROFILE):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("post-publish verify failed")
        return {}

    monkeypatch.setattr(cache_script, "snapshot_download", fake_snapshot_download)
    monkeypatch.setattr(cache_script, "verify_model_manifest", fail_on_output)

    with pytest.raises(ValueError, match="post-publish verify failed"):
        cache_embedding_model(output=existing)

    assert (existing / "model.safetensors").read_bytes() == b"old"


def _service(
    tmp_path,
    *,
    embedding: FakeEmbedding | None = None,
) -> tuple[RetrievalService, AuditSpy, FaissEvidenceIndex]:
    audit = AuditSpy()
    embedder = embedding or FakeEmbedding()
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    index = FaissEvidenceIndex(
        root=tmp_path / "index",
        embedding=embedder,
        artifact_store=artifact_store,
    )
    service = RetrievalService(
        artifact_store=artifact_store,
        parser=FilingParsingService(max_tokens=8, overlap_tokens=2),
        index=index,
        audit_sink=audit,
    )
    return service, audit, index


def _filing_artifact(content: bytes) -> FilingArtifact:
    digest = sha256(content).hexdigest()
    return FilingArtifact(
        accession_number="0000320193-26-000001",
        content=content,
        snapshot=SourceSnapshot(
            provider="sec-edgar",
            provider_version="fixture@1",
            source_url="https://www.sec.gov/Archives/example.htm",
            query={"accession": "0000320193-26-000001"},
            as_of=date(2026, 8, 9),
            retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            content_hash=digest,
            license_class="public",
            media_type="text/html",
            storage_ref="fixture://filing",
        ),
    )


def _normalized(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def _rewrite_metadata_with_manifest(metadata_path, metadata: dict[str, object]) -> None:
    metadata_path.write_text(json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8")
    case_dir = metadata_path.parent
    index_bytes = (case_dir / "index.faiss").read_bytes()
    from hashlib import sha256

    manifest = {
        "index_sha256": sha256(index_bytes).hexdigest(),
        "metadata_sha256": sha256(metadata_path.read_bytes()).hexdigest(),
        "index_version": metadata["index_version"],
        "dimension": metadata["dimension"],
        "count": metadata["count"],
    }
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2),
        encoding="utf-8",
    )

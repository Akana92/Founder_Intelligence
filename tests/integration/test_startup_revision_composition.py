from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4
import sys

import pytest

from due_diligence_agent.application.startup_cases import StartupCaseCoordinator
from due_diligence_agent.bootstrap import container
from due_diligence_agent.presentation.api import dependencies as api_dependencies
from due_diligence_agent.presentation.api.dependencies import get_startup_case_coordinator


def test_startup_case_revision_port_is_backed_by_canonical_case_repository(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "revision-port"
    port = container.build_startup_case_revision_port(data_dir)
    case_id = str(uuid4())

    assert port.current_revision(case_id) == 0

    first = port.advance_revision(
        case_id,
        expected_current_revision=0,
        document_ids=["doc-0001"],
        source_refs=[_source_ref("doc-0001", _hash_bytes(b"one"))],
        metadata={"declared_mime_type": "text/plain"},
    )
    second = port.advance_revision(
        case_id,
        expected_current_revision=1,
        document_ids=["doc-0001", "doc-0002"],
        source_refs=[
            _source_ref("doc-0001", _hash_bytes(b"one")),
            _source_ref("doc-0002", _hash_bytes(b"two")),
        ],
        metadata={"declared_mime_type": "text/plain"},
    )

    repositories = container.build_local_repositories(data_dir / "startup-metadata.sqlite3")
    assert first == 1
    assert second == 2
    assert port.current_revision(case_id) == 2
    assert repositories.case_repository.get(UUID(case_id)).data_revision == 2

    with pytest.raises(ValueError, match="case_revision_conflict"):
        port.advance_revision(
            case_id,
            expected_current_revision=1,
            document_ids=["doc-0003"],
            source_refs=[_source_ref("doc-0003", _hash_bytes(b"three"))],
            metadata={},
        )


def test_startup_api_dependency_wires_mode_aware_case_revision_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"
    live_data_dir = data_root / "startup-api"
    deterministic_data_dir = live_data_dir / "deterministic"
    revision_dirs: list[Path] = []
    profile_dirs: list[Path] = []
    received_ports: dict[str, object] = {}

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    class RevisionProbe:
        def __init__(self, label: str) -> None:
            self.label = label

        def current_revision(self, case_id: str) -> int:
            del case_id
            return 0

        def advance_revision(
            self,
            case_id: str,
            *,
            expected_current_revision: int,
            document_ids: list[str],
            source_refs: list[dict[str, str]],
            metadata: dict[str, str],
        ) -> int:
            del case_id, document_ids, source_refs, metadata
            return expected_current_revision + 1

    class AnalysisProbe:
        def start(self, payload: dict[str, object], *, thread_id: str) -> dict[str, object]:
            del payload, thread_id
            return {"status": "gate2_preview_ready", "preview": {"summary": "ok"}}

        def resume(self, approval: dict[str, object], *, thread_id: str) -> dict[str, object]:
            del approval, thread_id
            return {"status": "analysis_complete_report_pending"}

    def build_revision_port(data_dir: Path) -> RevisionProbe:
        revision_dirs.append(data_dir)
        return RevisionProbe(data_dir.name)

    def build_profile_port(data_dir: Path) -> RevisionProbe:
        profile_dirs.append(data_dir)
        return RevisionProbe(data_dir.name)

    def coordinator_factory(**kwargs: object) -> StartupCaseCoordinator:
        received_ports["live"] = kwargs.get("case_revision_port")
        received_ports["deterministic"] = kwargs.get("deterministic_case_revision_port")
        received_ports["live_profile"] = kwargs.get("profile_port")
        received_ports["deterministic_profile"] = kwargs.get("deterministic_profile_port")
        return StartupCaseCoordinator(**kwargs)  # type: ignore[arg-type]

    fake_bootstrap = ModuleType("due_diligence_agent.bootstrap")
    fake_container = ModuleType("due_diligence_agent.bootstrap.container")
    setattr(fake_container, "build_startup_analysis_composer", lambda _data_dir, **_kwargs: AnalysisProbe())
    setattr(
        fake_container,
        "build_deterministic_startup_analysis_composer",
        lambda _data_dir, **_kwargs: AnalysisProbe(),
    )
    setattr(fake_container, "build_startup_report_port", lambda _data_dir: None)
    setattr(fake_container, "build_startup_case_revision_port", build_revision_port)
    setattr(fake_container, "build_startup_profile_query_port", build_profile_port)
    setattr(fake_bootstrap, "container", fake_container)
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap.container", fake_container)
    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(api_dependencies, "StartupCaseCoordinator", coordinator_factory)

    coordinator = get_startup_case_coordinator()

    assert coordinator.get_status(
        coordinator.create_case({"fixture_mode": "live", "auto_start": False}).case_id
    ).provider_status == "unavailable"
    assert revision_dirs == [live_data_dir, deterministic_data_dir]
    assert profile_dirs == [live_data_dir, deterministic_data_dir]
    assert getattr(received_ports["live"], "label") == "startup-api"
    assert getattr(received_ports["deterministic"], "label") == "deterministic"
    assert getattr(received_ports["live_profile"], "label") == "startup-api"
    assert getattr(received_ports["deterministic_profile"], "label") == "deterministic"
    _clear_startup_dependency_cache()


def test_startup_source_ref_requires_case_root_inside_inbox_and_direct_child(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "source-ref-boundary"
    inbox_root = data_dir / "inbox"
    case_id = uuid4()
    payload = b"safe source"
    content_hash = _hash_bytes(payload)
    case_root = inbox_root / str(case_id)
    case_root.mkdir(parents=True)
    (case_root / "doc-0001.pdf").write_bytes(payload)

    assert container._resolve_source_ref(  # noqa: SLF001
        inbox_root,
        case_id,
        _source_ref("doc-0001", content_hash, suffix="pdf"),
    ) == (content_hash, (case_root / "doc-0001.pdf").resolve())

    nested_dir = case_root / "nested"
    nested_dir.mkdir()
    (nested_dir / "doc-0001.pdf").write_bytes(payload)

    with pytest.raises(ValueError, match="startup_source_ref_private_name_invalid"):
        container._resolve_source_ref(  # noqa: SLF001
            inbox_root,
            case_id,
            {
                "document_id": "doc-0001",
                "private_name": "doc-0001.pdf",
                "content_sha256": content_hash,
            }
            | {"private_name": "doc-0001.pdf/../doc-0001.pdf"},
        )

    outside_root = data_dir / "inbox-evil" / str(case_id)
    outside_root.mkdir(parents=True)
    (outside_root / "doc-0001.pdf").write_bytes(payload)
    escaped_inbox = data_dir / "escaped-inbox"
    escaped_inbox.mkdir()
    escaped_case_link = escaped_inbox / str(case_id)
    try:
        os.symlink(outside_root, escaped_case_link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable on this Windows environment: {exc}")

    with pytest.raises(ValueError, match="startup_source_ref_private_name_invalid"):
        container._resolve_source_ref(  # noqa: SLF001
            escaped_inbox,
            case_id,
            _source_ref("doc-0001", content_hash, suffix="pdf"),
        )


def _source_ref(document_id: str, content_hash: str, *, suffix: str = "pdf") -> dict[str, str]:
    return {
        "document_id": document_id,
        "private_name": f"{document_id}.{suffix}",
        "content_sha256": content_hash,
    }


def _hash_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _clear_startup_dependency_cache() -> None:
    cache_clear = getattr(get_startup_case_coordinator, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.application import startup_cases as startup_cases_module
from due_diligence_agent.workflows.startup import runtime as startup_runtime_module
from due_diligence_agent.application.startup_cases import (
    CanonicalReportSnapshot,
    FreezeStatus,
    PdfStatus,
    StartupCaseCoordinator,
    StartupGateConflict,
    StartupNotFound,
    StartupReportRendererUnavailable,
    StartupValidationError,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.workflows.startup.runtime import (
    InMemoryStartupWorkflowRuntimeStore,
    JsonFileStartupWorkflowRuntimeStore,
    SQLiteStartupWorkflowRuntimeStore,
)


def test_create_case_shell_stores_founder_metadata_without_starting_analysis(tmp_path: Path) -> None:
    analysis = AnalysisProbe()
    deterministic = AnalysisProbe()
    store = InMemoryStartupWorkflowRuntimeStore()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        deterministic_analysis_service=deterministic,
        workflow_store=store,
        inbox_root=tmp_path,
    )

    response = coordinator.create_case(
        {
            "fixture_mode": "deterministic_offline",
            "auto_start": True,
            "company_name": "FounderCo",
            "website": "https://founder.example",
        }
    )

    assert response.case_status == "awaiting_upload"
    assert response.analysis_status == "awaiting_upload"
    assert response.provider_status == "deterministic_offline_fixture"
    assert response.auto_start_triggered is False
    assert response.model_dump().keys() == {
        "case_id",
        "case_status",
        "analysis_status",
        "provider_status",
        "auto_start_triggered",
    }
    assert analysis.starts == []
    assert deterministic.starts == []
    runtime = store.load(response.case_id)
    assert runtime["company_name"] == "FounderCo"
    assert runtime["website"] == "https://founder.example"
    assert "original_filenames" not in runtime


def test_deterministic_mode_uses_bound_deterministic_execution_path(tmp_path: Path) -> None:
    live = AnalysisProbe()
    deterministic = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=live,
        deterministic_analysis_service=deterministic,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "deterministic_offline", "auto_start": True})

    response = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=True,
    )

    assert response.auto_start_triggered is True
    assert live.starts == []
    assert deterministic.starts[0]["payload"]["execution_mode"] == "deterministic_offline_fixture"


def test_upload_generates_safe_private_ids_and_starts_until_gate2_pause(tmp_path: Path) -> None:
    analysis = AnalysisProbe(
        start_result={
            "status": "approval_required",
            "pending_gate": "startup_disclosure",
            "evidence_fact_ids": ["fact-1"],
        }
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        deterministic_analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": True})

    response = coordinator.upload_documents(
        created.case_id,
        files=[
            {
                "filename": "pitch deck secret.pdf",
                "content": b"ARR 100\nfounder@example.com",
                "content_type": "application/pdf",
            }
        ],
        auto_start=True,
    )

    assert response.case_id == created.case_id
    assert response.accepted_document_ids == ["doc-0001"]
    assert response.auto_start_triggered is True
    assert response.next_poll_after_ms == 0
    assert "pitch deck secret.pdf" not in response.model_dump_json()
    stored_path = tmp_path / created.case_id / "doc-0001.pdf"
    assert stored_path.read_bytes() == b"ARR 100\nfounder@example.com"
    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["documents"] == [
        {
            "document_id": "doc-0001",
            "private_name": "doc-0001.pdf",
            "declared_mime_type": "application/pdf",
            "byte_size": 27,
            "source_name_sha256": _sha256_text("pitch deck secret.pdf"),
            "content_sha256": _sha256_bytes(b"ARR 100\nfounder@example.com"),
        }
    ]
    assert runtime["data_revision"] == 1
    assert runtime["active_analysis_thread_id"] == f"{created.case_id}:r1"
    assert runtime["source_document_ids"] == ["doc-0001"]
    assert runtime["source_refs"] == [
        {
            "document_id": "doc-0001",
            "private_name": "doc-0001.pdf",
            "content_sha256": _sha256_bytes(b"ARR 100\nfounder@example.com"),
        }
    ]
    assert "sources" not in runtime
    assert str(tmp_path) not in repr(runtime)
    assert "pitch deck secret.pdf" not in repr(runtime)
    assert analysis.starts[0]["thread_id"] == f"{created.case_id}:r1"
    assert analysis.starts[0]["payload"]["source_document_ids"] == ["doc-0001"]
    assert analysis.starts[0]["payload"]["source_refs"] == [
        {
            "document_id": "doc-0001",
            "private_name": "doc-0001.pdf",
            "content_sha256": _sha256_bytes(b"ARR 100\nfounder@example.com"),
        }
    ]
    assert analysis.starts[0]["payload"]["data_revision"] == 1
    assert "sources" not in analysis.starts[0]["payload"]
    assert str(tmp_path) not in repr(analysis.starts[0]["payload"])
    assert "pitch deck secret.pdf" not in repr(analysis.starts[0]["payload"])
    status = coordinator.get_status(created.case_id)
    assert status.analysis_status == "gate2_preview_ready"
    assert status.gate2_status == "required"
    assert status.gate4_status == "not_ready"
    assert status.snapshot_hash is None
    assert status.snapshot_revision is None


def test_upload_derives_private_suffix_from_basename_and_falls_back_to_bin(
    tmp_path: Path,
) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    response = coordinator.upload_documents(
        created.case_id,
        files=[
            {
                "filename": "..\\..\\Investor Deck.PDF",
                "content": b"pdf bytes",
                "content_type": "application/pdf",
            },
            {
                "filename": "/tmp/founder.secret.exe",
                "content": b"exe bytes",
                "content_type": "application/octet-stream",
            },
            {
                "filename": "brief.txt",
                "content": b"plain idea brief",
                "content_type": "text/plain",
            },
        ],
        auto_start=False,
    )

    assert response.accepted_document_ids == ["doc-0001", "doc-0002", "doc-0003"]
    runtime = coordinator.runtime_for_test(created.case_id)
    assert [item["private_name"] for item in runtime["documents"]] == [
        "doc-0001.pdf",
        "doc-0002.bin",
        "doc-0003.txt",
    ]
    assert (tmp_path / created.case_id / "doc-0001.pdf").read_bytes() == b"pdf bytes"
    assert (tmp_path / created.case_id / "doc-0002.bin").read_bytes() == b"exe bytes"
    assert (tmp_path / created.case_id / "doc-0003.txt").read_bytes() == b"plain idea brief"
    assert ".." not in repr(runtime)
    assert "Investor Deck" not in repr(runtime)
    assert "founder.secret.exe" not in repr(runtime)


def test_duplicate_content_upload_is_idempotent_and_does_not_increment_revision(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    first = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
        auto_start=True,
    )
    second = coordinator.upload_documents(
        created.case_id,
        files=[
            {
                "filename": "renamed secret.csv",
                "content": b"same bytes",
                "content_type": "text/csv",
            }
        ],
        auto_start=True,
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert first.accepted_document_ids == ["doc-0001"]
    assert second.accepted_document_ids == ["doc-0001"]
    assert runtime["document_ids"] == ["doc-0001"]
    assert len(runtime["documents"]) == 1
    assert runtime["data_revision"] == 1
    assert [start["thread_id"] for start in analysis.starts] == [f"{created.case_id}:r1"]


def test_canonical_revision_port_sets_first_accepted_upload_revision_and_start_payload(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    revision_port = CanonicalRevisionProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        case_revision_port=revision_port,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    response = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"first", "content_type": "application/pdf"}],
        auto_start=True,
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert response.accepted_document_ids == ["doc-0001"]
    assert runtime["data_revision"] == 1
    assert runtime["active_analysis_thread_id"] == f"{created.case_id}:r1"
    assert analysis.starts[0]["thread_id"] == f"{created.case_id}:r1"
    assert analysis.starts[0]["payload"]["data_revision"] == 1
    assert revision_port.advances == [
        {
            "case_id": created.case_id,
            "expected_current_revision": 0,
            "next_revision": 1,
            "document_ids": ["doc-0001"],
        }
    ]


def test_duplicate_content_does_not_advance_canonical_revision_port(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    revision_port = CanonicalRevisionProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        case_revision_port=revision_port,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    first = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
        auto_start=False,
    )
    second = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "copy.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
        auto_start=True,
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert first.accepted_document_ids == ["doc-0001"]
    assert second.accepted_document_ids == ["doc-0001"]
    assert runtime["data_revision"] == 1
    assert [start["thread_id"] for start in analysis.starts] == [f"{created.case_id}:r1"]
    assert len(revision_port.advances) == 1


def test_duplicate_content_auto_start_claims_existing_awaiting_revision_without_increment(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    first = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
        auto_start=False,
    )
    second = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "renamed.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
        auto_start=True,
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert first.auto_start_triggered is False
    assert second.accepted_document_ids == ["doc-0001"]
    assert second.auto_start_triggered is True
    assert runtime["data_revision"] == 1
    assert [start["thread_id"] for start in analysis.starts] == [f"{created.case_id}:r1"]


def test_canonical_revision_port_reconciles_second_upload_to_authoritative_revision(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    revision_port = CanonicalRevisionProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        case_revision_port=revision_port,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"first", "content_type": "application/pdf"}],
        auto_start=False,
    )
    revision_port.revisions[created.case_id] = 3
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "data_revision": 1,
            "active_analysis_thread_id": f"{created.case_id}:r1",
            "gate3_reviewed": True,
            "gate3_exclusions": [{"evidence_fact_id": "fact-stale"}],
            "gate3_exclusion_reasons": {"fact-stale": "stale"},
            "gate3_recompute_started": True,
            "gate3_report_finalized": True,
            "gate3_affected_nodes": ["metrics"],
            "gate4_reviewed": True,
            "gate4_last_decision": "approved",
        },
    )

    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "metrics.csv", "content": b"second", "content_type": "text/csv"}],
        auto_start=True,
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["data_revision"] == 4
    assert runtime["active_analysis_thread_id"] == f"{created.case_id}:r4"
    for stale_key in (
        "gate3_reviewed",
        "gate3_exclusions",
        "gate3_exclusion_reasons",
        "gate3_recompute_started",
        "gate3_report_finalized",
        "gate3_affected_nodes",
        "gate4_reviewed",
        "gate4_last_decision",
    ):
        assert stale_key not in runtime
    assert analysis.starts[0]["thread_id"] == f"{created.case_id}:r4"
    assert analysis.starts[0]["payload"]["data_revision"] == 4
    assert revision_port.advances[-1] == {
        "case_id": created.case_id,
        "expected_current_revision": 3,
        "next_revision": 4,
        "document_ids": ["doc-0001", "doc-0002"],
    }


def test_canonical_revision_port_conflict_fails_closed_without_starting_analysis(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    revision_port = CanonicalRevisionProbe(next_revision_override=3)
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        case_revision_port=revision_port,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    with pytest.raises(StartupGateConflict, match="case_revision_conflict"):
        coordinator.upload_documents(
            created.case_id,
            files=[{"filename": "deck.pdf", "content": b"first", "content_type": "application/pdf"}],
            auto_start=True,
        )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["document_ids"] == []
    assert "data_revision" not in runtime
    assert analysis.starts == []


def test_deterministic_mode_advances_deterministic_canonical_revision_port_only(
    tmp_path: Path,
) -> None:
    live_revision_port = CanonicalRevisionProbe()
    deterministic_revision_port = CanonicalRevisionProbe()
    live_analysis = AnalysisProbe()
    deterministic_analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=live_analysis,
        deterministic_analysis_service=deterministic_analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        case_revision_port=live_revision_port,
        deterministic_case_revision_port=deterministic_revision_port,
    )
    created = coordinator.create_case(
        {"fixture_mode": "deterministic_offline", "auto_start": False}
    )

    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"fixture", "content_type": "application/pdf"}],
        auto_start=True,
    )

    assert live_revision_port.advances == []
    assert deterministic_revision_port.advances[0]["document_ids"] == ["doc-0001"]
    assert deterministic_analysis.starts[0]["payload"]["data_revision"] == 1
    assert live_analysis.starts == []


def test_declared_mime_type_is_normalized_or_dropped(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    coordinator.upload_documents(
        created.case_id,
        files=[
            {
                "filename": "deck.pdf",
                "content": b"pdf",
                "content_type": " Application/PDF ; charset=utf-8 ",
            },
            {
                "filename": "notes.txt",
                "content": b"text",
                "content_type": "text/plain\r\nx-secret: founder",
            },
            {
                "filename": "metrics.csv",
                "content": b"csv",
                "content_type": "x" * 200 + "/csv",
            },
        ],
        auto_start=False,
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert [item["declared_mime_type"] for item in runtime["documents"]] == [
        "application/pdf",
        None,
        None,
    ]


def test_concurrent_distinct_uploads_reserve_unique_documents_and_matching_bytes(
    tmp_path: Path,
) -> None:
    analysis = BlockingStartProbe(expected_starts=2)
    store = InMemoryStartupWorkflowRuntimeStore()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=store,
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                coordinator.upload_documents,
                created.case_id,
                files=[{"filename": f"deck-{index}.pdf", "content": content, "content_type": "application/pdf"}],
                auto_start=True,
            )
            for index, content in enumerate((b"first bytes", b"second bytes"), start=1)
        ]
        assert analysis.entered.wait(timeout=5)
        analysis.release.set()
        responses = [future.result(timeout=5) for future in futures]

    runtime = coordinator.runtime_for_test(created.case_id)
    assert sorted(response.accepted_document_ids[0] for response in responses) == [
        "doc-0001",
        "doc-0002",
    ]
    assert runtime["document_ids"] == ["doc-0001", "doc-0002"]
    assert runtime["data_revision"] == 2
    assert sorted(start["thread_id"] for start in analysis.starts) == [
        f"{created.case_id}:r1",
        f"{created.case_id}:r2",
    ]
    stored_by_hash = {
        sha256((tmp_path / created.case_id / item["private_name"]).read_bytes()).hexdigest(): item
        for item in runtime["documents"]
    }
    assert set(stored_by_hash) == {item["content_sha256"] for item in runtime["documents"]}
    assert {item["byte_size"] for item in stored_by_hash.values()} == {11, 12}


@pytest.mark.parametrize("store_kind", ["json", "sqlite"])
def test_concurrent_distinct_uploads_across_store_instances_reserve_unique_documents(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store_path = tmp_path / f"startup-runtime-distinct.{store_kind}"
    store_factory = (
        JsonFileStartupWorkflowRuntimeStore
        if store_kind == "json"
        else SQLiteStartupWorkflowRuntimeStore
    )
    analysis = BlockingStartProbe(expected_starts=2)
    first = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=store_factory(store_path),
        inbox_root=tmp_path / "inbox",
    )
    second = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=store_factory(store_path),
        inbox_root=tmp_path / "inbox",
    )
    created = first.create_case({"fixture_mode": "live", "auto_start": False})

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                coordinator.upload_documents,
                created.case_id,
                files=[{"filename": "deck.pdf", "content": content, "content_type": "application/pdf"}],
                auto_start=True,
            )
            for coordinator, content in ((first, b"first bytes"), (second, b"second bytes"))
        ]
        assert analysis.entered.wait(timeout=5)
        analysis.release.set()
        responses = [future.result(timeout=5) for future in futures]

    runtime = store_factory(store_path).load(created.case_id)
    assert sorted(response.accepted_document_ids[0] for response in responses) == [
        "doc-0001",
        "doc-0002",
    ]
    assert runtime["document_ids"] == ["doc-0001", "doc-0002"]
    assert runtime["data_revision"] == 2
    assert len(runtime["documents"]) == 2
    assert sorted(start["thread_id"] for start in analysis.starts) == [
        f"{created.case_id}:r1",
        f"{created.case_id}:r2",
    ]
    assert {
        sha256((tmp_path / "inbox" / created.case_id / item["private_name"]).read_bytes()).hexdigest()
        for item in runtime["documents"]
    } == {item["content_sha256"] for item in runtime["documents"]}


@pytest.mark.parametrize("store_kind", ["json", "sqlite"])
def test_concurrent_duplicate_auto_start_across_store_instances_claims_once(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store_path = tmp_path / f"startup-runtime.{store_kind}"
    store_factory = (
        JsonFileStartupWorkflowRuntimeStore
        if store_kind == "json"
        else SQLiteStartupWorkflowRuntimeStore
    )
    first_analysis = BlockingStartProbe(expected_starts=1)
    second_analysis = first_analysis
    first = StartupCaseCoordinator(
        analysis_service=first_analysis,
        workflow_store=store_factory(store_path),
        inbox_root=tmp_path / "inbox",
    )
    second = StartupCaseCoordinator(
        analysis_service=second_analysis,
        workflow_store=store_factory(store_path),
        inbox_root=tmp_path / "inbox",
    )
    created = first.create_case({"fixture_mode": "live", "auto_start": False})
    first.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
        auto_start=False,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                coordinator.upload_documents,
                created.case_id,
                files=[{"filename": "renamed.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
                auto_start=True,
            )
            for coordinator in (first, second)
        ]
        assert first_analysis.entered.wait(timeout=5)
        first_analysis.release.set()
        responses = [future.result(timeout=5) for future in futures]

    runtime = store_factory(store_path).load(created.case_id)
    assert [response.accepted_document_ids for response in responses] == [
        ["doc-0001"],
        ["doc-0001"],
    ]
    assert sum(response.auto_start_triggered for response in responses) == 1
    assert runtime["data_revision"] == 1
    assert len(runtime["documents"]) == 1
    assert [start["thread_id"] for start in first_analysis.starts] == [f"{created.case_id}:r1"]


@pytest.mark.parametrize("store_kind", ["memory", "json", "sqlite"])
def test_failed_upload_write_does_not_publish_document_revision_or_start_claim(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store = _runtime_store_for(store_kind, tmp_path / f"startup-runtime-write-fail.{store_kind}")
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=store,
        inbox_root=tmp_path / "inbox",
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    blocked_private_path = tmp_path / "inbox" / created.case_id / "doc-0001.pdf"
    blocked_private_path.mkdir(parents=True)

    with pytest.raises((OSError, StartupGateConflict)):
        coordinator.upload_documents(
            created.case_id,
            files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
            auto_start=True,
        )

    runtime = store.load(created.case_id)
    assert runtime["document_ids"] == []
    assert runtime["documents"] == []
    assert "data_revision" not in runtime
    assert "active_analysis_thread_id" not in runtime
    assert "source_document_ids" not in runtime
    assert "source_refs" not in runtime
    assert "analysis_start_claim_thread_id" not in runtime


def test_duplicate_auto_start_waits_until_reserved_bytes_are_written_and_hash_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryStartupWorkflowRuntimeStore()
    analysis = FileExistsAtStartProbe(inbox_root=tmp_path / "inbox")
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=store,
        inbox_root=tmp_path / "inbox",
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    write_entered = Event()
    release_write = Event()
    waiter_entered = Event()
    first_write_blocked = False
    original_atomic_write = getattr(startup_cases_module, "_atomic_write_verified", None)

    def blocking_atomic_write(path: Path, content: bytes, *, expected_hash: str) -> None:
        nonlocal first_write_blocked
        if path.name == "doc-0001.pdf" and content == b"same bytes" and not first_write_blocked:
            first_write_blocked = True
            write_entered.set()
            if not release_write.wait(timeout=5):
                raise RuntimeError("write_release_timeout")
        if callable(original_atomic_write):
            original_atomic_write(path, content, expected_hash=expected_hash)
            return
        path.write_bytes(content)
        if sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError("test_hash_mismatch")

    def wait_for_pending_retry() -> None:
        waiter_entered.set()
        if not release_write.is_set() and not release_write.wait(timeout=5):
            raise RuntimeError("pending_wait_timeout")

    monkeypatch.setattr(startup_cases_module, "_atomic_write_verified", blocking_atomic_write, raising=False)
    monkeypatch.setattr(
        startup_cases_module,
        "_wait_for_pending_upload_retry",
        wait_for_pending_retry,
        raising=False,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            coordinator.upload_documents,
            created.case_id,
            files=[{"filename": "deck.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
            auto_start=False,
        )
        assert write_entered.wait(timeout=5)
        second_future = executor.submit(
            coordinator.upload_documents,
            created.case_id,
            files=[{"filename": "deck-copy.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
            auto_start=True,
        )
        if not waiter_entered.wait(timeout=2):
            analysis.entered.wait(timeout=2)
        release_write.set()
        first_response = first_future.result(timeout=5)
        second_response = second_future.result(timeout=5)

    assert first_response.auto_start_triggered is False
    assert second_response.accepted_document_ids == ["doc-0001"]
    assert second_response.auto_start_triggered is True
    assert [start["thread_id"] for start in analysis.starts] == [f"{created.case_id}:r1"]


def test_failed_auto_start_releases_claim_for_duplicate_retry(tmp_path: Path) -> None:
    analysis = FailingOnceStartProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    with pytest.raises(RuntimeError, match="start_failed_once"):
        coordinator.upload_documents(
            created.case_id,
            files=[{"filename": "deck.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
            auto_start=True,
        )
    runtime_after_failure = coordinator.runtime_for_test(created.case_id)
    assert runtime_after_failure["data_revision"] == 1
    assert runtime_after_failure["analysis_status"] == "awaiting_start"
    assert "analysis_start_claim_thread_id" not in runtime_after_failure

    retry = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "renamed.pdf", "content": b"same bytes", "content_type": "application/pdf"}],
        auto_start=True,
    )

    assert retry.accepted_document_ids == ["doc-0001"]
    assert retry.auto_start_triggered is True
    assert [start["thread_id"] for start in analysis.starts] == [
        f"{created.case_id}:r1",
        f"{created.case_id}:r1",
    ]
    assert coordinator.get_status(created.case_id).analysis_status == "gate2_preview_ready"


@pytest.mark.parametrize("store_kind", ["memory", "json", "sqlite"])
def test_stale_pending_upload_lease_replaces_partial_file_and_publishes_after_restart(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store = _runtime_store_for(store_kind, tmp_path / f"startup-runtime-stale.{store_kind}")
    analysis = FileExistsAtStartProbe(inbox_root=tmp_path / "inbox")
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=store,
        inbox_root=tmp_path / "inbox",
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    content = b"same bytes"
    content_hash = _sha256_bytes(content)
    private_path = tmp_path / "inbox" / created.case_id / "doc-0001.pdf"
    private_path.parent.mkdir(parents=True)
    private_path.write_bytes(b"partial stale write")
    store.save(
        created.case_id,
        {
            "pending_document_uploads": {
                content_hash: {
                    "lease_id": "stale-lease",
                    "created_at": 0.0,
                    "document": {
                        "document_id": "doc-0001",
                        "private_name": "doc-0001.pdf",
                        "declared_mime_type": "application/pdf",
                        "byte_size": len(content),
                        "source_name_sha256": _sha256_text("deck.pdf"),
                        "content_sha256": content_hash,
                    },
                }
            }
        },
    )

    response = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": content, "content_type": "application/pdf"}],
        auto_start=True,
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert response.accepted_document_ids == ["doc-0001"]
    assert response.auto_start_triggered is True
    assert private_path.read_bytes() == content
    assert runtime["document_ids"] == ["doc-0001"]
    assert runtime["documents"][0]["content_sha256"] == content_hash
    assert runtime["data_revision"] == 1
    assert "pending_document_uploads" not in runtime
    assert [start["thread_id"] for start in analysis.starts] == [f"{created.case_id}:r1"]


def test_new_artifact_increments_revision_invalidates_stale_tuples_and_uses_revision_threads(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe(
        resume_results=[{"status": "review_required", "pending_gate": "startup_gate3_review"}]
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"first", "content_type": "application/pdf"}],
        auto_start=True,
    )
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "gate2_resume_token_digest": "stale-token",
            "gate2_resume_token_used": False,
            "gate2_preview": {"evidence_fact_ids": ["stale"]},
            "gate2_status": "required",
            "gate3_status": "completed",
            "gate4_status": "completed",
            "report_status": "ready",
            "canonical_report_snapshot_id": "snapshot-stale",
            "canonical_report_snapshot_hash": "hash-stale",
            "canonical_report_snapshot_revision": 1,
            "profile_id": "profile-stale",
            "profile_hash": "profile-hash-stale",
        },
    )

    response = coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "metrics.csv", "content": b"second", "content_type": "text/csv"}],
        auto_start=True,
    )
    preview = coordinator.get_gate2_preview(created.case_id)
    decision = coordinator.decide_gate2(
        created.case_id,
        {"decision": "approved", "resume_token": preview.resume_token},
    )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert response.accepted_document_ids == ["doc-0002"]
    assert runtime["data_revision"] == 2
    assert runtime["active_analysis_thread_id"] == f"{created.case_id}:r2"
    assert runtime["gate2_status"] == "completed"
    assert runtime["gate3_status"] == "required"
    assert runtime["gate4_status"] == "not_ready"
    assert runtime["report_status"] == "not_ready"
    assert runtime["canonical_report_snapshot_id"] is None
    assert runtime["canonical_report_snapshot_hash"] is None
    assert runtime["canonical_report_snapshot_revision"] is None
    assert runtime["profile_id"] is None
    assert runtime["profile_hash"] is None
    assert [start["thread_id"] for start in analysis.starts] == [
        f"{created.case_id}:r1",
        f"{created.case_id}:r2",
    ]
    assert analysis.starts[1]["payload"]["data_revision"] == 2
    assert analysis.starts[1]["payload"]["source_document_ids"] == ["doc-0001", "doc-0002"]
    assert analysis.resumes[0]["thread_id"] == f"{created.case_id}:r2"
    assert decision.analysis_status == "gate3_review_required"


def test_seed_revision_analysis_starts_current_revision_once_and_is_idempotent(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    payload, thread_id = _seed_revision_two_runtime(coordinator, created.case_id)

    coordinator.seed_revision_analysis(payload, thread_id=thread_id)
    coordinator.seed_revision_analysis(payload, thread_id=thread_id)

    assert analysis.starts == [{"payload": payload, "thread_id": thread_id}]
    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["analysis_revision_seed_status"] == "seeded"
    assert runtime["analysis_status"] == "gate2_preview_ready"
    assert "analysis_revision_seed_claim_id" not in runtime


def test_seed_revision_analysis_rejects_stale_payload_without_starting_graph(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    payload, thread_id = _seed_revision_two_runtime(coordinator, created.case_id)
    stale_payload = {**payload, "data_revision": 1}

    with pytest.raises(StartupGateConflict, match="analysis_revision_seed_payload_invalid"):
        coordinator.seed_revision_analysis(stale_payload, thread_id=thread_id)

    assert analysis.starts == []
    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["data_revision"] == 2
    assert runtime["active_analysis_thread_id"] == thread_id
    assert runtime.get("gate2_resume_token_digest") is None


def test_seed_revision_analysis_start_failure_marks_visible_retryable_failure(
    tmp_path: Path,
) -> None:
    analysis = FailingOnceStartProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    payload, thread_id = _seed_revision_two_runtime(coordinator, created.case_id)

    with pytest.raises(StartupGateConflict, match="analysis_revision_seed_failed"):
        coordinator.seed_revision_analysis(payload, thread_id=thread_id)

    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["analysis_status"] == "failed"
    assert runtime["error_code"] == "analysis_revision_seed_failed"
    assert runtime["analysis_revision_seed_status"] == "retryable"
    assert "analysis_revision_seed_claim_id" not in runtime
    assert "gate2_resume_token_digest" not in runtime


def test_gate2_decision_cannot_resume_with_old_token_while_revision_seed_is_retryable(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=True,
    )
    stale_preview = coordinator.get_gate2_preview(created.case_id)
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "data_revision": 2,
            "active_analysis_thread_id": f"{created.case_id}:r2",
            "analysis_status": "failed",
            "gate2_status": "not_ready",
            "analysis_revision_seed_required": True,
            "analysis_revision_seed_status": "retryable",
        },
    )
    analysis.resumes.clear()

    with pytest.raises(StartupGateConflict, match="analysis_checkpoint_not_ready"):
        coordinator.decide_gate2(
            created.case_id,
            {"decision": "approved", "resume_token": stale_preview.resume_token},
        )

    assert analysis.resumes == []


def test_seed_revision_analysis_retry_completes_after_transient_start_failure(
    tmp_path: Path,
) -> None:
    analysis = FailingOnceStartProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    payload, thread_id = _seed_revision_two_runtime(coordinator, created.case_id)

    with pytest.raises(StartupGateConflict, match="analysis_revision_seed_failed"):
        coordinator.seed_revision_analysis(payload, thread_id=thread_id)

    coordinator.seed_revision_analysis(payload, thread_id=thread_id)
    preview = coordinator.get_gate2_preview(created.case_id)

    assert len(analysis.starts) == 2
    assert preview.case_id == created.case_id
    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["analysis_status"] == "gate2_preview_ready"
    assert runtime["analysis_revision_seed_status"] == "seeded"
    assert "analysis_revision_seed_claim_id" not in runtime


def test_seeded_revision_requires_checkpoint_before_gate2_resume_token(
    tmp_path: Path,
) -> None:
    analysis = CheckpointAnalysisProbe(expose_checkpoint_after_start=False)
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    payload, thread_id = _seed_revision_two_runtime(coordinator, created.case_id)

    with pytest.raises(StartupGateConflict, match="analysis_revision_seed_failed"):
        coordinator.seed_revision_analysis(payload, thread_id=thread_id)
    with pytest.raises(StartupNotFound, match="gate2_preview_not_ready"):
        coordinator.get_gate2_preview(created.case_id)

    assert analysis.resumes == []
    assert "gate2_resume_token_digest" not in coordinator.runtime_for_test(created.case_id)


def test_checkpoint_lookup_failure_returns_stable_visible_error_without_starting_graph(
    tmp_path: Path,
) -> None:
    analysis = FailingCheckpointLookupProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    payload, thread_id = _seed_revision_two_runtime(coordinator, created.case_id)

    with pytest.raises(StartupGateConflict, match="analysis_checkpoint_lookup_failed"):
        coordinator.seed_revision_analysis(payload, thread_id=thread_id)

    assert analysis.starts == []


def test_seeded_revision_allows_gate2_resume_to_gate3_on_current_thread(
    tmp_path: Path,
) -> None:
    analysis = CheckpointAnalysisProbe(expose_checkpoint_after_start=True)
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    payload, thread_id = _seed_revision_two_runtime(coordinator, created.case_id)

    coordinator.seed_revision_analysis(payload, thread_id=thread_id)
    preview = coordinator.get_gate2_preview(created.case_id)
    response = coordinator.decide_gate2(
        created.case_id,
        {"decision": "approved", "resume_token": preview.resume_token},
    )

    assert analysis.resumes == [
        {"approval": {"action": "approved"}, "thread_id": thread_id}
    ]
    assert response.analysis_status == "gate3_review_required"


def test_live_provider_status_is_configured_only_when_explicitly_wired(tmp_path: Path) -> None:
    unavailable = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path / "unavailable",
    )
    configured = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path / "configured",
        live_provider_configured=True,
    )

    unavailable_case = unavailable.create_case({"fixture_mode": "live", "auto_start": False})
    configured_case = configured.create_case({"fixture_mode": "live", "auto_start": False})

    assert unavailable_case.provider_status == "unavailable"
    assert unavailable.runtime_for_test(unavailable_case.case_id)["provider_status"] == "unavailable"
    assert unavailable.get_status(unavailable_case.case_id).provider_status == "unavailable"
    assert configured_case.provider_status == "configured"
    assert configured.runtime_for_test(configured_case.case_id)["provider_status"] == "configured"
    assert configured.get_status(configured_case.case_id).provider_status == "configured"


def test_live_provider_status_is_used_as_auto_start_execution_mode(tmp_path: Path) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        live_provider_configured=True,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=True,
    )

    assert analysis.starts[0]["payload"]["execution_mode"] == "configured"


def test_gate2_tokens_are_opaque_single_use_and_resume_with_internal_action(tmp_path: Path) -> None:
    analysis = AnalysisProbe(
        resume_results=[
            {"status": "review_required", "pending_gate": "startup_gate3_review"},
        ]
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        deterministic_analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "deterministic_offline", "auto_start": False})
    coordinator.upload_documents(
        created.case_id,
        files=[{"filename": "deck.pdf", "content": b"metrics", "content_type": "application/pdf"}],
        auto_start=False,
    )
    coordinator.seed_gate2_preview_for_test(created.case_id, {"artifact_counts": {"pdf": 1}})

    preview = coordinator.get_gate2_preview(created.case_id)
    assert preview.resume_token
    assert len(preview.resume_token) >= 32
    assert preview.provider_mode == "deterministic_offline_fixture"
    assert preview.resume_token not in repr(coordinator.runtime_for_test(created.case_id))
    with pytest.raises(StartupGateConflict, match="resume_token_invalid"):
        coordinator.decide_gate2(created.case_id, {"decision": "approved", "resume_token": "wrong"})

    response = coordinator.decide_gate2(
        created.case_id,
        {"decision": "approved", "resume_token": preview.resume_token, "reason": "ok to proceed"},
    )

    assert response.analysis_status == "gate3_review_required"
    assert analysis.resumes[0]["approval"] == {"action": "approved"}
    assert coordinator.runtime_for_test(created.case_id)["gate2_decision_reason"] == "ok to proceed"
    with pytest.raises(StartupGateConflict, match="resume_token_invalid"):
        coordinator.decide_gate2(
            created.case_id,
            {"decision": "approved", "resume_token": preview.resume_token},
        )


def test_concurrent_gate2_decisions_consume_same_token_once(tmp_path: Path) -> None:
    analysis = BlockingResumeProbe(
        resume_result={"status": "review_required", "pending_gate": "startup_gate3_review"}
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_gate2_preview_for_test(created.case_id, {"artifact_counts": {"pdf": 1}})
    token = coordinator.get_gate2_preview(created.case_id).resume_token

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                coordinator.decide_gate2,
                created.case_id,
                {"decision": "approved", "resume_token": token},
            )
            for _ in range(2)
        ]
        analysis.entered.wait(timeout=5)
        analysis.release.set()
        outcomes: list[str] = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=5).analysis_status)
            except StartupGateConflict as exc:
                outcomes.append(str(exc))

    assert sorted(outcomes) == ["gate3_review_required", "resume_token_invalid"]
    assert len(analysis.resumes) == 1


def test_json_runtime_store_consumes_token_once_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "startup-runtime.json"
    first = JsonFileStartupWorkflowRuntimeStore(path)
    second = JsonFileStartupWorkflowRuntimeStore(path)
    first.save(
        "case-1",
        {
            "gate2_resume_token_digest": "digest-1",
            "gate2_resume_token_used": False,
        },
    )
    writes_entered = Event()
    release_writes = Event()

    def hold_first_write(records: dict[str, Any]) -> None:
        writes_entered.set()
        if not release_writes.wait(timeout=5):
            raise RuntimeError("write_barrier_timeout")
        original_first_write(records)

    original_first_write = first._write_all
    first._write_all = hold_first_write  # type: ignore[method-assign]

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            first.consume_resume_token,
            "case-1",
            gate="gate2",
            expected_digest="digest-1",
        )
        assert writes_entered.wait(timeout=5)
        second_future = executor.submit(
            second.consume_resume_token,
            "case-1",
            gate="gate2",
            expected_digest="digest-1",
        )
        release_writes.set()
        outcomes = [first_future.result(timeout=5), second_future.result(timeout=5)]

    assert sorted(outcomes) == [False, True]
    assert JsonFileStartupWorkflowRuntimeStore(path).load("case-1") == {
        "gate2_resume_token_digest": None,
        "gate2_resume_token_used": True,
    }


def test_json_runtime_store_retries_transient_windows_replace_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "startup-runtime.json"
    store = JsonFileStartupWorkflowRuntimeStore(path)
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(source: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            error = PermissionError("transient Windows sharing violation")
            setattr(error, "winerror", 32)
            raise error
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    store.save("case-1", {"analysis_status": "gate2_preview_ready"})

    assert attempts == 3
    assert store.load("case-1") == {"analysis_status": "gate2_preview_ready"}


def test_json_runtime_store_bounds_windows_replace_retries_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "startup-runtime.json"
    store = JsonFileStartupWorkflowRuntimeStore(path)
    attempts = 0

    def blocked_replace(_source: Path, _target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        error = PermissionError("persistent Windows sharing violation")
        setattr(error, "winerror", 32)
        raise error

    monkeypatch.setattr(Path, "replace", blocked_replace)
    monkeypatch.setattr(startup_runtime_module, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="persistent Windows sharing violation"):
        store.save("case-1", {"analysis_status": "gate2_preview_ready"})

    assert attempts == 5
    assert not path.exists()


def test_gate2_resume_exception_persists_safe_failure_state(tmp_path: Path) -> None:
    analysis = ThrowingResumeProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_gate2_preview_for_test(created.case_id, {"artifact_counts": {"pdf": 1}})
    token = coordinator.get_gate2_preview(created.case_id).resume_token

    with pytest.raises(StartupGateConflict, match="gate2_resume_failed"):
        coordinator.decide_gate2(
            created.case_id,
            {"decision": "approved", "resume_token": token},
        )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["analysis_status"] == "failed"
    assert runtime["gate2_status"] == "required"
    assert runtime["error_code"] == "gate2_resume_failed"
    assert runtime["gate2_resume_token_digest"] is None
    assert runtime["gate2_resume_token_used"] is True
    with pytest.raises(StartupGateConflict, match="resume_token_invalid"):
        coordinator.decide_gate2(
            created.case_id,
            {"decision": "approved", "resume_token": token},
        )


def test_gate2_failed_graph_resume_persists_safe_failure_state(tmp_path: Path) -> None:
    analysis = AnalysisProbe(
        resume_results=[
            {
                "status": "failed",
                "pending_gate": None,
                "error_code": "startup_document_intelligence_input_invalid",
                "raw_payload": "secret filename.pdf token abc123",
            }
        ]
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_gate2_preview_for_test(created.case_id, {"artifact_counts": {"pdf": 1}})
    token = coordinator.get_gate2_preview(created.case_id).resume_token

    with pytest.raises(
        StartupGateConflict,
        match="startup_document_intelligence_input_invalid",
    ):
        coordinator.decide_gate2(
            created.case_id,
            {"decision": "approved", "resume_token": token},
        )

    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["analysis_status"] == "failed"
    assert runtime["gate2_status"] == "required"
    assert runtime["error_code"] == "startup_document_intelligence_input_invalid"
    assert runtime["gate2_resume_token_digest"] is None
    assert runtime["gate2_resume_token_used"] is True
    assert "raw_payload" not in runtime


def test_gate3_validates_evidence_exclusions_and_report_boundary_is_truthful(tmp_path: Path) -> None:
    analysis = AnalysisProbe(
        resume_results=[
            {"status": "completed", "pending_gate": None, "report_snapshot_id": "draft-not-canonical"},
        ]
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "analysis_status": "gate3_review_required",
            "evidence_fact_ids": ["fact-1"],
        },
    )

    with pytest.raises(StartupValidationError, match="unknown_evidence_fact_id"):
        coordinator.decide_gate3(
            created.case_id,
            {"decision": "continue", "exclusions": [{"evidence_fact_id": "fact-x"}]},
        )

    response = coordinator.decide_gate3(
        created.case_id,
        {
            "decision": "continue",
            "exclusions": [
                {
                    "evidence_fact_id": "fact-1",
                    "reason": "duplicate source; founder@example.com ignored",
                }
            ],
        },
    )

    assert response.analysis_status == "analysis_complete_report_pending"
    assert analysis.resumes[0]["approval"] == {
        "gate": "startup_gate3_review",
        "action": "continue",
        "exclusions": [{"evidence_fact_id": "fact-1"}],
    }
    assert coordinator.runtime_for_test(created.case_id)["gate3_exclusion_reasons"] == {
        "fact-1": "duplicate source founder example com ignored"
    }
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_html(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_pdf(created.case_id)


def test_completed_with_policy_blocks_projects_report_pending_with_indicator(tmp_path: Path) -> None:
    analysis = AnalysisProbe(
        resume_results=[
            {
                "status": "completed_with_policy_blocks",
                "pending_gate": None,
                "policy_block_codes": ["blocked_by_policy:startup_disclosure"],
            }
        ]
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "analysis_status": "gate3_review_required",
            "evidence_fact_ids": [],
        },
    )

    response = coordinator.decide_gate3(
        created.case_id,
        {"decision": "continue", "exclusions": []},
    )

    assert response.analysis_status == "analysis_complete_report_pending"
    runtime = coordinator.runtime_for_test(created.case_id)
    assert runtime["policy_blocked"] is True
    assert runtime["policy_block_codes"] == ["blocked_by_policy:startup_disclosure"]


def test_report_pdf_and_gate4_distinguish_no_snapshot_from_unfrozen_snapshot(
    tmp_path: Path,
) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_pdf(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.decide_gate4(
            created.case_id,
            {"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
        )

    coordinator.seed_status_for_test(
        created.case_id,
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_hash": "hash-1",
            "canonical_report_snapshot_revision": 1,
        },
    )

    report = coordinator.get_report(created.case_id)
    assert report.model_dump() == {
        "case_id": created.case_id,
        "report_status": "ready",
        "snapshot_id": "snapshot-1",
        "snapshot_hash": "hash-1",
        "snapshot_revision": 1,
        "json_url": f"/api/v1/startup/cases/{created.case_id}/report/json",
        "html_url": f"/api/v1/startup/cases/{created.case_id}/report/html",
        "pdf_url": f"/api/v1/startup/cases/{created.case_id}/report/pdf",
        "freeze_status": "required",
        "pdf_status": "freeze_required",
    }
    with pytest.raises(StartupGateConflict, match="gate_4_freeze_required"):
        coordinator.get_report_pdf(created.case_id)
    with pytest.raises(StartupGateConflict, match="gate_4_freeze_required"):
        coordinator.decide_gate4(
            created.case_id,
            {"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
        )


def test_report_metadata_and_artifacts_are_served_from_injected_report_port(
    tmp_path: Path,
) -> None:
    reports = ReportFacadeProbe(
        snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1),
        canonical_json=b'{"schema":"startup_report_snapshot.v1"}',
        html="<main>canonical draft</main>",
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "canonical_report_snapshot_id": "runtime-snapshot-must-not-win",
            "canonical_report_snapshot_hash": "runtime-hash",
            "canonical_report_snapshot_revision": 99,
            "canonical_report_html": "<main>runtime html must not win</main>",
            "canonical_report_pdf": b"%PDF-runtime-must-not-win",
            "gate4_approved": True,
        },
    )

    report = coordinator.get_report(created.case_id)

    assert report.snapshot_id == "snapshot-1"
    assert report.snapshot_hash == "hash-1"
    assert report.snapshot_revision == 1
    assert report.json_url == f"/api/v1/startup/cases/{created.case_id}/report/json"
    assert report.html_url == f"/api/v1/startup/cases/{created.case_id}/report/html"
    assert report.pdf_url == f"/api/v1/startup/cases/{created.case_id}/report/pdf"
    assert report.freeze_status == "required"
    assert report.pdf_status == "freeze_required"
    assert coordinator.get_report_json(created.case_id) == b'{"data_revision":1,"main_sections":[]}'
    assert coordinator.get_report_html(created.case_id) == "<main>canonical draft</main>"
    with pytest.raises(StartupGateConflict, match="gate_4_freeze_required"):
        coordinator.get_report_pdf(created.case_id)
    assert ("founder_json", created.case_id) in reports.calls
    assert ("html", created.case_id) in reports.calls
    assert ("pdf", created.case_id) in reports.calls


def test_missing_report_port_snapshot_maps_to_typed_not_ready_errors(tmp_path: Path) -> None:
    reports = MissingReportFacadeProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_json(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_html(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_pdf(created.case_id)
    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.decide_gate4(
            created.case_id,
            {"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
        )


def test_gate4_exact_approval_and_rejection_are_persisted_and_echo_snapshot_tuple(
    tmp_path: Path,
) -> None:
    reports = ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1))
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    with pytest.raises(StartupGateConflict, match="gate_4_snapshot_mismatch"):
        coordinator.decide_gate4(
            created.case_id,
            {"decision": "approved", "snapshot_hash": "wrong", "snapshot_revision": 1},
        )
    assert reports.decisions == []

    approved = coordinator.decide_gate4(
        created.case_id,
        {"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
    )
    rejected = coordinator.decide_gate4(
        created.case_id,
        {"decision": "rejected", "snapshot_hash": "hash-1", "snapshot_revision": 1},
    )

    assert [item["decision"] for item in reports.decisions] == ["approved", "rejected"]
    assert approved.gate4_status == "completed"
    assert approved.report_status == "ready"
    assert approved.snapshot_hash == "hash-1"
    assert approved.snapshot_revision == 1
    assert rejected.snapshot_hash == "hash-1"
    assert rejected.snapshot_revision == 1
    report = coordinator.get_report(created.case_id)
    assert report.freeze_status == "required"
    assert report.pdf_status == "freeze_required"


def test_report_snapshot_tuple_survives_runtime_reload_without_report_bytes(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "startup-runtime.json"
    first = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(
            resume_results=[
                {
                    "status": "completed",
                    "pending_gate": None,
                    "report_snapshot_id": "snapshot-1",
                    "report_snapshot_hash": "hash-1",
                    "report_snapshot_revision": 7,
                }
            ]
        ),
        workflow_store=JsonFileStartupWorkflowRuntimeStore(store_path),
        inbox_root=tmp_path / "inbox-a",
    )
    created = first.create_case({"fixture_mode": "live", "auto_start": False})
    first.seed_status_for_test(
        created.case_id,
        {
            "analysis_status": "gate3_review_required",
            "evidence_fact_ids": [],
        },
    )
    decision = first.decide_gate3(created.case_id, {"decision": "continue", "exclusions": []})
    assert decision.snapshot_hash == "hash-1"
    assert decision.snapshot_revision == 7

    reloaded = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=JsonFileStartupWorkflowRuntimeStore(store_path),
        inbox_root=tmp_path / "inbox-b",
        report_port=ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 7)),
    )

    status = reloaded.get_status(created.case_id)
    report = reloaded.get_report(created.case_id)

    assert status.report_status == "ready"
    assert status.snapshot_hash == "hash-1"
    assert status.snapshot_revision == 7
    assert report.snapshot_id == "snapshot-1"
    assert "canonical_report_html" not in reloaded.runtime_for_test(created.case_id)
    assert "canonical_report_pdf" not in reloaded.runtime_for_test(created.case_id)


def test_boolean_snapshot_revision_is_never_projected_as_report_tuple(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_hash": "hash-1",
            "canonical_report_snapshot_revision": True,
        },
    )

    status = coordinator.get_status(created.case_id)

    assert status.report_status == "not_ready"
    assert status.snapshot_hash == "hash-1"
    assert status.snapshot_revision is None


def test_pdf_renderer_unavailable_is_distinct_from_gate4_freeze(
    tmp_path: Path,
) -> None:
    reports = ReportFacadeProbe(
        snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1),
        pdf_error=StartupReportRendererUnavailable("report_renderer_unavailable"),
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.decide_gate4(
        created.case_id,
        {"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
    )

    with pytest.raises(StartupReportRendererUnavailable, match="report_renderer_unavailable"):
        coordinator.get_report_pdf(created.case_id)


def test_partial_report_snapshot_tuple_is_not_ready_for_pdf_or_gate4(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    for values in (
        {"canonical_report_snapshot_id": "snapshot-1"},
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_hash": "hash-1",
        },
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_revision": 1,
        },
        {
            "canonical_report_snapshot_hash": "hash-1",
            "canonical_report_snapshot_revision": 1,
        },
        {
            "canonical_report_snapshot_id": "",
            "canonical_report_snapshot_hash": "hash-1",
            "canonical_report_snapshot_revision": 1,
        },
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_hash": "",
            "canonical_report_snapshot_revision": 1,
        },
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_hash": "hash-1",
            "canonical_report_snapshot_revision": "1",
        },
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_hash": "hash-1",
            "canonical_report_snapshot_revision": True,
        },
        {
            "canonical_report_snapshot_id": "snapshot-1",
            "canonical_report_snapshot_hash": "hash-1",
            "canonical_report_snapshot_revision": False,
        },
    ):
        coordinator.seed_status_for_test(
            created.case_id,
            {
                "canonical_report_snapshot_id": None,
                "canonical_report_snapshot_hash": None,
                "canonical_report_snapshot_revision": None,
                "canonical_report_pdf": b"%PDF-1.4",
                "gate4_approved": True,
                **values,
            },
        )

        with pytest.raises(StartupNotFound, match="report_not_ready"):
            coordinator.get_report(created.case_id)
        with pytest.raises(StartupNotFound, match="report_not_ready"):
            coordinator.get_report_html(created.case_id)
        with pytest.raises(StartupNotFound, match="report_not_ready"):
            coordinator.get_report_pdf(created.case_id)
        with pytest.raises(StartupNotFound, match="report_not_ready"):
            coordinator.decide_gate4(
                created.case_id,
                {"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
            )


def test_report_html_requires_canonical_snapshot_tuple(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    coordinator.seed_status_for_test(
        created.case_id,
        {"canonical_report_html": "<main>draft only</main>"},
    )

    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_html(created.case_id)

    with pytest.raises(StartupNotFound, match="report_not_ready"):
        coordinator.get_report_html(created.case_id)

    reports = ReportFacadeProbe(
        snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1),
        html="<main>canonical draft</main>",
    )
    coordinator_with_port = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    created_with_port = coordinator_with_port.create_case(
        {"fixture_mode": "live", "auto_start": False}
    )

    assert coordinator_with_port.get_report_html(created_with_port.case_id) == (
        "<main>canonical draft</main>"
    )


def test_get_profile_returns_current_canonical_profile_projection(tmp_path: Path) -> None:
    profiles = ProfileQueryProbe(_startup_profile())
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=profiles,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    profile = _startup_profile(case_id=UUID(created.case_id))
    profiles.profile = profile
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "profile_id": str(profile.profile_id),
            "profile_hash": profile.profile_hash,
            "profile_revision": profile.data_revision,
        },
    )

    response = coordinator.get_profile(created.case_id)

    assert response.case_id == created.case_id
    assert response.profile_id == str(profile.profile_id)
    assert response.profile_hash == profile.profile_hash
    assert response.data_revision == 1
    assert response.analysis_stage == "primary"
    assert response.parent_profile_id is None
    assert set(response.fields) == {field.value for field in StartupProfileFieldName}
    assert response.fields["startup_name"].status == "source_fact"
    assert response.fields["startup_name"].confidence == "0.95"
    assert response.fields["startup_name"].evidence_refs[0].artifact_hash == f"sha256:{'1' * 64}"
    assert response.gaps == ["users"]
    assert response.contradictions == []
    assert response.parse_inventory.source_hashes == {"doc-0001": f"sha256:{'1' * 64}"}
    assert response.parse_inventory.parse_outcomes == {"doc-0001": "parsed"}


def test_get_profile_fails_closed_when_runtime_has_no_current_profile_tuple(
    tmp_path: Path,
) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=ProfileQueryProbe(_startup_profile()),
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    with pytest.raises(StartupGateConflict, match="startup_profile_not_ready"):
        coordinator.get_profile(created.case_id)


def test_get_profile_fails_closed_when_persisted_profile_tuple_is_stale(
    tmp_path: Path,
) -> None:
    profiles = ProfileQueryProbe(_startup_profile())
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=profiles,
    )
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    profile = _startup_profile(case_id=UUID(created.case_id))
    profiles.profile = profile
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "profile_id": str(profile.profile_id),
            "profile_hash": f"sha256:{'9' * 64}",
            "profile_revision": profile.data_revision,
        },
    )

    with pytest.raises(StartupGateConflict, match="startup_profile_stale"):
        coordinator.get_profile(created.case_id)


def test_get_profile_uses_deterministic_profile_port_for_deterministic_mode(
    tmp_path: Path,
) -> None:
    live = ProfileQueryProbe(_startup_profile())
    deterministic = ProfileQueryProbe(_startup_profile(name="DeterministicCo"))
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        deterministic_analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=live,
        deterministic_profile_port=deterministic,
    )
    created = coordinator.create_case(
        {"fixture_mode": "deterministic_offline", "auto_start": False}
    )
    deterministic_profile = _startup_profile(
        case_id=UUID(created.case_id),
        name="DeterministicCo",
    )
    deterministic.profile = deterministic_profile
    coordinator.seed_status_for_test(
        created.case_id,
        {
            "profile_id": str(deterministic_profile.profile_id),
            "profile_hash": deterministic_profile.profile_hash,
            "profile_revision": deterministic_profile.data_revision,
        },
    )

    response = coordinator.get_profile(created.case_id)

    assert response.fields["startup_name"].values == ["DeterministicCo"]
    assert live.current_calls == []
    assert deterministic.current_calls == [created.case_id]


def test_unknown_case_is_not_found(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )

    with pytest.raises(StartupNotFound):
        coordinator.get_status("00000000-0000-0000-0000-000000000000")


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _runtime_store_for(
    store_kind: str,
    path: Path,
) -> InMemoryStartupWorkflowRuntimeStore | JsonFileStartupWorkflowRuntimeStore | SQLiteStartupWorkflowRuntimeStore:
    if store_kind == "memory":
        return InMemoryStartupWorkflowRuntimeStore()
    if store_kind == "json":
        return JsonFileStartupWorkflowRuntimeStore(path)
    if store_kind == "sqlite":
        return SQLiteStartupWorkflowRuntimeStore(path)
    raise AssertionError(f"unknown store kind: {store_kind}")


class AnalysisProbe:
    def __init__(
        self,
        *,
        start_result: dict[str, Any] | None = None,
        resume_results: list[dict[str, Any]] | None = None,
    ) -> None:
        self.start_result = start_result or {
            "status": "approval_required",
            "pending_gate": "startup_disclosure",
        }
        self.resume_results = list(resume_results or [])
        self.starts: list[dict[str, Any]] = []
        self.resumes: list[dict[str, Any]] = []

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.starts.append({"payload": payload, "thread_id": thread_id})
        return dict(self.start_result)

    def resume(self, approval: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.resumes.append({"approval": approval, "thread_id": thread_id})
        if self.resume_results:
            return self.resume_results.pop(0)
        return {"status": "completed", "pending_gate": None}


class CheckpointAnalysisProbe(AnalysisProbe):
    checkpoint_identity_required_for_resume = True

    def __init__(self, *, expose_checkpoint_after_start: bool) -> None:
        super().__init__(
            resume_results=[
                {"status": "review_required", "pending_gate": "startup_gate3_review"}
            ]
        )
        self.expose_checkpoint_after_start = expose_checkpoint_after_start
        self.identities: dict[str, dict[str, Any]] = {}

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        result = super().start(payload, thread_id=thread_id)
        if self.expose_checkpoint_after_start:
            self.identities[thread_id] = {
                "checkpoint_hash": "d" * 64,
                "checkpoint_id": "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
                "data_revision": payload["data_revision"],
                "thread_id": thread_id,
            }
        return result

    def checkpoint_identity(self, *, thread_id: str) -> dict[str, Any] | None:
        identity = self.identities.get(thread_id)
        return dict(identity) if identity is not None else None


class FailingCheckpointLookupProbe(CheckpointAnalysisProbe):
    def __init__(self) -> None:
        super().__init__(expose_checkpoint_after_start=True)

    def checkpoint_identity(self, *, thread_id: str) -> dict[str, Any] | None:
        del thread_id
        raise RuntimeError("checkpoint_store_unavailable")


class BlockingResumeProbe(AnalysisProbe):
    def __init__(self, *, resume_result: dict[str, Any]) -> None:
        super().__init__(resume_results=[resume_result, resume_result])
        self.entered = Event()
        self.release = Event()

    def resume(self, approval: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("blocking_resume_timeout")
        return super().resume(approval, thread_id=thread_id)


class BlockingStartProbe(AnalysisProbe):
    def __init__(self, *, expected_starts: int) -> None:
        super().__init__()
        self.expected_starts = expected_starts
        self.entered = Event()
        self.release = Event()

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        result = super().start(payload, thread_id=thread_id)
        if len(self.starts) >= self.expected_starts:
            self.entered.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("blocking_start_timeout")
        return result


class FileExistsAtStartProbe(AnalysisProbe):
    def __init__(self, *, inbox_root: Path) -> None:
        super().__init__()
        self.inbox_root = inbox_root
        self.entered = Event()

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.entered.set()
        case_id = str(payload["case_id"])
        for source_ref in payload["source_refs"]:
            private_name = str(source_ref["private_name"])
            expected_hash = str(source_ref["content_sha256"])
            stored_path = self.inbox_root / case_id / private_name
            if not stored_path.is_file():
                raise RuntimeError("source_file_missing_at_start")
            if sha256(stored_path.read_bytes()).hexdigest() != expected_hash:
                raise RuntimeError("source_file_hash_mismatch_at_start")
        return super().start(payload, thread_id=thread_id)


class FailingOnceStartProbe(AnalysisProbe):
    def __init__(self) -> None:
        super().__init__()
        self.failures_remaining = 1

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.starts.append({"payload": payload, "thread_id": thread_id})
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("start_failed_once")
        return dict(self.start_result)


class ThrowingResumeProbe(AnalysisProbe):
    def resume(self, approval: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.resumes.append({"approval": approval, "thread_id": thread_id})
        raise RuntimeError("provider exploded with filename secret.pdf token abc123")


def _seed_revision_two_runtime(
    coordinator: StartupCaseCoordinator,
    case_id: str,
) -> tuple[dict[str, Any], str]:
    runtime = coordinator.runtime_for_test(case_id)
    thread_id = f"{case_id}:r2"
    payload = {
        "case_id": case_id,
        "run_id": f"startup-api-{case_id}",
        "correlation_id": case_id,
        "source_document_ids": list(runtime["source_document_ids"]),
        "source_refs": [dict(item) for item in runtime["source_refs"]],
        "data_revision": 2,
        "fixture_mode": "live",
        "execution_mode": "configured",
    }
    coordinator.seed_status_for_test(
        case_id,
        {
            "data_revision": 2,
            "active_analysis_thread_id": thread_id,
            "analysis_status": "gate2_preview_ready",
            "gate2_status": "required",
            "source_refs_revision": 2,
            "analysis_start_claim_data_revision": 2,
            "analysis_start_claim_thread_id": thread_id,
            "analysis_revision_seed_required": True,
            "analysis_revision_seed_status": "pending",
        },
    )
    return payload, thread_id


class ReportFacadeProbe:
    def __init__(
        self,
        *,
        snapshot: CanonicalReportSnapshot,
        canonical_json: bytes = b'{"schema":"startup_report_snapshot.v1"}',
        html: str = "<main>canonical draft</main>",
        pdf: bytes = b"%PDF-1.4\n",
        pdf_error: Exception | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.canonical_json = canonical_json
        self.html_body = html
        self.pdf_body = pdf
        self.pdf_error = pdf_error
        self.calls: list[tuple[str, str]] = []
        self.decisions: list[dict[str, object]] = []
        self.latest_decision: str | None = None

    def current_snapshot(self, case_id: str) -> CanonicalReportSnapshot:
        self.calls.append(("current_snapshot", case_id))
        return self.snapshot

    def canonical_json_bytes(self, case_id: str) -> bytes:
        self.calls.append(("canonical_json", case_id))
        return self.canonical_json

    def founder_json_bytes(self, case_id: str) -> bytes:
        self.calls.append(("founder_json", case_id))
        return b'{"data_revision":1,"main_sections":[]}'

    def html(self, case_id: str) -> str:
        self.calls.append(("html", case_id))
        return self.html_body

    def pdf(self, case_id: str) -> bytes:
        self.calls.append(("pdf", case_id))
        if self.latest_decision != "approved":
            raise StartupGateConflict("gate_4_freeze_required")
        if self.pdf_error is not None:
            raise self.pdf_error
        return self.pdf_body

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: str,
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot:
        self.calls.append(("decide_gate4", case_id))
        if snapshot_hash != self.snapshot.snapshot_hash or snapshot_revision != self.snapshot.snapshot_revision:
            raise StartupGateConflict("gate_4_snapshot_mismatch")
        self.decisions.append(
            {
                "case_id": case_id,
                "decision": decision,
                "snapshot_hash": snapshot_hash,
                "snapshot_revision": snapshot_revision,
                "reason": reason,
            }
        )
        self.latest_decision = decision
        return self.snapshot

    def freeze_status(self, case_id: str) -> FreezeStatus:
        self.calls.append(("freeze_status", case_id))
        return "approved" if self.latest_decision == "approved" else "required"

    def pdf_status(self, case_id: str) -> PdfStatus:
        self.calls.append(("pdf_status", case_id))
        return "ready" if self.latest_decision == "approved" and self.pdf_error is None else "freeze_required"


class MissingReportFacadeProbe:
    def current_snapshot(self, case_id: str) -> CanonicalReportSnapshot:
        raise KeyError("report_not_ready")

    def canonical_json_bytes(self, case_id: str) -> bytes:
        raise KeyError("report_not_ready")

    def founder_json_bytes(self, case_id: str) -> bytes:
        raise KeyError("report_not_ready")

    def html(self, case_id: str) -> str:
        raise KeyError("report_not_ready")

    def pdf(self, case_id: str) -> bytes:
        raise KeyError("report_not_ready")

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: str,
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot:
        raise KeyError("report_not_ready")

    def freeze_status(self, case_id: str) -> FreezeStatus:
        raise KeyError("report_not_ready")

    def pdf_status(self, case_id: str) -> PdfStatus:
        raise KeyError("report_not_ready")


class CanonicalRevisionProbe:
    def __init__(self, *, next_revision_override: int | None = None) -> None:
        self.revisions: dict[str, int] = {}
        self.next_revision_override = next_revision_override
        self.advances: list[dict[str, object]] = []
        self.current_calls: list[str] = []

    def current_revision(self, case_id: str) -> int:
        self.current_calls.append(case_id)
        return self.revisions.get(case_id, 0)

    def advance_revision(
        self,
        case_id: str,
        *,
        expected_current_revision: int,
        document_ids: list[str],
        source_refs: list[dict[str, str]],
        metadata: dict[str, str],
    ) -> int:
        del source_refs, metadata
        current = self.revisions.get(case_id, 0)
        if current != expected_current_revision:
            raise StartupGateConflict("case_revision_conflict")
        next_revision = (
            self.next_revision_override
            if self.next_revision_override is not None
            else expected_current_revision + 1
        )
        self.advances.append(
            {
                "case_id": case_id,
                "expected_current_revision": expected_current_revision,
                "next_revision": next_revision,
                "document_ids": list(document_ids),
            }
        )
        self.revisions[case_id] = next_revision
        return next_revision


class ProfileQueryProbe:
    def __init__(self, profile: StartupProfile) -> None:
        self.profile = profile
        self.current_calls: list[str] = []
        self.get_calls: list[UUID] = []

    def get_current(self, case_id: UUID) -> StartupProfile:
        self.current_calls.append(str(case_id))
        return self.profile

    def get(self, profile_id: UUID) -> StartupProfile:
        self.get_calls.append(profile_id)
        if profile_id != self.profile.profile_id:
            raise KeyError(f"startup_profile_not_found:{profile_id}")
        return self.profile


def _startup_profile(*, case_id: UUID | None = None, name: str = "FounderCo") -> StartupProfile:
    evidence_id = uuid4()
    artifact_id = uuid4()
    fragment_id = uuid4()
    field_values: dict[StartupProfileFieldName, StartupProfileField] = {}
    for field_name in StartupProfileFieldName:
        if field_name is StartupProfileFieldName.STARTUP_NAME:
            field_values[field_name] = StartupProfileField(
                name=field_name,
                status=StartupProfileFieldStatus.SOURCE_FACT,
                values=(name,),
                confidence=Decimal("0.95"),
                evidence_refs=(
                    StartupProfileEvidenceRef(
                        evidence_id=evidence_id,
                        fragment_id=fragment_id,
                        artifact_id=artifact_id,
                        artifact_hash=f"sha256:{'1' * 64}",
                        locator_hash=f"sha256:{'2' * 64}",
                        page=1,
                        field_name=field_name,
                        confidence=Decimal("0.95"),
                    ),
                ),
            )
        else:
            field_values[field_name] = StartupProfileField(
                name=field_name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal(0),
                reason_code=f"{field_name.value}_missing",
            )
    return StartupProfile.build(
        case_id=case_id or uuid4(),
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="test-profile-query@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=1,
        source_hashes={"doc-0001": f"sha256:{'1' * 64}"},
        parse_outcomes={"doc-0001": "parsed"},
        fields={name.value: field for name, field in field_values.items()},
        gap_codes=("users",),
        case_revision_at=datetime(2026, 8, 13, tzinfo=UTC),
    )

from __future__ import annotations

import os
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from due_diligence_agent.config import Settings


def test_local_container_boots_without_network_or_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    from due_diligence_agent.bootstrap.container import build_container

    settings = Settings(data_dir=tmp_path, langsmith_tracing=False)
    container = build_container(settings, use_fixture_adapters=True)

    assert container.public_analysis_service is not None
    assert container.report_service is not None
    assert container.audit_spool is not None
    assert container.settings.langsmith_tracing is False
    container.close()


def test_container_uses_reopenable_sqlite_checkpoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    from due_diligence_agent.bootstrap.container import build_container

    settings = Settings(data_dir=tmp_path, langsmith_tracing=False)
    container = build_container(settings, use_fixture_adapters=True)
    case = container.case_service.create_public_case(
        ticker="AAPL",
        entity_name="Apple Inc.",
        as_of=datetime(2026, 6, 30, tzinfo=UTC),
    )
    state = container.public_analysis_service.start(
        ticker="AAPL",
        case_id=str(case.case_id),
        as_of="2026-06-30T00:00:00+00:00",
    )
    assert state["status"] == "awaiting_scope_approval"
    container.close()

    reopened = build_container(settings, use_fixture_adapters=True)
    snapshot = reopened.public_graph.get_state({"configurable": {"thread_id": str(case.case_id)}})
    assert snapshot.values["status"] == "awaiting_scope_approval"
    reopened.close()


def test_fixture_retrieval_index_survives_container_reopen(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    from due_diligence_agent.bootstrap.container import build_container
    from due_diligence_agent.domain.common import SensitivityClass

    settings = Settings(data_dir=tmp_path, langsmith_tracing=False)
    container = build_container(settings, use_fixture_adapters=True)
    case = container.case_service.create_public_case(
        ticker="AAPL",
        entity_name="Apple Inc.",
        as_of=datetime(2026, 6, 30, tzinfo=UTC),
    )
    filing = asyncio_run(
        container.public_sources.sec.fetch_filing(
            "0000320193-26-000001",
            as_of=datetime(2026, 6, 30, tzinfo=UTC).date(),
        )
    ).data
    assert filing is not None
    chunks = container.retrieval_service.index_filing(
        case_id=case.case_id,
        filing=filing,
        sensitivity=SensitivityClass.PUBLIC,
    )
    first_hits = container.retrieval_service.search("revenue", k=3, case_id=case.case_id)
    container.close()

    reopened = build_container(settings, use_fixture_adapters=True)
    reopened_hits = reopened.retrieval_service.search("revenue", k=3, case_id=case.case_id)

    assert chunks
    assert [hit.chunk_id for hit in reopened_hits] == [hit.chunk_id for hit in first_hits]
    assert {hit.model_id for hit in reopened_hits} == {"fixture-deterministic-embedding"}
    assert (tmp_path / "retrieval-index" / str(case.case_id) / "index.faiss").exists()
    reopened.close()


def test_presentation_modules_import_without_runtime_side_effects(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    import due_diligence_agent.presentation.cli as cli
    from due_diligence_agent.presentation.api.app import create_app
    import due_diligence_agent.presentation.streamlit.app as app
    from due_diligence_agent.presentation.streamlit.pages import public_case

    assert cli.main is not None
    assert create_app().title == "Founder Launch Intelligence API"
    assert app.STARTUP_MODE_AVAILABLE is False
    assert "startup" not in app.REGISTERED_WORKFLOWS
    assert public_case.PUBLIC_PAGE_SECTIONS >= {
        "new_case",
        "source_inventory",
        "workflow_status",
        "evidence_ledger",
        "metrics",
        "risk_matrix",
        "hitl_inbox",
        "report_preview",
        "approved_download",
    }
    assert public_case.create_public_case_state is not None


def test_streamlit_shell_uses_stretch_width_api() -> None:
    presentation_root = Path("src/due_diligence_agent/presentation/streamlit")
    offenders = [
        str(path)
        for path in presentation_root.rglob("*.py")
        if "use_container_width" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_streamlit_flow_helper_runs_fixture_case_through_container(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    from due_diligence_agent.bootstrap.container import build_container
    from due_diligence_agent.presentation.streamlit.pages.public_case import (
        create_public_case_state,
        current_case_rows,
    )

    settings = Settings(data_dir=tmp_path, langsmith_tracing=False)
    container = build_container(settings, use_fixture_adapters=True)
    state = create_public_case_state(
        container,
        ticker="AAPL",
        as_of="2026-06-30",
        fixture="public_us_frozen_v1",
    )

    assert state["status"] == "awaiting_scope_approval"
    assert current_case_rows(container)
    container.close()


def test_streamlit_fixture_default_as_of_is_derived_from_manifest() -> None:
    from due_diligence_agent.presentation.streamlit.pages.public_case import (
        public_us_frozen_fixture_as_of,
    )

    manifest = json.loads(
        Path("tests/fixtures/public_us_frozen_v1/manifest.json").read_text(encoding="utf-8")
    )

    assert public_us_frozen_fixture_as_of().isoformat() == manifest["as_of"]


def test_streamlit_rejects_live_mode_when_fixture_container_is_active(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    from due_diligence_agent.bootstrap.container import build_container
    from due_diligence_agent.presentation.streamlit.pages.public_case import (
        create_public_case_state,
    )

    settings = Settings(data_dir=tmp_path, langsmith_tracing=False)
    container = build_container(settings, use_fixture_adapters=True)
    try:
        create_public_case_state(container, ticker="AAPL", as_of="2026-06-30", fixture=None)
    except ValueError as exc:
        assert "live_mode_unavailable" in str(exc)
    else:
        raise AssertionError("fixture container accepted unchecked live mode")
    finally:
        container.close()


def test_cli_help_registers_public_and_eval_commands_without_api_key(monkeypatch) -> None:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    env["LANGSMITH_TRACING"] = "false"
    env["LANGCHAIN_TRACING_V2"] = "false"
    env["UV_OFFLINE"] = "true"

    result = subprocess.run(
        [sys.executable, "-m", "due_diligence_agent.presentation.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )

    assert result.returncode == 0
    assert "run-public" in result.stdout
    assert "run-eval" in result.stdout


def test_run_eval_executes_gate_b_for_frozen_public_fixture(monkeypatch) -> None:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    env["LANGSMITH_TRACING"] = "false"
    env["LANGCHAIN_TRACING_V2"] = "false"
    env["UV_OFFLINE"] = "true"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "due_diligence_agent.presentation.cli",
            "run-eval",
            "--dataset",
            "public_us_frozen_v1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["dataset"] == "public_us_frozen_v1"
    assert payload["gate_b_passed"] is True
    assert payload["offline_no_key"]["openai_api_key_blank"] is True


def test_run_public_fixture_returns_structured_scope_checkpoint(
    tmp_path: Path, monkeypatch
) -> None:
    env = os.environ.copy()
    env["DDA_DATA_DIR"] = str(tmp_path)
    env["OPENAI_API_KEY"] = ""
    env["LANGSMITH_TRACING"] = "false"
    env["LANGCHAIN_TRACING_V2"] = "false"
    env["UV_OFFLINE"] = "true"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "due_diligence_agent.presentation.cli",
            "run-public",
            "--ticker",
            "AAPL",
            "--as-of",
            "2026-06-30",
            "--fixture",
            "public_us_frozen_v1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ticker"] == "AAPL"
    assert payload["fixture"] == "public_us_frozen_v1"
    assert payload["offline"] is True
    assert payload["state"]["status"] == "awaiting_scope_approval"
    assert "case_id" in payload["state"]


def test_run_public_rejects_malformed_as_of_before_container_build(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    import due_diligence_agent.presentation.cli as cli

    def fail_build_container(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("container should not be built for malformed --as-of")

    monkeypatch.setattr(cli, "build_container", fail_build_container)
    result = cli.main(
        [
            "run-public",
            "--ticker",
            "AAPL",
            "--as-of",
            "not-a-date",
            "--fixture",
            "public_us_frozen_v1",
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "invalid --as-of" in captured.err


def test_run_public_closes_container_when_case_creation_fails(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    import due_diligence_agent.presentation.cli as cli

    class FailingCaseService:
        def create_public_case(self, **_kwargs: Any) -> None:
            raise RuntimeError("case creation failed")

    class FakeContainer:
        def __init__(self) -> None:
            self.case_service = FailingCaseService()
            self.closed = False

        def close(self) -> None:
            self.closed = True

    container = FakeContainer()
    monkeypatch.setattr(cli, "build_container", lambda *_args, **_kwargs: container)

    try:
        cli.main(
            [
                "run-public",
                "--ticker",
                "AAPL",
                "--as-of",
                "2026-06-30",
                "--fixture",
                "public_us_frozen_v1",
            ]
        )
    except RuntimeError as exc:
        assert "case creation failed" in str(exc)
    else:
        raise AssertionError("case creation failure was swallowed")

    assert container.closed is True


def test_build_container_closes_database_when_graph_build_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    import due_diligence_agent.bootstrap.container as container_module
    from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase

    closed_paths: list[Path] = []
    original_close = SQLiteDatabase.close

    def tracking_close(self: SQLiteDatabase) -> None:
        closed_paths.append(self.path)
        original_close(self)

    monkeypatch.setattr(SQLiteDatabase, "close", tracking_close)
    monkeypatch.setattr(
        container_module,
        "build_public_graph",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("graph failed")),
    )

    try:
        container_module.build_container(
            Settings(data_dir=tmp_path, langsmith_tracing=False),
            use_fixture_adapters=True,
        )
    except RuntimeError as exc:
        assert "graph failed" in str(exc)
    else:
        raise AssertionError("graph build failure was swallowed")

    assert tmp_path / "metadata.sqlite3" in closed_paths


def test_live_container_uses_real_sleepers_and_data_dir_relative_embedding_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    from due_diligence_agent.bootstrap.container import build_container

    settings = Settings(
        data_dir=tmp_path,
        langsmith_tracing=False,
        sec_user_agent="Task14 smoke test contact@example.com",
        embedding_model_dir=Path("models/e5"),
    )
    container = build_container(settings, use_fixture_adapters=False)

    assert container.public_graph_dependencies.async_sleeper.__module__ == "asyncio.tasks"
    assert container.public_graph_dependencies.sync_sleeper.__module__ == "time"
    assert (
        container.retrieval_service._index.embedding.model_dir
        == (tmp_path / "models" / "e5").resolve()
    )
    container.close()


def test_live_container_resolves_default_and_absolute_embedding_model_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("UV_OFFLINE", "true")

    from due_diligence_agent.bootstrap.container import build_container

    default_settings = Settings(
        data_dir=tmp_path / "default",
        langsmith_tracing=False,
        sec_user_agent="Task14 smoke test contact@example.com",
    )
    default_container = build_container(default_settings, use_fixture_adapters=False)
    assert (
        default_container.retrieval_service._index.embedding.model_dir
        == (tmp_path / "default" / "models" / "intfloat-multilingual-e5-base").resolve()
    )
    default_container.close()

    absolute_model_dir = (tmp_path / "absolute-model").resolve()
    absolute_settings = Settings(
        data_dir=tmp_path / "absolute",
        langsmith_tracing=False,
        sec_user_agent="Task14 smoke test contact@example.com",
        embedding_model_dir=absolute_model_dir,
    )
    absolute_container = build_container(absolute_settings, use_fixture_adapters=False)
    assert absolute_container.retrieval_service._index.embedding.model_dir == absolute_model_dir
    absolute_container.close()


def asyncio_run(awaitable: Any) -> Any:
    import asyncio

    return asyncio.run(awaitable)

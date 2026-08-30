from __future__ import annotations

import importlib as importlib_module
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, cast

import pytest
from pydantic import SecretStr


def test_langsmith_smoke_missing_key_runs_real_workflow_without_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import due_diligence_agent.evals.langsmith_live_smoke as smoke

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setitem(smoke._LangSmithSmokeSettings.model_config, "env_file", None)
    factory = ExplodingFactory()

    evidence = smoke.run_queue5_langsmith_live_smoke(
        tmp_path / "missing-key",
        execute_live=True,
        client_factory=factory,
    )

    assert evidence.schema_version == "langsmith_trace_evidence@1"
    assert evidence.status == "blocked_missing_credential"
    assert evidence.credential_present is False
    assert evidence.execute_live_requested is True
    assert evidence.live_call_attempted is False
    assert evidence.live_call_succeeded is False
    assert evidence.client_constructed is False
    assert evidence.workflow.case_id == "00000000-0000-0000-0000-000000000951"
    assert evidence.workflow.report_lineage["source"] == "workflow_completed_state"
    assert evidence.workflow.report_lineage["report_id"]
    assert evidence.workflow.admin_langsmith_health["status"] == "blocked_missing_credential"
    assert {"initialize", "ingest", "report"} <= set(evidence.workflow.node_names)
    assert evidence.privacy["inputs_sanitized"] is True
    assert evidence.privacy["outputs_sanitized"] is True
    assert evidence.privacy["attachments_absent"] is True
    assert evidence.privacy["filesystem_disabled"] is True
    assert evidence.privacy["unsafe_capture_rejected"] is True
    assert factory.created == 0
    persisted = json.loads(
        (tmp_path / "missing-key" / "langsmith-trace-evidence.json").read_text(encoding="utf-8")
    )
    assert persisted["semantic_hash"] == evidence.semantic_hash
    assert "artifact_hashes" not in persisted
    assert not Path(persisted["artifact_paths"]["evidence"]).is_absolute()


def test_langsmith_smoke_key_without_execute_is_armed_but_no_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        run_queue5_langsmith_live_smoke,
    )

    monkeypatch.setenv("LANGSMITH_API_KEY", "present-but-never-printed")
    factory = ExplodingFactory()

    evidence = run_queue5_langsmith_live_smoke(
        tmp_path / "armed",
        execute_live=False,
        client_factory=factory,
    )

    assert evidence.status == "armed_not_executed"
    assert evidence.credential_present is True
    assert evidence.execute_live_requested is False
    assert evidence.live_call_attempted is False
    assert evidence.client_constructed is False
    assert evidence.workflow.admin_langsmith_health["status"] == "disabled"
    assert "present-but-never-printed" not in json.dumps(
        evidence.to_json_dict(),
        sort_keys=True,
    )
    assert factory.created == 0


def test_langsmith_smoke_no_key_without_execute_reports_blocked_health(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import due_diligence_agent.evals.langsmith_live_smoke as smoke

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setitem(smoke._LangSmithSmokeSettings.model_config, "env_file", None)
    factory = ExplodingFactory()

    evidence = smoke.run_queue5_langsmith_live_smoke(
        tmp_path / "no-key-validation",
        execute_live=False,
        client_factory=factory,
    )

    assert evidence.status == "blocked_missing_credential"
    assert evidence.execute_live_requested is False
    assert evidence.live_call_attempted is False
    assert evidence.client_constructed is False
    assert evidence.workflow.admin_langsmith_health["status"] == "blocked_missing_credential"
    assert factory.created == 0


def test_langsmith_smoke_fake_live_records_safe_node_inventory_and_stable_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        run_queue5_langsmith_live_smoke,
    )

    monkeypatch.setenv("LANGSMITH_API_KEY", "present-for-fake-client-only")
    client_a = RecordingLangSmithClient()
    client_b = RecordingLangSmithClient()

    first = run_queue5_langsmith_live_smoke(
        tmp_path / "healthy-a",
        execute_live=True,
        client_factory=lambda **_: client_a,
    )
    second = run_queue5_langsmith_live_smoke(
        tmp_path / "healthy-b",
        execute_live=True,
        client_factory=lambda **_: client_b,
    )

    assert first.status == "pass"
    assert first.live_call_attempted is True
    assert first.live_call_succeeded is True
    assert first.client_constructed is True
    assert first.semantic_hash == second.semantic_hash
    assert first.workflow.admin_langsmith_health["status"] == "healthy"
    assert first.workflow.node_names == tuple(sorted(first.workflow.node_names))
    run_names = cast(list[str], first.langsmith_trace["run_names"])
    run_count = cast(int, first.langsmith_trace["run_count"])
    metadata_keys = cast(list[str], first.langsmith_trace["metadata_keys"])
    assert "startup.workflow" in run_names
    assert "startup.report" in run_names
    assert run_count >= 14
    assert {
        "agent_role",
        "case_id",
        "gate",
        "node_name",
        "report_checksum",
        "report_id",
        "run_id",
        "total_tokens",
    } <= set(metadata_keys)
    assert first.privacy == {
        "inputs_sanitized": True,
        "outputs_sanitized": True,
        "attachments_absent": True,
        "filesystem_disabled": True,
        "unsafe_capture_rejected": True,
        "privacy_leak_count": 0,
    }
    serialized = json.dumps(first.to_json_dict(), sort_keys=True)
    assert "pitch.pdf" not in serialized
    assert str(tmp_path) not in serialized
    assert "present-for-fake-client-only" not in serialized
    assert "%PDF" not in serialized
    assert "prompt" not in serialized.lower()


def test_langsmith_smoke_fake_live_persists_sanitized_run_metrics_gate4_and_financial_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        run_queue5_langsmith_live_smoke,
    )

    monkeypatch.setenv("LANGSMITH_API_KEY", "present-for-safe-metadata")
    client = RecordingLangSmithClient()

    evidence = run_queue5_langsmith_live_smoke(
        tmp_path / "safe-metadata",
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "pass"
    persisted = json.loads(
        (tmp_path / "safe-metadata" / "langsmith-trace-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert "gate4" in persisted["workflow"]["node_names"]
    assert persisted["workflow"]["report_lineage"]["gate4_status"] == "completed"
    assert persisted["workflow"]["report_lineage"]["gate4_decision"] == "approved"

    created = persisted["langsmith_trace"]["created"]
    assert all(call["inputs"]["schema_version"] == "startup_langsmith_input@1" for call in created)
    assert all(call.get("outputs") in (None, {}) for call in created)
    assert all("prompt" not in json.dumps(call["inputs"], sort_keys=True).lower() for call in created)
    metadata_by_name = {call["name"]: call["metadata"] for call in created}
    root_input = next(call["inputs"] for call in created if call["name"] == "startup.workflow")
    report_input = next(call["inputs"] for call in created if call["name"] == "startup.report")
    assert root_input == {
        "case_id": persisted["workflow"]["case_id"],
        "run_id": persisted["workflow"]["run_id"],
        "workflow_type": "startup",
        "schema_version": "startup_langsmith_input@1",
    }
    assert report_input["case_id"] == persisted["workflow"]["case_id"]
    assert report_input["run_id"] == persisted["workflow"]["run_id"]
    assert report_input["node_name"] == "report"
    assert report_input["agent_role"]
    report_metadata = metadata_by_name["startup.report"]
    gate4_metadata = metadata_by_name["startup.gate4"]
    financial_metadata = metadata_by_name["startup.financial_analysis"]

    for metadata in (report_metadata, gate4_metadata, financial_metadata):
        assert isinstance(metadata["duration_ms"], int | float)
        assert metadata["duration_ms"] >= 0
        assert isinstance(metadata["retry_count"], int)
        assert metadata["retry_count"] >= 0
        assert isinstance(metadata["input_tokens"], int)
        assert isinstance(metadata["output_tokens"], int)
        assert isinstance(metadata["total_tokens"], int)
        assert metadata["total_tokens"] == metadata["input_tokens"] + metadata["output_tokens"]
        assert isinstance(metadata["estimated_cost_usd"], int | float)
        assert metadata["estimated_cost_usd"] >= 0

    assert gate4_metadata["gate"] == "gate4"
    assert gate4_metadata["gate_status"] == "approved"
    assert gate4_metadata["report_id"] == persisted["workflow"]["report_lineage"]["report_id"]
    assert financial_metadata["agent_role"] == "financial"
    assert "finance" not in json.dumps(created, sort_keys=True)


def test_langsmith_smoke_custom_run_id_is_used_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        run_queue5_langsmith_live_smoke,
    )

    monkeypatch.setenv("LANGSMITH_API_KEY", "present-for-custom-run")
    client = RecordingLangSmithClient()

    evidence = run_queue5_langsmith_live_smoke(
        tmp_path / "custom-run",
        execute_live=True,
        client_factory=lambda **_: client,
        run_id="queue5-langsmith-run-custom-001",
    )

    assert evidence.status == "pass"
    assert evidence.workflow.run_id == "queue5-langsmith-run-custom-001"
    root = next(call for call in client.created if call["name"] == "startup.workflow")
    assert root["extra"]["metadata"]["run_id"] == "queue5-langsmith-run-custom-001"


def test_langsmith_semantic_hash_normalizes_reordered_node_names() -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import _semantic_hash

    base = {
        "schema_version": "langsmith_trace_evidence@1",
        "status": "pass",
        "credential_present": True,
        "execute_live_requested": True,
        "live_call_attempted": True,
        "live_call_succeeded": True,
        "client_constructed": True,
        "workflow": {
            "case_id": "case-1",
            "run_id": "run-1",
            "node_count": 3,
            "node_names": ["report", "initialize", "ingest"],
            "admin_langsmith_health": {
                "provider": "langsmith",
                "status": "healthy",
                "error_code": "none",
                "fallback_used": "local_audit",
            },
            "report_lineage": {
                "source": "workflow_completed_state",
                "report_id": "report-a",
                "report_revision": "1",
                "report_checksum": "a" * 64,
            },
        },
        "langsmith_trace": {
            "run_count": 3,
            "run_names": ["startup.ingest", "startup.report"],
            "metadata_keys": ["case_id", "node_name"],
            "created": [],
            "updated": [],
            "flush_count": 1,
            "export_errors": 0,
        },
        "privacy": {
            "inputs_sanitized": True,
            "outputs_sanitized": True,
            "attachments_absent": True,
            "filesystem_disabled": True,
            "unsafe_capture_rejected": True,
            "privacy_leak_count": 0,
        },
        "semantic_hash": "",
        "artifact_paths": {"evidence": "langsmith-trace-evidence.json"},
        "fail_reasons": [],
    }
    reordered = json.loads(json.dumps(base))
    reordered["workflow"]["node_names"] = ["ingest", "report", "initialize"]

    assert _semantic_hash(base) == _semantic_hash(reordered)


def test_langsmith_smoke_outage_degrades_without_breaking_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        run_queue5_langsmith_live_smoke,
    )

    monkeypatch.setenv("LANGSMITH_API_KEY", "present-for-failing-client")
    client = FailingLangSmithClient()

    evidence = run_queue5_langsmith_live_smoke(
        tmp_path / "outage",
        execute_live=True,
        client_factory=lambda **_: client,
    )

    assert evidence.status == "degraded"
    assert evidence.live_call_attempted is True
    assert evidence.live_call_succeeded is False
    assert evidence.workflow.report_lineage["report_id"]
    assert evidence.workflow.admin_langsmith_health == {
        "provider": "langsmith",
        "status": "degraded",
        "error_code": "external_export_failed",
        "fallback_used": "local_audit",
    }
    assert client.create_calls == 1
    assert "private exporter failure" not in json.dumps(evidence.to_json_dict())


def test_langsmith_smoke_outage_records_only_safe_error_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        run_queue5_langsmith_live_smoke,
    )

    monkeypatch.setenv("LANGSMITH_API_KEY", "present-for-http-failure")

    evidence = run_queue5_langsmith_live_smoke(
        tmp_path / "categorized-outage",
        execute_live=True,
        client_factory=lambda **_: CategorizedFailingLangSmithClient(),
    )

    assert evidence.status == "degraded"
    assert evidence.langsmith_trace["export_error_categories"] == [
        {
            "category": "authentication",
            "exception_types": ["FakeLangSmithError", "FakeHttpError"],
            "http_status": 401,
            "stage": "create_run",
        }
    ]
    serialized = json.dumps(evidence.to_json_dict(), sort_keys=True)
    assert "private exporter failure" not in serialized
    assert "C:\\secret" not in serialized


def test_default_langsmith_factory_disables_sdk_payload_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import due_diligence_agent.evals.langsmith_live_smoke as smoke

    captured: dict[str, object] = {}

    class FakeLangSmithModule:
        @staticmethod
        def Client(**kwargs: object) -> object:
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(importlib_module, "import_module", lambda _: FakeLangSmithModule)

    smoke._default_langsmith_client_factory(SecretStr("present-for-test"))()

    assert captured == {
        "api_key": "present-for-test",
        "auto_batch_tracing": False,
        "hide_inputs": True,
        "hide_outputs": True,
        "omit_traced_runtime_info": True,
        "timeout_ms": (5_000, 5_000),
    }


def test_langsmith_smoke_rejects_output_collision_before_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        run_queue5_langsmith_live_smoke,
    )

    output_dir = tmp_path / "occupied"
    output_dir.mkdir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    monkeypatch.setenv("LANGSMITH_API_KEY", "present")
    factory = ExplodingFactory()

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_empty$"):
        run_queue5_langsmith_live_smoke(
            output_dir,
            execute_live=True,
            client_factory=factory,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert factory.created == 0


def test_langsmith_smoke_rejects_unsafe_captured_payload() -> None:
    from due_diligence_agent.evals.langsmith_live_smoke import (
        validate_langsmith_capture_privacy,
    )

    unsafe_capture = {
        "created": [
            {
                "name": "startup.report",
                "inputs": {"raw": "%PDF"},
                "extra": {
                    "metadata": {
                        "case_id": "case-1",
                        "private_name": "pitch.pdf",
                        "local_path": "C:\\secret\\pitch.pdf",
                        "prompt": "summarize this",
                    }
                },
                "dangerously_allow_filesystem": True,
            }
        ],
        "updated": [{"outputs": {"answer": "secret@example.com"}}],
    }

    with pytest.raises(ValueError, match="^langsmith_capture_privacy_rejected$"):
        validate_langsmith_capture_privacy(unsafe_capture)


def test_langsmith_smoke_script_forwards_safe_default_and_live_switch(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the LangSmith smoke contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_queue5_langsmith_smoke.ps1"
    capture_path = tmp_path / "capture.json"
    fake_uv = tmp_path / "fake-uv.ps1"
    fake_uv.write_text(
        "\n".join(
            [
                "$payload = @{ args = $args; env = @{",
                "  LANGSMITH_TRACING = $env:LANGSMITH_TRACING",
                "  LANGCHAIN_TRACING = $env:LANGCHAIN_TRACING",
                "  LANGCHAIN_TRACING_V2 = $env:LANGCHAIN_TRACING_V2",
                "  DDA_LANGSMITH_TRACING = $env:DDA_LANGSMITH_TRACING",
                "  OPENAI_API_KEY = if ($null -eq $env:OPENAI_API_KEY) { '' } else { $env:OPENAI_API_KEY }",
                "  UV_OFFLINE = $env:UV_OFFLINE",
                "} }",
                f"$payload | ConvertTo-Json -Depth 4 | Set-Content -Path '{capture_path}' -Encoding UTF8",
                "exit 43",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "langsmith-output"
    process_env = os.environ.copy()
    process_env["LANGSMITH_API_KEY"] = "must-not-be-printed"
    process_env["OPENAI_API_KEY"] = "caller-openai-key"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutputDir",
            str(output_dir),
            "-ExecuteLive",
            "-RunId",
            "queue5-langsmith-cli-test",
            "-UvExecutable",
            str(fake_uv),
        ],
        cwd=repo_root,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 43, result.stderr
    assert "must-not-be-printed" not in result.stdout
    assert "must-not-be-printed" not in result.stderr
    captured = json.loads(capture_path.read_text(encoding="utf-8-sig"))
    assert captured["args"][-8:] == [
        "python",
        "-m",
        "due_diligence_agent.evals.langsmith_live_smoke",
        "--output-dir",
        str(output_dir),
        "--run-id",
        "queue5-langsmith-cli-test",
        "--execute-live",
    ]
    assert captured["env"] == {
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "DDA_LANGSMITH_TRACING": "false",
        "OPENAI_API_KEY": "",
        "UV_OFFLINE": "true",
    }


class ExplodingFactory:
    def __init__(self) -> None:
        self.created = 0

    def __call__(self, **_: object) -> object:
        self.created += 1
        raise AssertionError("LangSmith client must not be constructed")


class RecordingLangSmithClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.flush_calls = 0

    def create_run(
        self,
        name: str,
        inputs: dict[str, object],
        run_type: str,
        **kwargs: Any,
    ) -> None:
        self.created.append({"name": name, "inputs": inputs, "run_type": run_type, **kwargs})

    def update_run(self, run_id: object, **kwargs: Any) -> None:
        self.updated.append({"run_id": run_id, **kwargs})

    def flush(self, timeout: float | None = None) -> None:
        del timeout
        self.flush_calls += 1


class FailingLangSmithClient:
    def __init__(self) -> None:
        self.create_calls = 0

    def create_run(
        self,
        name: str,
        inputs: dict[str, object],
        run_type: str,
        **kwargs: Any,
    ) -> None:
        del name, inputs, run_type, kwargs
        self.create_calls += 1
        raise RuntimeError("private exporter failure C:\\secret\\pitch.pdf")


class CategorizedFailingLangSmithClient:
    def create_run(
        self,
        name: str,
        inputs: dict[str, object],
        run_type: str,
        **kwargs: Any,
    ) -> None:
        del name, inputs, run_type, kwargs
        try:
            raise FakeHttpError("private HTTP failure C:\\secret\\pitch.pdf")
        except FakeHttpError:
            raise FakeLangSmithError(
                "private exporter failure C:\\secret\\pitch.pdf"
            )

    def flush(self, timeout: float | None = None) -> None:
        del timeout


class FakeLangSmithError(RuntimeError):
    pass


class FakeHttpError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.response = FakeResponse()


class FakeResponse:
    status_code = 401

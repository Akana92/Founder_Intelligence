from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import TextIO, cast

import pytest


COMMIT_ID = "64c3a70bb528f2f71b1930ad7d7a2ab57a4d62b6"


def test_queue5_failure_matrix_is_stable_complete_and_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.failure_matrix import (
        calculate_queue5_failure_matrix_hash,
        run_queue5_failure_matrix,
        validate_queue5_failure_matrix_payload,
    )

    calls: list[list[str]] = []

    def passing_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        duration = "1.11s" if len(calls) == 1 else "9.99s"
        cast(TextIO, kwargs["stdout"]).write(f"12 passed in {duration}\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", passing_run)

    first = run_queue5_failure_matrix(tmp_path / "matrix-a", commit_id=COMMIT_ID)
    second = run_queue5_failure_matrix(tmp_path / "matrix-b", commit_id=COMMIT_ID)

    assert first.matrix_passed is True
    assert first.matrix_hash == second.matrix_hash
    assert first.artifact_hashes != second.artifact_hashes
    assert first.live_provider_smoke_status == "deferred_by_policy"
    assert {row["category"] for row in first.rows} == {
        "provider_unavailable",
        "external_source_outage",
        "retry",
        "provider_outage_replanning",
        "budget_exhaustion",
        "renderer_fallback",
    }
    rows_by_id = {str(row["id"]): row for row in first.rows}
    assert set(rows_by_id) == {
        "provider_unavailable_no_key",
        "external_source_outage_partial",
        "typed_retry_bounded",
        "provider_outage_graph_replan",
        "budget_exhaustion_local_fallback_restart",
        "report_renderer_fallback",
    }
    assert rows_by_id["provider_outage_graph_replan"]["proof_tests"] == [
        "tests/graph/test_startup_workflow.py::test_provider_outage_replans_with_local_market_fallback_and_reaches_gate4_report_path"
    ]
    assert rows_by_id["budget_exhaustion_local_fallback_restart"]["proof_tests"] == [
        "tests/graph/test_startup_workflow.py::test_budget_exhaustion_replans_to_local_evidence_before_over_budget_provider_call",
        "tests/graph/test_startup_workflow.py::test_budget_exhaustion_restart_resumes_gate4_after_fallback_without_extra_calls",
    ]
    assert {row["id"] for row in first.supporting_validations} == {
        "checkpoint_restart",
        "checkpoint_privacy",
        "report_trace_lineage",
        "exporter_fallback_privacy",
    }
    assert all(row["status"] == "pass" for row in first.rows)
    assert all(row["live_calls_made"] == 0 for row in first.rows)
    assert len(calls) == 2
    assert "-p" in calls[0]
    assert "no:cacheprovider" in calls[0]
    persisted = json.loads(
        (tmp_path / "matrix-a" / "failure-matrix.json").read_text(encoding="utf-8")
    )
    assert persisted["schema_version"] == "queue5_failure_matrix@1"
    assert persisted["matrix_hash"] == first.matrix_hash
    assert persisted["matrix_hash"] == calculate_queue5_failure_matrix_hash(persisted)
    assert validate_queue5_failure_matrix_payload(persisted) == (True, ())
    assert all(not Path(path).is_absolute() for path in persisted["artifact_paths"].values())


def test_queue5_failure_matrix_records_failed_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.failure_matrix import run_queue5_failure_matrix

    def failing_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cast(TextIO, kwargs["stderr"]).write("1 failed\n")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(subprocess, "run", failing_run)

    result = run_queue5_failure_matrix(tmp_path / "matrix", commit_id=COMMIT_ID)

    assert result.matrix_passed is False
    assert result.fail_reasons == ("failure_matrix_pytest_failed",)
    assert all(row["status"] == "fail" for row in result.rows)


def test_queue5_failure_matrix_records_timed_out_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.failure_matrix import run_queue5_failure_matrix

    def timing_out_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 300
        cast(TextIO, kwargs["stdout"]).write("collected 12 items\n")
        cast(TextIO, kwargs["stderr"]).write("still running after budget\n")
        raise subprocess.TimeoutExpired(command, timeout=300, output="safe out", stderr="safe err")

    monkeypatch.setattr(subprocess, "run", timing_out_run)

    result = run_queue5_failure_matrix(tmp_path / "matrix", commit_id=COMMIT_ID)

    assert result.matrix_passed is False
    assert result.fail_reasons == ("failure_matrix_pytest_timeout",)
    assert result.command_evidence["exit_code"] == "timeout"
    assert result.command_evidence["timeout_seconds"] == 300
    assert result.command_evidence["timed_out"] is True
    assert all(row["status"] == "fail" for row in result.rows)
    assert all(row["fail_reasons"] == ["proof_command_timeout"] for row in result.rows)
    stderr_log = tmp_path / "matrix" / "failure-matrix.pytest.stderr.log"
    assert "failure_matrix_pytest_timeout" in stderr_log.read_text(encoding="utf-8")


def test_queue5_failure_matrix_rejects_existing_output_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.evals.failure_matrix import run_queue5_failure_matrix

    output_dir = tmp_path / "occupied"
    output_dir.mkdir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: calls.append("run"))

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_empty$"):
        run_queue5_failure_matrix(output_dir, commit_id=COMMIT_ID)

    assert calls == []
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_queue5_failure_matrix_script_forwards_offline_contract(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the failure matrix contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_queue5_failure_matrix.ps1"
    capture_path = tmp_path / "capture.json"
    fake_uv = tmp_path / "fake-uv.ps1"
    fake_uv.write_text(
        "\n".join(
            [
                "function BlankValue($value) { if ($null -eq $value) { '' } else { $value } }",
                "$payload = @{ args = $args; env = @{",
                "  OPENAI_API_KEY = BlankValue $env:OPENAI_API_KEY",
                "  OPENAI_STARTUP_API_KEY = BlankValue $env:OPENAI_STARTUP_API_KEY",
                "  LANGSMITH_TRACING = $env:LANGSMITH_TRACING",
                "  HF_HUB_OFFLINE = $env:HF_HUB_OFFLINE",
                "  TRANSFORMERS_OFFLINE = $env:TRANSFORMERS_OFFLINE",
                "  UV_OFFLINE = $env:UV_OFFLINE",
                "} }",
                f"$payload | ConvertTo-Json -Depth 4 | Set-Content -Path '{capture_path}' -Encoding UTF8",
                "exit 44",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "matrix-output"
    process_env = os.environ.copy()
    process_env["OPENAI_API_KEY"] = "caller-key"
    process_env["OPENAI_STARTUP_API_KEY"] = "caller-startup-key"

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
            "-CommitId",
            COMMIT_ID,
            "-UvExecutable",
            str(fake_uv),
        ],
        cwd=repo_root,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 44, result.stderr
    captured = json.loads(capture_path.read_text(encoding="utf-8-sig"))
    assert captured["args"][-7:] == [
        "python",
        "-m",
        "due_diligence_agent.evals.failure_matrix",
        "--output-dir",
        str(output_dir),
        "--commit-id",
        COMMIT_ID,
    ]
    assert captured["env"] == {
        "OPENAI_API_KEY": "",
        "OPENAI_STARTUP_API_KEY": "",
        "LANGSMITH_TRACING": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "UV_OFFLINE": "true",
    }

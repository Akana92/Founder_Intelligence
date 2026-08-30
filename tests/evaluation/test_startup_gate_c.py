from __future__ import annotations

import json
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4

import pytest
from pytest import CaptureFixture

from due_diligence_agent.evals.metrics import EvaluationResult


def test_stage1b_gate_c_script_forwards_offline_contract_and_child_exit() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the stage1b Gate C wrapper contract")

    repo_root = Path(__file__).resolve().parents[2]
    contract_dir = repo_root / ".tmp-q0-task2-script-contract" / uuid4().hex
    contract_dir.mkdir(parents=True, exist_ok=False)
    capture_path = contract_dir / "uv-contract.json"
    fake_uv = contract_dir / "fake-uv.ps1"
    fake_uv.write_text(
        "\n".join(
            [
                "function BlankValue($value) { if ($null -eq $value) { '' } else { $value } }",
                "$payload = @{",
                "  args = $args",
                "  env = @{",
                "    OPENAI_API_KEY = BlankValue $env:OPENAI_API_KEY",
                "    OPENAI_STARTUP_API_KEY = BlankValue $env:OPENAI_STARTUP_API_KEY",
                "    LANGSMITH_TRACING = $env:LANGSMITH_TRACING",
                "    LANGCHAIN_TRACING = $env:LANGCHAIN_TRACING",
                "    LANGCHAIN_TRACING_V2 = $env:LANGCHAIN_TRACING_V2",
                "    DDA_LANGSMITH_TRACING = $env:DDA_LANGSMITH_TRACING",
                "    HF_HUB_OFFLINE = $env:HF_HUB_OFFLINE",
                "    TRANSFORMERS_OFFLINE = $env:TRANSFORMERS_OFFLINE",
                "    UV_OFFLINE = $env:UV_OFFLINE",
                "  }",
                "}",
                f"$payload | ConvertTo-Json -Depth 4 | Set-Content -Path '{capture_path}' -Encoding UTF8",
                "exit 37",
                "",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = Path(".tmp-q0-task2-script-output") / uuid4().hex
    process_env = os.environ.copy()
    process_env["OPENAI_API_KEY"] = "caller-openai-key"
    process_env["OPENAI_STARTUP_API_KEY"] = "caller-startup-key"
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo_root / "scripts" / "run_stage1b_gate_c.ps1"),
            "-OutputDir",
            str(output_dir),
            "-UvExecutable",
            str(fake_uv),
        ],
        cwd=repo_root,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 37
    assert result.stdout == ""
    assert capture_path.exists(), result.stderr
    payload = json.loads(capture_path.read_text(encoding="utf-8-sig"))
    assert payload["args"] == [
        "run",
        "--offline",
        "--no-sync",
        "--no-default-groups",
        "--group",
        "stage1b",
        "--group",
        "founder-api",
        "--group",
        "dev",
        "investment-dd",
        "run-gate-c",
        "--dataset",
        "startup_secure_ingest_v1",
        "--output-dir",
        str(repo_root / output_dir),
    ]
    assert payload["env"] == {
        "OPENAI_API_KEY": "",
        "OPENAI_STARTUP_API_KEY": "",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "DDA_LANGSMITH_TRACING": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "UV_OFFLINE": "true",
    }


def test_gate_c_runs_fixed_startup_checks_and_gate_b_once(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    commands: list[list[str]] = []
    gate_b_datasets: list[str] = []

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="1 passed\n", stderr="")

    def fake_gate_b(dataset: str, **_kwargs: Any) -> EvaluationResult:
        gate_b_datasets.append(dataset)
        return _gate_b_result(gate_b_passed=True)

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=fake_gate_b,
    )

    assert result.gate_c_passed is True
    assert result.dataset == "startup_secure_ingest_v1"
    assert gate_b_datasets == ["public_us_frozen_v1"]
    assert [command[-1] for command in commands] == [
        "tests/security/test_archive_safety.py",
        "tests/parsing/test_document_parsers.py",
        "tests/parsing/test_spreadsheets.py",
        "tests/privacy/test_ai_egress.py",
        "tests/privacy/test_startup_redaction.py",
        "tests/graph/test_startup_disclosure_gate.py",
        "tests/evaluation/test_queue1_startup_profile.py",
    ]
    assert all("--basetemp" in command for command in commands)
    assert result.privacy_leak_count == 0
    assert result.denied_gate2_external_calls == 0
    assert result.offline_no_key["openai_api_key_blank"] is True
    assert result.offline_no_key["openai_startup_api_key_blank"] is True


def test_gate_c_records_queue1_profile_evidence(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="passed", stderr=""
        ),
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert result.profile_determinism is True
    assert result.required_profile_field_status_coverage == 1.0
    assert result.contradiction_retention is True
    assert result.parse_format_coverage == (
        "csv",
        "docx",
        "jpeg",
        "pdf",
        "png",
        "safe_zip",
        "xlsx",
    )
    assert result.restart_equivalence is True
    assert result.canonical_profile_hash is not None
    assert result.canonical_profile_hash.startswith("sha256:")


def test_gate_c_blanks_openai_keys_for_commands_gate_b_and_result(
    gate_c_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    caller_values = {
        "OPENAI_API_KEY": "caller-openai-key",
        "OPENAI_STARTUP_API_KEY": "caller-startup-key",
    }
    for name, value in caller_values.items():
        monkeypatch.setenv(name, value)

    envs: list[dict[str, str]] = []
    gate_b_env: dict[str, str | None] = {}

    def fake_command_runner(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        envs.append(dict(kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    def fake_gate_b(_dataset: str, **_kwargs: Any) -> EvaluationResult:
        gate_b_env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY")
        gate_b_env["OPENAI_STARTUP_API_KEY"] = os.environ.get("OPENAI_STARTUP_API_KEY")
        return _gate_b_result(gate_b_passed=True)

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=fake_gate_b,
    )

    assert envs
    assert all(env["OPENAI_API_KEY"] == "" for env in envs)
    assert all(env["OPENAI_STARTUP_API_KEY"] == "" for env in envs)
    assert gate_b_env == {"OPENAI_API_KEY": "", "OPENAI_STARTUP_API_KEY": ""}
    assert result.offline_no_key["openai_api_key_blank"] is True
    assert result.offline_no_key["openai_startup_api_key_blank"] is True
    assert {name: os.environ[name] for name in caller_values} == caller_values


def test_gate_c_disables_legacy_langchain_tracing_for_commands_gate_b_and_result(
    gate_c_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    monkeypatch.setenv("LANGCHAIN_TRACING", "true")
    envs: list[dict[str, str]] = []
    gate_b_env: dict[str, str | None] = {}

    def fake_command_runner(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        envs.append(dict(kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    def fake_gate_b(_dataset: str, **_kwargs: Any) -> EvaluationResult:
        gate_b_env["LANGCHAIN_TRACING"] = os.environ.get("LANGCHAIN_TRACING")
        return _gate_b_result(gate_b_passed=True)

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=fake_gate_b,
    )

    assert envs
    assert all(env["LANGCHAIN_TRACING"] == "false" for env in envs)
    assert gate_b_env == {"LANGCHAIN_TRACING": "false"}
    assert result.offline_no_key["langchain_legacy_tracing_disabled"] is True
    assert os.environ["LANGCHAIN_TRACING"] == "true"


def test_gate_c_forces_model_hub_offline_environment(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    envs: list[dict[str, str]] = []

    def fake_command_runner(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        envs.append(dict(kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert envs
    assert all(env["HF_HUB_OFFLINE"] == "1" for env in envs)
    assert all(env["TRANSFORMERS_OFFLINE"] == "1" for env in envs)
    assert result.offline_no_key["hf_hub_offline"] is True
    assert result.offline_no_key["transformers_offline"] is True


def test_gate_c_uses_unique_pytest_subtree_for_each_run(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    basetemps: list[str] = []

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        basetemps.append(command[command.index("--basetemp") + 1])
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    for _ in range(2):
        run_gate_c_eval(
            "startup_secure_ingest_v1",
            output_dir=gate_c_output_dir,
            command_runner=fake_command_runner,
            public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
        )

    first_run = basetemps[:7]
    second_run = basetemps[7:]
    assert first_run
    assert second_run
    assert set(first_run).isdisjoint(second_run)
    assert all(f"{gate_c_output_dir}\\runs\\" in item for item in basetemps)


def test_gate_c_isolates_pytest_temp_environment_per_behavior_check(
    gate_c_output_dir: Path,
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    command_temp_roots: list[tuple[Path, Path, Path, Path, bool]] = []

    def fake_command_runner(
        command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        basetemp = Path(command[command.index("--basetemp") + 1])
        tmp_root = Path(env["TMP"])
        command_temp_roots.append(
            (basetemp, tmp_root, Path(env["TEMP"]), Path(env["TMPDIR"]), tmp_root.is_dir())
        )
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert len(command_temp_roots) == 7
    for basetemp, tmp_root, temp_root, tmpdir_root, existed_during_command in command_temp_roots:
        assert tmp_root == temp_root
        assert tmp_root == tmpdir_root
        assert tmp_root == basetemp.parent / f"{basetemp.name}-tmp"
        assert basetemp not in tmp_root.parents
        assert existed_during_command is True
        assert not tmp_root.exists()
        assert gate_c_output_dir.resolve() in tmp_root.parents
    assert len({tmp_root for _basetemp, tmp_root, _temp_root, _tmpdir_root, _exists in command_temp_roots}) == 7


def test_gate_c_writes_bounded_machine_readable_json(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="passed", stderr=""
        ),
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    payload = Path(result.artifact_paths["eval_result"]).read_text(encoding="utf-8")

    assert len(payload) < 100_000
    assert '"dataset": "startup_secure_ingest_v1"' in payload
    assert '"gate_c_passed": true' in payload
    assert '"commit_id":' in payload
    assert '"environment":' in payload
    assert '"offline_no_key":' in payload
    assert '"command_evidence":' in payload
    assert '"profile_determinism": true' in payload
    assert '"required_profile_field_status_coverage": 1.0' in payload
    assert '"contradiction_retention": true' in payload
    assert '"parse_format_coverage": [' in payload
    assert '"restart_equivalence": true' in payload
    assert '"canonical_profile_hash": "sha256:' in payload


def test_failed_startup_check_fails_gate_c_and_records_reason(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        returncode = 1 if command[-1] == "tests/privacy/test_ai_egress.py" else 0
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="failed")

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert result.gate_c_passed is False
    assert "privacy_egress" in result.fail_reasons
    assert result.privacy_leak_count is None
    assert result.denied_gate2_external_calls == 0
    assert result.command_evidence[3].check_name == "privacy_egress"
    assert result.command_evidence[3].returncode == 1


def test_failed_denied_gate2_proof_reports_external_calls_unknown(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        returncode = 1 if command[-1] == "tests/graph/test_startup_disclosure_gate.py" else 0
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="failed")

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert result.gate_c_passed is False
    assert "denied_gate2" in result.fail_reasons
    assert result.privacy_leak_count == 0
    assert result.denied_gate2_external_calls is None


def test_failed_queue1_profile_proof_reports_profile_evidence_unknown(
    gate_c_output_dir: Path,
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    def fake_command_runner(
        command: list[str], **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        returncode = 1 if command[-1] == "tests/evaluation/test_queue1_startup_profile.py" else 0
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="failed")

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert result.gate_c_passed is False
    assert "queue1_startup_profile" in result.fail_reasons
    assert result.profile_determinism is None
    assert result.required_profile_field_status_coverage is None
    assert result.contradiction_retention is None
    assert result.parse_format_coverage is None
    assert result.restart_equivalence is None
    assert result.canonical_profile_hash is None


def test_gate_b_failure_fails_gate_c_without_duplicate_public_eval(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    gate_b_calls = 0

    def fake_gate_b(dataset: str, **_kwargs: Any) -> EvaluationResult:
        nonlocal gate_b_calls
        gate_b_calls += 1
        assert dataset == "public_us_frozen_v1"
        return _gate_b_result(gate_b_passed=False, fail_reasons=("schema_validity",))

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="passed", stderr=""
        ),
        public_eval_runner=fake_gate_b,
    )

    assert gate_b_calls == 1
    assert result.gate_c_passed is False
    assert "gate_b_regression" in result.fail_reasons
    assert "gate_b:schema_validity" in result.fail_reasons


def test_command_timeout_fails_closed_and_continues_through_gate_b(
    gate_c_output_dir: Path,
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    commands: list[list[str]] = []
    gate_b_calls = 0

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[-1] == "tests/security/test_archive_safety.py":
            raise subprocess.TimeoutExpired(command, timeout=120, output="late", stderr="timed out")
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    def fake_gate_b(dataset: str, **_kwargs: Any) -> EvaluationResult:
        nonlocal gate_b_calls
        gate_b_calls += 1
        assert dataset == "public_us_frozen_v1"
        return _gate_b_result(gate_b_passed=True)

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=fake_gate_b,
    )

    payload = Path(result.artifact_paths["eval_result"]).read_text(encoding="utf-8")
    assert result.gate_c_passed is False
    assert "archive_safety:command_timeout" in result.fail_reasons
    assert len(commands) == 7
    assert gate_b_calls == 1
    assert len(result.command_evidence) == 7
    assert result.command_evidence[0].check_name == "archive_safety"
    assert result.command_evidence[0].returncode != 0
    assert result.parse_format_coverage is None
    assert '"archive_safety:command_timeout"' in payload


def test_command_os_error_fails_closed_and_continues_through_gate_b(
    gate_c_output_dir: Path,
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    commands: list[list[str]] = []
    gate_b_calls = 0

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[-1] == "tests/parsing/test_document_parsers.py":
            raise OSError("cannot spawn pytest")
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    def fake_gate_b(dataset: str, **_kwargs: Any) -> EvaluationResult:
        nonlocal gate_b_calls
        gate_b_calls += 1
        assert dataset == "public_us_frozen_v1"
        return _gate_b_result(gate_b_passed=True)

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=fake_gate_b,
    )

    payload = Path(result.artifact_paths["eval_result"]).read_text(encoding="utf-8")
    assert result.gate_c_passed is False
    assert "document_parsing:command_error" in result.fail_reasons
    assert len(commands) == 7
    assert gate_b_calls == 1
    assert len(result.command_evidence) == 7
    assert result.command_evidence[1].check_name == "document_parsing"
    assert result.command_evidence[1].returncode != 0
    assert result.parse_format_coverage is None
    assert '"document_parsing:command_error"' in payload


def test_gate_c_disables_pytest_cache_for_behavior_checks(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    commands: list[list[str]] = []

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert commands
    assert all(_has_adjacent_args(command, "-p", "no:cacheprovider") for command in commands)


def test_command_evidence_summarizes_nonempty_stdout_stderr_for_failing_commands(
    gate_c_output_dir: Path,
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    stdout = "Acme confidential revenue roadmap has no regex marker"
    stderr = "Board memo: expansion plan and founder negotiation context"

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        returncode = 1 if command[-1] == "tests/privacy/test_ai_egress.py" else 0
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout=stdout if returncode else "",
            stderr=stderr if returncode else "",
        )

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    persisted = Path(result.artifact_paths["eval_result"]).read_text(encoding="utf-8")
    in_memory = str(result.to_json_dict())
    failed_evidence = result.command_evidence[3]
    assert failed_evidence.stdout_tail == _stream_summary(stdout)
    assert failed_evidence.stderr_tail == _stream_summary(stderr)
    assert stdout not in persisted
    assert stderr not in persisted
    assert stdout not in in_memory
    assert stderr not in in_memory


def test_command_evidence_summarizes_nonempty_stdout_stderr_for_passing_commands(
    gate_c_output_dir: Path,
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    stdout = "Passed check printed confidential customer acquisition plan"
    stderr = "Passing stderr with confidential business text and no marker"

    def fake_command_runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=stderr)

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=fake_command_runner,
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    persisted = Path(result.artifact_paths["eval_result"]).read_text(encoding="utf-8")
    assert result.command_evidence[0].stdout_tail == _stream_summary(stdout)
    assert result.command_evidence[0].stderr_tail == _stream_summary(stderr)
    assert stdout not in persisted
    assert stderr not in persisted


def test_command_evidence_keeps_empty_stdout_stderr_empty(gate_c_output_dir: Path) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    result = run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="", stderr=""
        ),
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert result.command_evidence[0].stdout_tail == ""
    assert result.command_evidence[0].stderr_tail == ""


def test_gate_c_restores_caller_environment_after_success(
    gate_c_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    original_values = {
        "OPENAI_API_KEY": "caller-key",
        "OPENAI_STARTUP_API_KEY": "caller-startup-key",
        "LANGSMITH_TRACING": "true",
        "LANGCHAIN_TRACING_V2": "true",
        "DDA_LANGSMITH_TRACING": "true",
        "HF_HUB_OFFLINE": "0",
        "TRANSFORMERS_OFFLINE": "0",
    }
    for name, value in original_values.items():
        monkeypatch.setenv(name, value)

    run_gate_c_eval(
        "startup_secure_ingest_v1",
        output_dir=gate_c_output_dir,
        command_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="passed", stderr=""
        ),
        public_eval_runner=lambda _dataset, **_kwargs: _gate_b_result(gate_b_passed=True),
    )

    assert {name: os.environ[name] for name in original_values} == original_values


def test_gate_c_restores_caller_environment_after_exception(
    gate_c_output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    monkeypatch.setenv("OPENAI_API_KEY", "caller-key")
    monkeypatch.setenv("OPENAI_STARTUP_API_KEY", "caller-startup-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("DDA_LANGSMITH_TRACING", "true")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")

    def failing_gate_b(_dataset: str, **_kwargs: Any) -> EvaluationResult:
        raise RuntimeError("gate b crashed")

    with pytest.raises(RuntimeError, match="gate b crashed"):
        run_gate_c_eval(
            "startup_secure_ingest_v1",
            output_dir=gate_c_output_dir,
            command_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
                command, 0, stdout="passed", stderr=""
            ),
            public_eval_runner=failing_gate_b,
        )

    assert os.environ["OPENAI_API_KEY"] == "caller-key"
    assert os.environ["OPENAI_STARTUP_API_KEY"] == "caller-startup-key"
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["DDA_LANGSMITH_TRACING"] == "true"
    assert os.environ["HF_HUB_OFFLINE"] == "0"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "0"


def test_cli_run_gate_c_propagates_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    class FailingGateC:
        gate_c_passed = False
        artifact_paths: dict[str, str] = {}

        def to_json_dict(self: FailingGateC) -> dict[str, object]:
            return {
                "dataset": "startup_secure_ingest_v1",
                "gate_c_passed": False,
                "fail_reasons": ["privacy_egress"],
            }

    monkeypatch.setattr(
        "due_diligence_agent.evals.gate_c.run_gate_c_eval",
        lambda dataset, **_kwargs: FailingGateC(),
    )

    exit_code = cli.main(["run-gate-c", "--dataset", "startup_secure_ingest_v1"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"gate_c_passed": false' in captured.out
    assert '"privacy_egress"' in captured.out


def test_cli_run_gate_c_uses_dedicated_command_and_output_dir(
    gate_c_output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    calls: list[tuple[str, Path | None]] = []

    class PassingGateC:
        gate_c_passed = True
        artifact_paths: dict[str, str] = {}

        def to_json_dict(self: PassingGateC) -> dict[str, object]:
            return {"dataset": "startup_secure_ingest_v1", "gate_c_passed": True}

    def fake_gate_c(dataset: str, *, output_dir: Path | None = None) -> PassingGateC:
        calls.append((dataset, output_dir))
        return PassingGateC()

    monkeypatch.setattr("due_diligence_agent.evals.gate_c.run_gate_c_eval", fake_gate_c)

    exit_code = cli.main(
        [
            "run-gate-c",
            "--dataset",
            "startup_secure_ingest_v1",
            "--output-dir",
            str(gate_c_output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [("startup_secure_ingest_v1", gate_c_output_dir)]
    assert '"gate_c_passed": true' in captured.out


def test_run_eval_keeps_public_gate_b_behavior(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    monkeypatch.setattr(
        "due_diligence_agent.evals.runner.run_public_eval",
        lambda dataset: _gate_b_result(gate_b_passed=True),
    )

    exit_code = cli.main(["run-eval", "--dataset", "public_us_frozen_v1"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"gate_b_passed": true' in captured.out
    assert '"dataset": "public_us_frozen_v1"' in captured.out


def _has_adjacent_args(command: list[str], first: str, second: str) -> bool:
    return any(left == first and right == second for left, right in zip(command, command[1:]))


def _stream_summary(value: str) -> str:
    raw = value.encode("utf-8", errors="replace")
    return f"command-output-sha256:{sha256(raw).hexdigest()}:bytes:{len(raw)}"


@pytest.fixture
def gate_c_output_dir() -> Path:
    path = Path(".tmp-q0-task1-test-output") / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path


def _gate_b_result(
    *,
    gate_b_passed: bool,
    fail_reasons: tuple[str, ...] = (),
) -> EvaluationResult:
    return EvaluationResult(
        dataset="public_us_frozen_v1",
        schema_validity=1.0,
        critical_evidence_coverage=1.0,
        unsupported_critical_claim_rate=0.0,
        numerical_accuracy=1.0,
        unit_period_consistency=1.0,
        retrieval_recall_at_5=1.0,
        privacy_leak_count=0,
        trace_completeness=1.0,
        reflexion_max_rounds=1,
        budget_violations=0,
        offline_latency_minutes=0.1,
        report_completeness=1.0,
        exporter_outage_non_blocking=True,
        checkpoint_recovery=True,
        gate_b_passed=gate_b_passed,
        fail_reasons=fail_reasons,
        artifact_paths={},
    )

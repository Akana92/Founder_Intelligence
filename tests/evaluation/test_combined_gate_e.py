from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import re
import subprocess
import tempfile
import shutil
import uuid
from typing import Any, cast

from due_diligence_agent.evals.metrics import EvaluationResult
import pytest
from pytest import CaptureFixture


def _gate_b_result(*, gate_b_passed: bool) -> EvaluationResult:
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
        reflexion_max_rounds=0,
        budget_violations=0,
        offline_latency_minutes=0.001,
        report_completeness=1.0,
        exporter_outage_non_blocking=True,
        checkpoint_recovery=True,
        gate_b_passed=gate_b_passed,
        fail_reasons=(),
        artifact_paths={"eval_result": "public.json"},
    )


def _simple_gate_c(*, gate_c_passed: bool) -> object:
    class _Result:
        def __init__(self) -> None:
            self.gate_c_passed = gate_c_passed
            self.queue2_assertions = {
                "profile_determinism": True,
                "readiness_scored": True,
                "metric_pack_hash": "a" * 64,
                "contradiction_count": 0,
                "unsupported_claim_count": 0,
                "report_sections_ok": True,
                "trace_sections_ok": True,
                "max_questions": 3,
            }

    return _Result()


def _temp_output_dir() -> Path:
    base = Path(tempfile.gettempdir()) / "q2d-2d-manual"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"q2d-combined-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _simple_gate_d(*, gate_d_passed: bool) -> object:
    class _Result:
        def __init__(self) -> None:
            self.gate_d_passed = gate_d_passed
            self.artifact_paths = {"eval_result": "startup-d.json"}

    return _Result()


def test_gate_e_rejects_unsupported_dataset() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    with __import__("pytest").raises(ValueError, match="unsupported_dataset:foo"):
        run_gate_e_eval(
            "foo",
            output_dir=tmp_path,
            public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
            gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=True),
            gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        )
    shutil.rmtree(tmp_path)


def test_gate_e_result_schema_and_artifact() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=True),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
    )

    payload = result.to_json_dict()
    artifact_paths = cast(dict[str, str], payload["artifact_paths"])
    offline_no_key = cast(dict[str, bool], payload["offline_no_key"])
    assert payload["schema_version"] == "gate_e_result@1"
    assert payload["gate_e_passed"] is True
    assert payload["public_passed"] is True
    assert payload["gate_c_passed"] is True
    assert payload["gate_d_passed"] is True
    assert payload["compatibility_ok"] is True
    assert payload["report_repo_sanitized"] is True
    assert payload["pdf_fallback_ok"] is True
    assert payload["checkpoint_recovery_ok"] is True
    assert payload["shared_schema_ok"] is True
    assert payload["fail_reasons"] == []
    assert artifact_paths["eval_result"].endswith("eval-result.json")
    assert Path(artifact_paths["eval_result"]).exists()
    assert offline_no_key["openai_api_key_blank"] is True
    assert "private" not in artifact_paths["eval_result"].lower()

    contract = json.loads(Path(artifact_paths["eval_result"]).read_text(encoding="utf-8"))
    assert contract == result.to_json_dict()
    assert (tmp_path / ".evaluation-output-root.reserved").read_text(
        encoding="utf-8"
    ) == "evaluation_output_root_reserved@1\n"
    shutil.rmtree(tmp_path)


def test_gate_e_records_command_evidence_and_rejects_failed_compatibility_check() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    def fake_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        command_runner=lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout="nope", stderr="fail")
        if command == ["shared_schema"] or command == ["python", "-V"] and "shared_schema" in " ".join(command)
        else subprocess.CompletedProcess(command, 0, stdout="ok", stderr=""),
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=True),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
    )

    assert len(result.command_evidence) == 4
    check_names = {item.check_name for item in result.command_evidence}
    assert check_names == {"report_repo_sanitized", "pdf_fallback", "checkpoint_recovery", "shared_schema"}
    assert not re.search(r"Temp|tmp|/tmp|\\tmp", result.command_evidence[0].stderr_tail)
    shutil.rmtree(tmp_path)


def test_gate_e_rejects_failed_compatibility_proof_command() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    call_count = 0

    def fake_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal call_count
        call_count += 1
        if call_count == 4:
            return subprocess.CompletedProcess(command, 1, stdout="nope", stderr="fail")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        command_runner=fake_command,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=True),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
    )

    assert result.gate_e_passed is False
    assert result.fail_reasons == ("shared_schema:command_nonzero", "compatibility_failed")
    shutil.rmtree(tmp_path)


def test_gate_e_fails_when_gate_c_or_gate_d_fail() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=False),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(),
    )
    assert result.gate_e_passed is False
    assert "compatibility_proofs_missing" in result.fail_reasons
    assert "gate_c_regression" in result.fail_reasons
    shutil.rmtree(tmp_path)


def test_gate_e_separates_artifact_paths_for_public_and_startup() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    def fake_gate_d(*_args: object, **_kwargs: object) -> object:
        result = _simple_gate_d(gate_d_passed=True)
        result.artifact_paths = {"eval_result": "startup-d.json"}  # type: ignore[attr-defined]
        return result

    def fake_gate_c(*_args: object, **_kwargs: object) -> object:
        result = _simple_gate_c(gate_c_passed=True)
        result.artifact_paths = {"eval_result": "startup-c.json"}  # type: ignore[attr-defined]
        return result

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
        gate_c_evaluation_runner=fake_gate_c,
        gate_d_evaluation_runner=fake_gate_d,
    )

    assert result.public_artifact_paths == {"eval_result": "public.json"}
    assert result.startup_artifact_paths == {"eval_result": "startup-d.json"}
    assert result.gate_e_passed is True
    shutil.rmtree(tmp_path)


def test_gate_e_rejects_missing_compatibility_proofs() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=True),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(),
    )

    assert result.gate_e_passed is False
    assert "compatibility_proofs_missing" in result.fail_reasons
    assert result.report_repo_sanitized is None
    assert result.pdf_fallback_ok is None
    assert result.checkpoint_recovery_ok is None
    assert result.shared_schema_ok is None
    shutil.rmtree(tmp_path)


def test_gate_e_rejects_partial_compatibility_proofs() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    def fake_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        command_runner=fake_command,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=True),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(("report_repo_sanitized", "python -V"), ("shared_schema", "python -V")),
    )

    assert result.gate_e_passed is False
    assert result.fail_reasons == ("compatibility_proofs_missing", "compatibility_failed")
    shutil.rmtree(tmp_path)


def test_gate_e_uses_separate_output_roots_for_public_gate_c_and_gate_d() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    calls: list[tuple[str, Path]] = []

    def fake_gate_b(dataset: str, *, output_dir: Path) -> EvaluationResult:
        calls.append((f"public:{dataset}", output_dir))
        return _gate_b_result(gate_b_passed=True)

    def fake_gate_c(dataset: str, *, output_dir: Path) -> object:
        calls.append((f"gate-c:{dataset}", output_dir))
        result = _simple_gate_c(gate_c_passed=True)
        result.artifact_paths = {"eval_result": str(output_dir / "eval-result.json")}  # type: ignore[attr-defined]
        return result

    def fake_gate_d(dataset: str, *, output_dir: Path) -> object:
        calls.append((f"gate-d:{dataset}", output_dir))
        result = _simple_gate_d(gate_d_passed=True)
        result.artifact_paths = {"eval_result": str(output_dir / "eval-result.json")}  # type: ignore[attr-defined]
        return result

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=fake_gate_b,
        gate_c_evaluation_runner=fake_gate_c,
        gate_d_evaluation_runner=fake_gate_d,
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
    )

    assert result.gate_e_passed is True
    assert calls == [
        ("public:public_us_frozen_v1", tmp_path / "public"),
        ("gate-c:startup_secure_ingest_v1", tmp_path / "startup" / "gate-c"),
        ("gate-d:startup_synthetic_v1", tmp_path / "startup" / "gate-d"),
    ]
    assert result.public_artifact_paths != result.startup_artifact_paths
    shutil.rmtree(tmp_path)


def test_gate_e_default_gate_c_runner_uses_gate_c_baseline_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = _temp_output_dir()
    import due_diligence_agent.evals.gate_e as gate_e

    gate_c_calls: list[tuple[str, Path]] = []

    def fake_gate_c(dataset: str, *, output_dir: Path) -> object:
        gate_c_calls.append((dataset, output_dir))
        result = _simple_gate_c(gate_c_passed=True)
        result.artifact_paths = {"eval_result": str(output_dir / "eval-result.json")}  # type: ignore[attr-defined]
        return result

    monkeypatch.setattr(gate_e, "run_gate_c_eval", fake_gate_c)

    result = gate_e.run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
    )

    assert result.gate_e_passed is True
    assert gate_c_calls == [("startup_secure_ingest_v1", tmp_path / "startup" / "gate-c")]
    shutil.rmtree(tmp_path)


def test_gate_e_blanks_keys_for_nested_runners_and_restores_caller_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    caller_values = {
        "OPENAI_API_KEY": "caller-openai-key",
        "OPENAI_STARTUP_API_KEY": "caller-startup-key",
        "LANGSMITH_TRACING": "true",
        "LANGCHAIN_TRACING": "true",
        "LANGCHAIN_TRACING_V2": "true",
        "DDA_LANGSMITH_TRACING": "true",
        "HF_HUB_OFFLINE": "0",
        "TRANSFORMERS_OFFLINE": "0",
    }
    for name, value in caller_values.items():
        monkeypatch.setenv(name, value)

    nested_envs: list[dict[str, str | None]] = []

    def capture_env() -> dict[str, str | None]:
        return {name: os.environ.get(name) for name in caller_values}

    def fake_public_runner(*_args: object, **_kwargs: object) -> EvaluationResult:
        nested_envs.append(capture_env())
        return _gate_b_result(gate_b_passed=True)

    def fake_gate_c_runner(*_args: object, **_kwargs: object) -> object:
        nested_envs.append(capture_env())
        return _simple_gate_c(gate_c_passed=True)

    def fake_gate_d_runner(*_args: object, **_kwargs: object) -> object:
        nested_envs.append(capture_env())
        return _simple_gate_d(gate_d_passed=True)

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=fake_public_runner,
        gate_c_evaluation_runner=fake_gate_c_runner,
        gate_d_evaluation_runner=fake_gate_d_runner,
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
    )

    expected_nested = {
        "OPENAI_API_KEY": "",
        "OPENAI_STARTUP_API_KEY": "",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "DDA_LANGSMITH_TRACING": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    assert result.gate_e_passed is True
    assert nested_envs == [expected_nested, expected_nested, expected_nested]
    assert {name: os.environ[name] for name in caller_values} == caller_values
    shutil.rmtree(tmp_path)


def test_gate_e_rejects_missing_public_or_startup_artifacts() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    def fake_public(*_args: object, **_kwargs: object) -> EvaluationResult:
        result = _gate_b_result(gate_b_passed=True)
        return replace(result, artifact_paths={})

    result = run_gate_e_eval(
        "capstone_combined_v1",
        output_dir=tmp_path,
        public_eval_runner=fake_public,
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_c(gate_c_passed=True),
        gate_d_evaluation_runner=lambda *_args, **_kwargs: _simple_gate_d(gate_d_passed=True),
        compatibility_checks=(
            ("report_repo_sanitized", "python -V"),
            ("pdf_fallback", "python -V"),
            ("checkpoint_recovery", "python -V"),
            ("shared_schema", "python -V"),
        ),
    )

    assert result.gate_e_passed is False
    assert "public_artifact_paths_missing" in result.fail_reasons
    assert "startup_artifact_paths_missing" not in result.fail_reasons
    shutil.rmtree(tmp_path)


def test_gate_e_collision_rejects_non_empty_root_before_dispatch() -> None:
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    output_dir = _temp_output_dir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    dispatches: list[str] = []

    def dispatched(name: str, result: object) -> object:
        dispatches.append(name)
        return result

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_empty$"):
        run_gate_e_eval(
            "capstone_combined_v1",
            output_dir=output_dir,
            command_runner=lambda *_args, **_kwargs: cast(
                subprocess.CompletedProcess[str],
                dispatched("command", subprocess.CompletedProcess([], 0, "", "")),
            ),
            public_eval_runner=lambda *_args, **_kwargs: cast(
                EvaluationResult,
                dispatched("gate-b", _gate_b_result(gate_b_passed=True)),
            ),
            gate_c_evaluation_runner=lambda *_args, **_kwargs: dispatched(
                "gate-c", _simple_gate_c(gate_c_passed=True)
            ),
            gate_d_evaluation_runner=lambda *_args, **_kwargs: dispatched(
                "gate-d", _simple_gate_d(gate_d_passed=True)
            ),
            compatibility_checks=(("report_repo_sanitized", "python -V"),),
        )

    assert dispatches == []
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    shutil.rmtree(output_dir)


def test_gate_e_output_dir_file_is_rejected_before_dispatch() -> None:
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    parent = _temp_output_dir()
    output_file = parent / "not-a-directory"
    output_file.write_text("sentinel", encoding="utf-8")
    dispatches: list[str] = []

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_directory$"):
        run_gate_e_eval(
            "capstone_combined_v1",
            output_dir=output_file,
            command_runner=lambda *_args, **_kwargs: cast(
                subprocess.CompletedProcess[str],
                dispatches.append("command"),
            ),
            public_eval_runner=lambda *_args, **_kwargs: cast(
                EvaluationResult,
                dispatches.append("gate-b"),
            ),
            gate_c_evaluation_runner=lambda *_args, **_kwargs: dispatches.append("gate-c"),
            gate_d_evaluation_runner=lambda *_args, **_kwargs: dispatches.append("gate-d"),
            compatibility_checks=(("report_repo_sanitized", "python -V"),),
        )

    assert dispatches == []
    assert output_file.read_text(encoding="utf-8") == "sentinel"
    shutil.rmtree(parent)


def test_cli_run_gate_e_uses_dataset_output_dir_and_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    output_dir = _temp_output_dir()
    calls: list[tuple[str, Path | None]] = []

    class PassingGateE:
        gate_e_passed = True
        artifact_paths: dict[str, str] = {}

        def to_json_dict(self: PassingGateE) -> dict[str, object]:
            return {"dataset": "capstone_combined_v1", "gate_e_passed": True}

    def fake_gate_e(dataset: str, *, output_dir: Path | None = None) -> PassingGateE:
        assert output_dir is not None
        assert list(output_dir.iterdir()) == []
        calls.append((dataset, output_dir))
        return PassingGateE()

    monkeypatch.setattr("due_diligence_agent.evals.gate_e.run_gate_e_eval", fake_gate_e)

    exit_code = cli.main(
        ["run-gate-e", "--dataset", "capstone_combined_v1", "--output-dir", str(output_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [("capstone_combined_v1", output_dir)]
    assert '"gate_e_passed": true' in captured.out
    shutil.rmtree(output_dir)


def test_cli_run_gate_e_rejects_missing_output_dir(capsys: CaptureFixture[str]) -> None:
    import due_diligence_agent.presentation.cli as cli

    exit_code = cli.main(["run-gate-e", "--dataset", "capstone_combined_v1"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--output-dir is required" in captured.err


def test_cli_run_gate_e_collision_returns_two_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    output_dir = _temp_output_dir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    calls: list[str] = []

    def fake_gate_e(*_args: object, **_kwargs: object) -> object:
        calls.append("gate-e")
        raise AssertionError("Gate E must not be dispatched for an output collision")

    monkeypatch.setattr("due_diligence_agent.evals.gate_e.run_gate_e_eval", fake_gate_e)

    exit_code = cli.main(
        ["run-gate-e", "--dataset", "capstone_combined_v1", "--output-dir", str(output_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "evaluation_output_dir_not_empty"
    assert calls == []
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    shutil.rmtree(output_dir)


def test_cli_run_gate_e_reservation_race_returns_two_with_stable_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    output_dir = _temp_output_dir()
    calls: list[str] = []

    def fake_gate_e(*_args: object, **_kwargs: object) -> object:
        calls.append("gate-e")
        raise ValueError("evaluation_output_dir_not_empty")

    monkeypatch.setattr("due_diligence_agent.evals.gate_e.run_gate_e_eval", fake_gate_e)

    exit_code = cli.main(
        ["run-gate-e", "--dataset", "capstone_combined_v1", "--output-dir", str(output_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "evaluation_output_dir_not_empty"
    assert calls == ["gate-e"]
    shutil.rmtree(output_dir)


def test_stage1b_gate_d_and_e_scripts_forward_offline_contract_and_child_exit() -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the Gate D/E wrapper contract")

    repo_root = Path(__file__).resolve().parents[2]
    contract_dir = repo_root / ".tmp-q2d-script-contract" / uuid.uuid4().hex
    contract_dir.mkdir(parents=True, exist_ok=False)

    for script_name, command_name, dataset, exit_code in (
        ("run_stage1b_gate_d.ps1", "run-gate-d", "startup_synthetic_v1", 41),
        ("run_stage1b_gate_e.ps1", "run-gate-e", "capstone_combined_v1", 42),
    ):
        capture_path = contract_dir / f"{script_name}.json"
        fake_uv = contract_dir / f"fake-uv-{script_name}.ps1"
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
                    f"exit {exit_code}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        output_dir = Path(".tmp-q2d-script-output") / uuid.uuid4().hex
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
                str(repo_root / "scripts" / script_name),
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

        assert result.returncode == exit_code
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
            command_name,
            "--dataset",
            dataset,
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

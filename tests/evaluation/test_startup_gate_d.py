from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import shutil
import threading
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


def _valid_queue2_assertions() -> dict[str, object]:
    return {
        "profile_determinism": True,
        "readiness_scored": True,
        "metric_pack_hash": "a" * 64,
        "contradiction_count": 4,
        "unsupported_claim_count": 4,
        "report_sections_ok": True,
        "trace_sections_ok": True,
        "max_questions": 3,
    }


def _temp_output_dir() -> Path:
    base = Path(tempfile.gettempdir()) / "q2d-2d-manual"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"q2d-startup-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _queue2_result(*, gate_c_passed: bool, assertions: dict[str, object] | None = None) -> object:
    payload = _valid_queue2_assertions() if assertions is None else assertions

    class _Result:
        def __init__(self) -> None:
            self.gate_c_passed = gate_c_passed
            self.queue2_assertions = payload

    return _Result()


def _gate_c_result(*, gate_c_passed: bool) -> object:
    return _queue2_result(gate_c_passed=gate_c_passed)


def _gate_d_result(*, gate_d_passed: bool) -> object:
    class _Result:
        def __init__(self) -> None:
            self.gate_d_passed = gate_d_passed

    return _Result()


def _runtime_result(
    *,
    runtime_passed: bool = True,
    assertions: dict[str, object] | None = None,
    fail_reasons: tuple[str, ...] = (),
    privacy_leak_count: int | None = 0,
    denied_gate2_external_calls: int | None = 0,
) -> object:
    payload = _valid_queue2_assertions() if assertions is None else assertions

    class _Result:
        def __init__(self) -> None:
            self.queue2_runtime_passed = runtime_passed
            self.queue2_assertion_provenance = "runtime_api:startup_synthetic_v1"
            self.queue2_assertions = payload
            self.privacy_leak_count = privacy_leak_count
            self.denied_gate2_external_calls = denied_gate2_external_calls
            self.fail_reasons = fail_reasons
            self.artifact_paths = {"runtime_evidence": "runtime/runtime-evidence.json"}

    return _Result()


def test_gate_d_rejects_unsupported_dataset() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    with __import__("pytest").raises(ValueError, match="unsupported_dataset:foo"):
        run_gate_d_eval(
            "foo",
            output_dir=tmp_path,
            public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
            gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
            startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
            command_probes=(),
        )
    shutil.rmtree(tmp_path)


def test_gate_d_result_is_canonical_json_safe() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(("python", "-V"),),
    )

    payload = result.to_json_dict()
    artifact_paths = cast(dict[str, str], payload["artifact_paths"])
    offline_no_key = cast(dict[str, bool], payload["offline_no_key"])
    environment = cast(dict[str, object], payload["environment"])
    assert payload["schema_version"] == "gate_d_result@1"
    assert payload["dataset"] == "startup_synthetic_v1"
    assert payload["gate_d_passed"] is True
    assert payload["fail_reasons"] == []
    assert payload["queue2_assertion_provenance"] == "runtime_api:startup_synthetic_v1"
    assert payload["privacy_leak_count"] == 0
    assert payload["denied_gate2_external_calls"] == 0
    assert isinstance(payload["command_evidence"], list)
    assert isinstance(payload["artifact_paths"], dict)
    assert Path(artifact_paths["eval_result"]).exists()
    assert offline_no_key["openai_api_key_blank"] is True
    assert environment["python"]

    contract = json.loads(Path(artifact_paths["eval_result"]).read_text(encoding="utf-8"))
    assert contract == result.to_json_dict()
    shutil.rmtree(tmp_path)


def test_gate_d_records_command_evidence_without_exception_strings() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    evidence: list[list[str]] = []

    def fake_runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        evidence.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        command_runner=fake_runner,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(("python", "-V"),),
    )

    assert evidence
    assert result.command_evidence[0].check_name == "python"
    assert result.command_evidence[0].returncode == 0
    assert not re.search(r"Temp|tmp|/tmp|\\tmp", result.command_evidence[0].stderr_tail)
    assert len(result.command_evidence[0].stdout_tail) < 200
    assert result.fail_reasons == ()
    shutil.rmtree(tmp_path)


def test_gate_d_includes_queue2_assertion_fields() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(),
    )

    assertions = cast(dict[str, object], result.to_json_dict()["queue2_assertions"])
    assert assertions["max_questions"] == 3
    assert "readiness_scored" in assertions
    assert isinstance(assertions["readiness_scored"], bool)
    shutil.rmtree(tmp_path)


def test_gate_d_fails_when_runner_reports_fail_reason() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=False),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=False),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(),
    )

    assert result.gate_d_passed is False
    assert result.fail_reasons == ("gate_b_regression", "gate_c_regression")
    shutil.rmtree(tmp_path)


def test_gate_d_uses_runtime_queue2_evidence_when_gate_c_has_no_queue2_assertions() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    def fake_gate_c(*_args: object, **_kwargs: object) -> object:
        class _Result:
            def __init__(self) -> None:
                self.gate_c_passed = True

        return _Result()

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=fake_gate_c,
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(),
    )

    assert result.gate_d_passed is True
    assert result.fail_reasons == ()
    assert result.queue2_assertions["max_questions"] == 3
    assert result.queue2_assertion_provenance == "runtime_api:startup_synthetic_v1"
    shutil.rmtree(tmp_path)


def test_gate_d_default_gate_c_runner_uses_gate_c_baseline_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = _temp_output_dir()
    import due_diligence_agent.evals.gate_d as gate_d

    gate_c_calls: list[tuple[str, Path]] = []

    def fake_gate_c(dataset: str, *, output_dir: Path) -> object:
        gate_c_calls.append((dataset, output_dir))
        return _queue2_result(gate_c_passed=True)

    monkeypatch.setattr(gate_d, "run_gate_c_eval", fake_gate_c)

    result = gate_d.run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(),
    )

    assert result.gate_d_passed is True
    assert gate_c_calls == [("startup_secure_ingest_v1", tmp_path / "gate-c")]
    shutil.rmtree(tmp_path)


def test_gate_d_rejects_invalid_queue2_assertions() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    invalid_assertions = _valid_queue2_assertions()
    invalid_assertions["metric_pack_hash"] = "badhash"
    invalid_assertions["max_questions"] = 5

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True, assertions=invalid_assertions),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(assertions=invalid_assertions),
        command_probes=(),
    )

    assert result.gate_d_passed is False
    assert result.fail_reasons == ("startup_queue2_assertions_invalid",)
    shutil.rmtree(tmp_path)


def test_gate_d_fails_closed_when_runtime_queue2_evidence_fails() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(
            runtime_passed=False,
            fail_reasons=("case_a:contradiction_runtime_evidence_missing",),
        ),
        command_probes=(),
    )

    assert result.gate_d_passed is False
    assert result.fail_reasons == (
        "startup_queue2_runtime",
        "startup_runtime:case_a:contradiction_runtime_evidence_missing",
    )
    shutil.rmtree(tmp_path)


def test_gate_d_fails_closed_when_runtime_privacy_or_external_call_counters_are_bad() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(
            privacy_leak_count=1,
            denied_gate2_external_calls=1,
        ),
        command_probes=(),
    )

    assert result.gate_d_passed is False
    assert "startup_runtime_privacy_leaks_detected" in result.fail_reasons
    assert "startup_runtime_external_calls_denied" in result.fail_reasons
    shutil.rmtree(tmp_path)


def test_gate_d_fails_closed_when_runtime_counters_are_missing() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(
            privacy_leak_count=None,
            denied_gate2_external_calls=None,
        ),
        command_probes=(),
    )

    assert result.gate_d_passed is False
    assert "startup_runtime_privacy_count_missing" in result.fail_reasons
    assert "startup_runtime_denied_external_calls_missing" in result.fail_reasons
    shutil.rmtree(tmp_path)


def test_gate_d_requires_runtime_materialized_contradictions_and_unsupported_claims() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    missing_assertions = _valid_queue2_assertions()
    missing_assertions["contradiction_count"] = 0
    missing_assertions["unsupported_claim_count"] = 0

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(assertions=missing_assertions),
        command_probes=(),
    )

    assert result.gate_d_passed is False
    assert result.fail_reasons == ("startup_queue2_assertions_invalid",)
    shutil.rmtree(tmp_path)


def test_gate_d_source_no_longer_contains_queue2_expected_contracts_fallback() -> None:
    import due_diligence_agent.evals.gate_d as gate_d

    source = Path(gate_d.__file__).read_text(encoding="utf-8")
    assert "expected_contracts" not in source
    assert "_load_fixture_evidence" not in source
    assert "verified_fixture" not in source


def test_gate_d_blanks_keys_for_nested_gate_runners_and_restores_caller_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

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

    def fake_gate_b(*_args: object, **_kwargs: object) -> EvaluationResult:
        nested_envs.append({name: os.environ.get(name) for name in caller_values})
        return _gate_b_result(gate_b_passed=True)

    def fake_gate_c(*_args: object, **_kwargs: object) -> object:
        nested_envs.append({name: os.environ.get(name) for name in caller_values})
        return _queue2_result(gate_c_passed=True)

    def fake_runtime(*_args: object, **_kwargs: object) -> object:
        nested_envs.append({name: os.environ.get(name) for name in caller_values})
        return _runtime_result()

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        public_eval_runner=fake_gate_b,
        gate_c_evaluation_runner=fake_gate_c,
        startup_runtime_runner=fake_runtime,
        command_probes=(),
    )

    assert result.gate_d_passed is True
    assert nested_envs == [
        {
            "OPENAI_API_KEY": "",
            "OPENAI_STARTUP_API_KEY": "",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "DDA_LANGSMITH_TRACING": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        {
            "OPENAI_API_KEY": "",
            "OPENAI_STARTUP_API_KEY": "",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "DDA_LANGSMITH_TRACING": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        {
            "OPENAI_API_KEY": "",
            "OPENAI_STARTUP_API_KEY": "",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "DDA_LANGSMITH_TRACING": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
    ]
    assert {name: os.environ[name] for name in caller_values} == caller_values
    shutil.rmtree(tmp_path)


def test_gate_d_command_timeout_and_os_error_fail_closed() -> None:
    tmp_path = _temp_output_dir()
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    def fake_runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command == ["timeout-check"]:
            raise subprocess.TimeoutExpired(command, timeout=120, output="late", stderr="timed out")
        if command == ["spawn-error"]:
            raise OSError("cannot spawn")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path,
        command_runner=fake_runner,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(("timeout-check",), ("spawn-error",)),
    )

    assert result.gate_d_passed is False
    assert result.fail_reasons == ("timeout-check:command_timeout", "spawn-error:command_error")
    assert [item.returncode for item in result.command_evidence] == [124, 1]
    payload = Path(result.artifact_paths["eval_result"]).read_text(encoding="utf-8")
    assert "cannot spawn" not in payload
    assert "timed out" not in payload
    shutil.rmtree(tmp_path)


def test_gate_d_collision_rejects_stale_eval_result_without_dispatch() -> None:
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    output_dir = _temp_output_dir()
    stale_path = output_dir / "eval-result.json"
    stale_path.write_text("stale", encoding="utf-8")
    dispatches: list[str] = []

    def dispatched(name: str, result: object) -> object:
        dispatches.append(name)
        return result

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_empty$"):
        run_gate_d_eval(
            "startup_synthetic_v1",
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
                "gate-c", _queue2_result(gate_c_passed=True)
            ),
            startup_runtime_runner=lambda *_args, **_kwargs: dispatched(
                "runtime", _runtime_result()
            ),
            command_probes=(("collision-probe", ("python", "-V")),),
        )

    assert dispatches == []
    assert stale_path.read_text(encoding="utf-8") == "stale"
    shutil.rmtree(output_dir)


def test_gate_d_output_dir_file_is_rejected_before_dispatch() -> None:
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    parent = _temp_output_dir()
    output_file = parent / "not-a-directory"
    output_file.write_text("sentinel", encoding="utf-8")
    dispatches: list[str] = []

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_directory$"):
        run_gate_d_eval(
            "startup_synthetic_v1",
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
            startup_runtime_runner=lambda *_args, **_kwargs: dispatches.append("runtime"),
            command_probes=(("collision-probe", ("python", "-V")),),
        )

    assert dispatches == []
    assert output_file.read_text(encoding="utf-8") == "sentinel"
    shutil.rmtree(parent)


def test_gate_d_missing_output_dir_is_created() -> None:
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    parent = _temp_output_dir()
    output_dir = parent / "new-run"

    result = run_gate_d_eval(
        "startup_synthetic_v1",
        output_dir=output_dir,
        public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
        gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(gate_c_passed=True),
        startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
        command_probes=(),
    )

    assert result.gate_d_passed is True
    assert output_dir.is_dir()
    assert (output_dir / "eval-result.json").is_file()
    shutil.rmtree(parent)


@pytest.mark.parametrize("initial_state", ("missing", "empty"))
def test_gate_d_concurrent_output_root_reservation_allows_one_dispatch(
    initial_state: str,
) -> None:
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    parent = _temp_output_dir()
    output_dir = parent / "shared-run"
    if initial_state == "empty":
        output_dir.mkdir()

    first_dispatched = threading.Event()
    release_first = threading.Event()
    dispatch_lock = threading.Lock()
    command_dispatches: list[str] = []
    nested_dispatches: list[str] = []
    results: list[object] = []
    errors: list[Exception] = []

    def fake_command(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        with dispatch_lock:
            command_dispatches.append(threading.current_thread().name)
            call_number = len(command_dispatches)
        if call_number == 1:
            first_dispatched.set()
            if not release_first.wait(timeout=5):
                raise AssertionError("timed out waiting to release first Gate D attempt")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    def nested(name: str, result: object) -> object:
        nested_dispatches.append(name)
        return result

    def run_attempt() -> None:
        try:
            results.append(
                run_gate_d_eval(
                    "startup_synthetic_v1",
                    output_dir=output_dir,
                    command_runner=fake_command,
                    public_eval_runner=lambda *_args, **_kwargs: cast(
                        EvaluationResult,
                        nested("gate-b", _gate_b_result(gate_b_passed=True)),
                    ),
                    gate_c_evaluation_runner=lambda *_args, **_kwargs: nested(
                        "gate-c", _queue2_result(gate_c_passed=True)
                    ),
                    startup_runtime_runner=lambda *_args, **_kwargs: nested(
                        "runtime", _runtime_result()
                    ),
                    command_probes=(("reservation-probe", ("python", "-V")),),
                )
            )
        except Exception as exc:  # noqa: BLE001 - the thread must report all failures
            errors.append(exc)

    first_attempt = threading.Thread(target=run_attempt, name="first-gate-d-attempt")
    try:
        first_attempt.start()
        assert first_dispatched.wait(timeout=5)
        run_attempt()
        release_first.set()
        first_attempt.join(timeout=5)

        assert not first_attempt.is_alive()
        assert len(results) == 1
        assert [str(error) for error in errors] == ["evaluation_output_dir_not_empty"]
        assert command_dispatches == ["first-gate-d-attempt"]
        assert nested_dispatches == ["gate-b", "gate-c", "runtime"]

        reservation = output_dir / ".evaluation-output-root.reserved"
        assert reservation.read_text(encoding="utf-8") == "evaluation_output_root_reserved@1\n"
        result_path = output_dir / "eval-result.json"
        evidence = result_path.read_bytes()

        with pytest.raises(ValueError, match="^evaluation_output_dir_not_empty$"):
            run_gate_d_eval(
                "startup_synthetic_v1",
                output_dir=output_dir,
                command_runner=fake_command,
                public_eval_runner=lambda *_args, **_kwargs: _gate_b_result(gate_b_passed=True),
                gate_c_evaluation_runner=lambda *_args, **_kwargs: _queue2_result(
                    gate_c_passed=True
                ),
                startup_runtime_runner=lambda *_args, **_kwargs: _runtime_result(),
                command_probes=(),
            )
        assert result_path.read_bytes() == evidence
    finally:
        release_first.set()
        first_attempt.join(timeout=5)
        shutil.rmtree(parent)


def test_cli_run_gate_d_uses_dataset_output_dir_and_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    output_dir = _temp_output_dir()
    calls: list[tuple[str, Path | None]] = []

    class PassingGateD:
        gate_d_passed = True
        artifact_paths: dict[str, str] = {}

        def to_json_dict(self: PassingGateD) -> dict[str, object]:
            return {"dataset": "startup_synthetic_v1", "gate_d_passed": True}

    def fake_gate_d(dataset: str, *, output_dir: Path | None = None) -> PassingGateD:
        assert output_dir is not None
        assert list(output_dir.iterdir()) == []
        calls.append((dataset, output_dir))
        return PassingGateD()

    monkeypatch.setattr("due_diligence_agent.evals.gate_d.run_gate_d_eval", fake_gate_d)

    exit_code = cli.main(
        ["run-gate-d", "--dataset", "startup_synthetic_v1", "--output-dir", str(output_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [("startup_synthetic_v1", output_dir)]
    assert '"gate_d_passed": true' in captured.out
    shutil.rmtree(output_dir)


def test_cli_run_gate_d_rejects_missing_output_dir(capsys: CaptureFixture[str]) -> None:
    import due_diligence_agent.presentation.cli as cli

    exit_code = cli.main(["run-gate-d", "--dataset", "startup_synthetic_v1"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--output-dir is required" in captured.err


def test_cli_run_gate_d_collision_returns_two_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    output_dir = _temp_output_dir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    calls: list[str] = []

    def fake_gate_d(*_args: object, **_kwargs: object) -> object:
        calls.append("gate-d")
        raise AssertionError("Gate D must not be dispatched for an output collision")

    monkeypatch.setattr("due_diligence_agent.evals.gate_d.run_gate_d_eval", fake_gate_d)

    exit_code = cli.main(
        ["run-gate-d", "--dataset", "startup_synthetic_v1", "--output-dir", str(output_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "evaluation_output_dir_not_empty"
    assert calls == []
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    shutil.rmtree(output_dir)


def test_cli_run_gate_d_reservation_race_returns_two_with_stable_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    import due_diligence_agent.presentation.cli as cli

    output_dir = _temp_output_dir()
    calls: list[str] = []

    def fake_gate_d(*_args: object, **_kwargs: object) -> object:
        calls.append("gate-d")
        raise ValueError("evaluation_output_dir_not_empty")

    monkeypatch.setattr("due_diligence_agent.evals.gate_d.run_gate_d_eval", fake_gate_d)

    exit_code = cli.main(
        ["run-gate-d", "--dataset", "startup_synthetic_v1", "--output-dir", str(output_dir)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "evaluation_output_dir_not_empty"
    assert calls == ["gate-d"]
    shutil.rmtree(output_dir)

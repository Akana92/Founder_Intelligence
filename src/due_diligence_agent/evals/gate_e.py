from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import hashlib
import os
import platform
import subprocess
import sys
import time
from typing import Callable, Mapping, Sequence

from due_diligence_agent.evals.metrics import EvaluationResult
from due_diligence_agent.evals.output_root import prepare_evaluation_output_root
from due_diligence_agent.evals.runner import run_public_eval
from due_diligence_agent.evals.gate_c import GATE_C_DATASET, run_gate_c_eval
from due_diligence_agent.evals.gate_d import run_gate_d_eval


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GATE_E_DATASET = "capstone_combined_v1"
GATE_B_REGRESSION_DATASET = "public_us_frozen_v1"
GATE_D_REGRESSION_DATASET = "startup_synthetic_v1"
COMMAND_ERROR_RETURNCODE = 1
COMMAND_TIMEOUT_RETURNCODE = 124
OFFLINE_ENV_OVERRIDES = {
    "OPENAI_API_KEY": "",
    "OPENAI_STARTUP_API_KEY": "",
    "LANGSMITH_TRACING": "false",
    "LANGCHAIN_TRACING": "false",
    "LANGCHAIN_TRACING_V2": "false",
    "DDA_LANGSMITH_TRACING": "false",
    "UV_OFFLINE": "true",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _stream_value(value: str | None) -> str:
    if not value:
        return ""
    raw = value.encode("utf-8", errors="replace")
    return f"command-output-sha256:{sha256(raw).hexdigest()}:bytes:{len(raw)}"


@dataclass(frozen=True)
class CommandEvidence:
    check_name: str
    command: list[str]
    returncode: int
    stdout_tail: str
    stderr_tail: str

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GateEResult:
    schema_version: str
    dataset: str
    gate_e_passed: bool
    public_passed: bool | None
    gate_c_passed: bool | None
    gate_d_passed: bool | None
    compatibility_ok: bool | None
    report_repo_sanitized: bool | None
    pdf_fallback_ok: bool | None
    checkpoint_recovery_ok: bool | None
    shared_schema_ok: bool | None
    offline_latency_minutes: float
    fail_reasons: tuple[str, ...] = ()
    command_evidence: tuple[CommandEvidence, ...] = ()
    artifact_paths: dict[str, str] = field(default_factory=dict)
    commit_id: str = "unknown"
    environment: dict[str, object] = field(default_factory=dict)
    offline_no_key: dict[str, bool] = field(default_factory=dict)
    public_artifact_paths: dict[str, str] = field(default_factory=dict)
    startup_artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["fail_reasons"] = list(self.fail_reasons)
        payload["command_evidence"] = [item.to_json_dict() for item in self.command_evidence]
        return payload


REQUIRED_COMPATIBILITY_PROOFS = (
    "report_repo_sanitized",
    "pdf_fallback",
    "checkpoint_recovery",
    "shared_schema",
)
DEFAULT_COMPATIBILITY_CHECKS: tuple[tuple[str, list[str]], ...] = (
    (
        "report_repo_sanitized",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/privacy/test_startup_redaction.py",
            "tests/privacy/test_langsmith_masking.py",
        ],
    ),
    (
        "pdf_fallback",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/unit/reporting/test_startup_report_snapshot.py",
        ],
    ),
    (
        "checkpoint_recovery",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/graph/test_startup_workflow.py",
        ],
    ),
    (
        "shared_schema",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/smoke/test_application_boot.py",
            "tests/evaluation/test_startup_gate_c.py",
        ],
    ),
)


PublicEvalRunner = Callable[..., EvaluationResult]
GateCRunner = Callable[..., object]
GateDRunner = Callable[..., object]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def run_gate_e_eval(
    dataset: str,
    *,
    output_dir: Path | None = None,
    command_runner: CommandRunner = subprocess.run,
    public_eval_runner: PublicEvalRunner = run_public_eval,
    gate_c_evaluation_runner: GateCRunner | None = None,
    gate_d_evaluation_runner: GateDRunner = run_gate_d_eval,
    compatibility_checks: tuple[tuple[str, Sequence[str] | str], ...] | None = None,
) -> GateEResult:
    if dataset != GATE_E_DATASET:
        raise ValueError(f"unsupported_dataset:{dataset}")

    output_dir = prepare_evaluation_output_root(
        output_dir or PROJECT_ROOT / "output" / "gate-e" / dataset
    )
    started = time.monotonic()
    env = _offline_environment()
    command_evidence: list[CommandEvidence] = []
    fail_reasons: list[str] = []
    compatibility_proofs: dict[str, bool | None] = {name: None for name in REQUIRED_COMPATIBILITY_PROOFS}

    compatibility_checks = DEFAULT_COMPATIBILITY_CHECKS if compatibility_checks is None else tuple(compatibility_checks)
    provided_proof_names = {name for name, _ in compatibility_checks}
    missing_proofs = set(REQUIRED_COMPATIBILITY_PROOFS) - provided_proof_names
    if missing_proofs:
        fail_reasons.append("compatibility_proofs_missing")

    compatibility_passed = not bool(missing_proofs)
    for name, command in compatibility_checks:
        completed, command_fail_reason = _run_command(command, command_runner=command_runner, env=env)
        command_evidence.append(_to_command_evidence(name, completed))
        if name in compatibility_proofs:
            compatibility_proofs[name] = completed.returncode == 0
        if completed.returncode != 0:
            fail_reasons.append(command_fail_reason or f"{name}:command_nonzero")
            compatibility_passed = False

    with _scoped_environment(OFFLINE_ENV_OVERRIDES):
        public_result = public_eval_runner(
            GATE_B_REGRESSION_DATASET,
            output_dir=output_dir / "public",
        )
        public_passed = public_result.gate_b_passed
        if not public_passed:
            fail_reasons.append("public_regression")
            fail_reasons.extend(f"public:{reason}" for reason in public_result.fail_reasons)

        gate_c_runner = run_gate_c_eval if gate_c_evaluation_runner is None else gate_c_evaluation_runner
        gate_c_result = gate_c_runner(
            GATE_C_DATASET,
            output_dir=output_dir / "startup" / "gate-c",
        )
        gate_c_passed = getattr(gate_c_result, "gate_c_passed", None)
        if not gate_c_passed:
            fail_reasons.append("gate_c_regression")

        gate_d_result = gate_d_evaluation_runner(
            GATE_D_REGRESSION_DATASET,
            output_dir=output_dir / "startup" / "gate-d",
        )
        gate_d_passed = getattr(gate_d_result, "gate_d_passed", None)
        if not gate_d_passed:
            fail_reasons.append("gate_d_regression")
        offline_no_key = _offline_no_key(os.environ)

    public_artifact_paths = _artifact_paths(public_result)
    startup_artifact_paths = _artifact_paths(gate_d_result)
    if not public_artifact_paths:
        fail_reasons.append("public_artifact_paths_missing")
    if not startup_artifact_paths:
        fail_reasons.append("startup_artifact_paths_missing")

    compatibility_ok = (
        compatibility_passed
        and bool(compatibility_proofs["report_repo_sanitized"])
        and bool(compatibility_proofs["pdf_fallback"])
        and bool(compatibility_proofs["checkpoint_recovery"])
        and bool(compatibility_proofs["shared_schema"])
        and all([public_passed, bool(gate_c_passed), bool(gate_d_passed)])
    )
    if compatibility_ok is not True:
        fail_reasons.append("compatibility_failed")

    result = GateEResult(
        schema_version="gate_e_result@1",
        dataset=dataset,
        gate_e_passed=not fail_reasons,
        public_passed=public_passed,
        gate_c_passed=gate_c_passed,
        gate_d_passed=gate_d_passed,
        compatibility_ok=compatibility_ok,
        report_repo_sanitized=compatibility_proofs["report_repo_sanitized"],
        pdf_fallback_ok=compatibility_proofs["pdf_fallback"],
        checkpoint_recovery_ok=compatibility_proofs["checkpoint_recovery"],
        shared_schema_ok=compatibility_proofs["shared_schema"],
        offline_latency_minutes=round((time.monotonic() - started) / 60, 6),
        fail_reasons=tuple(fail_reasons),
        command_evidence=tuple(command_evidence),
        artifact_paths={"eval_result": str(output_dir / "eval-result.json")},
        commit_id=_git_commit(),
        environment=_environment(),
        offline_no_key=offline_no_key,
        public_artifact_paths=public_artifact_paths,
        startup_artifact_paths=startup_artifact_paths,
    )
    _write_result(output_dir / "eval-result.json", result)
    return result


def _run_command(
    command: Sequence[str] | str,
    *,
    command_runner: CommandRunner,
    env: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], str | None]:
    command_tokens = [str(item) for item in command] if not isinstance(command, str) else [item for item in command.split() if item]
    try:
        return (
            command_runner(
                command_tokens,
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            ),
            None,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            subprocess.CompletedProcess(
                command_tokens,
                COMMAND_TIMEOUT_RETURNCODE,
                stdout=_string_output(exc.output),
                stderr=_string_output(exc.stderr) or "command timed out",
            ),
            f"{command_tokens[0] if command_tokens else 'compatibility'}:command_timeout",
        )
    except OSError:
        return (
            subprocess.CompletedProcess(
                command_tokens,
                COMMAND_ERROR_RETURNCODE,
                stdout="",
                stderr="OSError: command failed to start",
            ),
            f"{command_tokens[0] if command_tokens else 'compatibility'}:command_error",
        )


def _to_command_evidence(check_name: str, completed: subprocess.CompletedProcess[str]) -> CommandEvidence:
    command = [str(item) for item in completed.args]
    return CommandEvidence(
        check_name=check_name,
        command=command,
        returncode=completed.returncode,
        stdout_tail=_stream_value(completed.stdout),
        stderr_tail=_stream_value(completed.stderr),
    )


def _write_result(path: Path, result: GateEResult) -> None:
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(result.to_json_dict(), sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _offline_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(OFFLINE_ENV_OVERRIDES)
    return env


def _offline_no_key(env: Mapping[str, str]) -> dict[str, bool]:
    return {
        "openai_api_key_blank": env.get("OPENAI_API_KEY") == "",
        "openai_startup_api_key_blank": env.get("OPENAI_STARTUP_API_KEY") == "",
        "langsmith_tracing_disabled": env.get("LANGSMITH_TRACING") == "false",
        "langchain_legacy_tracing_disabled": env.get("LANGCHAIN_TRACING") == "false",
        "langchain_tracing_disabled": env.get("LANGCHAIN_TRACING_V2") == "false",
        "hf_hub_offline": env.get("HF_HUB_OFFLINE") == "1",
        "transformers_offline": env.get("TRANSFORMERS_OFFLINE") == "1",
    }


def _artifact_paths(result: object) -> dict[str, str]:
    raw = getattr(result, "artifact_paths", {})
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


class _scoped_environment:
    def __init__(self, overrides: dict[str, str]) -> None:
        self._overrides = overrides
        self._previous: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for name, value in self._overrides.items():
            self._previous[name] = os.environ.get(name)
            os.environ[name] = value

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        for name, value in self._previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _environment() -> dict[str, object]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executable": sys.executable,
    }


def _git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip()


def _string_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value

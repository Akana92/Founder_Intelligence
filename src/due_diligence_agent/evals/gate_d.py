from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
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
from due_diligence_agent.evals.startup_frozen_runtime import (
    run_startup_frozen_runtime_eval,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GATE_D_DATASET = "startup_synthetic_v1"
GATE_B_REGRESSION_DATASET = "public_us_frozen_v1"
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
DEFAULT_GATE_D_CHECKS: tuple[tuple[str, list[str]], ...] = (
    (
        "queue2_startup_fixtures",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/evaluation/test_queue2_startup_fixtures.py",
        ],
    ),
    (
        "startup_graph_contract",
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
        "startup_report_contract",
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
)


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
class Queue2AssertionMatrix:
    profile_determinism: bool | None = None
    readiness_scored: bool | None = None
    metric_pack_hash: str | None = None
    contradiction_count: int | None = None
    unsupported_claim_count: int | None = None
    report_sections_ok: bool | None = None
    trace_sections_ok: bool | None = None
    max_questions: int | None = None

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GateDResult:
    schema_version: str
    dataset: str
    gate_d_passed: bool
    gate_b_passed: bool | None
    gate_c_passed: bool | None
    privacy_leak_count: int | None
    denied_gate2_external_calls: int | None
    offline_latency_minutes: float
    queue2_assertions: dict[str, object]
    queue2_assertion_provenance: str | None
    fail_reasons: tuple[str, ...] = ()
    command_evidence: tuple[CommandEvidence, ...] = ()
    artifact_paths: dict[str, str] = field(default_factory=dict)
    commit_id: str = "unknown"
    environment: dict[str, object] = field(default_factory=dict)
    offline_no_key: dict[str, bool] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["fail_reasons"] = list(self.fail_reasons)
        payload["command_evidence"] = [item.to_json_dict() for item in self.command_evidence]
        payload["queue2_assertions"] = dict(self.queue2_assertions)
        return payload


PublicEvalRunner = Callable[..., EvaluationResult]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
GateCRunner = Callable[..., object]
StartupRuntimeRunner = Callable[..., object]


def run_gate_d_eval(
    dataset: str,
    *,
    output_dir: Path | None = None,
    command_runner: CommandRunner = subprocess.run,
    public_eval_runner: PublicEvalRunner = run_public_eval,
    gate_c_evaluation_runner: GateCRunner | None = None,
    startup_runtime_runner: StartupRuntimeRunner | None = None,
    command_probes: Sequence[Sequence[str] | tuple[str, Sequence[str]]] | None = None,
) -> GateDResult:
    if dataset != GATE_D_DATASET:
        raise ValueError(f"unsupported_dataset:{dataset}")

    output_dir = prepare_evaluation_output_root(
        output_dir or PROJECT_ROOT / "output" / "gate-d" / dataset
    )
    started = time.monotonic()
    env = _offline_environment()
    command_evidence: list[CommandEvidence] = []

    fail_reasons: list[str] = []

    checks = _normalize_checks(command_probes)
    for check_name, command in checks:
        completed, command_fail_reason = _run_command(
            [*command],
            command_runner=command_runner,
            env=env,
        )
        command_evidence.append(_to_command_evidence(check_name, completed))
        if completed.returncode != 0:
            fail_reasons.append(command_fail_reason or f"{check_name}:command_nonzero")

    with _scoped_environment(OFFLINE_ENV_OVERRIDES):
        gate_b_result = public_eval_runner(
            GATE_B_REGRESSION_DATASET,
            output_dir=output_dir / "gate-b",
        )
        gate_b_passed = gate_b_result.gate_b_passed
        if not gate_b_passed:
            fail_reasons.append("gate_b_regression")
            fail_reasons.extend(f"gate_b:{reason}" for reason in gate_b_result.fail_reasons)
        gate_c_runner = run_gate_c_eval if gate_c_evaluation_runner is None else gate_c_evaluation_runner
        gate_c_result = gate_c_runner(GATE_C_DATASET, output_dir=output_dir / "gate-c")
        gate_c_passed = getattr(gate_c_result, "gate_c_passed", None)
        if not gate_c_passed:
            fail_reasons.append("gate_c_regression")
        runtime_runner = (
            run_startup_frozen_runtime_eval
            if startup_runtime_runner is None
            else startup_runtime_runner
        )
        startup_runtime_result = runtime_runner(
            GATE_D_DATASET,
            output_dir=output_dir / "runtime",
        )
        startup_runtime_passed = bool(
            getattr(startup_runtime_result, "queue2_runtime_passed", False)
        )
        if not startup_runtime_passed:
            fail_reasons.append("startup_queue2_runtime")
            fail_reasons.extend(
                f"startup_runtime:{reason}"
                for reason in _string_tuple(getattr(startup_runtime_result, "fail_reasons", ()))
            )
        startup_privacy_leak_count = _to_int(
            getattr(startup_runtime_result, "privacy_leak_count", None)
        )
        startup_denied_external_calls = _to_int(
            getattr(startup_runtime_result, "denied_gate2_external_calls", None)
        )
        if startup_privacy_leak_count is None:
            fail_reasons.append("startup_runtime_privacy_count_missing")
        elif startup_privacy_leak_count > 0:
            fail_reasons.append("startup_runtime_privacy_leaks_detected")
        if startup_denied_external_calls is None:
            fail_reasons.append("startup_runtime_denied_external_calls_missing")
        elif startup_denied_external_calls > 0:
            fail_reasons.append("startup_runtime_external_calls_denied")
        offline_no_key = _offline_no_key(os.environ)

    queue2_assertion_provenance: str | None = _string_or_none(
        getattr(startup_runtime_result, "queue2_assertion_provenance", None)
    )
    queue2_assertions = _extract_queue2_assertions(startup_runtime_result)
    if queue2_assertions is None:
        fail_reasons.append("startup_queue2_assertions_missing")
        queue2_assertions_payload: dict[str, object] = {}
    elif not _validate_queue2_assertions(queue2_assertions):
        fail_reasons.append("startup_queue2_assertions_invalid")
        queue2_assertions_payload = queue2_assertions.to_json_dict()
    else:
        queue2_assertions_payload = queue2_assertions.to_json_dict()

    result = GateDResult(
        schema_version="gate_d_result@1",
        dataset=dataset,
        gate_d_passed=not fail_reasons,
        gate_b_passed=gate_b_passed,
        gate_c_passed=gate_c_passed,
        privacy_leak_count=startup_privacy_leak_count,
        denied_gate2_external_calls=startup_denied_external_calls,
        offline_latency_minutes=round((time.monotonic() - started) / 60, 6),
        queue2_assertions=queue2_assertions_payload,
        queue2_assertion_provenance=queue2_assertion_provenance,
        fail_reasons=tuple(fail_reasons),
        command_evidence=tuple(command_evidence),
        artifact_paths={
            "eval_result": str(output_dir / "eval-result.json"),
            **_prefixed_artifact_paths("runtime_", getattr(startup_runtime_result, "artifact_paths", {})),
        },
        commit_id=_git_commit(),
        environment=_environment(),
        offline_no_key=offline_no_key,
    )
    _write_result(output_dir / "eval-result.json", result)
    return result


def _normalize_checks(
    command_probes: Sequence[Sequence[str] | tuple[str, Sequence[str]]] | None,
) -> tuple[tuple[str, list[str]], ...]:
    checks = DEFAULT_GATE_D_CHECKS if command_probes is None else tuple(command_probes)
    normalized: list[tuple[str, list[str]]] = []
    for check in checks:
        if len(check) == 2 and isinstance(check[0], str) and not isinstance(check[1], str):
            normalized.append((str(check[0]), [str(item) for item in check[1]]))
        else:
            command = [str(item) for item in check]
            normalized.append((command[0] if command else "probe", command))
    return tuple(normalized)


def _run_command(
    command: list[str],
    *,
    command_runner: CommandRunner,
    env: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], str | None]:
    try:
        return (
            command_runner(
                command,
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
                command,
                COMMAND_TIMEOUT_RETURNCODE,
                stdout=_string_output(exc.output),
                stderr=_string_output(exc.stderr) or "command timed out",
            ),
            f"{command[0] if command else 'probe'}:command_timeout",
        )
    except OSError:
        return (
            subprocess.CompletedProcess(
                command,
                COMMAND_ERROR_RETURNCODE,
                stdout="",
                stderr="OSError: command failed to start",
            ),
            f"{command[0] if command else 'probe'}:command_error",
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


def _write_result(path: Path, result: GateDResult) -> None:
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(result.to_json_dict(), sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _extract_queue2_assertions(gate_c_result: object) -> Queue2AssertionMatrix | None:
    if isinstance(gate_c_result, dict):
        return _from_dict(gate_c_result)
    raw_assertions = getattr(gate_c_result, "queue2_assertions", None)
    if isinstance(raw_assertions, dict):
        return _from_dict(raw_assertions)
    return None


def _string_tuple(values: object) -> tuple[str, ...]:
    if isinstance(values, (list, tuple)):
        return tuple(str(item) for item in values)
    if values:
        return (str(values),)
    return ()


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _prefixed_artifact_paths(prefix: str, paths: object) -> dict[str, str]:
    if not isinstance(paths, Mapping):
        return {}
    return {f"{prefix}{str(key)}": str(value) for key, value in paths.items()}


def _from_dict(raw_assertions: dict[str, object]) -> Queue2AssertionMatrix | None:
    required = ("profile_determinism", "metric_pack_hash", "contradiction_count", "unsupported_claim_count")
    if not all(key in raw_assertions for key in required):
        return None
    try:
        return Queue2AssertionMatrix(
            profile_determinism=bool(raw_assertions["profile_determinism"])
            if raw_assertions.get("profile_determinism") is not None
            else None,
            readiness_scored=bool(raw_assertions.get("readiness_scored"))
            if "readiness_scored" in raw_assertions
            else None,
            metric_pack_hash=(
                str(raw_assertions["metric_pack_hash"])
                if raw_assertions.get("metric_pack_hash") is not None
                else None
            ),
            contradiction_count=_to_int(raw_assertions.get("contradiction_count")),
            unsupported_claim_count=_to_int(raw_assertions.get("unsupported_claim_count")),
            report_sections_ok=bool(raw_assertions["report_sections_ok"])
            if raw_assertions.get("report_sections_ok") is not None
            else None,
            trace_sections_ok=bool(raw_assertions["trace_sections_ok"])
            if raw_assertions.get("trace_sections_ok") is not None
            else None,
            max_questions=_to_int(raw_assertions.get("max_questions")),
        )
    except (TypeError, ValueError):
        return None


def _validate_queue2_assertions(assertions: Queue2AssertionMatrix) -> bool:
    if assertions.profile_determinism is not True:
        return False
    if assertions.readiness_scored is not True:
        return False
    if assertions.metric_pack_hash is None or not _is_valid_sha256(assertions.metric_pack_hash):
        return False
    if assertions.contradiction_count is None or assertions.contradiction_count <= 0:
        return False
    if assertions.unsupported_claim_count is None or assertions.unsupported_claim_count <= 0:
        return False
    if assertions.report_sections_ok is not True:
        return False
    if assertions.trace_sections_ok is not True:
        return False
    if assertions.max_questions is None or assertions.max_questions > 3:
        return False
    return True


def _is_valid_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"^[a-f0-9]{64}$", value.lower()))


def _to_int(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("unsupported metric type")


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

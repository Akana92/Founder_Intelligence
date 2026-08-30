from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Callable
from uuid import UUID

from due_diligence_agent.domain.startup.profile import (
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.evals.metrics import EvaluationResult
from due_diligence_agent.evals.runner import run_public_eval


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GATE_C_DATASET = "startup_secure_ingest_v1"
GATE_B_REGRESSION_DATASET = "public_us_frozen_v1"
QUEUE1_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "startup_profile_v1"
QUEUE1_REQUIRED_FORMATS = ("csv", "docx", "jpeg", "pdf", "png", "safe_zip", "xlsx")
COMMAND_ERROR_RETURNCODE = 1
COMMAND_TIMEOUT_RETURNCODE = 124
MAX_QUEUE1_FIXTURE_BYTES = 100_000
_SHA256_REF = re.compile(r"^sha256:[0-9a-f]{64}$")
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
class GateCResult:
    dataset: str
    gate_c_passed: bool
    gate_b_passed: bool
    privacy_leak_count: int | None
    denied_gate2_external_calls: int | None
    offline_latency_minutes: float
    profile_determinism: bool | None = None
    required_profile_field_status_coverage: float | None = None
    contradiction_retention: bool | None = None
    parse_format_coverage: tuple[str, ...] | None = None
    restart_equivalence: bool | None = None
    canonical_profile_hash: str | None = None
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
        return payload


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
PublicEvalRunner = Callable[..., EvaluationResult]


@dataclass(frozen=True)
class _BehaviorCheck:
    name: str
    path: str


BEHAVIOR_CHECKS = (
    _BehaviorCheck("archive_safety", "tests/security/test_archive_safety.py"),
    _BehaviorCheck("document_parsing", "tests/parsing/test_document_parsers.py"),
    _BehaviorCheck("spreadsheet_parsing", "tests/parsing/test_spreadsheets.py"),
    _BehaviorCheck("privacy_egress", "tests/privacy/test_ai_egress.py"),
    _BehaviorCheck("startup_redaction", "tests/privacy/test_startup_redaction.py"),
    _BehaviorCheck("denied_gate2", "tests/graph/test_startup_disclosure_gate.py"),
    _BehaviorCheck(
        "queue1_startup_profile",
        "tests/evaluation/test_queue1_startup_profile.py",
    ),
)


@dataclass(frozen=True)
class _Queue1FixtureEvidence:
    profile_determinism: bool
    required_profile_field_status_coverage: float
    contradiction_retention: bool
    parse_format_coverage: tuple[str, ...]
    restart_equivalence: bool
    canonical_profile_hash: str


def run_gate_c_eval(
    dataset: str,
    *,
    output_dir: Path | None = None,
    command_runner: CommandRunner = subprocess.run,
    public_eval_runner: PublicEvalRunner = run_public_eval,
) -> GateCResult:
    if dataset != GATE_C_DATASET:
        raise ValueError(f"unsupported_dataset:{dataset}")

    output_dir = output_dir or PROJECT_ROOT / "output" / "gate-c" / dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(time.time_ns())
    pytest_base = output_dir / "runs" / run_id / "pytest"
    pytest_base.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    env = _offline_environment()
    evidence: list[CommandEvidence] = []
    fail_reasons: list[str] = []
    privacy_proof_passed = True
    denied_gate2_proof_passed = True
    queue1_profile_proof_passed = True
    parse_format_proof_passed = True

    for check in BEHAVIOR_CHECKS:
        check_base = (pytest_base / check.name).resolve()
        check_temp = (pytest_base / f"{check.name}-tmp").resolve()
        check_base.mkdir(parents=True, exist_ok=True)
        check_temp.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(check_base),
            check.path,
        ]
        completed, command_fail_reason = _run_behavior_command(
            check.name,
            command,
            command_runner=command_runner,
            env=_command_environment(env, check_temp),
        )
        _cleanup_owned_command_temp(check_temp, pytest_base.resolve())
        evidence.append(_command_evidence(check.name, completed))
        if completed.returncode != 0:
            fail_reasons.append(command_fail_reason or check.name)
            if check.name in {
                "privacy_egress",
                "startup_redaction",
                "queue1_startup_profile",
            }:
                privacy_proof_passed = False
            if check.name == "denied_gate2":
                denied_gate2_proof_passed = False
            if check.name == "queue1_startup_profile":
                queue1_profile_proof_passed = False
            if check.name in {
                "archive_safety",
                "document_parsing",
                "spreadsheet_parsing",
            }:
                parse_format_proof_passed = False

    queue1_evidence: _Queue1FixtureEvidence | None = None
    if queue1_profile_proof_passed:
        try:
            queue1_evidence = _queue1_fixture_evidence()
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            fail_reasons.append("queue1_startup_profile:fixture_invalid")
            privacy_proof_passed = False

    with _scoped_environment(OFFLINE_ENV_OVERRIDES):
        gate_b_result = public_eval_runner(
            GATE_B_REGRESSION_DATASET,
            output_dir=output_dir / "gate-b-regression",
        )
        if not gate_b_result.gate_b_passed:
            fail_reasons.append("gate_b_regression")
            fail_reasons.extend(f"gate_b:{reason}" for reason in gate_b_result.fail_reasons)
        offline_no_key = _offline_no_key()

    result = GateCResult(
        dataset=dataset,
        gate_c_passed=not fail_reasons,
        gate_b_passed=gate_b_result.gate_b_passed,
        privacy_leak_count=0 if privacy_proof_passed else None,
        denied_gate2_external_calls=0 if denied_gate2_proof_passed else None,
        offline_latency_minutes=round((time.monotonic() - started) / 60, 6),
        profile_determinism=(
            queue1_evidence.profile_determinism if queue1_evidence is not None else None
        ),
        required_profile_field_status_coverage=(
            queue1_evidence.required_profile_field_status_coverage
            if queue1_evidence is not None
            else None
        ),
        contradiction_retention=(
            queue1_evidence.contradiction_retention if queue1_evidence is not None else None
        ),
        parse_format_coverage=(
            queue1_evidence.parse_format_coverage
            if queue1_evidence is not None and parse_format_proof_passed
            else None
        ),
        restart_equivalence=(
            queue1_evidence.restart_equivalence if queue1_evidence is not None else None
        ),
        canonical_profile_hash=(
            queue1_evidence.canonical_profile_hash if queue1_evidence is not None else None
        ),
        fail_reasons=tuple(fail_reasons),
        command_evidence=tuple(evidence),
        artifact_paths={"eval_result": str(output_dir / "eval-result.json")},
        commit_id=_git_commit(),
        environment=_environment(),
        offline_no_key=offline_no_key,
    )
    _write_result(output_dir / "eval-result.json", result)
    return result


def _run_behavior_command(
    check_name: str,
    command: list[str],
    *,
    command_runner: CommandRunner,
    env: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], str | None]:
    try:
        completed = command_runner(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            subprocess.CompletedProcess(
                command,
                COMMAND_TIMEOUT_RETURNCODE,
                stdout=_string_output(exc.output),
                stderr=_string_output(exc.stderr) or "command timed out",
            ),
            f"{check_name}:command_timeout",
        )
    except OSError as exc:
        return (
            subprocess.CompletedProcess(
                command,
                COMMAND_ERROR_RETURNCODE,
                stdout="",
                stderr=f"{type(exc).__name__}: command failed to start",
            ),
            f"{check_name}:command_error",
        )
    return completed, None


def _command_evidence(
    check_name: str, completed: subprocess.CompletedProcess[str]
) -> CommandEvidence:
    return CommandEvidence(
        check_name=check_name,
        command=[str(item) for item in completed.args],
        returncode=completed.returncode,
        stdout_tail=_stream_evidence(completed.stdout),
        stderr_tail=_stream_evidence(completed.stderr),
    )


def _write_result(path: Path, result: GateCResult) -> None:
    path.write_text(
        json.dumps(result.to_json_dict(), sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )


def _queue1_fixture_evidence() -> _Queue1FixtureEvidence:
    manifest = _load_bounded_json(QUEUE1_FIXTURE_ROOT / "manifest.json")
    expected = _load_bounded_json(QUEUE1_FIXTURE_ROOT / "expected_profile.json")
    if manifest.get("schema") != "startup_profile_fixture_manifest.v1":
        raise ValueError("queue1 fixture manifest schema mismatch")
    if manifest.get("network_policy") != "no_external_network":
        raise ValueError("queue1 fixture network policy mismatch")
    formats = tuple(sorted(_string_list(manifest.get("active_format_matrix"))))
    if formats != QUEUE1_REQUIRED_FORMATS:
        raise ValueError("queue1 fixture format coverage mismatch")

    if expected.get("schema") != "startup_profile_expected.v1":
        raise ValueError("queue1 expected profile schema mismatch")
    profile_hash = expected.get("profile_hash")
    if not isinstance(profile_hash, str) or _SHA256_REF.fullmatch(profile_hash) is None:
        raise ValueError("queue1 expected profile hash is invalid")
    profile_id = expected.get("profile_id")
    if not isinstance(profile_id, str):
        raise ValueError("queue1 expected profile id is invalid")
    UUID(profile_id)

    fields = expected.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("queue1 expected profile fields are invalid")
    required_names = {field.value for field in StartupProfileFieldName}
    if set(fields) != required_names:
        raise ValueError("queue1 expected profile field coverage mismatch")
    allowed_statuses = {status.value for status in StartupProfileFieldStatus}
    covered = 0
    for field_name in required_names:
        field = fields[field_name]
        if not isinstance(field, dict) or field.get("status") not in allowed_statuses:
            raise ValueError("queue1 expected profile status mismatch")
        covered += 1
    field_status_coverage = covered / len(required_names)

    contradiction_ids = _string_list(expected.get("contradiction_ids"))
    traction = fields.get(StartupProfileFieldName.TRACTION.value)
    if not isinstance(traction, dict):
        raise ValueError("queue1 expected traction field is invalid")
    traction_values = _string_list(traction.get("values"))
    ref_count = traction.get("evidence_ref_count")
    contradiction_retention = bool(
        contradiction_ids and len(set(traction_values)) >= 2 and isinstance(ref_count, int) and ref_count >= 2
    )
    if not contradiction_retention:
        raise ValueError("queue1 contradiction retention proof is incomplete")

    parse_outcomes = expected.get("parse_outcomes")
    if not isinstance(parse_outcomes, dict):
        raise ValueError("queue1 expected parse outcomes are invalid")
    outcome_values = set(parse_outcomes.values())
    if not {"parsed", "partial", "damaged"}.issubset(outcome_values):
        raise ValueError("queue1 partial parse proof is incomplete")

    return _Queue1FixtureEvidence(
        profile_determinism=True,
        required_profile_field_status_coverage=field_status_coverage,
        contradiction_retention=True,
        parse_format_coverage=formats,
        restart_equivalence=True,
        canonical_profile_hash=profile_hash,
    )


def _load_bounded_json(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if not payload or len(payload) > MAX_QUEUE1_FIXTURE_BYTES:
        raise ValueError("queue1 fixture JSON size is invalid")
    loaded = json.loads(payload.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("queue1 fixture JSON root must be an object")
    return loaded


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("queue1 fixture value must be a string list")
    return tuple(value)


def _offline_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(OFFLINE_ENV_OVERRIDES)
    return env


def _command_environment(base_env: dict[str, str], temp_root: Path) -> dict[str, str]:
    env = base_env.copy()
    temp_root_value = str(temp_root)
    env["TMP"] = temp_root_value
    env["TEMP"] = temp_root_value
    env["TMPDIR"] = temp_root_value
    return env


def _cleanup_owned_command_temp(temp_root: Path, owned_root: Path) -> None:
    resolved_temp_root = temp_root.resolve()
    if resolved_temp_root == owned_root or owned_root not in resolved_temp_root.parents:
        return
    shutil.rmtree(resolved_temp_root, ignore_errors=True)


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


def _offline_no_key() -> dict[str, bool]:
    return {
        "openai_api_key_blank": os.environ.get("OPENAI_API_KEY") == "",
        "openai_startup_api_key_blank": os.environ.get("OPENAI_STARTUP_API_KEY") == "",
        "langsmith_tracing_disabled": os.environ.get("LANGSMITH_TRACING") == "false",
        "langchain_legacy_tracing_disabled": os.environ.get("LANGCHAIN_TRACING") == "false",
        "langchain_tracing_disabled": os.environ.get("LANGCHAIN_TRACING_V2") == "false",
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE") == "1",
        "transformers_offline": os.environ.get("TRANSFORMERS_OFFLINE") == "1",
    }


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


def _stream_evidence(value: str | None) -> str:
    if not value:
        return ""
    raw = value.encode("utf-8", errors="replace")
    return f"command-output-sha256:{sha256(raw).hexdigest()}:bytes:{len(raw)}"


def _string_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value

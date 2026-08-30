from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import TextIO

from due_diligence_agent.evals.output_root import (
    EVALUATION_OUTPUT_ERROR_CODES,
    prepare_evaluation_output_root,
)


SCHEMA_VERSION = "queue5_failure_matrix@1"
MATRIX_FILENAME = "failure-matrix.json"
STDOUT_FILENAME = "failure-matrix.pytest.stdout.log"
STDERR_FILENAME = "failure-matrix.pytest.stderr.log"
PYTEST_TIMEOUT_SECONDS = 300
_COMMIT_RE = re.compile(r"[a-f0-9]{40}\Z", re.IGNORECASE)

_PROOF_TESTS = (
    "tests/api/test_startup_api.py::test_startup_api_dependency_keeps_live_provider_unavailable_without_openai_key",
    "tests/unit/application/test_startup_live_research_policy.py::test_web_outage_yields_partial_result_without_inventing_competitors",
    "tests/unit/application/test_startup_live_research_policy.py::test_provider_unavailable_maps_to_stable_outage_code_without_provider_text",
    "tests/graph/test_startup_workflow.py::test_retry_policy_retries_typed_transient_failures_at_most_three_times",
    "tests/graph/test_startup_workflow.py::test_provider_outage_replans_with_local_market_fallback_and_reaches_gate4_report_path",
    "tests/graph/test_startup_workflow.py::test_budget_exhaustion_replans_to_local_evidence_before_over_budget_provider_call",
    "tests/graph/test_startup_workflow.py::test_budget_exhaustion_restart_resumes_gate4_after_fallback_without_extra_calls",
    "tests/e2e/test_public_report.py::test_reportlab_fallback_preserves_snapshot_identity",
    "tests/api/test_startup_api.py::test_startup_api_renderer_failure_is_typed_503_after_gate4_approval",
    "tests/graph/test_startup_workflow.py::test_checkpoint_can_resume_after_process_restart_without_repeating_ingest_or_parse",
    "tests/graph/test_startup_workflow.py::test_startup_checkpoint_state_is_id_only_and_never_serializes_raw_payload",
    "tests/graph/test_startup_workflow.py::test_report_adapter_binds_stable_checkpoint_ids_from_latest_case_run",
    "tests/unit/observability/test_exporter_fallback.py::test_exporter_failure_spools_sanitized_event_without_failing_workflow",
)

_REQUIRED_ROWS = (
    {
        "id": "provider_unavailable_no_key",
        "category": "provider_unavailable",
        "expected_behavior": "Live startup provider remains unavailable when provider keys are blank.",
        "proof_tests": (_PROOF_TESTS[0], _PROOF_TESTS[2]),
    },
    {
        "id": "external_source_outage_partial",
        "category": "external_source_outage",
        "expected_behavior": "External-source outage yields a typed partial result without invented competitors.",
        "proof_tests": (_PROOF_TESTS[1], _PROOF_TESTS[2]),
    },
    {
        "id": "typed_retry_bounded",
        "category": "retry",
        "expected_behavior": "Typed transient failures retry at most three attempts with trace evidence.",
        "proof_tests": (_PROOF_TESTS[3],),
    },
    {
        "id": "provider_outage_graph_replan",
        "category": "provider_outage_replanning",
        "expected_behavior": "Typed provider outage exhausts bounded retries, records a sanitized partial result, replans to cached local market evidence, and reaches same-case Gate 3, Gate 4, and report completion.",
        "proof_tests": (_PROOF_TESTS[4],),
    },
    {
        "id": "budget_exhaustion_local_fallback_restart",
        "category": "budget_exhaustion",
        "expected_behavior": "Budget exhaustion prevents the over-budget provider call, replans to cached local evidence, and resumes the same Gate 4 checkpoint after restart without replaying provider calls.",
        "proof_tests": (_PROOF_TESTS[5], _PROOF_TESTS[6]),
    },
    {
        "id": "report_renderer_fallback",
        "category": "renderer_fallback",
        "expected_behavior": "ReportLab fallback preserves snapshot identity and renderer outage remains a typed API failure.",
        "proof_tests": (_PROOF_TESTS[7], _PROOF_TESTS[8]),
    },
)

_SUPPORTING_VALIDATIONS = (
    {
        "id": "checkpoint_restart",
        "proof_tests": (_PROOF_TESTS[9],),
    },
    {
        "id": "checkpoint_privacy",
        "proof_tests": (_PROOF_TESTS[10],),
    },
    {
        "id": "report_trace_lineage",
        "proof_tests": (_PROOF_TESTS[11],),
    },
    {
        "id": "exporter_fallback_privacy",
        "proof_tests": (_PROOF_TESTS[12],),
    },
)


@dataclass(frozen=True)
class Queue5FailureMatrix:
    schema_version: str
    commit_id: str
    offline_no_live_calls: bool
    live_provider_smoke_status: str
    matrix_passed: bool
    matrix_hash: str
    rows: tuple[dict[str, object], ...]
    supporting_validations: tuple[dict[str, object], ...]
    command_evidence: dict[str, object]
    artifact_paths: dict[str, str]
    artifact_hashes: dict[str, str]
    fail_reasons: tuple[str, ...]

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["rows"] = list(self.rows)
        payload["supporting_validations"] = list(self.supporting_validations)
        payload["fail_reasons"] = list(self.fail_reasons)
        return payload


def run_queue5_failure_matrix(output_dir: Path, *, commit_id: str) -> Queue5FailureMatrix:
    if _COMMIT_RE.fullmatch(commit_id) is None:
        raise ValueError("failure_matrix_commit_id_invalid")
    output_root = prepare_evaluation_output_root(output_dir)
    stdout_path = output_root / STDOUT_FILENAME
    stderr_path = output_root / STDERR_FILENAME
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *_PROOF_TESTS,
    ]
    child_env = os.environ.copy()
    child_env.update(
        {
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
    )
    project_root = Path(__file__).resolve().parents[3]
    with (
        stdout_path.open("w", encoding="utf-8", newline="\n") as stdout_stream,
        stderr_path.open("w", encoding="utf-8", newline="\n") as stderr_stream,
    ):
        try:
            completed = subprocess.run(
                command,
                cwd=project_root,
                env=child_env,
                stdout=stdout_stream,
                stderr=stderr_stream,
                text=True,
                check=False,
                timeout=PYTEST_TIMEOUT_SECONDS,
            )
            exit_code: int | str = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            exit_code = "timeout"
            timed_out = True
            _write_timeout_evidence(stderr_stream, exc)

    passed = exit_code == 0
    status = "pass" if passed else "fail"
    proof_fail_reason = "proof_command_timeout" if timed_out else "proof_command_failed"
    rows = tuple(
        {
            **template,
            "proof_tests": list(template["proof_tests"]),
            "status": status,
            "live_calls_made": 0,
            "fail_reasons": [] if passed else [proof_fail_reason],
        }
        for template in _REQUIRED_ROWS
    )
    supporting = tuple(
        {
            **template,
            "proof_tests": list(template["proof_tests"]),
            "status": status,
        }
        for template in _SUPPORTING_VALIDATIONS
    )
    fail_reasons = (
        ()
        if passed
        else ("failure_matrix_pytest_timeout",)
        if timed_out
        else ("failure_matrix_pytest_failed",)
    )
    artifact_paths = {
        "failure_matrix": MATRIX_FILENAME,
        "pytest_stdout": STDOUT_FILENAME,
        "pytest_stderr": STDERR_FILENAME,
    }
    artifact_hashes = {
        "pytest_stdout": _hash_file(stdout_path),
        "pytest_stderr": _hash_file(stderr_path),
    }
    public_payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "commit_id": commit_id,
        "offline_no_live_calls": True,
        "live_provider_smoke_status": "deferred_by_policy",
        "matrix_passed": passed,
        "matrix_hash": "",
        "rows": list(rows),
        "supporting_validations": list(supporting),
        "command_evidence": {
            "command_id": "queue5_failure_matrix_pytest",
            "proof_tests": list(_PROOF_TESTS),
            "exit_code": exit_code,
            "timeout_seconds": PYTEST_TIMEOUT_SECONDS,
            "timed_out": timed_out,
            "stdout_log": STDOUT_FILENAME,
            "stderr_log": STDERR_FILENAME,
        },
        "artifact_paths": artifact_paths,
        "artifact_hashes": artifact_hashes,
        "fail_reasons": list(fail_reasons),
    }
    public_payload["matrix_hash"] = calculate_queue5_failure_matrix_hash(public_payload)
    matrix_path = output_root / MATRIX_FILENAME
    _write_json(matrix_path, public_payload)
    return _matrix_from_payload(public_payload)


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def calculate_queue5_failure_matrix_hash(payload: Mapping[str, object]) -> str:
    return _matrix_hash(payload)


def validate_queue5_failure_matrix_payload(
    payload: Mapping[str, object],
) -> tuple[bool, tuple[str, ...]]:
    fail_reasons: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        fail_reasons.append("failure_matrix_schema_invalid")
    if _COMMIT_RE.fullmatch(str(payload.get("commit_id") or "")) is None:
        fail_reasons.append("failure_matrix_commit_id_invalid")
    if payload.get("offline_no_live_calls") is not True:
        fail_reasons.append("failure_matrix_live_calls_not_excluded")
    if payload.get("live_provider_smoke_status") != "deferred_by_policy":
        fail_reasons.append("failure_matrix_live_smoke_status_invalid")
    if payload.get("matrix_passed") is not True:
        fail_reasons.append("failure_matrix_not_passed")
    if _string_tuple(payload.get("fail_reasons")):
        fail_reasons.append("failure_matrix_fail_reasons_present")

    command_evidence = _object_mapping(payload.get("command_evidence"))
    if (
        command_evidence.get("command_id") != "queue5_failure_matrix_pytest"
        or command_evidence.get("exit_code") != 0
        or command_evidence.get("timed_out") is not False
        or _string_tuple(command_evidence.get("proof_tests")) != _PROOF_TESTS
    ):
        fail_reasons.append("failure_matrix_command_evidence_invalid")

    rows_by_id = {
        str(row.get("id") or ""): row for row in _mapping_tuple(payload.get("rows"))
    }
    for expected in _REQUIRED_ROWS:
        row = rows_by_id.get(str(expected["id"]))
        if row is None:
            fail_reasons.append("failure_matrix_required_row_missing")
            continue
        if (
            row.get("category") != expected["category"]
            or row.get("status") != "pass"
            or row.get("live_calls_made") != 0
            or _string_tuple(row.get("fail_reasons"))
            or _string_tuple(row.get("proof_tests")) != expected["proof_tests"]
        ):
            fail_reasons.append("failure_matrix_required_row_invalid")

    supporting_by_id = {
        str(item.get("id") or ""): item
        for item in _mapping_tuple(payload.get("supporting_validations"))
    }
    for expected in _SUPPORTING_VALIDATIONS:
        item = supporting_by_id.get(str(expected["id"]))
        if item is None:
            fail_reasons.append("failure_matrix_supporting_validation_missing")
            continue
        if item.get("status") != "pass" or _string_tuple(item.get("proof_tests")) != expected[
            "proof_tests"
        ]:
            fail_reasons.append("failure_matrix_supporting_validation_invalid")

    if payload.get("matrix_hash") != calculate_queue5_failure_matrix_hash(payload):
        fail_reasons.append("failure_matrix_hash_mismatch")

    return (not fail_reasons, tuple(dict.fromkeys(fail_reasons)))


def _write_timeout_evidence(stderr_stream: TextIO, exc: subprocess.TimeoutExpired) -> None:
    stderr_stream.write("\nfailure_matrix_pytest_timeout\n")
    stderr_stream.write(f"timeout_seconds={PYTEST_TIMEOUT_SECONDS}\n")
    stdout_text = _timeout_fragment(exc.output)
    stderr_text = _timeout_fragment(exc.stderr)
    if stdout_text:
        stderr_stream.write(f"timeout_stdout={stdout_text}\n")
    if stderr_text:
        stderr_stream.write(f"timeout_stderr={stderr_text}\n")


def _timeout_fragment(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value
    return text.replace("\r", "\\r").replace("\n", "\\n")[:500]


def _matrix_hash(payload: Mapping[str, object]) -> str:
    canonical = {
        str(key): value
        for key, value in payload.items()
        if key not in {"artifact_hashes", "matrix_hash"}
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _matrix_from_payload(payload: Mapping[str, object]) -> Queue5FailureMatrix:
    return Queue5FailureMatrix(
        schema_version=str(payload["schema_version"]),
        commit_id=str(payload["commit_id"]),
        offline_no_live_calls=payload.get("offline_no_live_calls") is True,
        live_provider_smoke_status=str(payload["live_provider_smoke_status"]),
        matrix_passed=payload.get("matrix_passed") is True,
        matrix_hash=str(payload["matrix_hash"]),
        rows=_mapping_tuple(payload.get("rows")),
        supporting_validations=_mapping_tuple(payload.get("supporting_validations")),
        command_evidence=_object_mapping(payload.get("command_evidence")),
        artifact_paths=_string_mapping(payload.get("artifact_paths")),
        artifact_hashes=_string_mapping(payload.get("artifact_hashes")),
        fail_reasons=_string_tuple(payload.get("fail_reasons")),
    )


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_mapping(value: object) -> dict[str, str]:
    return {key: str(item) for key, item in _object_mapping(value).items()}


def _mapping_tuple(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_object_mapping(item) for item in value if isinstance(item, Mapping))


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="queue5-failure-matrix")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--commit-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_queue5_failure_matrix(Path(args.output_dir), commit_id=str(args.commit_id))
    except ValueError as exc:
        if str(exc) in EVALUATION_OUTPUT_ERROR_CODES:
            print(str(exc), file=sys.stderr)
            return 2
        raise
    print(json.dumps(result.to_json_dict(), sort_keys=True))
    return 0 if result.matrix_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

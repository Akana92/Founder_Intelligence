from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import socket
from typing import Any, Iterator, cast
from unittest.mock import patch
import urllib.request

from starlette.testclient import TestClient

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.startup_cases import StartupCaseCoordinator
from due_diligence_agent.bootstrap import container
from due_diligence_agent.evals.startup_fixture_contract import (
    validate_startup_fixture_contract,
)
from due_diligence_agent.presentation.api.app import create_app
from due_diligence_agent.presentation.api.dependencies import get_startup_case_coordinator
from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STARTUP_SYNTHETIC_DATASET = "startup_synthetic_v1"
STARTUP_SYNTHETIC_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / STARTUP_SYNTHETIC_DATASET
OFFLINE_ENV_OVERRIDES: dict[str, str] = {
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
REQUIRED_RUNTIME_NODES: frozenset[str] = frozenset(
    {
        "ingest",
        "parse",
        "classify_redact",
        "evidence",
        "claims",
        "primary_profile",
        "disclosure",
        "plan",
        "profile_enrichment",
        "market_research",
        "metrics",
        "financial_analysis",
        "risk_analysis",
        "market_analysis",
        "critic",
        "arbiter",
        "report",
        "gate4",
    }
)
REQUIRED_REPORT_SECTIONS: frozenset[str] = frozenset(
    {
        "business_idea_summary",
        "problem_solution",
        "market_size",
        "competitors",
        "metrics",
        "risks",
        "evidence_gaps",
        "diligence_questions",
        "methodology",
        "source_appendix",
    }
)
SENSITIVE_VALUE_RE = re.compile(
    r"(?i)([A-Z]:\\|/Users/|/home/|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])|"
    r"\bbearer[\s_-]+\S+|\bapi[_ -]?key\b|\bsecret\b)"
)
FORMULA_VERSION_RE = re.compile(r"^[a-z][a-z0-9_.-]*@\d+$", re.IGNORECASE)
UUID_TOKEN_RE = re.compile(
    r"(?<![0-9a-f])(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}|[0-9a-f]{32})(?![0-9a-f])",
    re.IGNORECASE,
)
VOLATILE_HASH_ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:report|profile|case_snapshot|readiness_snapshot|supporting|"
    r"market_research_snapshot|snapshot|pack)_hash)=(?:sha256:)?[0-9a-f]{64}\b"
)
STANDALONE_SHA256_RE = re.compile(r"(?i)\bsha256:[0-9a-f]{64}\b")
DOCUMENT_TEXT_BLOCK_ID_RE = re.compile(r"\bdocument_text_block_\d+\b")
STARTUP_TRACE_ID_RE = re.compile(r"\b(startup-[a-z_]+)-[0-9a-f]{12}\b")
RUNTIME_REF_ASSIGNMENT_RE = re.compile(
    r"\b((?:evidence|claim|contradiction|dimension|snapshot|fact|finding|calculation)_refs?)="
    r"[0-9a-f,-]+",
    re.IGNORECASE,
)
PROFILE_CONTRADICTION_RE = re.compile(
    r"\b(profile_contradiction):[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
ALLOWED_METRIC_LINEAGE_PREFIXES: tuple[str, ...] = (
    "evidence_ref=",
    "supporting_hash=",
    "snapshot_hash=",
    "calculation_ref=",
    "dimension_ref=",
)
VOLATILE_TIMESTAMP_KEYS: frozenset[str] = frozenset(
    {"built_at", "created_at", "generated_at", "timestamp_utc", "updated_at"}
)
ORDER_INDEPENDENT_DISCLOSURE_SET_KEYS: frozenset[str] = frozenset(
    {
        "allowed_classes",
        "detected_classes",
        "minimized_fragment_refs",
        "redaction_policy_versions",
    }
)


@dataclass(frozen=True)
class StartupFrozenRuntimeCaseEvidence:
    case_name: str
    evidence_source: str
    uploaded_document_count: int
    provider_status: str
    gate2_status: str
    gate3_status: str
    gate4_status: str
    report_status: str
    report_json_status: int
    report_html_status: int
    report_pdf_status: int
    report_hash: str
    profile_hash: str
    readiness_snapshot_hash: str
    market_research_snapshot_hash: str
    metric_pack_hash: str
    readiness_question_count: int
    metric_count: int
    metric_formula_source_count: int
    contradiction_count: int
    unsupported_claim_count: int
    competitor_count: int
    competitor_source_ref_count: int
    source_appendix_hash_count: int
    runtime_trace_event_count: int
    runtime_node_count: int
    runtime_nodes_hash: str
    trace_to_report_lineage: bool
    semantic_fingerprint: str
    persisted_hash_fingerprint: str
    competitor_sources_resolved: bool
    competitor_sources_with_as_of: int
    privacy_leak_count: int
    semantic_fingerprint_match: bool | None = None
    persisted_hash_fingerprint_match: bool | None = None
    fail_reasons: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["fail_reasons"] = list(self.fail_reasons)
        return payload


@dataclass(frozen=True)
class StartupFrozenRuntimeResult:
    schema_version: str
    dataset: str
    queue2_runtime_passed: bool
    queue2_assertion_provenance: str
    case_count: int
    privacy_leak_count: int
    denied_gate2_external_calls: int
    queue2_assertions: dict[str, object]
    fail_reasons: tuple[str, ...] = ()
    cases: tuple[StartupFrozenRuntimeCaseEvidence, ...] = ()
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["fail_reasons"] = list(self.fail_reasons)
        payload["cases"] = [case.to_json_dict() for case in self.cases]
        payload["queue2_assertions"] = dict(self.queue2_assertions)
        return payload


def run_startup_frozen_runtime_eval(
    dataset: str,
    *,
    output_dir: Path | None = None,
    repeat_determinism: bool = True,
) -> StartupFrozenRuntimeResult:
    if dataset != STARTUP_SYNTHETIC_DATASET:
        raise ValueError(f"unsupported_dataset:{dataset}")

    case_names = validate_startup_fixture_contract(
        STARTUP_SYNTHETIC_FIXTURE_ROOT,
        dataset=dataset,
    )
    output_dir = output_dir or PROJECT_ROOT / "output" / "gate-d" / dataset / "runtime"
    output_dir.mkdir(parents=True, exist_ok=True)

    with _scoped_environment(OFFLINE_ENV_OVERRIDES), _OutboundGuard() as outbound_guard:
        first_run = _run_all_cases(
            fixture_root=STARTUP_SYNTHETIC_FIXTURE_ROOT,
            case_names=case_names,
            runtime_root=output_dir / "runtime-a",
        )
        second_run_by_case: dict[str, StartupFrozenRuntimeCaseEvidence] = {}
        if repeat_determinism:
            second_run = _run_all_cases(
                fixture_root=STARTUP_SYNTHETIC_FIXTURE_ROOT,
                case_names=case_names,
                runtime_root=output_dir / "runtime-b",
            )
            second_run_by_case = {case.case_name: case for case in second_run}
        denied_gate2_external_calls = outbound_guard.violation_count

    cases: list[StartupFrozenRuntimeCaseEvidence] = []
    for case in first_run:
        repeated = second_run_by_case.get(case.case_name)
        cases.append(
            case
            if repeated is None
            else _replace_case(
                case,
                semantic_fingerprint_match=case.semantic_fingerprint
                == repeated.semantic_fingerprint,
                persisted_hash_fingerprint_match=case.persisted_hash_fingerprint
                == repeated.persisted_hash_fingerprint,
            )
        )

    case_fail_reasons = [
        f"{case.case_name}:{reason}" for case in cases for reason in case.fail_reasons
    ]
    aggregate = _queue2_assertions(cases)
    fail_reasons = [
        *case_fail_reasons,
        *_aggregate_fail_reasons(cases=cases, assertions=aggregate),
    ]
    privacy_leak_count = sum(case.privacy_leak_count for case in cases)
    if privacy_leak_count:
        fail_reasons.append("privacy_leaks_detected")
    if denied_gate2_external_calls:
        fail_reasons.append("external_calls_denied")

    artifact_path = output_dir / "runtime-evidence.json"
    result = StartupFrozenRuntimeResult(
        schema_version="startup_frozen_runtime_result@1",
        dataset=dataset,
        queue2_runtime_passed=not fail_reasons,
        queue2_assertion_provenance=f"runtime_api:{dataset}",
        case_count=len(cases),
        privacy_leak_count=privacy_leak_count,
        denied_gate2_external_calls=denied_gate2_external_calls,
        queue2_assertions=aggregate,
        fail_reasons=tuple(fail_reasons),
        cases=tuple(cases),
        artifact_paths={"runtime_evidence": _display_path(artifact_path)},
    )
    _write_result(artifact_path, result)
    artifact_privacy_leak_count = _privacy_leak_count(artifact_path.read_text(encoding="utf-8"))
    if artifact_privacy_leak_count:
        updated_fail_reasons = (*result.fail_reasons, "final_artifact_privacy_leaks_detected")
        result = replace(
            result,
            queue2_runtime_passed=False,
            privacy_leak_count=result.privacy_leak_count + artifact_privacy_leak_count,
            fail_reasons=updated_fail_reasons,
        )
        _write_result(artifact_path, result)
    return result


def _run_all_cases(
    *,
    fixture_root: Path,
    case_names: tuple[str, ...],
    runtime_root: Path,
) -> tuple[StartupFrozenRuntimeCaseEvidence, ...]:
    coordinator = _build_runtime_coordinator(runtime_root)
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    return tuple(
        _run_case(
            client=client,
            coordinator=coordinator,
            fixture_root=fixture_root,
            runtime_root=runtime_root,
            case_name=case_name,
        )
        for case_name in case_names
    )


def _run_case(
    *,
    client: TestClient,
    coordinator: StartupCaseCoordinator,
    fixture_root: Path,
    runtime_root: Path,
    case_name: str,
) -> StartupFrozenRuntimeCaseEvidence:
    fail_reasons: list[str] = []
    created = client.post(
        "/api/v1/startup/cases",
        json={
            "fixture_mode": "deterministic_offline",
            "auto_start": False,
            "company_name": case_name,
        },
    )
    if created.status_code != 201:
        return _failed_case(case_name, f"create_case_http_{created.status_code}")
    case_id = str(created.json()["case_id"])

    files = _multipart_files(fixture_root / "cases" / case_name)
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true", "company_name": case_name, "as_of": "2026-08-13"},
        files=files,
    )
    if uploaded.status_code != 200:
        return _failed_case(case_name, f"upload_http_{uploaded.status_code}")
    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    if preview.status_code != 200:
        return _failed_case(case_name, f"gate2_preview_http_{preview.status_code}")
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    if gate2.status_code != 200:
        return _failed_case(case_name, f"gate2_decision_http_{gate2.status_code}")
    gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    if gate3.status_code != 200:
        return _failed_case(case_name, f"gate3_decision_http_{gate3.status_code}")

    report_json_response = client.get(f"/api/v1/startup/cases/{case_id}/report/json")
    public_report_json: dict[str, Any] = {}
    if report_json_response.status_code == 200:
        public_report_json = cast(dict[str, Any], report_json_response.json())
    else:
        fail_reasons.append(f"report_json_http_{report_json_response.status_code}")

    report_json = _canonical_report_json_for_eval(
        coordinator=coordinator,
        runtime_root=runtime_root,
        case_id=case_id,
        fallback=public_report_json,
    )

    snapshot_hash = _as_str(gate3.json().get("snapshot_hash"))
    snapshot_revision = gate3.json().get("snapshot_revision")
    if snapshot_hash is None or not isinstance(snapshot_revision, int):
        fail_reasons.append("gate3_snapshot_tuple_missing")
        gate4_status = "not_ready"
    else:
        gate4 = client.post(
            f"/api/v1/startup/cases/{case_id}/gate4/decision",
            json={
                "decision": "approved",
                "snapshot_hash": snapshot_hash,
                "snapshot_revision": snapshot_revision,
            },
        )
        gate4_status = _as_str(gate4.json().get("gate4_status")) or f"http_{gate4.status_code}"
        if gate4.status_code != 200:
            fail_reasons.append(f"gate4_decision_http_{gate4.status_code}")

    report_html_response = client.get(f"/api/v1/startup/cases/{case_id}/report/html")
    report_pdf_response = client.get(f"/api/v1/startup/cases/{case_id}/report/pdf")

    runtime = _read_runtime_payload(runtime_root / "deterministic" / "startup-runtime.sqlite3", case_id)
    runtime_nodes = _runtime_nodes(runtime)
    runtime_node_names = {str(node.get("node_name")) for node in runtime_nodes}
    if not REQUIRED_RUNTIME_NODES <= runtime_node_names:
        fail_reasons.append("runtime_nodes_missing")
    sections = cast(dict[str, Any], report_json.get("sections") or {})
    if not REQUIRED_REPORT_SECTIONS <= set(sections):
        fail_reasons.append("report_sections_missing")

    readiness_artifact = cast(dict[str, Any], runtime.get("startup_readiness_artifact") or {})
    market_artifact = cast(dict[str, Any], runtime.get("startup_market_research_artifact") or {})
    readiness_snapshot = cast(dict[str, Any], readiness_artifact.get("snapshot") or {})
    market_snapshot = cast(dict[str, Any], market_artifact.get("snapshot") or {})
    metric_pack = cast(dict[str, Any], readiness_snapshot.get("metric_pack") or {})
    adaptive_questions = _list(metric_pack.get("adaptive_questions"))
    metric_ids = [str(item) for item in _list(metric_pack.get("metric_ids"))]
    competitors = _list(market_snapshot.get("competitors"))
    market_sources = _market_sources_by_id(market_snapshot)
    competitor_source_ids = {
        str(source_id)
        for item in competitors
        if isinstance(item, dict)
        for source_id in _list(cast(dict[str, Any], item).get("source_ids"))
    }
    competitor_source_ref_count = len(competitor_source_ids)
    competitor_sources_resolved = all(source_id in market_sources for source_id in competitor_source_ids)
    competitor_sources_with_as_of = sum(
        1
        for source_id in competitor_source_ids
        if _as_str(market_sources.get(source_id, {}).get("as_of")) is not None
    )
    if competitor_source_ids and not competitor_sources_resolved:
        fail_reasons.append("competitor_source_id_unresolved")
    if competitor_sources_with_as_of != competitor_source_ref_count:
        fail_reasons.append("competitor_source_as_of_missing")
    source_rows = _section_rows(sections, "source_appendix")
    metric_rows = _section_rows(sections, "metrics")
    contradiction_count = len(_list(runtime.get("contradiction_ids")))
    unsupported_claim_count = _unsupported_claim_count(runtime)
    if contradiction_count == 0:
        fail_reasons.append("contradiction_runtime_evidence_missing")
    if unsupported_claim_count == 0:
        fail_reasons.append("unsupported_claim_runtime_evidence_missing")

    trace_event_count = _trace_event_count(runtime_root / "deterministic" / "startup-audit-spool", case_id)
    if trace_event_count == 0:
        fail_reasons.append("runtime_trace_events_missing")

    status = client.get(f"/api/v1/startup/cases/{case_id}").json()
    profile_hash = _as_str(runtime.get("profile_hash")) or "MISSING"
    readiness_hash = _as_str(readiness_snapshot.get("snapshot_hash")) or "MISSING"
    market_hash = _as_str(market_snapshot.get("snapshot_hash")) or "MISSING"
    metric_pack_hash = _as_str(metric_pack.get("pack_hash")) or "MISSING"
    report_hash = _as_str(status.get("snapshot_hash")) or "MISSING"
    trace_to_report_lineage = (
        "report" in runtime_node_names
        and readiness_hash == _as_str(runtime.get("report_readiness_snapshot_hash"))
        and market_hash == _as_str(runtime.get("report_market_research_snapshot_hash"))
        and report_hash != "MISSING"
    )
    if not trace_to_report_lineage:
        fail_reasons.append("trace_to_report_lineage_missing")

    audit_text = _audit_text(runtime_root / "deterministic" / "startup-audit-spool", case_id)
    runtime_text = json.dumps(runtime, sort_keys=True, ensure_ascii=False, default=str)
    privacy_leak_count = _privacy_leak_count(
        "\n".join(
            (
                json.dumps(public_report_json, sort_keys=True, ensure_ascii=False, default=str),
                report_html_response.text,
                runtime_text,
                audit_text,
            )
        )
    )
    if privacy_leak_count:
        fail_reasons.append("case_privacy_leaks_detected")
    metric_formula_source_count = _metric_formula_source_count(
        metric_rows,
        metric_ids=metric_ids,
    )
    if metric_formula_source_count != len(metric_ids):
        fail_reasons.append("metric_formula_source_evidence_missing")
    persisted_hash_fingerprint = _persisted_semantic_fingerprint(
        report_json=report_json,
        runtime=runtime,
    )

    return StartupFrozenRuntimeCaseEvidence(
        case_name=case_name,
        evidence_source="runtime_api",
        uploaded_document_count=len(_list(uploaded.json().get("accepted_document_ids"))),
        provider_status=_as_str(status.get("provider_status")) or "MISSING",
        gate2_status=_as_str(status.get("gate2_status")) or "MISSING",
        gate3_status=_as_str(status.get("gate3_status")) or "MISSING",
        gate4_status=gate4_status,
        report_status=_as_str(status.get("report_status")) or "MISSING",
        report_json_status=report_json_response.status_code,
        report_html_status=report_html_response.status_code,
        report_pdf_status=report_pdf_response.status_code,
        report_hash=report_hash,
        profile_hash=profile_hash,
        readiness_snapshot_hash=readiness_hash,
        market_research_snapshot_hash=market_hash,
        metric_pack_hash=metric_pack_hash,
        readiness_question_count=len(adaptive_questions),
        metric_count=len(metric_ids),
        metric_formula_source_count=metric_formula_source_count,
        contradiction_count=contradiction_count,
        unsupported_claim_count=unsupported_claim_count,
        competitor_count=len(competitors),
        competitor_source_ref_count=competitor_source_ref_count,
        source_appendix_hash_count=_source_appendix_hash_count(source_rows),
        runtime_trace_event_count=trace_event_count,
        runtime_node_count=len(runtime_nodes),
        runtime_nodes_hash=_hash_json(sorted(runtime_node_names)),
        trace_to_report_lineage=trace_to_report_lineage,
        semantic_fingerprint=_semantic_fingerprint(
            case_name=case_name,
            report_json=report_json,
            runtime=runtime,
            runtime_node_names=runtime_node_names,
        ),
        persisted_hash_fingerprint=persisted_hash_fingerprint,
        competitor_sources_resolved=competitor_sources_resolved,
        competitor_sources_with_as_of=competitor_sources_with_as_of,
        privacy_leak_count=privacy_leak_count,
        fail_reasons=tuple(fail_reasons),
    )


def _build_runtime_coordinator(runtime_root: Path) -> StartupCaseCoordinator:
    data_dir = runtime_root
    deterministic_data_dir = data_dir / "deterministic"
    inbox_root = data_dir / "inbox"
    revision_port_factory = getattr(container, "build_startup_case_revision_port")
    profile_port_factory = getattr(container, "build_startup_profile_query_port")
    return StartupCaseCoordinator(
        analysis_service=container.build_startup_analysis_composer(data_dir),
        deterministic_analysis_service=container.build_deterministic_startup_analysis_composer(
            deterministic_data_dir,
            inbox_root=inbox_root,
        ),
        report_port=container.build_startup_report_port(data_dir),
        deterministic_report_port=container.build_startup_report_port(deterministic_data_dir),
        profile_port=profile_port_factory(data_dir),
        deterministic_profile_port=profile_port_factory(deterministic_data_dir),
        case_revision_port=revision_port_factory(data_dir),
        deterministic_case_revision_port=revision_port_factory(deterministic_data_dir),
        audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
        deterministic_audit_spool=JsonlAuditSpool(
            deterministic_data_dir / "startup-audit-spool"
        ),
        workflow_store=SQLiteStartupWorkflowRuntimeStore(data_dir / "startup-runtime.sqlite3"),
        inbox_root=inbox_root,
        live_provider_configured=False,
    )


def _multipart_files(case_dir: Path) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", (path.name, path.read_bytes(), "application/octet-stream"))
        for path in sorted(case_dir.iterdir())
        if path.is_file()
    ]


def _read_runtime_payload(sqlite_path: Path, case_id: str) -> dict[str, Any]:
    with sqlite3.connect(sqlite_path) as connection:
        row = connection.execute(
            "select payload from startup_workflow_runtime where case_id = ?",
            (case_id,),
        ).fetchone()
    if row is None:
        return {}
    payload = json.loads(str(row[0]))
    return payload if isinstance(payload, dict) else {}


def _canonical_report_json_for_eval(
    *,
    coordinator: object,
    runtime_root: Path,
    case_id: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Read canonical audit data without exposing it through the founder API."""

    del runtime_root
    report_port = getattr(coordinator, "_deterministic_report_port", None)
    if report_port is None:
        report_port = getattr(coordinator, "_report_port", None)
    canonical_json_bytes = getattr(report_port, "canonical_json_bytes", None)
    if not callable(canonical_json_bytes):
        return fallback
    try:
        payload = canonical_json_bytes(case_id)
        decoded = json.loads(payload)
    except (KeyError, LookupError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return cast(dict[str, Any], decoded) if isinstance(decoded, dict) else fallback


def _runtime_nodes(runtime: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(runtime.get("node_results")) if isinstance(item, dict)]


def _trace_event_count(audit_root: Path, case_id: str) -> int:
    if not audit_root.exists():
        return 0
    count = 0
    for path in audit_root.rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if case_id in line:
                count += 1
    return count


def _audit_text(audit_root: Path, case_id: str) -> str:
    if not audit_root.exists():
        return ""
    lines: list[str] = []
    for path in audit_root.rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if case_id in line:
                lines.append(line)
    return "\n".join(lines)


def _section_rows(sections: Mapping[str, Any], section_name: str) -> list[list[str]]:
    section = sections.get(section_name)
    if not isinstance(section, dict):
        return []
    rows = section.get("rows")
    if not isinstance(rows, list):
        return []
    result: list[list[str]] = []
    for row in rows:
        if isinstance(row, list):
            result.append([str(cell) for cell in row])
    return result


def _metric_formula_source_count(
    rows: Iterable[list[str]],
    *,
    metric_ids: Iterable[str],
) -> int:
    requested_metrics = {str(metric_id) for metric_id in metric_ids}
    covered_metrics: set[str] = set()
    for row in rows:
        if len(row) < 2 or row[0] not in requested_metrics:
            continue
        lineage_cells = tuple(
            cell
            for cell in row[2:]
            if any(cell.startswith(prefix) for prefix in ALLOWED_METRIC_LINEAGE_PREFIXES)
            and not cell.endswith("=MISSING")
        )
        if not lineage_cells:
            continue
        if row[1].casefold() == "blocked":
            reason_code = row[2] if len(row) >= 3 else ""
            if reason_code and reason_code != "MISSING" and ":" in reason_code:
                covered_metrics.add(row[0])
            continue
        has_formula_version = any(
            (cell.startswith("formula_version=") and not cell.endswith("=MISSING"))
            or FORMULA_VERSION_RE.fullmatch(cell) is not None
            for cell in row[2:]
        )
        if has_formula_version:
            covered_metrics.add(row[0])
    return len(covered_metrics)


def _source_appendix_hash_count(rows: Iterable[list[str]]) -> int:
    return sum(1 for row in rows if len(row) >= 2 and str(row[1]).startswith("sha256:"))


def _unsupported_claim_count(runtime: Mapping[str, Any]) -> int:
    statuses = runtime.get("claim_status_by_id")
    if isinstance(statuses, dict):
        return sum(1 for status in statuses.values() if str(status) == "unsupported")
    summary = runtime.get("claim_matrix_summary")
    if isinstance(summary, list):
        return sum(1 for item in summary if isinstance(item, dict) and item.get("status") == "unsupported")
    return 0


def _market_sources_by_id(market_snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for item in _list(market_snapshot.get("sources")):
        if not isinstance(item, dict):
            continue
        source_id = _as_str(item.get("source_id"))
        if source_id is not None:
            sources[source_id] = cast(dict[str, Any], item)
    return sources


def _queue2_assertions(cases: Iterable[StartupFrozenRuntimeCaseEvidence]) -> dict[str, object]:
    case_list = tuple(cases)
    metric_pack_hashes = sorted(case.metric_pack_hash for case in case_list)
    return {
        "profile_determinism": all(case.semantic_fingerprint_match is True for case in case_list),
        "persisted_hash_determinism": all(
            case.persisted_hash_fingerprint_match is True for case in case_list
        ),
        "readiness_scored": all(
            case.readiness_snapshot_hash.startswith("sha256:") and case.metric_count > 0
            for case in case_list
        ),
        "metric_pack_hash": _hash_json(metric_pack_hashes),
        "contradiction_count": sum(case.contradiction_count for case in case_list),
        "unsupported_claim_count": sum(case.unsupported_claim_count for case in case_list),
        "report_sections_ok": all(
            case.report_json_status == 200
            and case.report_html_status == 200
            and case.report_pdf_status == 200
            for case in case_list
        ),
        "trace_sections_ok": all(
            case.runtime_trace_event_count > 0
            and case.trace_to_report_lineage
            and "report_trace_ids_missing" not in case.fail_reasons
            for case in case_list
        ),
        "max_questions": max((case.readiness_question_count for case in case_list), default=0),
        "formula_source_coverage": all(
            case.metric_count > 0 and case.metric_formula_source_count == case.metric_count
            for case in case_list
        ),
        "per_case_contradictions_and_unsupported": all(
            case.contradiction_count > 0 and case.unsupported_claim_count > 0
            for case in case_list
        ),
        "competitor_source_coverage": all(
            case.competitor_count > 0
            and case.source_appendix_hash_count >= case.competitor_source_ref_count
            for case in case_list
        ),
        "competitor_sources_resolved": all(
            case.competitor_sources_resolved
            and case.competitor_sources_with_as_of == case.competitor_source_ref_count
            for case in case_list
        ),
        "privacy_scan_ok": all(case.privacy_leak_count == 0 for case in case_list),
        "bounded_reflexion": all(
            "runtime_nodes_missing" not in case.fail_reasons and case.runtime_node_count > 0
            for case in case_list
        ),
    }


def _aggregate_fail_reasons(
    *,
    cases: Iterable[StartupFrozenRuntimeCaseEvidence],
    assertions: Mapping[str, object],
) -> list[str]:
    reasons: list[str] = []
    case_list = tuple(cases)
    if len(case_list) != 4:
        reasons.append("fixture_case_count_mismatch")
    if assertions.get("profile_determinism") is not True:
        reasons.append("profile_determinism_failed")
    if assertions.get("persisted_hash_determinism") is not True:
        reasons.append("persisted_hash_determinism_failed")
    if assertions.get("readiness_scored") is not True:
        reasons.append("readiness_scored_failed")
    if assertions.get("report_sections_ok") is not True:
        reasons.append("report_sections_failed")
    if assertions.get("trace_sections_ok") is not True:
        reasons.append("trace_sections_failed")
    max_questions = assertions.get("max_questions")
    if not isinstance(max_questions, int) or max_questions > 3:
        reasons.append("max_questions_failed")
    if assertions.get("competitor_source_coverage") is not True:
        reasons.append("competitor_source_coverage_failed")
    if assertions.get("competitor_sources_resolved") is not True:
        reasons.append("competitor_sources_resolved_failed")
    if assertions.get("formula_source_coverage") is not True:
        reasons.append("formula_source_coverage_failed")
    if assertions.get("per_case_contradictions_and_unsupported") is not True:
        reasons.append("per_case_contradictions_and_unsupported_failed")
    if assertions.get("privacy_scan_ok") is not True:
        reasons.append("privacy_scan_failed")
    if assertions.get("unsupported_claim_count") == 0:
        reasons.append("unsupported_claims_missing")
    return reasons


def _privacy_leak_count(payloads: object) -> int:
    serialized = (
        payloads
        if isinstance(payloads, str)
        else json.dumps(payloads, sort_keys=True, ensure_ascii=False, default=str)
    )
    return len(SENSITIVE_VALUE_RE.findall(serialized))


def _semantic_fingerprint(
    *,
    case_name: str,
    report_json: Mapping[str, Any],
    runtime: Mapping[str, Any],
    runtime_node_names: set[str],
) -> str:
    readiness = cast(
        dict[str, Any],
        cast(dict[str, Any], runtime.get("startup_readiness_artifact") or {}).get("snapshot") or {},
    )
    market = cast(
        dict[str, Any],
        cast(dict[str, Any], runtime.get("startup_market_research_artifact") or {}).get("snapshot") or {},
    )
    metric_pack = cast(dict[str, Any], readiness.get("metric_pack") or {})
    payload = {
        "case_name": case_name,
        "provider": runtime.get("provider_status"),
        "report_sections": sorted(cast(dict[str, Any], report_json.get("sections") or {}).keys()),
        "metric_ids": sorted(str(item) for item in _list(metric_pack.get("metric_ids"))),
        "adaptive_question_codes": sorted(
            str(cast(dict[str, Any], item).get("question_code"))
            for item in _list(metric_pack.get("adaptive_questions"))
            if isinstance(item, dict)
        ),
        "competitor_categories": sorted(
            str(cast(dict[str, Any], item).get("category"))
            for item in _list(market.get("competitors"))
            if isinstance(item, dict)
        ),
        "market_source_hashes": sorted(
            str(cast(dict[str, Any], item).get("source_hash"))
            for item in _list(market.get("sources"))
            if isinstance(item, dict)
        ),
        "runtime_nodes": sorted(runtime_node_names),
    }
    return "sha256:" + _hash_json(payload)


def _persisted_semantic_fingerprint(
    *,
    report_json: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> str:
    report_projection = dict(report_json)
    if "as_of" in report_projection:
        report_projection["as_of"] = "<runtime-timestamp>"
    runtime_projection = {
        "startup_readiness_artifact": runtime.get("startup_readiness_artifact"),
        "startup_market_research_artifact": runtime.get("startup_market_research_artifact"),
        "metric_diagnostics": runtime.get("metric_diagnostics"),
        "claim_matrix_summary": runtime.get("claim_matrix_summary"),
        "contradiction_ids": runtime.get("contradiction_ids"),
        "disclosure_scope": runtime.get("disclosure_scope"),
        "disclosure_snapshot": runtime.get("disclosure_snapshot"),
        "warnings": runtime.get("warnings"),
        "node_results": sorted(
            [
                {
                    "node_name": node.get("node_name"),
                    "status": node.get("status"),
                    "attempt_count": node.get("attempt_count"),
                    "retry_count": node.get("retry_count"),
                    "errors": node.get("errors"),
                    "warnings": node.get("warnings"),
                }
                for node in _runtime_nodes(runtime)
            ],
            key=lambda node: (
                str(node.get("node_name") or ""),
                str(node.get("status") or ""),
                str(node.get("attempt_count") or ""),
                str(node.get("retry_count") or ""),
                json.dumps(node.get("errors"), sort_keys=True, default=str),
                json.dumps(node.get("warnings"), sort_keys=True, default=str),
            ),
        ),
    }
    canonical = _canonicalize_persisted_semantics(
        {"report": report_projection, "runtime": runtime_projection}
    )
    return "sha256:" + _hash_json(canonical)


def _canonicalize_persisted_semantics(value: object) -> object:
    identity_tokens: dict[str, str] = {}

    def canonicalize(item: object, *, key: str | None = None) -> object:
        if isinstance(item, Mapping):
            return {
                canonicalize_text(str(item_key)): (
                    # The product keeps this ordered hash strict for Gate D. The
                    # cross-run evaluator normalizes it only when the same
                    # disclosure fragment set receives different runtime-local
                    # ordering or block identifiers.
                    "<derived-hash>"
                    if str(item_key) == "content_hash"
                    and "minimized_fragment_refs" in item
                    else _derived_hash_mapping(item_value)
                    if str(item_key) == "content_hashes"
                    else _source_hash_set(item_value)
                    if str(item_key) == "source_hashes"
                    else _runtime_ref_list(item_value)
                    if str(item_key)
                    in {
                        "calculation_ids",
                        "claim_ids",
                        "contradiction_ids",
                        "fact_ids",
                        "finding_ids",
                        "input_evidence_ids",
                        "startup_claim_ids",
                    }
                    else sorted(
                        (canonicalize(entry, key=str(item_key)) for entry in item_value),
                        key=lambda entry: json.dumps(entry, sort_keys=True, default=str),
                    )
                    if (
                        str(item_key) in {"items", "rows"}
                        or str(item_key) in ORDER_INDEPENDENT_DISCLOSURE_SET_KEYS
                    )
                    and isinstance(item_value, (list, tuple))
                    else canonicalize(item_value, key=str(item_key))
                )
                for item_key, item_value in item.items()
            }
        if isinstance(item, (list, tuple)):
            if (
                len(item) >= 2
                and isinstance(item[0], str)
                and item[0]
                in {
                    "case_snapshot_hash",
                    "market_research_snapshot_hash",
                    "metric_pack_hash",
                    "profile_hash",
                    "readiness_metric_pack",
                    "readiness_metric_pack_hash",
                    "readiness_snapshot_hash",
                    "report_hash",
                    "snapshot_hash",
                }
                and isinstance(item[1], str)
                and item[1].startswith("sha256:")
            ):
                return [
                    canonicalize(item[0]),
                    "<derived-hash>",
                    *(canonicalize(entry, key=key) for entry in item[2:]),
                ]
            return [canonicalize(entry, key=key) for entry in item]
        if isinstance(item, str):
            if key in VOLATILE_TIMESTAMP_KEYS:
                return "<runtime-timestamp>"
            if _is_identity_bound_hash_key(key):
                return "<derived-hash>"
            return canonicalize_text(item)
        return item

    def canonicalize_text(text: str) -> str:
        normalized = DOCUMENT_TEXT_BLOCK_ID_RE.sub(
            "document_text_block_<runtime-ref>",
            text,
        )
        normalized = STARTUP_TRACE_ID_RE.sub(r"\1-<trace-run>", normalized)
        normalized = RUNTIME_REF_ASSIGNMENT_RE.sub(r"\1=<runtime-ref>", normalized)
        normalized = PROFILE_CONTRADICTION_RE.sub(r"\1:<runtime-ref>", normalized)
        normalized = VOLATILE_HASH_ASSIGNMENT_RE.sub(r"\1=<derived-hash>", normalized)
        normalized = STANDALONE_SHA256_RE.sub("<derived-hash>", normalized)

        def replace_identity(match: re.Match[str]) -> str:
            identity = match.group(0).casefold()
            token = identity_tokens.get(identity)
            if token is None:
                token = f"<runtime-id:{len(identity_tokens) + 1}>"
                identity_tokens[identity] = token
            return token

        return UUID_TOKEN_RE.sub(replace_identity, normalized)

    return canonicalize(value)


def _is_identity_bound_hash_key(key: str | None) -> bool:
    if key is None:
        return False
    return key in {
        "configuration_hash",
        "html_artifact_ref",
        "json_artifact_ref",
        "pack_hash",
        "pdf_artifact_ref",
        "profile_hash",
        "report_hash",
    } or key.endswith("snapshot_hash")


def _derived_hash_mapping(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    return {str(item_key): "<derived-hash>" for item_key in value}


def _source_hash_set(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    return sorted(str(item_value) for item_value in value.values())


def _runtime_ref_list(value: object) -> object:
    if not isinstance(value, (list, tuple)):
        return value
    return ["<runtime-ref>" for _item in value]




def _failed_case(case_name: str, reason: str) -> StartupFrozenRuntimeCaseEvidence:
    return StartupFrozenRuntimeCaseEvidence(
        case_name=case_name,
        evidence_source="runtime_api",
        uploaded_document_count=0,
        provider_status="MISSING",
        gate2_status="MISSING",
        gate3_status="MISSING",
        gate4_status="MISSING",
        report_status="MISSING",
        report_json_status=0,
        report_html_status=0,
        report_pdf_status=0,
        report_hash="MISSING",
        profile_hash="MISSING",
        readiness_snapshot_hash="MISSING",
        market_research_snapshot_hash="MISSING",
        metric_pack_hash="MISSING",
        readiness_question_count=0,
        metric_count=0,
        metric_formula_source_count=0,
        contradiction_count=0,
        unsupported_claim_count=0,
        competitor_count=0,
        competitor_source_ref_count=0,
        source_appendix_hash_count=0,
        runtime_trace_event_count=0,
        runtime_node_count=0,
        runtime_nodes_hash=_hash_json([]),
        trace_to_report_lineage=False,
        semantic_fingerprint=_hash_json({"case_name": case_name, "failed": reason}),
        persisted_hash_fingerprint=_hash_json({"case_name": case_name, "failed": reason}),
        competitor_sources_resolved=False,
        competitor_sources_with_as_of=0,
        privacy_leak_count=0,
        semantic_fingerprint_match=None,
        persisted_hash_fingerprint_match=None,
        fail_reasons=(reason,),
    )


def _replace_case(
    case: StartupFrozenRuntimeCaseEvidence,
    *,
    semantic_fingerprint_match: bool,
    persisted_hash_fingerprint_match: bool,
) -> StartupFrozenRuntimeCaseEvidence:
    return replace(
        case,
        semantic_fingerprint_match=semantic_fingerprint_match,
        persisted_hash_fingerprint_match=persisted_hash_fingerprint_match,
    )


def _write_result(path: Path, result: StartupFrozenRuntimeResult) -> None:
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    payload = result.to_json_dict()
    payload["artifact_paths"] = {
        key: Path(value).name for key, value in result.artifact_paths.items()
    }
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _as_str(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


def _list(value: object | None) -> list[Any]:
    return value if isinstance(value, list) else []


class _OutboundGuard:
    def __init__(self) -> None:
        self.violation_count = 0
        self._patches: list[Any] = []
        self._original_socket_connect: Any | None = None

    def __enter__(self) -> _OutboundGuard:
        self._original_socket_connect = socket.socket.connect

        def guarded_socket_connect(active_socket: socket.socket, address: object) -> None:
            self._guarded_socket_connect(active_socket, address)

        self._patches = [
            patch("socket.create_connection", side_effect=self._deny),
            patch.object(socket.socket, "connect", guarded_socket_connect),
            patch.object(urllib.request, "urlopen", side_effect=self._deny),
        ]
        for active_patch in self._patches:
            active_patch.start()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        for active_patch in reversed(self._patches):
            active_patch.stop()
        self._patches.clear()

    def _deny(self, *_args: object, **_kwargs: object) -> None:
        self.violation_count += 1
        raise RuntimeError("startup_frozen_runtime_external_call_denied")

    def _guarded_socket_connect(self, active_socket: socket.socket, address: object) -> None:
        if _is_loopback_address(address) and self._original_socket_connect is not None:
            self._original_socket_connect(active_socket, address)
            return
        self._deny(address)


def _is_loopback_address(address: object) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if not isinstance(host, str):
        return False
    return host in {"localhost", "::1"} or host.startswith("127.")


@contextmanager
def _scoped_environment(overrides: Mapping[str, str]) -> Iterator[None]:
    previous: dict[str, str | None] = {name: os.environ.get(name) for name in overrides}
    try:
        for name, value in overrides.items():
            os.environ[name] = value
        yield
    finally:
        for name, previous_value in previous.items():
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Final, cast
from uuid import UUID

from due_diligence_agent.evals.failure_matrix import (
    validate_queue5_failure_matrix_payload,
)
from due_diligence_agent.evals.output_root import prepare_evaluation_output_root


SCHEMA_VERSION: Final[str] = "queue5_verification_summary@1"
SUMMARY_FILENAME: Final[str] = "queue5-verification-summary.json"
_MAX_JSON_BYTES: Final[int] = 5_000_000
_EXPECTED_SCHEMAS: Final[dict[str, str]] = {
    "frozen_packet": "sellable_demo_freeze_packet@1",
    "pdf_browser_evidence": "founder_browser_smoke_evidence@1",
    "langsmith_evidence": "langsmith_trace_evidence@1",
    "openai_competitor_evidence": "openai_competitor_smoke_evidence@1",
    "failure_matrix": "queue5_failure_matrix@1",
}
_EXPECTED_SCREENSHOTS: Final[dict[str, dict[str, int]]] = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}
_EXPECTED_DESKTOP_STATE_VIEWPORT: Final[dict[str, int]] = {"width": 1440, "height": 1000}
_CANONICAL_DESKTOP_STATE_SCREENSHOTS: Final[tuple[str, ...]] = (
    "01-start-dashboard.png",
    "02-data-room.png",
    "03-analysis-progress-gate2.png",
    "04-overview-readiness.png",
    "11-ai-advisor-next-question.png",
    "12-ai-advisor-answer.png",
    "13-ai-advisor-updated-analysis.png",
    "14-ai-advisor-improved-plan.png",
    "05-metrics-finance.png",
    "06-market-competitors.png",
    "07-risks-questions.png",
    "08-ai-action-plan.png",
    "09-report-center.png",
    "10-admin-observability-v2.png",
)
_EXPECTED_REPORT_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {"case_id", "snapshot_hash", "snapshot_id", "snapshot_revision"}
)
_EXPECTED_COMPETITOR_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"direct", "indirect", "substitute", "do_nothing", "potential_entrant"}
)
_EXPECTED_LANGSMITH_NODES: Final[frozenset[str]] = frozenset(
    {"initialize", "ingest", "report"}
)
_EXPECTED_LANGSMITH_RUN_NAMES: Final[frozenset[str]] = frozenset(
    {"startup.workflow", "startup.initialize", "startup.ingest", "startup.report"}
)
_EXPECTED_LANGSMITH_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "agent_role",
        "case_id",
        "duration_ms",
        "estimated_cost_usd",
        "gate",
        "node_name",
        "report_checksum",
        "report_id",
        "retry_count",
        "run_id",
        "status",
        "total_tokens",
    }
)
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"sha256:[a-f0-9]{64}\Z", re.IGNORECASE)
_HEX_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"[a-f0-9]{64}\Z", re.IGNORECASE)
_SENSITIVE_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"((?<![A-Za-z0-9])[A-Za-z]:[\\/]|"
    r"(?i:/Users/|/home/|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])|"
    r"\bbearer\s+\S+|api[_ -]?key\s*[=:]\s*\S+|%PDF|"
    r"raw[_ -]?pdf|document[_ -]?text|chain[_ -]?of[_ -]?thought|"
    r"local[_ -]?path|private[_ -]?name|\"prompt\"\s*:))"
)


@dataclass(frozen=True)
class Queue5VerificationInputs:
    frozen_packet_path: Path
    pdf_browser_evidence_path: Path
    langsmith_evidence_path: Path
    openai_competitor_evidence_path: Path
    failure_matrix_path: Path
    demo_script_path: Path
    capstone_map_path: Path
    output_dir: Path


@dataclass(frozen=True)
class Queue5VerificationSummary:
    schema_version: str
    frozen_demo: dict[str, object]
    pdf_journey: dict[str, object]
    langsmith_trace: dict[str, object]
    openai_competitor_smoke: dict[str, object]
    failure_matrix: dict[str, object]
    readiness: dict[str, bool]
    blockers: list[str]
    hashes: dict[str, str]
    raw_file_hashes: dict[str, str]
    semantic_summary_hash: str
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        return cast(dict[str, object], asdict(self))


def build_queue5_verification_summary(
    inputs: Queue5VerificationInputs,
) -> Queue5VerificationSummary:
    output_root = _prepare_output_root(inputs.output_dir)
    payloads = {
        "frozen_packet": _read_json(inputs.frozen_packet_path),
        "pdf_browser_evidence": _read_json(inputs.pdf_browser_evidence_path),
        "langsmith_evidence": _read_json(inputs.langsmith_evidence_path),
        "openai_competitor_evidence": _read_json(inputs.openai_competitor_evidence_path),
        "failure_matrix": _read_json(inputs.failure_matrix_path),
    }
    _validate_schemas(payloads)
    _validate_privacy(payloads)
    _validate_non_empty_text(inputs.demo_script_path)
    _validate_non_empty_text(inputs.capstone_map_path)

    frozen_demo = _frozen_demo_section(payloads["frozen_packet"])
    pdf_journey = _pdf_journey_section(payloads["pdf_browser_evidence"])
    _validate_frozen_pdf_case_lineage(frozen_demo, pdf_journey)
    langsmith_trace = _langsmith_trace_section(payloads["langsmith_evidence"])
    openai_competitor_smoke = _openai_competitor_section(payloads["openai_competitor_evidence"])
    failure_matrix = _failure_matrix_section(payloads["failure_matrix"])

    frozen_ready = frozen_demo["status"] == "pass"
    pdf_ready = pdf_journey["status"] == "pass"
    langsmith_ready = (
        langsmith_trace["status"] == "pass" and langsmith_trace["admin_health_status"] == "healthy"
    )
    openai_ready = openai_competitor_smoke["status"] in {
        "pass",
        "skipped_missing_credential",
    }
    matrix_ready = failure_matrix["status"] == "pass"

    blockers: list[str] = []
    if not frozen_ready:
        blockers.append("frozen_demo_not_passed")
    if not pdf_ready:
        blockers.append("pdf_journey_not_passed")
    if not langsmith_ready:
        if langsmith_trace["status"] == "blocked_missing_credential":
            blockers.append("langsmith_trace_missing_credential")
        else:
            blockers.append("langsmith_trace_not_healthy")
    if not openai_ready:
        blockers.append("openai_competitor_smoke_not_allowed")
    if not matrix_ready:
        blockers.append("failure_matrix_not_passed")

    readiness = {
        "frozen_packet_ready": frozen_ready,
        "pdf_journey_ready": pdf_ready,
        "langsmith_trace_ready": langsmith_ready,
        "openai_competitor_smoke_ready": openai_ready,
        "failure_matrix_ready": matrix_ready,
        "queue5_sellable_demo_ready": not blockers,
    }
    artifact_paths = {
        "frozen_packet": inputs.frozen_packet_path.name,
        "pdf_browser_evidence": inputs.pdf_browser_evidence_path.name,
        "langsmith_evidence": inputs.langsmith_evidence_path.name,
        "openai_competitor_evidence": inputs.openai_competitor_evidence_path.name,
        "failure_matrix": inputs.failure_matrix_path.name,
        "demo_script": inputs.demo_script_path.name,
        "capstone_map": inputs.capstone_map_path.name,
        "summary": SUMMARY_FILENAME,
    }
    raw_file_hashes = {
        "frozen_packet": _hash_file(inputs.frozen_packet_path),
        "pdf_browser_evidence": _hash_file(inputs.pdf_browser_evidence_path),
        "langsmith_evidence": _hash_file(inputs.langsmith_evidence_path),
        "openai_competitor_evidence": _hash_file(inputs.openai_competitor_evidence_path),
        "failure_matrix": _hash_file(inputs.failure_matrix_path),
        "demo_script": _hash_file(inputs.demo_script_path),
        "capstone_map": _hash_file(inputs.capstone_map_path),
    }
    hashes = {
        "canonical_frozen_packet_hash": str(frozen_demo["packet_hash"]),
        "pdf_journey_semantic_hash": _semantic_hash(pdf_journey),
        "langsmith_trace_semantic_hash": _semantic_hash(langsmith_trace),
        "openai_competitor_smoke_semantic_hash": _semantic_hash(openai_competitor_smoke),
        "failure_matrix_hash": str(failure_matrix["matrix_hash"]),
        "demo_script_hash": raw_file_hashes["demo_script"],
        "capstone_map_hash": raw_file_hashes["capstone_map"],
    }
    semantic_payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "frozen_demo": frozen_demo,
        "pdf_journey": pdf_journey,
        "langsmith_trace": langsmith_trace,
        "openai_competitor_smoke": openai_competitor_smoke,
        "failure_matrix": failure_matrix,
        "readiness": readiness,
        "blockers": blockers,
        "hashes": hashes,
    }
    semantic_summary_hash = _semantic_hash(semantic_payload)
    summary = Queue5VerificationSummary(
        schema_version=SCHEMA_VERSION,
        frozen_demo=frozen_demo,
        pdf_journey=pdf_journey,
        langsmith_trace=langsmith_trace,
        openai_competitor_smoke=openai_competitor_smoke,
        failure_matrix=failure_matrix,
        readiness=readiness,
        blockers=blockers,
        hashes=hashes,
        raw_file_hashes=raw_file_hashes,
        semantic_summary_hash=semantic_summary_hash,
        artifact_paths=artifact_paths,
    )
    _write_json(output_root / SUMMARY_FILENAME, summary.to_json_dict())
    return summary


def _prepare_output_root(output_dir: Path) -> Path:
    try:
        return prepare_evaluation_output_root(output_dir)
    except ValueError as exc:
        if str(exc) == "evaluation_output_dir_not_empty":
            raise ValueError("verification_output_dir_not_empty") from None
        if str(exc) == "evaluation_output_dir_not_directory":
            raise ValueError("verification_output_dir_not_directory") from None
        raise


def _read_json(path: Path) -> dict[str, object]:
    try:
        if path.stat().st_size > _MAX_JSON_BYTES:
            raise ValueError("queue5_evidence_json_too_large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("queue5_evidence_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("queue5_evidence_json_invalid")
    return {str(key): value for key, value in payload.items()}


def _validate_schemas(payloads: Mapping[str, Mapping[str, object]]) -> None:
    for key, expected in _EXPECTED_SCHEMAS.items():
        if payloads[key].get("schema_version") != expected:
            raise ValueError("queue5_evidence_schema_invalid")


def _validate_privacy(payloads: Mapping[str, Mapping[str, object]]) -> None:
    for payload in payloads.values():
        privacy = _mapping(payload.get("privacy"))
        if privacy and privacy.get("privacy_leak_count") != 0:
            raise ValueError("queue5_privacy_validation_failed")
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if _SENSITIVE_VALUE_RE.search(serialized) is not None:
            raise ValueError("queue5_privacy_validation_failed")


def _validate_non_empty_text(path: Path) -> None:
    try:
        if not path.read_text(encoding="utf-8").strip():
            raise ValueError("queue5_documentation_missing")
    except OSError as exc:
        raise ValueError("queue5_documentation_missing") from exc


def _frozen_demo_section(payload: Mapping[str, object]) -> dict[str, object]:
    gates = _mapping(payload.get("gates"))
    all_gates_pass = bool(gates) and all(value == "pass" for value in gates.values())
    packet_hash = str(payload.get("packet_hash") or "")
    gate_d_semantic_equivalence = payload.get("gate_d_semantic_equivalence") is True
    lineage = _mapping(payload.get("report_lineage"))
    approved_lineage = _mapping(payload.get("approved_report_lineage"))
    report_revision = _integer(approved_lineage.get("report_revision"))
    report_checksum = str(approved_lineage.get("report_checksum") or "")
    report_lineage: dict[str, object] = {
        "case_id": str(lineage.get("case_id") or ""),
        "html": str(lineage.get("html") or ""),
        "json": str(lineage.get("json") or ""),
        "pdf": str(lineage.get("pdf") or ""),
        "report_checksum": report_checksum,
        "report_html_hash": str(approved_lineage.get("report_html_hash") or ""),
        "report_id": str(approved_lineage.get("report_id") or ""),
        "report_json_hash": str(approved_lineage.get("report_json_hash") or ""),
        "report_pdf_hash": str(approved_lineage.get("report_pdf_hash") or ""),
        "report_revision": report_revision,
    }
    report_lineage_valid = (
        report_lineage["case_id"] == str(payload.get("case_id") or "")
        and report_lineage["report_id"] != ""
        and report_revision >= 1
        and _HEX_SHA256_RE.fullmatch(report_checksum) is not None
        and all(
            _SHA256_RE.fullmatch(str(report_lineage[key])) is not None
            for key in ("report_json_hash", "report_html_hash", "report_pdf_hash")
        )
    )
    status = (
        "pass"
        if payload.get("sellable_demo_passed") is True
        and all_gates_pass
        and gate_d_semantic_equivalence
        and _SHA256_RE.fullmatch(packet_hash) is not None
        and report_lineage_valid
        else "fail"
    )
    return {
        "schema_version": str(payload["schema_version"]),
        "status": status,
        "case_id": str(payload.get("case_id") or ""),
        "packet_hash": packet_hash,
        "gate_d_semantic_equivalence": gate_d_semantic_equivalence,
        "report_lineage": report_lineage,
    }


def _pdf_journey_section(payload: Mapping[str, object]) -> dict[str, object]:
    screenshots = _mapping(payload.get("screenshots"))
    legacy_dimensions: dict[str, object] = {
        name: {
            "width": _integer(_mapping(screenshots.get(name)).get("width")),
            "height": _integer(_mapping(screenshots.get(name)).get("height")),
        }
        for name in ("desktop", "mobile")
    }
    desktop_state_evidence = _desktop_state_evidence(screenshots)
    legacy_screenshots_valid = legacy_dimensions == _EXPECTED_SCREENSHOTS
    desktop_states_valid = desktop_state_evidence["valid"] is True
    screenshot_evidence_valid = legacy_screenshots_valid or desktop_states_valid
    screenshot_evidence_mode = (
        "legacy_desktop_mobile"
        if legacy_screenshots_valid
        else "desktop_states_14"
        if desktop_states_valid
        else "invalid"
    )
    dimensions: dict[str, object] = (
        legacy_dimensions
        if legacy_screenshots_valid
        else {"desktop_states": desktop_state_evidence["viewport"]}
    )
    admin = _mapping(payload.get("admin_trace"))
    report_lineage = _mapping(admin.get("report_lineage"))
    case_id = str(payload.get("case_id") or "")
    run_id = str(admin.get("run_id") or "")
    report_id = str(report_lineage.get("report_id") or "")
    report_revision = _integer(
        report_lineage.get("report_revision", report_lineage.get("revision"))
    )
    report_checksum = str(
        report_lineage.get("report_checksum", report_lineage.get("checksum")) or ""
    )
    report_metadata = _mapping(payload.get("report_metadata"))
    metadata_snapshot_id = str(report_metadata.get("snapshot_id") or "")
    metadata_snapshot_hash = str(report_metadata.get("snapshot_hash") or "")
    metadata_snapshot_revision = _integer(report_metadata.get("snapshot_revision"))
    metadata_binding_valid = (
        set(report_metadata) == _EXPECTED_REPORT_METADATA_KEYS
        and str(report_metadata.get("case_id") or "") == case_id
        and _is_uuid_string(metadata_snapshot_id)
        and _SHA256_RE.fullmatch(metadata_snapshot_hash) is not None
        and metadata_snapshot_revision >= 1
        and report_id == metadata_snapshot_id
        and report_revision == metadata_snapshot_revision
        and report_checksum == metadata_snapshot_hash.removeprefix("sha256:")
    )
    report_artifact_hashes = _mapping(payload.get("report_artifact_hashes"))
    artifact_hashes = {
        "report_html_hash": str(report_artifact_hashes.get("html") or ""),
        "report_json_hash": str(report_artifact_hashes.get("json") or ""),
        "report_pdf_hash": str(report_artifact_hashes.get("pdf") or ""),
    }
    intake_mode = str(payload.get("intake_mode") or "")
    prompt_selection_used = payload.get("prompt_selection_used")
    industry_selection_used = payload.get("industry_selection_used")
    status = (
        "pass"
        if payload.get("pdf_upload_journey") is True
        and intake_mode == "pdf_upload_only"
        and prompt_selection_used is False
        and industry_selection_used is False
        and payload.get("offline") is True
        and payload.get("network_external_calls") == 0
        and payload.get("gate4_status") == "approved"
        and payload.get("upload_mime_type") == "application/pdf"
        and _SHA256_RE.fullmatch(str(payload.get("upload_sha256") or "")) is not None
        and screenshot_evidence_valid
        and case_id != ""
        and str(admin.get("case_id") or "") == case_id
        and run_id != ""
        and report_id != ""
        and report_revision >= 1
        and _HEX_SHA256_RE.fullmatch(report_checksum) is not None
        and metadata_binding_valid
        and all(_SHA256_RE.fullmatch(value) is not None for value in artifact_hashes.values())
        else "fail"
    )
    return {
        "schema_version": str(payload["schema_version"]),
        "status": status,
        "case_id": case_id,
        "run_id": run_id,
        "intake_mode": intake_mode,
        "prompt_selection_used": prompt_selection_used,
        "industry_selection_used": industry_selection_used,
        "upload_mime_type": str(payload.get("upload_mime_type") or ""),
        "upload_sha256": str(payload.get("upload_sha256") or ""),
        "screenshot_evidence_mode": screenshot_evidence_mode,
        "screenshot_dimensions": dimensions,
        "desktop_state_evidence": desktop_state_evidence,
        "report_lineage": {
            "report_id": report_id,
            "report_revision": report_revision,
            "report_checksum": report_checksum,
            **artifact_hashes,
        },
    }


def _desktop_state_evidence(screenshots: Mapping[str, object]) -> dict[str, object]:
    desktop_states = _mapping(screenshots.get("desktop_states"))
    order = _string_list(desktop_states.get("order"))
    viewport = _mapping(desktop_states.get("viewport"))
    normalized_viewport = {
        "width": _integer(viewport.get("width")),
        "height": _integer(viewport.get("height")),
    }
    return {
        "valid": tuple(order) == _CANONICAL_DESKTOP_STATE_SCREENSHOTS
        and normalized_viewport == _EXPECTED_DESKTOP_STATE_VIEWPORT,
        "state_count": len(order),
        "order": order,
        "viewport": normalized_viewport,
    }


def _validate_frozen_pdf_case_lineage(
    frozen_demo: Mapping[str, object],
    pdf_journey: Mapping[str, object],
) -> None:
    frozen_case = str(frozen_demo.get("case_id") or "")
    pdf_case = str(pdf_journey.get("case_id") or "")
    frozen_lineage = _mapping(frozen_demo.get("report_lineage"))
    if (
        not frozen_case
        or frozen_case != pdf_case
        or str(frozen_lineage.get("case_id") or "") != frozen_case
    ):
        raise ValueError("queue5_case_lineage_mismatch")
    pdf_lineage = _mapping(pdf_journey.get("report_lineage"))
    if (
        str(frozen_lineage.get("report_id") or "") != str(pdf_lineage.get("report_id") or "")
        or _integer(frozen_lineage.get("report_revision"))
        != _integer(pdf_lineage.get("report_revision"))
        or str(frozen_lineage.get("report_checksum") or "")
        != str(pdf_lineage.get("report_checksum") or "")
        or str(frozen_lineage.get("report_json_hash") or "")
        != str(pdf_lineage.get("report_json_hash") or "")
        or str(frozen_lineage.get("report_html_hash") or "")
        != str(pdf_lineage.get("report_html_hash") or "")
        or str(frozen_lineage.get("report_pdf_hash") or "")
        != str(pdf_lineage.get("report_pdf_hash") or "")
    ):
        if frozen_demo.get("status") == "pass" and pdf_journey.get("status") == "pass":
            raise ValueError("queue5_report_lineage_mismatch")


def _langsmith_trace_section(payload: Mapping[str, object]) -> dict[str, object]:
    workflow = _mapping(payload.get("workflow"))
    health = _mapping(workflow.get("admin_langsmith_health"))
    lineage = _mapping(workflow.get("report_lineage"))
    trace = _mapping(payload.get("langsmith_trace"))
    report_id = str(lineage.get("report_id") or "")
    report_revision = _integer(lineage.get("report_revision"))
    report_checksum = str(lineage.get("report_checksum") or "")
    report_lineage: dict[str, object] = {
        "source": str(lineage.get("source") or ""),
        "report_id": report_id,
        "report_revision": report_revision,
        "report_checksum": report_checksum,
    }
    if not report_id or report_revision < 1 or _HEX_SHA256_RE.fullmatch(report_checksum) is None:
        raise ValueError("queue5_report_lineage_invalid")
    status = str(payload.get("status") or "failed")
    credential_present = payload.get("credential_present") is True
    case_id = str(workflow.get("case_id") or "")
    run_id = str(workflow.get("run_id") or "")
    health_status = str(health.get("status") or "missing")
    privacy_passed = _langsmith_privacy_passed(payload)
    live_export_proof = {
        "execute_live_requested": payload.get("execute_live_requested") is True,
        "live_call_attempted": payload.get("live_call_attempted") is True,
        "live_call_succeeded": payload.get("live_call_succeeded") is True,
        "client_constructed": payload.get("client_constructed") is True,
    }
    node_names = _string_set(workflow.get("node_names"))
    run_names = _string_set(trace.get("run_names"))
    metadata_keys = _string_set(trace.get("metadata_keys"))
    run_count = _integer(trace.get("run_count"))
    flush_count = _integer(trace.get("flush_count"))
    export_errors = _integer(trace.get("export_errors"))
    trace_inventory_valid = (
        _EXPECTED_LANGSMITH_NODES <= node_names
        and _EXPECTED_LANGSMITH_RUN_NAMES <= run_names
        and _EXPECTED_LANGSMITH_METADATA_KEYS <= metadata_keys
        and run_count >= len(run_names)
        and flush_count >= 1
        and export_errors == 0
    )
    if status == "pass" and (
        not credential_present
        or not all(live_export_proof.values())
        or not case_id
        or not run_id
        or health_status != "healthy"
        or report_lineage["source"] != "workflow_completed_state"
        or not trace_inventory_valid
        or not privacy_passed
    ):
        status = "failed"
    if status == "blocked_missing_credential" and (
        credential_present
        or live_export_proof["live_call_attempted"]
        or live_export_proof["live_call_succeeded"]
        or live_export_proof["client_constructed"]
        or not _langsmith_missing_credential_inventory_empty(trace)
    ):
        status = "failed"
    return {
        "schema_version": str(payload["schema_version"]),
        "status": status,
        "credential_present": credential_present,
        "case_id": case_id,
        "run_id": run_id,
        "admin_health_status": health_status,
        "live_export_proof": live_export_proof,
        "trace_inventory": {
            "run_count": run_count,
            "run_names": sorted(run_names),
            "metadata_keys": sorted(metadata_keys),
            "flush_count": flush_count,
            "export_errors": export_errors,
        },
        "report_lineage": report_lineage,
        "privacy_passed": privacy_passed,
    }


def _openai_competitor_section(payload: Mapping[str, object]) -> dict[str, object]:
    lineage = _mapping(payload.get("lineage"))
    gate2 = _mapping(payload.get("gate2"))
    result = _mapping(payload.get("result"))
    competitors = result.get("competitors")
    categories = (
        {
            str(_mapping(item).get("category") or "")
            for item in competitors
            if isinstance(item, Mapping)
        }
        if isinstance(competitors, list)
        else set()
    )
    status = str(payload.get("status") or "failed")
    credential_present = payload.get("credential_present") is True
    privacy_passed = _openai_privacy_passed(payload)
    case_id = str(lineage.get("case_id") or "")
    run_id = str(lineage.get("run_id") or "")
    gate2_decision = str(lineage.get("gate2_decision") or "")
    profile_hash = str(lineage.get("profile_hash") or "")
    inference_label = str(payload.get("inference_label") or "")
    research_label = str(payload.get("research_label") or "")
    live_call_proof = {
        "execute_live_requested": payload.get("execute_live_requested") is True,
        "live_call_attempted": payload.get("live_call_attempted") is True,
        "live_call_succeeded": payload.get("live_call_succeeded") is True,
        "call_count": _integer(payload.get("call_count")),
    }
    transport = _mapping(payload.get("transport"))
    budget = _mapping(payload.get("budget"))
    cost_evidence = _mapping(payload.get("cost_evidence"))
    source_summary_hashes = payload.get("source_summary_hashes")
    source_hashes_valid = (
        isinstance(source_summary_hashes, list)
        and bool(source_summary_hashes)
        and all(
            isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
            for value in source_summary_hashes
        )
    )
    gate2_valid = (
        str(gate2.get("case_id") or "") == case_id
        and str(gate2.get("run_id") or "") == run_id
        and gate2.get("status") == "approved"
        and gate2.get("decision") == "approved"
        and gate2.get("destination") == "openai.responses"
        and str(gate2.get("profile_hash") or "") == profile_hash
    )
    bounded_guards_valid = (
        str(transport.get("max_retries") or "") == "0"
        and _decimal_in_range(transport.get("timeout_seconds"), upper=Decimal("20"))
        and _decimal_in_range(budget.get("max_usd"), upper=Decimal("0.25"))
        and _decimal_in_range(budget.get("worst_case_usd"), upper=Decimal("0.25"))
        and _decimal_in_range(budget.get("reserved_usd"), upper=Decimal("0.25"))
        and _openai_cost_evidence_valid(cost_evidence)
    )
    competitor_evidence_valid = _competitor_evidence_refs_valid(competitors)
    if status == "pass" and (
        not credential_present
        or live_call_proof["execute_live_requested"] is not True
        or live_call_proof["live_call_attempted"] is not True
        or live_call_proof["live_call_succeeded"] is not True
        or live_call_proof["call_count"] != 1
        or not case_id
        or not run_id
        or gate2_decision != "approved"
        or not gate2_valid
        or _SHA256_RE.fullmatch(profile_hash) is None
        or inference_label != "live_inference"
        or research_label != "not_live_web_research"
        or categories != _EXPECTED_COMPETITOR_CATEGORIES
        or not competitor_evidence_valid
        or not source_hashes_valid
        or not bounded_guards_valid
        or not privacy_passed
    ):
        status = "failed"
    if status == "skipped_missing_credential" and (
        credential_present
        or live_call_proof["live_call_attempted"] is True
        or live_call_proof["live_call_succeeded"] is True
        or live_call_proof["call_count"] != 0
        or _openai_usage_inventory_nonzero(payload)
        or _openai_cost_inventory_nonzero(payload)
        or _openai_result_inventory_nonempty(payload)
    ):
        status = "failed"
    return {
        "schema_version": str(payload["schema_version"]),
        "status": status,
        "credential_present": credential_present,
        "case_id": case_id,
        "run_id": run_id,
        "gate2_decision": gate2_decision,
        "profile_hash": profile_hash,
        "inference_label": inference_label,
        "research_label": research_label,
        "live_call_proof": live_call_proof,
        "gate2_proof": {
            "status": str(gate2.get("status") or ""),
            "decision": str(gate2.get("decision") or ""),
            "destination": str(gate2.get("destination") or ""),
        },
        "transport": {key: str(value) for key, value in transport.items()},
        "budget": {key: str(value) for key, value in budget.items()},
        "cost_evidence": {key: str(value) for key, value in cost_evidence.items()},
        "source_summary_hash_count": (
            len(source_summary_hashes) if isinstance(source_summary_hashes, list) else 0
        ),
        "categories": sorted(categories),
        "privacy_passed": privacy_passed,
    }


def _failure_matrix_section(payload: Mapping[str, object]) -> dict[str, object]:
    matrix_hash = str(payload.get("matrix_hash") or "")
    matrix_valid, validation_fail_reasons = validate_queue5_failure_matrix_payload(payload)
    return {
        "schema_version": str(payload["schema_version"]),
        "status": (
            "pass"
            if payload.get("matrix_passed") is True
            and _SHA256_RE.fullmatch(matrix_hash) is not None
            and matrix_valid
            else "fail"
        ),
        "matrix_hash": matrix_hash,
        "validation_fail_reasons": list(validation_fail_reasons),
    }


def _langsmith_privacy_passed(payload: Mapping[str, object]) -> bool:
    privacy = _mapping(payload.get("privacy"))
    return privacy.get("privacy_leak_count") == 0 and all(
        privacy.get(field_name) is True
        for field_name in (
            "inputs_empty",
            "outputs_empty",
            "attachments_absent",
            "filesystem_disabled",
            "unsafe_capture_rejected",
        )
    )


def _openai_privacy_passed(payload: Mapping[str, object]) -> bool:
    privacy = _mapping(payload.get("privacy"))
    return privacy.get("privacy_leak_count") == 0 and all(
        privacy.get(field_name) is True
        for field_name in (
            "request_payload_checked",
            "response_payload_checked",
            "unsafe_payload_rejected",
        )
    )


def _langsmith_missing_credential_inventory_empty(trace: Mapping[str, object]) -> bool:
    expected_empty = {
        "run_count": 0,
        "run_names": [],
        "metadata_keys": [],
        "export_errors": 0,
        "flush_count": 0,
    }
    if any(trace.get(key) != value for key, value in expected_empty.items()):
        return False
    return all(key in expected_empty or _empty_inventory_value(value) for key, value in trace.items())


def _openai_usage_inventory_nonzero(payload: Mapping[str, object]) -> bool:
    raw_usage = payload.get("usage")
    if not isinstance(raw_usage, Mapping):
        return not _zero_inventory_value(raw_usage)
    usage = _mapping(raw_usage)
    return any(not _zero_inventory_value(value) for value in usage.values())


def _openai_result_inventory_nonempty(payload: Mapping[str, object]) -> bool:
    return not _empty_inventory_value(payload.get("result"))


def _openai_cost_evidence_valid(cost_evidence: Mapping[str, object]) -> bool:
    return (
        cost_evidence.get("currency") == "USD"
        and str(cost_evidence.get("pricing_model") or "") != ""
        and cost_evidence.get("calculation") == "estimated_from_observed_usage"
        and _decimal_in_range(
            cost_evidence.get("input_usd_per_million_tokens"),
            upper=Decimal("1000"),
        )
        and _decimal_in_range(
            cost_evidence.get("output_usd_per_million_tokens"),
            upper=Decimal("1000"),
        )
        and _decimal_in_range(
            cost_evidence.get("actual_or_estimated_usd"),
            upper=Decimal("0.25"),
        )
    )


def _openai_cost_inventory_nonzero(payload: Mapping[str, object]) -> bool:
    cost_evidence = payload.get("cost_evidence")
    if not isinstance(cost_evidence, Mapping):
        return not _empty_inventory_value(cost_evidence)
    return not _zero_inventory_value(_mapping(cost_evidence).get("actual_or_estimated_usd"))


def _competitor_evidence_refs_valid(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for raw_item in value:
        item = _mapping(raw_item)
        evidence_refs = item.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            return False
        if not all(isinstance(ref, str) and bool(ref.strip()) for ref in evidence_refs):
            return False
    return True


def _decimal_in_range(value: object, *, upper: Decimal) -> bool:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return Decimal("0") < parsed <= upper


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _integer(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _is_uuid_string(value: str) -> bool:
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def _empty_inventory_value(value: object) -> bool:
    if value in (None, "", 0, 0.0, False):
        return True
    if isinstance(value, list | tuple | set | dict):
        return not value
    return False


def _zero_inventory_value(value: object) -> bool:
    if _empty_inventory_value(value):
        return True
    try:
        return Decimal(str(value)) == Decimal("0")
    except (InvalidOperation, ValueError):
        return False


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _semantic_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
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
        newline="\n",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="queue5-verification")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--frozen-packet", required=True)
    parser.add_argument("--pdf-browser-evidence", required=True)
    parser.add_argument("--langsmith-evidence", required=True)
    parser.add_argument("--openai-competitor-evidence", required=True)
    parser.add_argument("--failure-matrix", required=True)
    parser.add_argument("--demo-script", required=True)
    parser.add_argument("--capstone-map", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_queue5_verification_summary(
            Queue5VerificationInputs(
                frozen_packet_path=Path(args.frozen_packet),
                pdf_browser_evidence_path=Path(args.pdf_browser_evidence),
                langsmith_evidence_path=Path(args.langsmith_evidence),
                openai_competitor_evidence_path=Path(args.openai_competitor_evidence),
                failure_matrix_path=Path(args.failure_matrix),
                demo_script_path=Path(args.demo_script),
                capstone_map_path=Path(args.capstone_map),
                output_dir=Path(args.output_dir),
            )
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result.to_json_dict(), sort_keys=True))
    return 0 if result.readiness["queue5_sellable_demo_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import UUID

import pymupdf

from due_diligence_agent.evals.output_root import prepare_evaluation_output_root


PACKET_SCHEMA_VERSION = "sellable_demo_freeze_packet@1"
BROWSER_EVIDENCE_SCHEMA_VERSION = "founder_browser_smoke_evidence@1"
GATE_B_DATASET = "public_us_frozen_v1"
GATE_C_DATASET = "startup_secure_ingest_v1"
GATE_D_DATASET = "startup_synthetic_v1"
GATE_E_DATASET = "capstone_combined_v1"
PACKET_FILENAME = "sellable-demo-freeze-packet.json"
MAX_JSON_BYTES = 5_000_000
EXPECTED_SCREENSHOT_DIMENSIONS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}
EXPECTED_DESKTOP_STATE_ORDER: tuple[str, ...] = (
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
DESKTOP_STATE_MANIFEST_FILENAME = "desktop-state-manifest.json"
DESKTOP_14_STATE_MODE = "desktop_14_state"
LEGACY_DESKTOP_MOBILE_MODE = "desktop_mobile"
_EXPECTED_GATES = {
    "gate_b",
    "gate_c",
    "gate_d_first",
    "gate_d_second",
    "gate_e",
}
_EXPECTED_ARTIFACT_PATHS = {
    "packet",
    "gate_b_result",
    "gate_c_result",
    "gate_d_first_result",
    "gate_d_second_result",
    "gate_d_first_runtime_evidence",
    "gate_d_second_runtime_evidence",
    "gate_e_result",
    "browser_evidence",
    "desktop_screenshot",
    "mobile_screenshot",
    "sample_pdf",
    "demo_script",
    "capstone_map",
}
_EXPECTED_ARTIFACT_HASHES = _EXPECTED_ARTIFACT_PATHS - {"packet"}
_DESKTOP_14_STATE_ARTIFACT_PATHS = (
    (_EXPECTED_ARTIFACT_PATHS - {"mobile_screenshot"})
    | {"desktop_state_manifest"}
    | {f"desktop_state_{index:02d}" for index in range(1, 15)}
)
_DESKTOP_14_STATE_ARTIFACT_HASHES = _DESKTOP_14_STATE_ARTIFACT_PATHS - {"packet"}
_EXPECTED_GATE_D_RAW_HASHES = {
    "first_eval_result",
    "second_eval_result",
    "first_runtime_evidence",
    "second_runtime_evidence",
}
_EXPECTED_REPORT_LINEAGE = {"case_id", "html", "json", "pdf"}
_EXPECTED_BROWSER_REPORT_METADATA = {
    "case_id",
    "snapshot_hash",
    "snapshot_id",
    "snapshot_revision",
}
_EXPECTED_FOUNDER_REPORT_TOP_LEVEL = {
    "analytics",
    "as_of_ru",
    "data_revision",
    "improvement_proposals",
    "main_sections",
    "metric_cards",
    "subtitle_ru",
    "technical_appendix",
    "title_ru",
}
_EXPECTED_APPROVED_REPORT_LINEAGE = {
    "report_checksum",
    "report_html_hash",
    "report_id",
    "report_json_hash",
    "report_pdf_hash",
    "report_revision",
}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PDF_STREAM_RE = re.compile(
    rb"(stream(?:\r\n|\n|\r))(.*?)(endstream)",
    re.DOTALL,
)
_EMAIL_LIKE_BYTES_RE = re.compile(
    rb"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    re.IGNORECASE,
)
_WINDOWS_PATH_LIKE_BYTES_RE = re.compile(
    rb"(?<![A-Za-z0-9])[A-Za-z]:[\\/]",
)
_SENSITIVE_VALUE_RE = re.compile(
    r"((?<![A-Za-z0-9])[A-Za-z]:[\\/]|"
    r"(?i:/Users/|/home/|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])|"
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{20,}(?![A-Za-z0-9._~+/=-])|"
    r"OPENAI_API_KEY\s*[=:]\s*\S+))"
)
_HTML_CASE_ID_RE = re.compile(r"\bdata-case-id=[\"']([^\"']+)[\"']", re.IGNORECASE)
_HTML_METADATA_CASE_ID_RE = re.compile(
    r"<td(?:\s+[^>]*)?>\s*case_id\s*</td>\s*"
    r"<td(?:\s+[^>]*)?>\s*([^<]+?)\s*</td>",
    re.IGNORECASE | re.DOTALL,
)
_SHA256_RE = re.compile(r"sha256:[a-f0-9]{64}\Z", re.IGNORECASE)
_FOUNDER_REPORT_FORBIDDEN_KEYS = frozenset(
    {
        "calculation_ref",
        "case_snapshot_hash",
        "evidence_refs",
        "prompt_versions",
        "report_hash",
        "snapshot_hash",
        "source_appendix",
        "source_hashes",
        "trace_ids",
    }
)
_FOUNDER_REPORT_FORBIDDEN_VALUE_RE = re.compile(
    r"(?:\bMISSING\b|document_text_block|sha256:|supporting_hash=|text_hash=)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SellableDemoFreezeInputs:
    output_dir: Path
    gate_b_result_path: Path
    gate_c_result_path: Path
    gate_d_first_result_path: Path
    gate_d_second_result_path: Path
    gate_e_result_path: Path
    browser_evidence_path: Path
    desktop_screenshot_path: Path
    sample_pdf_path: Path
    demo_script_path: Path
    capstone_map_path: Path
    mobile_screenshot_path: Path | None = None
    require_approved_report_lineage: bool = False


@dataclass(frozen=True)
class SellableDemoFreezePacket:
    schema_version: str
    sellable_demo_passed: bool
    packet_hash: str
    gates: dict[str, str]
    gate_d_semantic_equivalence: bool
    gate_d_raw_hashes: dict[str, str]
    screenshot_dimensions: dict[str, dict[str, int]]
    case_id: str | None
    report_lineage: dict[str, str]
    live_provider_smoke_status: str
    visual_evidence_mode: str = LEGACY_DESKTOP_MOBILE_MODE
    desktop_state_order: tuple[str, ...] = ()
    approved_report_lineage_policy: str = "optional"
    approved_report_lineage: dict[str, str] = field(default_factory=dict)
    fail_reasons: tuple[str, ...] = ()
    artifact_paths: dict[str, str] = field(default_factory=dict)
    artifact_hashes: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["fail_reasons"] = list(self.fail_reasons)
        return payload


def build_sellable_demo_freeze_packet(
    inputs: SellableDemoFreezeInputs,
) -> SellableDemoFreezePacket:
    output_dir = prepare_evaluation_output_root(inputs.output_dir)
    fail_reasons: list[str] = []

    gate_b = _read_json(inputs.gate_b_result_path, "gate_b_result", fail_reasons)
    gate_c = _read_json(inputs.gate_c_result_path, "gate_c_result", fail_reasons)
    gate_d_first = _read_json(
        inputs.gate_d_first_result_path,
        "gate_d_first_result",
        fail_reasons,
    )
    gate_d_second = _read_json(
        inputs.gate_d_second_result_path,
        "gate_d_second_result",
        fail_reasons,
    )
    gate_e = _read_json(inputs.gate_e_result_path, "gate_e_result", fail_reasons)
    browser = _read_json(inputs.browser_evidence_path, "browser_evidence", fail_reasons)
    visual_evidence_mode = _visual_evidence_mode(inputs)

    gate_passes = {
        "gate_b": _validate_gate_b(gate_b, fail_reasons),
        "gate_c": _validate_gate_c(gate_c, fail_reasons),
        "gate_d_first": _validate_gate_d(gate_d_first, "gate_d_first", fail_reasons),
        "gate_d_second": _validate_gate_d(gate_d_second, "gate_d_second", fail_reasons),
        "gate_e": _validate_gate_e(gate_e, fail_reasons),
    }
    gates = {name: "pass" if passed else "fail" for name, passed in gate_passes.items()}
    _validate_commit_consistency(
        (gate_b, gate_c, gate_d_first, gate_d_second, gate_e),
        fail_reasons,
    )

    runtime_first_path = _gate_d_runtime_path(
        inputs.gate_d_first_result_path,
        gate_d_first,
        "gate_d_first",
        fail_reasons,
    )
    runtime_second_path = _gate_d_runtime_path(
        inputs.gate_d_second_result_path,
        gate_d_second,
        "gate_d_second",
        fail_reasons,
    )
    runtime_first = _read_optional_json(
        runtime_first_path,
        "gate_d_first_runtime_evidence",
        fail_reasons,
    )
    runtime_second = _read_optional_json(
        runtime_second_path,
        "gate_d_second_runtime_evidence",
        fail_reasons,
    )
    runtime_first_ok = _validate_runtime_evidence(
        runtime_first,
        "gate_d_first_runtime",
        fail_reasons,
    )
    runtime_second_ok = _validate_runtime_evidence(
        runtime_second,
        "gate_d_second_runtime",
        fail_reasons,
    )
    gate_d_semantic_equivalence = (
        runtime_first_ok
        and runtime_second_ok
        and _gate_d_semantically_equivalent(runtime_first, runtime_second, fail_reasons)
    )

    screenshot_dimensions = {
        "desktop": _png_dimensions(
            inputs.desktop_screenshot_path,
            "desktop_screenshot",
            fail_reasons,
        )
    }
    if inputs.mobile_screenshot_path is not None:
        screenshot_dimensions["mobile"] = _png_dimensions(
            inputs.mobile_screenshot_path,
            "mobile_screenshot",
            fail_reasons,
        )
    _validate_screenshot_dimensions(
        screenshot_dimensions,
        visual_evidence_mode=visual_evidence_mode,
        fail_reasons=fail_reasons,
    )
    desktop_state_paths = _validate_browser_evidence(
        browser,
        visual_evidence_mode=visual_evidence_mode,
        screenshot_dimensions=screenshot_dimensions,
        desktop_path=inputs.desktop_screenshot_path,
        mobile_path=inputs.mobile_screenshot_path,
        browser_evidence_path=inputs.browser_evidence_path,
        fail_reasons=fail_reasons,
    )

    case_id, report_lineage = _report_lineage(
        browser,
        browser_evidence_path=inputs.browser_evidence_path,
        sample_pdf_path=inputs.sample_pdf_path,
        fail_reasons=fail_reasons,
    )
    approved_report_lineage = _approved_report_lineage(
        browser,
        browser_evidence_path=inputs.browser_evidence_path,
        fail_reasons=fail_reasons,
    )
    approved_report_lineage_policy = (
        "required" if inputs.require_approved_report_lineage else "optional"
    )
    if inputs.require_approved_report_lineage and not approved_report_lineage:
        if _has_approved_report_lineage_evidence(browser):
            fail_reasons.append("report_approved_lineage_invalid")
        else:
            fail_reasons.append("report_approved_lineage_missing")
    live_provider_smoke_status = _live_provider_smoke_status(browser, fail_reasons)

    _validate_non_empty_text(inputs.demo_script_path, "demo_script", fail_reasons)
    _validate_non_empty_text(inputs.capstone_map_path, "capstone_map", fail_reasons)

    artifact_paths = _artifact_paths(
        inputs,
        visual_evidence_mode=visual_evidence_mode,
        runtime_first_path=runtime_first_path,
        runtime_second_path=runtime_second_path,
        desktop_state_paths=desktop_state_paths,
    )
    artifact_hashes = _artifact_hashes(
        inputs,
        visual_evidence_mode=visual_evidence_mode,
        runtime_first_path=runtime_first_path,
        runtime_second_path=runtime_second_path,
        desktop_state_paths=desktop_state_paths,
        fail_reasons=fail_reasons,
    )
    gate_d_raw_hashes = {
        "first_eval_result": artifact_hashes.get("gate_d_first_result", "missing"),
        "second_eval_result": artifact_hashes.get("gate_d_second_result", "missing"),
        "first_runtime_evidence": artifact_hashes.get(
            "gate_d_first_runtime_evidence",
            "missing",
        ),
        "second_runtime_evidence": artifact_hashes.get(
            "gate_d_second_runtime_evidence",
            "missing",
        ),
    }

    public_payload: dict[str, object] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "sellable_demo_passed": False,
        "packet_hash": "",
        "gates": gates,
        "gate_d_semantic_equivalence": gate_d_semantic_equivalence,
        "gate_d_raw_hashes": gate_d_raw_hashes,
        "screenshot_dimensions": screenshot_dimensions,
        "case_id": case_id,
        "report_lineage": report_lineage,
        "approved_report_lineage": approved_report_lineage,
        "approved_report_lineage_policy": approved_report_lineage_policy,
        "live_provider_smoke_status": live_provider_smoke_status,
        "visual_evidence_mode": visual_evidence_mode,
        "desktop_state_order": (
            list(EXPECTED_DESKTOP_STATE_ORDER)
            if visual_evidence_mode == DESKTOP_14_STATE_MODE
            else []
        ),
        "fail_reasons": [],
        "artifact_paths": artifact_paths,
        "artifact_hashes": artifact_hashes,
    }
    privacy_sources = (
        _sanitized_browser_payload(browser),
        *_report_privacy_sources(
            browser,
            browser_evidence_path=inputs.browser_evidence_path,
            sample_pdf_path=inputs.sample_pdf_path,
            fail_reasons=fail_reasons,
        ),
        _read_text_for_privacy(inputs.demo_script_path),
        _read_text_for_privacy(inputs.capstone_map_path),
        public_payload,
    )
    founder_report_internal_leaks = _founder_report_internal_leak_count(
        browser,
        browser_evidence_path=inputs.browser_evidence_path,
        fail_reasons=fail_reasons,
    )
    if _privacy_leak_count(privacy_sources) or founder_report_internal_leaks:
        fail_reasons.append("privacy_leaks_detected")

    normalized_fail_reasons = tuple(dict.fromkeys(fail_reasons))
    public_payload["sellable_demo_passed"] = not normalized_fail_reasons
    public_payload["fail_reasons"] = list(normalized_fail_reasons)
    packet_hash = _packet_hash(public_payload)
    public_payload["packet_hash"] = packet_hash

    packet_path = output_dir / PACKET_FILENAME
    _write_json(packet_path, public_payload)
    return _packet_from_payload(public_payload)


def validate_sellable_demo_freeze_packet(packet_path: Path) -> SellableDemoFreezePacket:
    fail_reasons: list[str] = []
    payload = _read_json(packet_path, "packet", fail_reasons)
    if payload.get("schema_version") != PACKET_SCHEMA_VERSION:
        fail_reasons.append("packet_schema_invalid")

    expected_hash = _packet_hash(payload)
    actual_hash = payload.get("packet_hash")
    if actual_hash != expected_hash:
        fail_reasons.append("packet_hash_mismatch")
    if _privacy_leak_count((payload,)):
        fail_reasons.append("privacy_leaks_detected")

    stored_passed = payload.get("sellable_demo_passed") is True
    _validate_packet_shape(payload, stored_passed=stored_passed, fail_reasons=fail_reasons)

    stored_fail_reasons = _string_tuple(payload.get("fail_reasons"))
    fail_reasons.extend(stored_fail_reasons)
    if not stored_passed and not stored_fail_reasons:
        fail_reasons.append("packet_declared_failed")

    normalized_fail_reasons = tuple(dict.fromkeys(fail_reasons))
    validated = dict(payload)
    validated["sellable_demo_passed"] = stored_passed and not normalized_fail_reasons
    validated["fail_reasons"] = list(normalized_fail_reasons)
    return _packet_from_payload(validated)


def _validate_packet_shape(
    payload: Mapping[str, object],
    *,
    stored_passed: bool,
    fail_reasons: list[str],
) -> None:
    if not isinstance(payload.get("sellable_demo_passed"), bool):
        fail_reasons.append("packet_pass_status_invalid")

    gates = _mapping(payload.get("gates"))
    if set(gates) != _EXPECTED_GATES or any(
        status not in {"pass", "fail"} for status in gates.values()
    ):
        fail_reasons.append("packet_gates_invalid")
    elif stored_passed and any(status != "pass" for status in gates.values()):
        fail_reasons.append("packet_gates_not_passed")

    semantic_equivalence = payload.get("gate_d_semantic_equivalence")
    if not isinstance(semantic_equivalence, bool):
        fail_reasons.append("packet_gate_d_semantic_equivalence_invalid")
    elif stored_passed and semantic_equivalence is not True:
        fail_reasons.append("packet_gate_d_semantic_equivalence_failed")

    raw_hashes = _mapping(payload.get("gate_d_raw_hashes"))
    if set(raw_hashes) != _EXPECTED_GATE_D_RAW_HASHES or any(
        not isinstance(value, str) for value in raw_hashes.values()
    ):
        fail_reasons.append("packet_gate_d_raw_hashes_invalid")
    elif stored_passed and any(not _is_sha256(value) for value in raw_hashes.values()):
        fail_reasons.append("packet_gate_d_raw_hashes_invalid")

    visual_evidence_mode = _packet_visual_evidence_mode(payload, fail_reasons)

    dimensions = _dimensions(payload.get("screenshot_dimensions"))
    if dimensions != _expected_screenshot_dimensions(visual_evidence_mode):
        fail_reasons.append("packet_screenshot_dimensions_invalid")
    desktop_state_order = _string_tuple(payload.get("desktop_state_order"))
    if visual_evidence_mode == DESKTOP_14_STATE_MODE:
        if desktop_state_order != EXPECTED_DESKTOP_STATE_ORDER:
            fail_reasons.append("packet_desktop_state_order_invalid")
    elif desktop_state_order:
        fail_reasons.append("packet_desktop_state_order_invalid")

    case_id = payload.get("case_id")
    lineage = _mapping(payload.get("report_lineage"))
    lineage_valid = (
        isinstance(case_id, str)
        and bool(case_id)
        and set(lineage) == _EXPECTED_REPORT_LINEAGE
        and lineage.get("case_id") == case_id
        and all(
            isinstance(lineage.get(kind), str) and bool(lineage.get(kind))
            for kind in ("json", "html", "pdf")
        )
    )
    if not lineage_valid:
        fail_reasons.append("packet_report_lineage_invalid")

    approved_lineage = _mapping(payload.get("approved_report_lineage"))
    if approved_lineage and not _approved_report_lineage_shape_valid(approved_lineage):
        fail_reasons.append("packet_approved_report_lineage_invalid")
    approved_lineage_policy = payload.get("approved_report_lineage_policy")
    if approved_lineage_policy == "required":
        if not approved_lineage:
            fail_reasons.append("report_approved_lineage_missing")
        elif not _approved_report_lineage_shape_valid(approved_lineage):
            fail_reasons.append("report_approved_lineage_invalid")
    elif approved_lineage_policy not in {None, "optional"}:
        fail_reasons.append("packet_approved_report_lineage_policy_invalid")

    if payload.get("live_provider_smoke_status") != "deferred_by_policy":
        fail_reasons.append("packet_live_provider_smoke_status_invalid")

    artifact_paths = _mapping(payload.get("artifact_paths"))
    paths_valid = set(artifact_paths) == _expected_artifact_paths(
        visual_evidence_mode
    ) and all(
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and Path(value).name == value
        for value in artifact_paths.values()
    )
    if not paths_valid:
        fail_reasons.append("packet_artifact_paths_invalid")

    artifact_hashes = _mapping(payload.get("artifact_hashes"))
    hashes_valid = set(artifact_hashes) == _expected_artifact_hashes(
        visual_evidence_mode
    ) and all(
        _is_sha256(value) for value in artifact_hashes.values()
    )
    if not hashes_valid:
        fail_reasons.append("packet_artifact_hashes_invalid")

    raw_fail_reasons = payload.get("fail_reasons")
    if not isinstance(raw_fail_reasons, list) or any(
        not isinstance(reason, str) for reason in raw_fail_reasons
    ):
        fail_reasons.append("packet_fail_reasons_invalid")


def _validate_gate_b(payload: Mapping[str, object], fail_reasons: list[str]) -> bool:
    passed = _base_gate_passed(
        payload,
        gate_name="gate_b",
        dataset=GATE_B_DATASET,
        pass_field="gate_b_passed",
        fail_reasons=fail_reasons,
    )
    if payload.get("privacy_leak_count") != 0:
        fail_reasons.append("gate_b_privacy_invalid")
        passed = False
    if not _offline_no_key_valid(payload, require_startup_key=False):
        fail_reasons.append("gate_b_offline_no_key_invalid")
        passed = False
    return passed


def _validate_gate_c(payload: Mapping[str, object], fail_reasons: list[str]) -> bool:
    passed = _base_gate_passed(
        payload,
        gate_name="gate_c",
        dataset=GATE_C_DATASET,
        pass_field="gate_c_passed",
        fail_reasons=fail_reasons,
    )
    if payload.get("gate_b_passed") is not True:
        fail_reasons.append("gate_c_gate_b_regression_failed")
        passed = False
    if payload.get("privacy_leak_count") != 0:
        fail_reasons.append("gate_c_privacy_invalid")
        passed = False
    if payload.get("denied_gate2_external_calls") != 0:
        fail_reasons.append("gate_c_external_calls_invalid")
        passed = False
    if not _offline_no_key_valid(payload, require_startup_key=True):
        fail_reasons.append("gate_c_offline_no_key_invalid")
        passed = False
    return passed


def _validate_gate_d(
    payload: Mapping[str, object],
    gate_name: str,
    fail_reasons: list[str],
) -> bool:
    passed = _base_gate_passed(
        payload,
        gate_name=gate_name,
        dataset=GATE_D_DATASET,
        pass_field="gate_d_passed",
        fail_reasons=fail_reasons,
        schema_version="gate_d_result@1",
    )
    for dependency in ("gate_b_passed", "gate_c_passed"):
        if payload.get(dependency) is not True:
            fail_reasons.append(f"{gate_name}_{dependency}_failed")
            passed = False
    if payload.get("privacy_leak_count") != 0:
        fail_reasons.append(f"{gate_name}_privacy_invalid")
        passed = False
    if payload.get("denied_gate2_external_calls") != 0:
        fail_reasons.append(f"{gate_name}_external_calls_invalid")
        passed = False
    if payload.get("queue2_assertion_provenance") != "runtime_api:startup_synthetic_v1":
        fail_reasons.append(f"{gate_name}_assertion_provenance_invalid")
        passed = False
    if not _queue2_assertions_valid(payload.get("queue2_assertions")):
        fail_reasons.append(f"{gate_name}_queue2_assertions_invalid")
        passed = False
    if not _offline_no_key_valid(payload, require_startup_key=True):
        fail_reasons.append(f"{gate_name}_offline_no_key_invalid")
        passed = False
    return passed


def _validate_gate_e(payload: Mapping[str, object], fail_reasons: list[str]) -> bool:
    passed = _base_gate_passed(
        payload,
        gate_name="gate_e",
        dataset=GATE_E_DATASET,
        pass_field="gate_e_passed",
        fail_reasons=fail_reasons,
        schema_version="gate_e_result@1",
    )
    required_true = (
        "public_passed",
        "gate_c_passed",
        "gate_d_passed",
        "compatibility_ok",
        "report_repo_sanitized",
        "pdf_fallback_ok",
        "checkpoint_recovery_ok",
        "shared_schema_ok",
    )
    for field_name in required_true:
        if payload.get(field_name) is not True:
            fail_reasons.append(f"gate_e_{field_name}_failed")
            passed = False
    if not _offline_no_key_valid(payload, require_startup_key=True):
        fail_reasons.append("gate_e_offline_no_key_invalid")
        passed = False
    return passed


def _base_gate_passed(
    payload: Mapping[str, object],
    *,
    gate_name: str,
    dataset: str,
    pass_field: str,
    fail_reasons: list[str],
    schema_version: str | None = None,
) -> bool:
    passed = True
    if payload.get("dataset") != dataset:
        fail_reasons.append(f"{gate_name}_dataset_invalid")
        passed = False
    if schema_version is not None and payload.get("schema_version") != schema_version:
        fail_reasons.append(f"{gate_name}_schema_invalid")
        passed = False
    if payload.get(pass_field) is not True:
        fail_reasons.append(f"{gate_name}_failed")
        passed = False
    if _string_tuple(payload.get("fail_reasons")):
        fail_reasons.append(f"{gate_name}_fail_reasons_present")
        passed = False
    return passed


def _queue2_assertions_valid(value: object) -> bool:
    payload = _mapping(value)
    metric_pack_hash = payload.get("metric_pack_hash")
    max_questions = payload.get("max_questions")
    return (
        payload.get("profile_determinism") is True
        and payload.get("readiness_scored") is True
        and isinstance(metric_pack_hash, str)
        and bool(re.fullmatch(r"[a-f0-9]{64}", metric_pack_hash, re.IGNORECASE))
        and _positive_int(payload.get("contradiction_count"))
        and _positive_int(payload.get("unsupported_claim_count"))
        and payload.get("report_sections_ok") is True
        and payload.get("trace_sections_ok") is True
        and isinstance(max_questions, int)
        and not isinstance(max_questions, bool)
        and 0 <= max_questions <= 3
    )


def _validate_runtime_evidence(
    payload: Mapping[str, object],
    name: str,
    fail_reasons: list[str],
) -> bool:
    passed = True
    required = {
        "schema_version": "startup_frozen_runtime_result@1",
        "dataset": GATE_D_DATASET,
        "queue2_runtime_passed": True,
        "privacy_leak_count": 0,
        "denied_gate2_external_calls": 0,
    }
    for field_name, expected in required.items():
        if payload.get(field_name) != expected:
            fail_reasons.append(f"{name}_{field_name}_invalid")
            passed = False
    cases = payload.get("cases")
    if not isinstance(cases, list) or payload.get("case_count") != len(cases) or not cases:
        fail_reasons.append(f"{name}_cases_invalid")
        passed = False
    if _string_tuple(payload.get("fail_reasons")):
        fail_reasons.append(f"{name}_fail_reasons_present")
        passed = False
    return passed


def _gate_d_semantically_equivalent(
    first: Mapping[str, object],
    second: Mapping[str, object],
    fail_reasons: list[str],
) -> bool:
    first_cases = _runtime_case_map(first)
    second_cases = _runtime_case_map(second)
    if not first_cases or not second_cases:
        fail_reasons.append("gate_d_runtime_cases_missing")
        return False
    if set(first_cases) != set(second_cases):
        fail_reasons.append("gate_d_case_set_mismatch")
        return False

    equivalent = True
    for case_name in sorted(first_cases):
        first_case = first_cases[case_name]
        second_case = second_cases[case_name]
        if (
            first_case.get("semantic_fingerprint_match") is not True
            or second_case.get("semantic_fingerprint_match") is not True
            or first_case.get("semantic_fingerprint") != second_case.get("semantic_fingerprint")
        ):
            fail_reasons.append("gate_d_semantic_fingerprint_mismatch")
            equivalent = False
        if (
            first_case.get("persisted_hash_fingerprint_match") is not True
            or second_case.get("persisted_hash_fingerprint_match") is not True
            or first_case.get("persisted_hash_fingerprint")
            != second_case.get("persisted_hash_fingerprint")
        ):
            fail_reasons.append("gate_d_persisted_hash_fingerprint_mismatch")
            equivalent = False
    return equivalent


def _runtime_case_map(payload: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return result
    for raw_case in cases:
        case = _mapping(raw_case)
        case_name = case.get("case_name")
        semantic = case.get("semantic_fingerprint")
        persisted = case.get("persisted_hash_fingerprint")
        if not isinstance(case_name, str) or not case_name:
            continue
        if not isinstance(semantic, str) or not semantic:
            continue
        if not isinstance(persisted, str) or not persisted:
            continue
        if case_name in result:
            return {}
        result[case_name] = case
    return result


def _validate_browser_evidence(
    browser: Mapping[str, object],
    *,
    visual_evidence_mode: str,
    screenshot_dimensions: Mapping[str, Mapping[str, int]],
    desktop_path: Path,
    mobile_path: Path | None,
    browser_evidence_path: Path,
    fail_reasons: list[str],
) -> tuple[Path, ...]:
    if browser.get("schema_version") != BROWSER_EVIDENCE_SCHEMA_VERSION:
        fail_reasons.append("browser_evidence_schema_invalid")
    if browser.get("offline") is not True:
        fail_reasons.append("browser_offline_evidence_invalid")
    if browser.get("network_external_calls") != 0:
        fail_reasons.append("browser_external_calls_detected")
    if browser.get("gate4_status") != "approved":
        fail_reasons.append("browser_gate4_not_approved")

    screenshots = _mapping(browser.get("screenshots"))
    if visual_evidence_mode == DESKTOP_14_STATE_MODE:
        return _validate_desktop_14_state_evidence(
            screenshots,
            desktop_path=desktop_path,
            browser_evidence_path=browser_evidence_path,
            fail_reasons=fail_reasons,
        )

    for viewport, expected_path in (("desktop", desktop_path), ("mobile", mobile_path)):
        evidence = _mapping(screenshots.get(viewport))
        actual = screenshot_dimensions.get(viewport, {})
        if evidence.get("width") != actual.get("width") or evidence.get("height") != actual.get(
            "height"
        ):
            fail_reasons.append(f"{viewport}_browser_dimensions_mismatch")
        raw_path = evidence.get("path")
        if (
            expected_path is None
            or not isinstance(raw_path, str)
            or _resolve_owned_evidence_path(
                browser_evidence_path,
                raw_path,
                f"{viewport}_screenshot_path",
                fail_reasons,
            )
            != expected_path.resolve()
        ):
            fail_reasons.append(f"{viewport}_browser_path_mismatch")
    return ()


def _validate_desktop_14_state_evidence(
    screenshots: Mapping[str, object],
    *,
    desktop_path: Path,
    browser_evidence_path: Path,
    fail_reasons: list[str],
) -> tuple[Path, ...]:
    initial_failure_count = len(fail_reasons)
    evidence = _mapping(screenshots.get("desktop_states"))
    order = _string_tuple(evidence.get("order"))
    if order != EXPECTED_DESKTOP_STATE_ORDER:
        fail_reasons.append("desktop_states_order_invalid")
    viewport = _mapping(evidence.get("viewport"))
    if viewport != EXPECTED_SCREENSHOT_DIMENSIONS["desktop"]:
        fail_reasons.append("desktop_states_viewport_invalid")
    raw_state_root = evidence.get("path")
    state_root = (
        _resolve_owned_evidence_path(
            browser_evidence_path,
            raw_state_root,
            "desktop_states_path",
            fail_reasons,
        )
        if isinstance(raw_state_root, str)
        else None
    )
    if state_root is None or not state_root.is_dir():
        fail_reasons.append("desktop_states_path_invalid")
        _append_desktop_states_contract_failure(initial_failure_count, fail_reasons)
        return ()

    manifest_path = state_root / DESKTOP_STATE_MANIFEST_FILENAME
    manifest = _read_json(manifest_path, "desktop_state_manifest", fail_reasons)
    if manifest.get("schema_version") != "founder_desktop_state_manifest@1":
        fail_reasons.append("desktop_state_manifest_schema_invalid")
    if _string_tuple(manifest.get("order")) != EXPECTED_DESKTOP_STATE_ORDER:
        fail_reasons.append("desktop_state_manifest_order_invalid")
    if _mapping(manifest.get("viewport")) != EXPECTED_SCREENSHOT_DIMENSIONS["desktop"]:
        fail_reasons.append("desktop_state_manifest_viewport_invalid")

    states = manifest.get("states")
    if not isinstance(states, list) or len(states) != len(EXPECTED_DESKTOP_STATE_ORDER):
        fail_reasons.append("desktop_state_manifest_states_invalid")
        states = []

    state_paths: list[Path] = []
    for index, expected_file in enumerate(EXPECTED_DESKTOP_STATE_ORDER, start=1):
        state = _mapping(states[index - 1]) if index <= len(states) else {}
        state_path = _validate_desktop_state_manifest_entry(
            state,
            index=index,
            expected_file=expected_file,
            state_root=state_root,
            fail_reasons=fail_reasons,
        )
        if state_path is not None:
            state_paths.append(state_path)

    if desktop_path.resolve() not in {path.resolve() for path in state_paths}:
        fail_reasons.append("desktop_screenshot_not_in_desktop_states")
    _append_desktop_states_contract_failure(initial_failure_count, fail_reasons)
    return tuple(state_paths)


def _append_desktop_states_contract_failure(
    initial_failure_count: int,
    fail_reasons: list[str],
) -> None:
    if (
        len(fail_reasons) > initial_failure_count
        and "desktop_states_browser_contract_invalid" not in fail_reasons
    ):
        fail_reasons.append("desktop_states_browser_contract_invalid")


def _validate_desktop_state_manifest_entry(
    state: Mapping[str, object],
    *,
    index: int,
    expected_file: str,
    state_root: Path,
    fail_reasons: list[str],
) -> Path | None:
    if state.get("index") != index or state.get("file") != expected_file:
        fail_reasons.append("desktop_state_manifest_states_invalid")
    raw_path = state.get("path")
    state_path = None
    if isinstance(raw_path, str):
        candidate = Path(raw_path)
        if not candidate.is_absolute() and ".." not in candidate.parts:
            resolved = (state_root / candidate).resolve()
            try:
                resolved.relative_to(state_root.resolve())
                state_path = resolved
            except ValueError:
                state_path = None
    if state_path is None or state_path.name != expected_file:
        fail_reasons.append("desktop_state_path_invalid")
        return None
    if _png_dimensions(state_path, f"desktop_state_{index:02d}", fail_reasons) != (
        EXPECTED_SCREENSHOT_DIMENSIONS["desktop"]
    ):
        fail_reasons.append("desktop_state_dimensions_invalid")

    viewport = _mapping(state.get("viewport"))
    if viewport != EXPECTED_SCREENSHOT_DIMENSIONS["desktop"]:
        fail_reasons.append("desktop_state_viewport_invalid")
    overflow = _mapping(state.get("overflow"))
    vertical = overflow.get("verticalOverflowPx")
    tolerance = overflow.get("tolerancePx")
    if (
        not isinstance(vertical, int)
        or isinstance(vertical, bool)
        or not isinstance(tolerance, int)
        or isinstance(tolerance, bool)
        or vertical < 0
        or tolerance < 0
        or tolerance > 1
        or vertical > tolerance
    ):
        fail_reasons.append("desktop_state_overflow_invalid")
    return state_path


def _visual_evidence_mode(inputs: SellableDemoFreezeInputs) -> str:
    if inputs.mobile_screenshot_path is None:
        return DESKTOP_14_STATE_MODE
    return LEGACY_DESKTOP_MOBILE_MODE


def _packet_visual_evidence_mode(
    payload: Mapping[str, object],
    fail_reasons: list[str],
) -> str:
    raw_mode = payload.get("visual_evidence_mode")
    if raw_mode is None:
        return LEGACY_DESKTOP_MOBILE_MODE
    if raw_mode in {LEGACY_DESKTOP_MOBILE_MODE, DESKTOP_14_STATE_MODE}:
        return str(raw_mode)
    fail_reasons.append("packet_visual_evidence_mode_invalid")
    return LEGACY_DESKTOP_MOBILE_MODE


def _expected_screenshot_dimensions(mode: str) -> dict[str, dict[str, int]]:
    if mode == DESKTOP_14_STATE_MODE:
        return {"desktop": EXPECTED_SCREENSHOT_DIMENSIONS["desktop"]}
    return EXPECTED_SCREENSHOT_DIMENSIONS


def _expected_artifact_paths(mode: str) -> set[str]:
    if mode == DESKTOP_14_STATE_MODE:
        return _DESKTOP_14_STATE_ARTIFACT_PATHS
    return _EXPECTED_ARTIFACT_PATHS


def _expected_artifact_hashes(mode: str) -> set[str]:
    if mode == DESKTOP_14_STATE_MODE:
        return _DESKTOP_14_STATE_ARTIFACT_HASHES
    return _EXPECTED_ARTIFACT_HASHES


def _desktop_state_artifact_paths(state_paths: tuple[Path, ...]) -> dict[str, Path]:
    if len(state_paths) != len(EXPECTED_DESKTOP_STATE_ORDER):
        return {}
    state_root = state_paths[0].parent
    paths = {"desktop_state_manifest": state_root / DESKTOP_STATE_MANIFEST_FILENAME}
    paths.update(
        {
            f"desktop_state_{index:02d}": state_path
            for index, state_path in enumerate(state_paths, start=1)
        }
    )
    return paths


def _report_lineage(
    browser: Mapping[str, object],
    *,
    browser_evidence_path: Path,
    sample_pdf_path: Path,
    fail_reasons: list[str],
) -> tuple[str | None, dict[str, str]]:
    case_id = browser.get("case_id")
    normalized_case_id = case_id if isinstance(case_id, str) and case_id else None
    if normalized_case_id is None:
        fail_reasons.append("report_lineage_case_missing")

    report_paths: dict[str, Path | None] = {}
    for kind in ("json", "html", "pdf"):
        raw_path = browser.get(f"report_{kind}_path")
        resolved_path = (
            _resolve_owned_evidence_path(
                browser_evidence_path,
                raw_path,
                f"report_{kind}_path",
                fail_reasons,
            )
            if isinstance(raw_path, str)
            else None
        )
        report_paths[kind] = resolved_path
        if resolved_path is None or not resolved_path.is_file():
            fail_reasons.append(f"report_{kind}_missing")

    report_json: dict[str, object] = {}
    json_case_id: str | None = None
    json_report_id: str | None = None
    json_path = report_paths["json"]
    if json_path is not None and json_path.is_file():
        report_json = _read_json(json_path, "report_json", fail_reasons)
        raw_json_case_id = report_json.get("case_id")
        json_case_id = raw_json_case_id if isinstance(raw_json_case_id, str) else None
        raw_json_report_id = report_json.get("id")
        json_report_id = (
            raw_json_report_id
            if isinstance(raw_json_report_id, str) and _is_uuid(raw_json_report_id)
            else None
        )

    admin_trace = _mapping(browser.get("admin_trace"))
    admin_lineage = _mapping(admin_trace.get("report_lineage"))
    founder_admin_binding_matches = _founder_report_binding_matches(
        browser,
        report_json,
        admin_trace,
        admin_lineage,
    )

    html_case_id: str | None = None
    html_report_id_matches = False
    html_path = report_paths["html"]
    if html_path is not None and html_path.is_file():
        html_text = _read_text(html_path, "report_html", fail_reasons)
        html_case_id = _html_case_id(html_text)
        html_report_id_matches = json_report_id is not None and _html_contains_report_id(
            html_text, json_report_id
        )

    pdf_path = report_paths["pdf"]
    if pdf_path is not None and pdf_path.is_file():
        if pdf_path.resolve() != sample_pdf_path.resolve():
            fail_reasons.append("sample_pdf_lineage_mismatch")
        if not _is_pdf(pdf_path):
            fail_reasons.append("sample_pdf_invalid")

    html_lineage_matches = (
        html_case_id == normalized_case_id
        if html_case_id is not None
        else html_report_id_matches or founder_admin_binding_matches
    )
    json_lineage_matches = (
        json_case_id == normalized_case_id
        if json_case_id is not None
        else founder_admin_binding_matches
    )
    if normalized_case_id is None or not json_lineage_matches or not html_lineage_matches:
        fail_reasons.append("report_lineage_case_mismatch")

    lineage = {kind: path.name for kind, path in report_paths.items() if path is not None}
    if normalized_case_id is not None:
        lineage = {"case_id": normalized_case_id, **lineage}
    return normalized_case_id, lineage


def _approved_report_lineage(
    browser: Mapping[str, object],
    *,
    browser_evidence_path: Path,
    fail_reasons: list[str],
) -> dict[str, str]:
    if not _has_approved_report_lineage_evidence(browser):
        return {}

    report_paths: dict[str, Path | None] = {}
    for kind in ("json", "html", "pdf"):
        raw_path = browser.get(f"report_{kind}_path")
        path = (
            _resolve_owned_evidence_path(
                browser_evidence_path,
                raw_path,
                f"report_{kind}_path",
                fail_reasons,
            )
            if isinstance(raw_path, str)
            else None
        )
        report_paths[kind] = path
        if path is None or not path.is_file():
            fail_reasons.append(f"report_{kind}_missing")

    report_json_payload: dict[str, object] = {}
    json_path = report_paths["json"]
    if json_path is not None and json_path.is_file():
        report_json_payload = _read_json(json_path, "report_json", fail_reasons)

    admin_trace = _mapping(browser.get("admin_trace"))
    admin_lineage = _mapping(admin_trace.get("report_lineage"))
    admin_report_id = admin_lineage.get("report_id")
    admin_report_revision = admin_lineage.get("report_revision", admin_lineage.get("revision"))
    admin_report_checksum = admin_lineage.get("report_checksum", admin_lineage.get("checksum"))
    report_hash = report_json_payload.get("report_hash")
    json_report_checksum = (
        report_hash.removeprefix("sha256:") if isinstance(report_hash, str) else None
    )
    canonical_binding_matches = (
        admin_report_id == report_json_payload.get("id")
        and admin_report_revision == report_json_payload.get("data_revision")
        and admin_report_checksum == json_report_checksum
    )
    founder_binding_matches = _founder_report_binding_matches(
        browser,
        report_json_payload,
        admin_trace,
        admin_lineage,
    )
    admin_lineage_valid = (
        admin_trace.get("case_id") == browser.get("case_id")
        and _is_uuid(admin_report_id)
        and _positive_int(admin_report_revision)
        and _is_hex_sha256(admin_report_checksum)
        and (canonical_binding_matches or founder_binding_matches)
    )
    if not admin_lineage_valid:
        fail_reasons.append("report_admin_lineage_mismatch")

    report_artifact_hashes = _mapping(browser.get("report_artifact_hashes"))
    actual_report_hashes: dict[str, str] = {}
    for kind, path in report_paths.items():
        if path is None or not path.is_file():
            continue
        actual_hash = _hash_file(path)
        actual_report_hashes[kind] = actual_hash
        if report_artifact_hashes.get(kind) != actual_hash:
            fail_reasons.append(f"report_{kind}_hash_mismatch")

    if not admin_lineage_valid:
        return {}
    lineage = {
        "report_checksum": str(admin_report_checksum),
        "report_html_hash": actual_report_hashes.get("html", ""),
        "report_id": str(admin_report_id),
        "report_json_hash": actual_report_hashes.get("json", ""),
        "report_pdf_hash": actual_report_hashes.get("pdf", ""),
        "report_revision": str(admin_report_revision),
    }
    return lineage if _approved_report_lineage_shape_valid(lineage) else {}


def _has_approved_report_lineage_evidence(browser: Mapping[str, object]) -> bool:
    return "admin_trace" in browser or "report_artifact_hashes" in browser


def _live_provider_smoke_status(
    browser: Mapping[str, object],
    fail_reasons: list[str],
) -> str:
    live_smoke = _mapping(browser.get("live_provider_smoke"))
    status = live_smoke.get("status")
    if status != "deferred_by_policy":
        fail_reasons.append("live_provider_smoke_status_invalid")
        return str(status) if status is not None else "missing"
    return status


def _validate_screenshot_dimensions(
    dimensions: Mapping[str, Mapping[str, int]],
    *,
    visual_evidence_mode: str,
    fail_reasons: list[str],
) -> None:
    for viewport, expected in _expected_screenshot_dimensions(visual_evidence_mode).items():
        if dimensions.get(viewport) != expected:
            fail_reasons.append(f"{viewport}_screenshot_dimensions_invalid")


def _png_dimensions(path: Path, name: str, fail_reasons: list[str]) -> dict[str, int]:
    try:
        header = path.read_bytes()[:24]
    except OSError:
        fail_reasons.append(f"{name}_missing")
        return {"width": 0, "height": 0}
    if len(header) < 24 or not header.startswith(_PNG_SIGNATURE) or header[12:16] != b"IHDR":
        fail_reasons.append(f"{name}_invalid")
        return {"width": 0, "height": 0}
    return {
        "width": int.from_bytes(header[16:20], "big"),
        "height": int.from_bytes(header[20:24], "big"),
    }


def _validate_commit_consistency(
    payloads: tuple[Mapping[str, object], ...],
    fail_reasons: list[str],
) -> None:
    commit_ids = [payload.get("commit_id") for payload in payloads]
    if not all(isinstance(commit_id, str) and commit_id for commit_id in commit_ids):
        fail_reasons.append("gate_commit_id_missing")
        return
    if len(set(commit_ids)) != 1:
        fail_reasons.append("gate_commit_id_mismatch")


def _offline_no_key_valid(
    payload: Mapping[str, object],
    *,
    require_startup_key: bool,
) -> bool:
    evidence = _mapping(payload.get("offline_no_key"))
    if evidence.get("openai_api_key_blank") is not True:
        return False
    if require_startup_key and evidence.get("openai_startup_api_key_blank") is not True:
        return False
    return bool(evidence) and all(value is True for value in evidence.values())


def _gate_d_runtime_path(
    gate_result_path: Path,
    gate_result: Mapping[str, object],
    gate_name: str,
    fail_reasons: list[str],
) -> Path | None:
    artifact_paths = _mapping(gate_result.get("artifact_paths"))
    raw_path = artifact_paths.get("runtime_runtime_evidence")
    if not isinstance(raw_path, str) or not raw_path:
        fail_reasons.append(f"{gate_name}_runtime_evidence_missing")
        return None
    return _resolve_owned_evidence_path(
        gate_result_path,
        raw_path,
        f"{gate_name}_runtime_evidence_path",
        fail_reasons,
    )


def _resolve_owned_evidence_path(
    owner_path: Path,
    raw_path: str,
    name: str,
    fail_reasons: list[str],
) -> Path | None:
    candidate = Path(raw_path)
    if ".." in candidate.parts:
        fail_reasons.append(_path_fail_reason(name))
        return None
    owner_root = owner_path.parent.resolve()
    candidates = (
        (candidate.resolve(),)
        if candidate.is_absolute()
        else ((owner_root / candidate).resolve(), candidate.resolve())
    )
    confined: list[Path] = []
    for resolved in candidates:
        try:
            resolved.relative_to(owner_root)
        except ValueError:
            continue
        confined.append(resolved)
        if resolved.exists():
            return resolved
    if confined:
        return confined[0]
    fail_reasons.append(_path_fail_reason(name))
    return None


def _path_fail_reason(name: str) -> str:
    if name.startswith("report_"):
        return f"{name}_outside_evidence_dir"
    return f"{name}_invalid"


def _artifact_paths(
    inputs: SellableDemoFreezeInputs,
    *,
    visual_evidence_mode: str,
    runtime_first_path: Path | None,
    runtime_second_path: Path | None,
    desktop_state_paths: tuple[Path, ...],
) -> dict[str, str]:
    paths: dict[str, Path | None] = {
        "packet": Path(PACKET_FILENAME),
        "gate_b_result": inputs.gate_b_result_path,
        "gate_c_result": inputs.gate_c_result_path,
        "gate_d_first_result": inputs.gate_d_first_result_path,
        "gate_d_second_result": inputs.gate_d_second_result_path,
        "gate_d_first_runtime_evidence": runtime_first_path,
        "gate_d_second_runtime_evidence": runtime_second_path,
        "gate_e_result": inputs.gate_e_result_path,
        "browser_evidence": inputs.browser_evidence_path,
        "desktop_screenshot": inputs.desktop_screenshot_path,
        "mobile_screenshot": inputs.mobile_screenshot_path,
        "sample_pdf": inputs.sample_pdf_path,
        "demo_script": inputs.demo_script_path,
        "capstone_map": inputs.capstone_map_path,
    }
    if visual_evidence_mode == DESKTOP_14_STATE_MODE:
        paths.pop("mobile_screenshot", None)
        paths.update(_desktop_state_artifact_paths(desktop_state_paths))
    return {name: path.name for name, path in paths.items() if path is not None}


def _artifact_hashes(
    inputs: SellableDemoFreezeInputs,
    *,
    visual_evidence_mode: str,
    runtime_first_path: Path | None,
    runtime_second_path: Path | None,
    desktop_state_paths: tuple[Path, ...],
    fail_reasons: list[str],
) -> dict[str, str]:
    paths: dict[str, Path | None] = {
        "gate_b_result": inputs.gate_b_result_path,
        "gate_c_result": inputs.gate_c_result_path,
        "gate_d_first_result": inputs.gate_d_first_result_path,
        "gate_d_second_result": inputs.gate_d_second_result_path,
        "gate_d_first_runtime_evidence": runtime_first_path,
        "gate_d_second_runtime_evidence": runtime_second_path,
        "gate_e_result": inputs.gate_e_result_path,
        "browser_evidence": inputs.browser_evidence_path,
        "desktop_screenshot": inputs.desktop_screenshot_path,
        "mobile_screenshot": inputs.mobile_screenshot_path,
        "sample_pdf": inputs.sample_pdf_path,
        "demo_script": inputs.demo_script_path,
        "capstone_map": inputs.capstone_map_path,
    }
    if visual_evidence_mode == DESKTOP_14_STATE_MODE:
        paths.pop("mobile_screenshot", None)
        paths.update(_desktop_state_artifact_paths(desktop_state_paths))
    hashes: dict[str, str] = {}
    for name, path in paths.items():
        if path is None:
            continue
        try:
            hashes[name] = _hash_file(path)
        except OSError:
            fail_reasons.append(f"{name}_hash_unavailable")
    return hashes


def _read_json(path: Path, name: str, fail_reasons: list[str]) -> dict[str, object]:
    try:
        size = path.stat().st_size
        if size > MAX_JSON_BYTES:
            fail_reasons.append(f"{name}_too_large")
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail_reasons.append(f"{name}_missing")
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail_reasons.append(f"{name}_invalid")
        return {}
    if not isinstance(payload, dict):
        fail_reasons.append(f"{name}_invalid")
        return {}
    return {str(key): value for key, value in payload.items()}


def _read_optional_json(
    path: Path | None,
    name: str,
    fail_reasons: list[str],
) -> dict[str, object]:
    if path is None:
        return {}
    return _read_json(path, name, fail_reasons)


def _read_text(path: Path, name: str, fail_reasons: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail_reasons.append(f"{name}_invalid")
        return ""


def _validate_non_empty_text(path: Path, name: str, fail_reasons: list[str]) -> None:
    if not _read_text(path, name, fail_reasons).strip():
        fail_reasons.append(f"{name}_empty")


def _read_text_for_privacy(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _report_privacy_sources(
    browser: Mapping[str, object],
    *,
    browser_evidence_path: Path,
    sample_pdf_path: Path,
    fail_reasons: list[str],
) -> tuple[str, ...]:
    sources: list[str] = []
    for kind in ("json", "html"):
        raw_path = browser.get(f"report_{kind}_path")
        if not isinstance(raw_path, str):
            continue
        path = _resolve_owned_evidence_path(
            browser_evidence_path,
            raw_path,
            f"report_{kind}_path",
            fail_reasons,
        )
        if path is None:
            continue
        sources.append(_read_bounded_privacy_text(path, f"report_{kind}", fail_reasons))
    sources.append(_read_bounded_privacy_bytes(sample_pdf_path, "sample_pdf", fail_reasons))
    return tuple(sources)


def _founder_report_internal_leak_count(
    browser: Mapping[str, object],
    *,
    browser_evidence_path: Path,
    fail_reasons: list[str],
) -> int:
    raw_path = browser.get("report_json_path")
    if not isinstance(raw_path, str):
        return 0
    path = _resolve_owned_evidence_path(
        browser_evidence_path,
        raw_path,
        "report_json_path",
        fail_reasons,
    )
    if path is None or not path.is_file():
        return 0
    payload = _read_json(path, "report_json", fail_reasons)
    return _count_founder_report_internal_values(payload)


def _count_founder_report_internal_values(value: object) -> int:
    if isinstance(value, Mapping):
        return sum(
            (1 if str(key).casefold() in _FOUNDER_REPORT_FORBIDDEN_KEYS else 0)
            + _count_founder_report_internal_values(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return sum(_count_founder_report_internal_values(item) for item in value)
    if isinstance(value, str):
        return len(_FOUNDER_REPORT_FORBIDDEN_VALUE_RE.findall(value))
    return 0


def _read_bounded_privacy_text(
    path: Path,
    name: str,
    fail_reasons: list[str],
) -> str:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            fail_reasons.append(f"{name}_privacy_scan_too_large")
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail_reasons.append(f"{name}_privacy_scan_invalid")
        return ""


def _read_bounded_privacy_bytes(
    path: Path,
    name: str,
    fail_reasons: list[str],
) -> str:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            fail_reasons.append(f"{name}_privacy_scan_too_large")
            return ""
        payload = path.read_bytes()
        masked_streams = _PDF_STREAM_RE.search(payload) is not None
        raw_text = _mask_email_like_pdf_stream_bytes(payload).decode("latin-1")
        extracted_text, parsed = _extract_pdf_privacy_text(path)
        if not parsed and masked_streams:
            fail_reasons.append(f"{name}_privacy_parse_failed")
        if len(extracted_text.encode("utf-8")) > MAX_JSON_BYTES:
            fail_reasons.append(f"{name}_privacy_scan_too_large")
            return raw_text
        return f"{raw_text}\n{extracted_text}"
    except OSError:
        fail_reasons.append(f"{name}_privacy_scan_invalid")
        return ""


def _mask_email_like_pdf_stream_bytes(payload: bytes) -> bytes:
    def replace_stream(match: re.Match[bytes]) -> bytes:
        stream_payload = _EMAIL_LIKE_BYTES_RE.sub(b"", match.group(2))
        stream_payload = _WINDOWS_PATH_LIKE_BYTES_RE.sub(b"", stream_payload)
        return match.group(1) + stream_payload + match.group(3)

    return _PDF_STREAM_RE.sub(replace_stream, payload)


def _extract_pdf_privacy_text(path: Path) -> tuple[str, bool]:
    try:
        open_pdf: Any = getattr(pymupdf, "open")
        document: Any = open_pdf(path)
        try:
            metadata = getattr(document, "metadata", {})
            metadata_text = "\n".join(
                value for value in metadata.values() if isinstance(value, str)
            )
            page_text = "\n".join(str(page.get_text("text")) for page in document)
            return f"{metadata_text}\n{page_text}", True
        finally:
            document.close()
    except Exception:  # PyMuPDF exposes format-specific parser errors
        return "", False


def _html_case_id(html_text: str) -> str | None:
    for pattern in (_HTML_CASE_ID_RE, _HTML_METADATA_CASE_ID_RE):
        match = pattern.search(html_text)
        if match is not None:
            return match.group(1).strip()
    return None


def _html_contains_report_id(html_text: str, report_id: str) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(report_id)}(?![A-Za-z0-9_-])")
    return pattern.search(html_text) is not None


def _is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4) == b"%PDF"
    except OSError:
        return False


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _packet_hash(payload: Mapping[str, object]) -> str:
    canonical = {str(key): value for key, value in payload.items() if key != "packet_hash"}
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


def _packet_from_payload(payload: Mapping[str, object]) -> SellableDemoFreezePacket:
    raw_case_id = payload.get("case_id")
    case_id = raw_case_id if isinstance(raw_case_id, str) else None
    return SellableDemoFreezePacket(
        schema_version=_string(payload.get("schema_version"), "invalid"),
        sellable_demo_passed=payload.get("sellable_demo_passed") is True,
        packet_hash=_string(payload.get("packet_hash"), ""),
        gates=_string_dict(payload.get("gates")),
        gate_d_semantic_equivalence=payload.get("gate_d_semantic_equivalence") is True,
        gate_d_raw_hashes=_string_dict(payload.get("gate_d_raw_hashes")),
        screenshot_dimensions=_dimensions(payload.get("screenshot_dimensions")),
        case_id=case_id,
        report_lineage=_string_dict(payload.get("report_lineage")),
        live_provider_smoke_status=_string(
            payload.get("live_provider_smoke_status"),
            "missing",
        ),
        visual_evidence_mode=_string(
            payload.get("visual_evidence_mode"),
            LEGACY_DESKTOP_MOBILE_MODE,
        ),
        desktop_state_order=_string_tuple(payload.get("desktop_state_order")),
        approved_report_lineage_policy=_string(
            payload.get("approved_report_lineage_policy"),
            "optional",
        ),
        approved_report_lineage=_string_dict(payload.get("approved_report_lineage")),
        fail_reasons=_string_tuple(payload.get("fail_reasons")),
        artifact_paths=_string_dict(payload.get("artifact_paths")),
        artifact_hashes=_string_dict(payload.get("artifact_hashes")),
    )


def _dimensions(value: object) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for viewport, raw_dimensions in _mapping(value).items():
        dimensions = _mapping(raw_dimensions)
        width = dimensions.get("width")
        height = dimensions.get("height")
        if isinstance(width, int) and isinstance(height, int):
            result[str(viewport)] = {"width": width, "height": height}
    return result


def _sanitized_browser_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): _strip_path_values(value)
        for key, value in payload.items()
        if not str(key).endswith("_path") and str(key) != "path"
    }


def _strip_path_values(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _strip_path_values(item)
            for key, item in value.items()
            if not str(key).endswith("_path") and str(key) != "path"
        }
    if isinstance(value, list):
        return [_strip_path_values(item) for item in value]
    return value


def _privacy_leak_count(values: tuple[object, ...]) -> int:
    serialized = "\n".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        if not isinstance(value, str)
        else value
        for value in values
    )
    return len(_SENSITIVE_VALUE_RE.findall(serialized))


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_dict(value: object) -> dict[str, str]:
    return {str(key): item for key, item in _mapping(value).items() if isinstance(item, str)}


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _string(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_string(value: object) -> bool:
    return isinstance(value, str) and value.isdecimal() and int(value) > 0


def _founder_report_data_revision(payload: Mapping[str, object]) -> int | None:
    if set(payload) != _EXPECTED_FOUNDER_REPORT_TOP_LEVEL:
        return None
    data_revision = payload.get("data_revision")
    return data_revision if type(data_revision) is int and data_revision > 0 else None


def _founder_report_binding_matches(
    browser: Mapping[str, object],
    report_json_payload: Mapping[str, object],
    admin_trace: Mapping[str, object],
    admin_lineage: Mapping[str, object],
) -> bool:
    founder_data_revision = _founder_report_data_revision(report_json_payload)
    report_metadata = _mapping(browser.get("report_metadata"))
    snapshot_hash = report_metadata.get("snapshot_hash")
    snapshot_checksum = (
        snapshot_hash.removeprefix("sha256:") if isinstance(snapshot_hash, str) else None
    )
    return (
        founder_data_revision is not None
        and set(report_metadata) == _EXPECTED_BROWSER_REPORT_METADATA
        and report_metadata.get("case_id") == browser.get("case_id")
        and admin_trace.get("case_id") == browser.get("case_id")
        and _is_uuid(report_metadata.get("snapshot_id"))
        and _is_sha256(snapshot_hash)
        and _positive_int(report_metadata.get("snapshot_revision"))
        and report_metadata.get("snapshot_revision") == founder_data_revision
        and admin_lineage.get("report_id") == report_metadata.get("snapshot_id")
        and admin_lineage.get("report_revision", admin_lineage.get("revision"))
        == report_metadata.get("snapshot_revision")
        and admin_lineage.get("report_checksum", admin_lineage.get("checksum")) == snapshot_checksum
    )


def _approved_report_lineage_shape_valid(lineage: Mapping[str, object]) -> bool:
    return (
        set(lineage) == _EXPECTED_APPROVED_REPORT_LINEAGE
        and _is_uuid(lineage.get("report_id"))
        and _positive_int_string(lineage.get("report_revision"))
        and _is_hex_sha256(lineage.get("report_checksum"))
        and all(
            _is_sha256(lineage.get(kind))
            for kind in ("report_json_hash", "report_html_hash", "report_pdf_hash")
        )
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_hex_sha256(value: object) -> bool:
    return (
        isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value, re.IGNORECASE) is not None
    )


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False

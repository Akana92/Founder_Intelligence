from __future__ import annotations

from hashlib import sha256
import json
import struct
from pathlib import Path
from typing import Any

import pytest


def test_sellable_demo_freeze_packet_records_required_artifacts_and_stable_hash(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        SellableDemoFreezeInputs,
        build_sellable_demo_freeze_packet,
        validate_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path)

    first = build_sellable_demo_freeze_packet(inputs)
    second = build_sellable_demo_freeze_packet(
        SellableDemoFreezeInputs(
            output_dir=tmp_path / "freeze-output-second",
            gate_b_result_path=inputs.gate_b_result_path,
            gate_c_result_path=inputs.gate_c_result_path,
            gate_d_first_result_path=inputs.gate_d_first_result_path,
            gate_d_second_result_path=inputs.gate_d_second_result_path,
            gate_e_result_path=inputs.gate_e_result_path,
            browser_evidence_path=inputs.browser_evidence_path,
            desktop_screenshot_path=inputs.desktop_screenshot_path,
            mobile_screenshot_path=inputs.mobile_screenshot_path,
            sample_pdf_path=inputs.sample_pdf_path,
            demo_script_path=inputs.demo_script_path,
            capstone_map_path=inputs.capstone_map_path,
        )
    )

    assert first.fail_reasons == ()
    assert first.sellable_demo_passed is True
    assert first.packet_hash == second.packet_hash
    assert first.artifact_paths["packet"] == "sellable-demo-freeze-packet.json"
    assert all(not Path(path).is_absolute() for path in first.artifact_paths.values())
    assert first.artifact_paths["sample_pdf"].endswith("sample-report.pdf")
    assert first.artifact_hashes["sample_pdf"] == _hash(inputs.sample_pdf_path)
    assert first.visual_evidence_mode == "desktop_mobile"
    assert first.screenshot_dimensions == {
        "desktop": {"width": 1440, "height": 1000},
        "mobile": {"width": 390, "height": 844},
    }
    assert first.case_id == "startup-case-001"
    assert first.live_provider_smoke_status == "deferred_by_policy"
    assert first.report_lineage == {
        "case_id": "startup-case-001",
        "json": "report.json",
        "html": "report.html",
        "pdf": "sample-report.pdf",
    }

    packet_path = inputs.output_dir / first.artifact_paths["packet"]
    persisted = json.loads(packet_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == "sellable_demo_freeze_packet@1"
    assert persisted["packet_hash"] == first.packet_hash
    assert persisted["gates"] == {
        "gate_b": "pass",
        "gate_c": "pass",
        "gate_d_first": "pass",
        "gate_d_second": "pass",
        "gate_e": "pass",
    }

    validation = validate_sellable_demo_freeze_packet(packet_path)
    assert validation.sellable_demo_passed is True
    assert validation.fail_reasons == ()


def test_sellable_demo_freeze_accepts_canonical_desktop_state_suite_without_mobile(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
        validate_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path, desktop_state_order=CANONICAL_DESKTOP_STATE_SCREENSHOTS)

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.fail_reasons == ()
    assert result.sellable_demo_passed is True
    assert result.visual_evidence_mode == "desktop_14_state"
    assert result.screenshot_dimensions == {"desktop": {"width": 1440, "height": 1000}}
    assert result.desktop_state_order == CANONICAL_DESKTOP_STATE_SCREENSHOTS
    assert "mobile_screenshot" not in result.artifact_paths
    assert "mobile_screenshot" not in result.artifact_hashes

    packet_path = inputs.output_dir / "sellable-demo-freeze-packet.json"
    validation = validate_sellable_demo_freeze_packet(packet_path)
    assert validation.sellable_demo_passed is True
    assert validation.fail_reasons == ()


def test_sellable_demo_freeze_rejects_noncanonical_desktop_state_order(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    bad_order = list(CANONICAL_DESKTOP_STATE_SCREENSHOTS)
    bad_order[0], bad_order[1] = bad_order[1], bad_order[0]
    inputs = _freeze_inputs(tmp_path, desktop_state_order=tuple(bad_order))

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.sellable_demo_passed is False
    assert "desktop_states_browser_contract_invalid" in result.fail_reasons
    assert result.visual_evidence_mode == "desktop_14_state"


def test_sellable_demo_freeze_accepts_gate_d_semantic_match_when_raw_hashes_differ(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(
        tmp_path,
        gate_d_first_runtime_fingerprints=("semantic:A", "persisted:A"),
        gate_d_second_runtime_fingerprints=("semantic:A", "persisted:A"),
        gate_d_latency_minutes=(0.125, 0.25),
    )

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.fail_reasons == ()
    assert result.sellable_demo_passed is True
    assert result.gate_d_semantic_equivalence is True


def test_sellable_demo_freeze_rejects_gate_d_semantic_mismatch(tmp_path: Path) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(
        tmp_path,
        gate_d_first_runtime_fingerprints=("semantic:A", "persisted:A"),
        gate_d_second_runtime_fingerprints=("semantic:B", "persisted:A"),
    )

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.sellable_demo_passed is False
    assert "gate_d_semantic_fingerprint_mismatch" in result.fail_reasons


def test_sellable_demo_freeze_rejects_bad_browser_screenshot_dimensions(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path, mobile_dimensions=(412, 915))

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.sellable_demo_passed is False
    assert "mobile_screenshot_dimensions_invalid" in result.fail_reasons


def test_sellable_demo_freeze_rejects_cross_case_report_lineage(tmp_path: Path) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path, report_html_case_id="other-case")

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.sellable_demo_passed is False
    assert "report_lineage_case_mismatch" in result.fail_reasons


def test_sellable_demo_freeze_scans_packet_for_sensitive_values(tmp_path: Path) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path, browser_base_url="http://127.0.0.1:3000/C:/Users/Akana")

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.sellable_demo_passed is False
    assert "privacy_leaks_detected" in result.fail_reasons


@pytest.mark.parametrize(
    "forbidden_marker",
    (
        {"status": "MISSING"},
        {"raw_block": "document_text_block"},
        {"prompt_versions": ["startup-report@internal"]},
        {"trace_ids": ["trace-internal-001"]},
        {"source_hashes": {"doc-0001": "sha256:" + "a" * 64}},
        {"hash_table": {"report_hash": "sha256:" + "b" * 64}},
    ),
)
def test_sellable_demo_freeze_scans_report_json_for_internal_markers(
    tmp_path: Path,
    forbidden_marker: dict[str, object],
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path)
    report_json_path = inputs.browser_evidence_path.parent / "report.json"
    report_json = json.loads(report_json_path.read_text(encoding="utf-8"))
    report_json["sections"] = {"internal_marker_probe": forbidden_marker}
    report_json_path.write_text(json.dumps(report_json), encoding="utf-8")

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.sellable_demo_passed is False
    assert "privacy_leaks_detected" in result.fail_reasons


@pytest.mark.parametrize("artifact_kind", ["html", "pdf"])
def test_sellable_demo_freeze_scans_report_artifacts_for_sensitive_values(
    tmp_path: Path,
    artifact_kind: str,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path)
    sensitive_value = "OPENAI_API_KEY=" + "sk-" + ("A" * 24)
    if artifact_kind == "html":
        report_html_path = inputs.browser_evidence_path.parent / "report.html"
        report_html_path.write_text(
            report_html_path.read_text(encoding="utf-8") + sensitive_value,
            encoding="utf-8",
        )
    else:
        inputs.sample_pdf_path.write_bytes(
            b"%PDF-1.4\n" + sensitive_value.encode("ascii") + b"\n%%EOF\n"
        )

    result = build_sellable_demo_freeze_packet(inputs)

    assert result.sellable_demo_passed is False
    assert "privacy_leaks_detected" in result.fail_reasons


def test_sellable_demo_freeze_validation_rejects_rehashed_incomplete_packet(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        build_sellable_demo_freeze_packet,
        validate_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path)
    build_sellable_demo_freeze_packet(inputs)
    packet_path = inputs.output_dir / "sellable-demo-freeze-packet.json"
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    payload.pop("gates")
    payload["packet_hash"] = _canonical_packet_hash(payload)
    packet_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_sellable_demo_freeze_packet(packet_path)

    assert result.sellable_demo_passed is False
    assert "packet_gates_invalid" in result.fail_reasons


def test_sellable_demo_freeze_rejects_existing_output_root_before_dispatch(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        SellableDemoFreezeInputs,
        build_sellable_demo_freeze_packet,
    )

    inputs = _freeze_inputs(tmp_path)
    stale = inputs.output_dir / "sellable-demo-freeze-packet.json"
    inputs.output_dir.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="^evaluation_output_dir_not_empty$"):
        build_sellable_demo_freeze_packet(
            SellableDemoFreezeInputs(
                output_dir=inputs.output_dir,
                gate_b_result_path=Path("missing-gate-b.json"),
                gate_c_result_path=Path("missing-gate-c.json"),
                gate_d_first_result_path=Path("missing-gate-d-a.json"),
                gate_d_second_result_path=Path("missing-gate-d-b.json"),
                gate_e_result_path=Path("missing-gate-e.json"),
                browser_evidence_path=Path("missing-browser.json"),
                desktop_screenshot_path=Path("missing-desktop.png"),
                mobile_screenshot_path=Path("missing-mobile.png"),
                sample_pdf_path=Path("missing.pdf"),
                demo_script_path=Path("missing-demo.md"),
                capstone_map_path=Path("missing-map.md"),
            )
        )

    assert stale.read_text(encoding="utf-8") == "stale"


def _freeze_inputs(
    tmp_path: Path,
    *,
    gate_d_first_runtime_fingerprints: tuple[str, str] = ("semantic:A", "persisted:A"),
    gate_d_second_runtime_fingerprints: tuple[str, str] = ("semantic:A", "persisted:A"),
    gate_d_latency_minutes: tuple[float, float] = (0.125, 0.25),
    mobile_dimensions: tuple[int, int] = (390, 844),
    desktop_state_order: tuple[str, ...] | None = None,
    report_html_case_id: str = "startup-case-001",
    browser_base_url: str = "http://127.0.0.1:3000",
) -> Any:
    from due_diligence_agent.evals.sellable_demo_freeze import SellableDemoFreezeInputs

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    gate_b = evidence_root / "gate-b.json"
    gate_b.write_text(
        json.dumps(
            {
                "dataset": "public_us_frozen_v1",
                "schema_validity": 1.0,
                "critical_evidence_coverage": 1.0,
                "unsupported_critical_claim_rate": 0.0,
                "numerical_accuracy": 1.0,
                "unit_period_consistency": 1.0,
                "retrieval_recall_at_5": 1.0,
                "privacy_leak_count": 0,
                "trace_completeness": 1.0,
                "reflexion_max_rounds": 2,
                "budget_violations": 0,
                "offline_latency_minutes": 0.125,
                "report_completeness": 1.0,
                "exporter_outage_non_blocking": True,
                "checkpoint_recovery": True,
                "gate_b_passed": True,
                "fail_reasons": [],
                "artifact_paths": {"eval_result": "gate-b.json"},
                "commit_id": "abc123",
                "offline_no_key": {
                    "openai_api_key_blank": True,
                    "tracing_disabled": True,
                },
            }
        ),
        encoding="utf-8",
    )
    gate_c = evidence_root / "gate-c.json"
    gate_c.write_text(
        json.dumps(
            {
                "dataset": "startup_secure_ingest_v1",
                "gate_c_passed": True,
                "gate_b_passed": True,
                "privacy_leak_count": 0,
                "denied_gate2_external_calls": 0,
                "offline_latency_minutes": 0.125,
                "profile_determinism": True,
                "required_profile_field_status_coverage": 1.0,
                "contradiction_retention": True,
                "parse_format_coverage": ["csv", "docx", "jpeg", "pdf", "png", "safe_zip", "xlsx"],
                "restart_equivalence": True,
                "canonical_profile_hash": "a" * 64,
                "fail_reasons": [],
                "command_evidence": [],
                "artifact_paths": {"eval_result": "gate-c.json"},
                "commit_id": "abc123",
                "environment": {"python": "3.12.0", "platform": "test"},
                "offline_no_key": _offline_no_key(),
            }
        ),
        encoding="utf-8",
    )
    gate_d_first = _gate_d_result(
        evidence_root / "gate-d-a",
        gate_d_first_runtime_fingerprints,
        gate_d_latency_minutes[0],
    )
    gate_d_second = _gate_d_result(
        evidence_root / "gate-d-b",
        gate_d_second_runtime_fingerprints,
        gate_d_latency_minutes[1],
    )
    gate_e = evidence_root / "gate-e.json"
    gate_e.write_text(
        json.dumps(
            {
                "schema_version": "gate_e_result@1",
                "dataset": "capstone_combined_v1",
                "gate_e_passed": True,
                "public_passed": True,
                "gate_c_passed": True,
                "gate_d_passed": True,
                "compatibility_ok": True,
                "report_repo_sanitized": True,
                "pdf_fallback_ok": True,
                "checkpoint_recovery_ok": True,
                "shared_schema_ok": True,
                "offline_latency_minutes": 0.25,
                "fail_reasons": [],
                "command_evidence": [],
                "artifact_paths": {"eval_result": "gate-e.json"},
                "commit_id": "abc123",
                "environment": {"python": "3.12.0", "platform": "test"},
                "offline_no_key": _offline_no_key(),
                "public_artifact_paths": {"eval_result": "gate-b.json"},
                "startup_artifact_paths": {"eval_result": "gate-d.json"},
            }
        ),
        encoding="utf-8",
    )

    sample_pdf = evidence_root / "sample-report.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n% frozen sample\n")
    report_json = evidence_root / "report.json"
    report_json.write_text(json.dumps({"case_id": "startup-case-001"}), encoding="utf-8")
    report_html = evidence_root / "report.html"
    report_html.write_text(
        (
            '<html><section id="metadata"><table><tbody>'
            f"<tr><td>case_id</td><td>{report_html_case_id}</td></tr>"
            "</tbody></table></section></html>"
        ),
        encoding="utf-8",
    )
    screenshots: dict[str, object]
    if desktop_state_order is None:
        screenshots = {
            "desktop": {
                "path": str(evidence_root / "desktop.png"),
                "width": 1440,
                "height": 1000,
            },
            "mobile": {
                "path": str(evidence_root / "mobile.png"),
                "width": mobile_dimensions[0],
                "height": mobile_dimensions[1],
            },
        }
    else:
        screenshots = {
            "desktop_states": {
                "order": list(desktop_state_order),
                "path": "desktop-states",
                "viewport": {"width": 1440, "height": 1000},
            }
        }

    browser_evidence = evidence_root / "browser-evidence.json"
    browser_evidence.write_text(
        json.dumps(
            {
                "schema_version": "founder_browser_smoke_evidence@1",
                "base_url": browser_base_url,
                "offline": True,
                "network_external_calls": 0,
                "case_id": "startup-case-001",
                "gate4_status": "approved",
                "live_provider_smoke": {"status": "deferred_by_policy"},
                "report_json_path": str(report_json),
                "report_html_path": str(report_html),
                "report_pdf_path": str(sample_pdf),
                "startup_profile_fields": 18,
                "gtm_dimensions": 7,
                "readiness_dimensions": 22,
                "chart_cards": 3,
                "chart_points": 8,
                "screenshots": screenshots,
            }
        ),
        encoding="utf-8",
    )
    desktop = evidence_root / "desktop.png"
    mobile = evidence_root / "mobile.png"
    _write_png(desktop, 1440, 1000)
    _write_png(mobile, *mobile_dimensions)
    if desktop_state_order is not None:
        desktop = _write_desktop_states(evidence_root, desktop_state_order)
    demo_script = evidence_root / "demo-script.md"
    demo_script.write_text("# 7-10 minute demo script\n", encoding="utf-8")
    capstone_map = evidence_root / "capstone-map.md"
    capstone_map.write_text("# Capstone requirement map\n", encoding="utf-8")

    return SellableDemoFreezeInputs(
        output_dir=tmp_path / "freeze-output",
        gate_b_result_path=gate_b,
        gate_c_result_path=gate_c,
        gate_d_first_result_path=gate_d_first,
        gate_d_second_result_path=gate_d_second,
        gate_e_result_path=gate_e,
        browser_evidence_path=browser_evidence,
        desktop_screenshot_path=desktop,
        mobile_screenshot_path=mobile if desktop_state_order is None else None,
        sample_pdf_path=sample_pdf,
        demo_script_path=demo_script,
        capstone_map_path=capstone_map,
    )


def _gate_d_result(
    output_dir: Path,
    runtime_fingerprints: tuple[str, str],
    offline_latency_minutes: float,
) -> Path:
    output_dir.mkdir()
    runtime_path = output_dir / "runtime-evidence.json"
    runtime_path.write_text(
        json.dumps(
            {
                "schema_version": "startup_frozen_runtime_result@1",
                "dataset": "startup_synthetic_v1",
                "queue2_runtime_passed": True,
                "queue2_assertion_provenance": "runtime_api:startup_synthetic_v1",
                "case_count": 1,
                "privacy_leak_count": 0,
                "denied_gate2_external_calls": 0,
                "queue2_assertions": _queue2_assertions(),
                "fail_reasons": [],
                "cases": [
                    {
                        "case_name": "startup-case-001",
                        "evidence_source": "fixture:startup-case-001",
                        "uploaded_document_count": 1,
                        "provider_status": "available",
                        "gate2_status": "approved",
                        "gate3_status": "approved",
                        "gate4_status": "approved",
                        "report_status": "approved",
                        "report_json_status": 200,
                        "report_html_status": 200,
                        "report_pdf_status": 200,
                        "report_hash": "b" * 64,
                        "profile_hash": "c" * 64,
                        "readiness_snapshot_hash": "d" * 64,
                        "market_research_snapshot_hash": "e" * 64,
                        "metric_pack_hash": "f" * 64,
                        "readiness_question_count": 3,
                        "metric_count": 1,
                        "metric_formula_source_count": 1,
                        "contradiction_count": 1,
                        "unsupported_claim_count": 1,
                        "competitor_count": 1,
                        "competitor_source_ref_count": 1,
                        "source_appendix_hash_count": 1,
                        "runtime_trace_event_count": 1,
                        "runtime_node_count": 1,
                        "runtime_nodes_hash": "1" * 64,
                        "trace_to_report_lineage": True,
                        "semantic_fingerprint": runtime_fingerprints[0],
                        "persisted_hash_fingerprint": runtime_fingerprints[1],
                        "competitor_sources_resolved": True,
                        "competitor_sources_with_as_of": 1,
                        "privacy_leak_count": 0,
                        "semantic_fingerprint_match": True,
                        "persisted_hash_fingerprint_match": True,
                        "fail_reasons": [],
                    }
                ],
                "artifact_paths": {"runtime_evidence": "runtime-evidence.json"},
            }
        ),
        encoding="utf-8",
    )
    result_path = output_dir / "eval-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": "gate_d_result@1",
                "dataset": "startup_synthetic_v1",
                "gate_d_passed": True,
                "gate_b_passed": True,
                "gate_c_passed": True,
                "privacy_leak_count": 0,
                "denied_gate2_external_calls": 0,
                "offline_latency_minutes": offline_latency_minutes,
                "queue2_assertions": _queue2_assertions(),
                "queue2_assertion_provenance": "runtime_api:startup_synthetic_v1",
                "fail_reasons": [],
                "command_evidence": [],
                "artifact_paths": {
                    "eval_result": str(result_path),
                    "runtime_runtime_evidence": str(runtime_path),
                },
                "commit_id": "abc123",
                "environment": {"python": "3.12.0", "platform": "test"},
                "offline_no_key": _offline_no_key(),
            }
        ),
        encoding="utf-8",
    )
    return result_path


def _queue2_assertions() -> dict[str, object]:
    return {
        "profile_determinism": True,
        "readiness_scored": True,
        "metric_pack_hash": "f" * 64,
        "contradiction_count": 1,
        "unsupported_claim_count": 1,
        "report_sections_ok": True,
        "trace_sections_ok": True,
        "max_questions": 3,
    }


def _offline_no_key() -> dict[str, bool]:
    return {
        "openai_api_key_blank": True,
        "openai_startup_api_key_blank": True,
        "langsmith_tracing_disabled": True,
        "langchain_legacy_tracing_disabled": True,
        "langchain_tracing_disabled": True,
        "hf_hub_offline": True,
        "transformers_offline": True,
    }


def _write_desktop_states(evidence_root: Path, order: tuple[str, ...]) -> Path:
    states_root = evidence_root / "desktop-states"
    states_root.mkdir()
    states = []
    first_path: Path | None = None
    for index, filename in enumerate(order, start=1):
        path = states_root / filename
        _write_png(path, 1440, 1000)
        if first_path is None:
            first_path = path
        states.append(
            {
                "index": index,
                "file": filename,
                "path": filename,
                "viewport": {"width": 1440, "height": 1000},
                "overflow": {"verticalOverflowPx": 0, "tolerancePx": 1},
            }
        )
    (states_root / "desktop-state-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "founder_desktop_state_manifest@1",
                "order": list(order),
                "viewport": {"width": 1440, "height": 1000},
                "states": states,
            }
        ),
        encoding="utf-8",
    )
    assert first_path is not None
    return first_path


CANONICAL_DESKTOP_STATE_SCREENSHOTS = (
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


def _write_png(path: Path, width: int, height: int) -> None:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(signature + b"\x00\x00\x00\rIHDR" + ihdr + b"\x00\x00\x00\x00")


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _canonical_packet_hash(payload: dict[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "packet_hash"}
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"

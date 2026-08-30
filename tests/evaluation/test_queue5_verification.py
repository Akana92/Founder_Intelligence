from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from hashlib import sha256
import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from due_diligence_agent.evals.queue5_verification import Queue5VerificationInputs


CASE_ID = "00000000-0000-0000-0000-000000000951"
RUN_ID = "queue5-run-951"
REPORT_ID = "00000000-0000-0000-0000-000000000952"
PACKET_HASH = "sha256:" + "1" * 64
FROZEN_RAW_HASH = "sha256:" + "2" * 64
PDF_RAW_HASH = "sha256:" + "3" * 64
LANGSMITH_RAW_HASH = "sha256:" + "4" * 64
OPENAI_RAW_HASH = "sha256:" + "5" * 64
MATRIX_HASH = "sha256:" + "6" * 64
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
PROOF_TESTS = (
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


def test_verification_summary_keeps_four_status_namespaces_separate(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        Queue5VerificationInputs,
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path)

    summary = build_queue5_verification_summary(
        Queue5VerificationInputs(
            frozen_packet_path=inputs["frozen"],
            pdf_browser_evidence_path=inputs["pdf"],
            langsmith_evidence_path=inputs["langsmith"],
            openai_competitor_evidence_path=inputs["openai"],
            failure_matrix_path=inputs["failure_matrix"],
            demo_script_path=inputs["demo_script"],
            capstone_map_path=inputs["capstone_map"],
            output_dir=tmp_path / "summary",
        )
    )

    assert summary.schema_version == "queue5_verification_summary@1"
    assert summary.frozen_demo["status"] == "pass"
    assert summary.pdf_journey["status"] == "pass"
    assert summary.pdf_journey["screenshot_evidence_mode"] == "legacy_desktop_mobile"
    assert summary.langsmith_trace["status"] == "pass"
    assert summary.langsmith_trace["admin_health_status"] == "healthy"
    assert summary.openai_competitor_smoke["status"] == "pass"
    assert summary.readiness == {
        "frozen_packet_ready": True,
        "pdf_journey_ready": True,
        "langsmith_trace_ready": True,
        "openai_competitor_smoke_ready": True,
        "failure_matrix_ready": True,
        "queue5_sellable_demo_ready": True,
    }
    persisted = json.loads((tmp_path / "summary" / "queue5-verification-summary.json").read_text())
    assert persisted["schema_version"] == "queue5_verification_summary@1"


def test_verification_summary_accepts_canonical_desktop_state_suite_without_mobile(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    pdf = _pdf_evidence()
    pdf["screenshots"] = {
        "desktop_states": {
            "order": list(CANONICAL_DESKTOP_STATE_SCREENSHOTS),
            "path": "desktop-states",
            "viewport": {"width": 1440, "height": 1000},
        }
    }
    inputs = _write_inputs(tmp_path, pdf=pdf)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.pdf_journey["status"] == "pass"
    assert summary.pdf_journey["screenshot_evidence_mode"] == "desktop_states_14"
    assert summary.pdf_journey["screenshot_dimensions"] == {
        "desktop_states": {"width": 1440, "height": 1000}
    }
    assert summary.pdf_journey["desktop_state_evidence"] == {
        "valid": True,
        "state_count": 14,
        "order": list(CANONICAL_DESKTOP_STATE_SCREENSHOTS),
        "viewport": {"width": 1440, "height": 1000},
    }
    assert summary.readiness["pdf_journey_ready"] is True
    assert summary.readiness["queue5_sellable_demo_ready"] is True


def test_verification_summary_rejects_desktop_state_suite_with_noncanonical_order(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    order = list(CANONICAL_DESKTOP_STATE_SCREENSHOTS)
    order[0], order[1] = order[1], order[0]
    pdf = _pdf_evidence()
    pdf["screenshots"] = {
        "desktop_states": {
            "order": order,
            "path": "desktop-states",
            "viewport": {"width": 1440, "height": 1000},
        }
    }
    inputs = _write_inputs(tmp_path, pdf=pdf)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.pdf_journey["status"] == "fail"
    assert summary.pdf_journey["screenshot_evidence_mode"] == "invalid"
    assert summary.pdf_journey["desktop_state_evidence"]["valid"] is False
    assert summary.readiness["pdf_journey_ready"] is False
    assert "pdf_journey_not_passed" in summary.blockers


def test_verification_summary_passes_canonical_frozen_packet_hash_unchanged(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.frozen_demo["packet_hash"] == PACKET_HASH
    assert summary.hashes["canonical_frozen_packet_hash"] == PACKET_HASH


def test_verification_summary_allows_openai_missing_credential_when_required_lanes_pass(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        openai={"status": "skipped_missing_credential", "credential_present": False},
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "skipped_missing_credential"
    assert summary.readiness["openai_competitor_smoke_ready"] is True
    assert summary.readiness["queue5_sellable_demo_ready"] is True
    assert summary.blockers == []


def test_verification_summary_reports_missing_langsmith_as_sole_blocker(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        langsmith={"status": "blocked_missing_credential", "credential_present": False},
        openai={"status": "skipped_missing_credential", "credential_present": False},
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.langsmith_trace["status"] == "blocked_missing_credential"
    assert summary.langsmith_trace["admin_health_status"] == "blocked_missing_credential"
    assert summary.readiness["langsmith_trace_ready"] is False
    assert summary.readiness["openai_competitor_smoke_ready"] is True
    assert summary.readiness["queue5_sellable_demo_ready"] is False
    assert summary.blockers == ["langsmith_trace_missing_credential"]


def test_verification_summary_requires_passed_failure_matrix(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        failure_matrix={"matrix_passed": False, "fail_reasons": ["incomplete"]},
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.failure_matrix["status"] == "fail"
    assert summary.readiness["failure_matrix_ready"] is False
    assert "failure_matrix_not_passed" in summary.blockers


def test_verification_summary_requires_failure_matrix_hash(tmp_path: Path) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, failure_matrix={"matrix_hash": ""})

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.failure_matrix["status"] == "fail"
    assert summary.readiness["failure_matrix_ready"] is False
    assert "failure_matrix_not_passed" in summary.blockers


def test_verification_summary_recomputes_failure_matrix_hash(tmp_path: Path) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, failure_matrix={"matrix_hash": "sha256:" + "f" * 64})

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.failure_matrix["status"] == "fail"
    assert summary.readiness["failure_matrix_ready"] is False
    assert "failure_matrix_not_passed" in summary.blockers


@pytest.mark.parametrize(
    "command_evidence",
    (
        {},
        {"exit_code": 0, "timed_out": True},
        {"exit_code": 1, "timed_out": False},
    ),
)
def test_verification_summary_requires_successful_failure_matrix_command_evidence(
    tmp_path: Path,
    command_evidence: dict[str, object],
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, failure_matrix={"command_evidence": command_evidence})

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.failure_matrix["status"] == "fail"
    assert summary.readiness["failure_matrix_ready"] is False
    assert "failure_matrix_not_passed" in summary.blockers


@pytest.mark.parametrize(
    "failure_matrix_override",
    (
        {"offline_no_live_calls": False},
        {"fail_reasons": ["proof_command_failed"]},
        {
            "rows": [
                {
                    "id": "provider_unavailable_no_key",
                    "category": "provider_unavailable",
                    "expected_behavior": "Live startup provider remains unavailable when provider keys are blank.",
                    "proof_tests": [PROOF_TESTS[0], PROOF_TESTS[2]],
                    "status": "fail",
                    "live_calls_made": 0,
                    "fail_reasons": ["proof_command_failed"],
                }
            ]
        },
        {
            "supporting_validations": [
                {
                    "id": "checkpoint_restart",
                    "proof_tests": [PROOF_TESTS[8]],
                    "status": "fail",
                }
            ]
        },
    ),
)
def test_verification_summary_requires_complete_passing_failure_matrix_contract(
    tmp_path: Path,
    failure_matrix_override: dict[str, object],
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, failure_matrix=failure_matrix_override)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.failure_matrix["status"] == "fail"
    assert summary.readiness["failure_matrix_ready"] is False
    assert "failure_matrix_not_passed" in summary.blockers


def test_verification_summary_rejects_output_root_collision(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path)
    output_dir = tmp_path / "occupied"
    output_dir.mkdir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(ValueError, match="^verification_output_dir_not_empty$"):
        build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs, output_dir=output_dir))

    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_verification_summary_rejects_case_mismatch_across_evidence_lanes(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, pdf={"case_id": "other-case"})

    with pytest.raises(ValueError, match="^queue5_case_lineage_mismatch$"):
        build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))


@pytest.mark.parametrize(
    "lineage_override",
    (
        {"report_id": "other-report"},
        {"report_revision": 2},
        {"report_checksum": "b" * 64},
        {"report_pdf_hash": "sha256:" + "6" * 64},
    ),
)
def test_verification_summary_rejects_frozen_pdf_lineage_mismatch(
    tmp_path: Path,
    lineage_override: dict[str, object],
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    frozen = _frozen_packet()
    lineage = frozen["approved_report_lineage"]
    assert isinstance(lineage, dict)
    lineage.update(lineage_override)
    inputs = _write_inputs(tmp_path, frozen=frozen)

    with pytest.raises(ValueError, match="^queue5_report_lineage_mismatch$"):
        build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))


def test_verification_summary_rejects_missing_langsmith_report_lineage(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, langsmith={"report_id": ""})

    with pytest.raises(ValueError, match="^queue5_report_lineage_invalid$"):
        build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))


def test_verification_summary_requires_pdf_admin_report_lineage(tmp_path: Path) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        pdf={
            "admin_trace": {
                "case_id": CASE_ID,
                "run_id": RUN_ID,
                "report_lineage": {},
            }
        },
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.pdf_journey["status"] == "fail"
    assert summary.readiness["pdf_journey_ready"] is False
    assert "pdf_journey_not_passed" in summary.blockers


@pytest.mark.parametrize(
    "metadata_override",
    (
        {"snapshot_id": "00000000-0000-0000-0000-000000000953"},
        {"snapshot_hash": "sha256:" + "b" * 64},
        {"snapshot_revision": 2},
    ),
)
def test_verification_summary_requires_pdf_report_metadata_binding(
    tmp_path: Path,
    metadata_override: dict[str, object],
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    pdf = _pdf_evidence()
    report_metadata = pdf["report_metadata"]
    assert isinstance(report_metadata, dict)
    report_metadata.update(metadata_override)
    inputs = _write_inputs(tmp_path, pdf=pdf)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.pdf_journey["status"] == "fail"
    assert summary.readiness["pdf_journey_ready"] is False
    assert "pdf_journey_not_passed" in summary.blockers


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("intake_mode", "guided_form"),
        ("prompt_selection_used", True),
        ("industry_selection_used", True),
    ),
)
def test_verification_summary_requires_pdf_only_intake_proof(
    tmp_path: Path,
    field_name: str,
    invalid_value: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, pdf={field_name: invalid_value})

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.pdf_journey["status"] == "fail"
    assert summary.pdf_journey["intake_mode"] == (
        invalid_value if field_name == "intake_mode" else "pdf_upload_only"
    )
    assert summary.readiness["pdf_journey_ready"] is False
    assert "pdf_journey_not_passed" in summary.blockers


def test_verification_summary_requires_gate_d_semantic_equivalence(tmp_path: Path) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        frozen={"gate_d_semantic_equivalence": None},
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.frozen_demo["status"] == "fail"
    assert summary.frozen_demo["gate_d_semantic_equivalence"] is False
    assert summary.readiness["frozen_packet_ready"] is False


def test_verification_summary_requires_gate2_for_passed_openai_smoke(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    openai = _openai_evidence()
    lineage = openai["lineage"]
    assert isinstance(lineage, dict)
    lineage["gate2_decision"] = "pending"
    inputs = _write_inputs(tmp_path, openai=openai)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


@pytest.mark.parametrize(
    "field_name",
    (
        "execute_live_requested",
        "live_call_attempted",
        "live_call_succeeded",
        "client_constructed",
    ),
)
def test_verification_summary_rejects_langsmith_pass_without_live_export_proof(
    tmp_path: Path,
    field_name: str,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, langsmith={field_name: False})

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.langsmith_trace["status"] == "failed"
    assert summary.readiness["langsmith_trace_ready"] is False


def test_verification_summary_accepts_healthy_langsmith_trace_without_error_metadata(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    langsmith = _langsmith_evidence()
    trace = langsmith["langsmith_trace"]
    assert isinstance(trace, dict)
    metadata_keys = trace["metadata_keys"]
    assert isinstance(metadata_keys, list)
    metadata_keys.remove("error_code")
    metadata_keys.append("status")
    inputs = _write_inputs(tmp_path, langsmith=langsmith)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.langsmith_trace["status"] == "pass"
    assert summary.langsmith_trace["admin_health_status"] == "healthy"
    assert summary.readiness["langsmith_trace_ready"] is True


@pytest.mark.parametrize(
    ("trace_field", "invalid_value"),
    (
        ("run_count", 0),
        ("run_names", ["startup.report"]),
        ("metadata_keys", ["case_id", "run_id"]),
        ("export_errors", 1),
        ("flush_count", 0),
    ),
)
def test_verification_summary_rejects_langsmith_pass_without_trace_inventory(
    tmp_path: Path,
    trace_field: str,
    invalid_value: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    langsmith = _langsmith_evidence()
    trace = langsmith["langsmith_trace"]
    assert isinstance(trace, dict)
    trace[trace_field] = invalid_value
    inputs = _write_inputs(tmp_path, langsmith=langsmith)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.langsmith_trace["status"] == "failed"
    assert summary.readiness["langsmith_trace_ready"] is False


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("execute_live_requested", False),
        ("live_call_attempted", False),
        ("live_call_succeeded", False),
        ("call_count", 0),
    ),
)
def test_verification_summary_rejects_openai_pass_without_single_live_call_proof(
    tmp_path: Path,
    field_name: str,
    invalid_value: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, openai={field_name: invalid_value})

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


@pytest.mark.parametrize(
    "invalid_override",
    (
        {"transport": {"timeout_seconds": "21.0", "max_retries": "0"}},
        {"transport": {"timeout_seconds": "20.0", "max_retries": "1"}},
        {
            "budget": {
                "max_usd": "0.26",
                "worst_case_usd": "0.26",
                "reserved_usd": "0.26",
            }
        },
        {"source_summary_hashes": []},
    ),
)
def test_verification_summary_rejects_openai_pass_without_bounded_evidence_guards(
    tmp_path: Path,
    invalid_override: dict[str, object],
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, openai=invalid_override)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


def test_verification_summary_requires_openai_cost_evidence_for_passed_smoke(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path, openai={"cost_evidence": {}})

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


def test_verification_summary_rejects_openai_pass_without_competitor_evidence_refs(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    openai = _openai_evidence()
    result = openai["result"]
    assert isinstance(result, dict)
    competitors = result["competitors"]
    assert isinstance(competitors, list)
    first = competitors[0]
    assert isinstance(first, dict)
    first["evidence_refs"] = []
    inputs = _write_inputs(tmp_path, openai=openai)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


def test_verification_summary_rejects_missing_credentials_with_live_side_effects(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        langsmith={
            "status": "blocked_missing_credential",
            "credential_present": False,
            "live_call_attempted": True,
        },
        openai={
            "status": "skipped_missing_credential",
            "credential_present": False,
            "call_count": 1,
        },
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.langsmith_trace["status"] == "failed"
    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["queue5_sellable_demo_ready"] is False


@pytest.mark.parametrize(
    ("trace_field", "invalid_value"),
    (
        ("run_names", ["startup.workflow"]),
        ("metadata_keys", ["case_id"]),
        ("flush_count", 1),
        ("export_errors", 1),
    ),
)
def test_verification_summary_rejects_missing_langsmith_credential_with_trace_inventory(
    tmp_path: Path,
    trace_field: str,
    invalid_value: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    trace_inventory = {
        "run_count": 0,
        "run_names": [],
        "metadata_keys": [],
        "export_errors": 0,
        "flush_count": 0,
    }
    trace_inventory[trace_field] = invalid_value
    inputs = _write_inputs(
        tmp_path,
        langsmith={
            "status": "blocked_missing_credential",
            "credential_present": False,
            "langsmith_trace": trace_inventory,
        },
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.langsmith_trace["status"] == "failed"
    assert summary.readiness["langsmith_trace_ready"] is False


@pytest.mark.parametrize(
    ("usage_field", "invalid_value"),
    (
        ("input_tokens", 1),
        ("output_tokens", 1),
        ("total_tokens", 1),
        ("estimated_cost_usd", "0.01"),
    ),
)
def test_verification_summary_rejects_missing_openai_credential_with_usage_inventory(
    tmp_path: Path,
    usage_field: str,
    invalid_value: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        openai={
            "status": "skipped_missing_credential",
            "credential_present": False,
            "usage": {usage_field: invalid_value},
        },
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


@pytest.mark.parametrize(
    "raw_result",
    (
        ["direct competitor response"],
        "direct competitor response",
    ),
)
def test_verification_summary_rejects_missing_openai_credential_with_raw_result_inventory(
    tmp_path: Path,
    raw_result: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        openai={
            "status": "skipped_missing_credential",
            "credential_present": False,
            "result": raw_result,
        },
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


@pytest.mark.parametrize(
    "raw_usage",
    (
        ["input_tokens=10"],
        "input_tokens=10",
    ),
)
def test_verification_summary_rejects_missing_openai_credential_with_raw_usage_inventory(
    tmp_path: Path,
    raw_usage: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        openai={
            "status": "skipped_missing_credential",
            "credential_present": False,
            "usage": raw_usage,
        },
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "failed"
    assert summary.readiness["openai_competitor_smoke_ready"] is False


@pytest.mark.parametrize(
    ("raw_result", "raw_usage"),
    (
        (None, None),
        ({}, {}),
        ([], []),
        ("", ""),
    ),
)
def test_verification_summary_allows_missing_openai_credential_with_empty_raw_inventories(
    tmp_path: Path,
    raw_result: object,
    raw_usage: object,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        openai={
            "status": "skipped_missing_credential",
            "credential_present": False,
            "result": raw_result,
            "usage": raw_usage,
        },
    )

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.openai_competitor_smoke["status"] == "skipped_missing_credential"
    assert summary.readiness["openai_competitor_smoke_ready"] is True


def test_verification_summary_keeps_side_smoke_case_ids_independent(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    langsmith = _langsmith_evidence()
    langsmith_workflow = langsmith["workflow"]
    assert isinstance(langsmith_workflow, dict)
    langsmith_workflow["case_id"] = "langsmith-frozen-case"
    openai = _openai_evidence()
    openai_lineage = openai["lineage"]
    assert isinstance(openai_lineage, dict)
    openai_lineage["case_id"] = "openai-frozen-case"
    openai_gate2 = openai["gate2"]
    assert isinstance(openai_gate2, dict)
    openai_gate2["case_id"] = "openai-frozen-case"
    inputs = _write_inputs(tmp_path, langsmith=langsmith, openai=openai)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.pdf_journey["case_id"] == CASE_ID
    assert summary.langsmith_trace["case_id"] == "langsmith-frozen-case"
    assert summary.openai_competitor_smoke["case_id"] == "openai-frozen-case"
    assert summary.readiness["queue5_sellable_demo_ready"] is True


def test_verification_summary_hash_is_stable_when_remote_trace_ids_and_timings_change(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    first_inputs = _write_inputs(
        tmp_path / "first",
        langsmith={"remote_trace_id": "trace-a", "duration_ms": 123.4},
    )
    second_inputs = _write_inputs(
        tmp_path / "second",
        langsmith={"remote_trace_id": "trace-b", "duration_ms": 999.9},
    )

    first = build_queue5_verification_summary(_queue5_inputs(tmp_path / "first", first_inputs))
    second = build_queue5_verification_summary(_queue5_inputs(tmp_path / "second", second_inputs))

    assert first.semantic_summary_hash == second.semantic_summary_hash
    assert (
        first.raw_file_hashes["langsmith_evidence"] != second.raw_file_hashes["langsmith_evidence"]
    )


def test_verification_summary_rejects_privacy_leaks_in_side_evidence(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(
        tmp_path,
        openai={
            "privacy": {
                "request_payload_checked": True,
                "response_payload_checked": True,
                "unsafe_payload_rejected": True,
                "privacy_leak_count": 1,
            },
            "unsafe": "pitch.pdf C:\\secret\\founder@example.com %PDF prompt",
        },
    )

    with pytest.raises(ValueError, match="^queue5_privacy_validation_failed$"):
        build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))


def test_verification_summary_stores_artifact_paths_as_basenames_only(
    tmp_path: Path,
) -> None:
    from due_diligence_agent.evals.queue5_verification import (
        build_queue5_verification_summary,
    )

    inputs = _write_inputs(tmp_path)

    summary = build_queue5_verification_summary(_queue5_inputs(tmp_path, inputs))

    assert summary.artifact_paths == {
        "frozen_packet": "sellable-demo-freeze-packet.json",
        "pdf_browser_evidence": "browser-evidence.json",
        "langsmith_evidence": "langsmith-trace-evidence.json",
        "openai_competitor_evidence": "openai-competitor-smoke-evidence.json",
        "failure_matrix": "failure-matrix.json",
        "demo_script": "2026-08-16-sellable-demo-script.md",
        "capstone_map": "2026-08-16-capstone-requirement-evidence-map.md",
        "summary": "queue5-verification-summary.json",
    }
    assert all(not Path(path).is_absolute() for path in summary.artifact_paths.values())


def test_queue5_verification_script_forwards_offline_contract(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the verification wrapper contract")

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_queue5_verification.ps1"
    inputs = _write_inputs(tmp_path / "inputs")
    output_dir = tmp_path / "summary"
    capture_path = tmp_path / "capture.json"
    fake_uv = tmp_path / "fake-uv.ps1"
    fake_uv.write_text(
        "\n".join(
            [
                "function BlankValue($value) { if ($null -eq $value) { '' } else { $value } }",
                "$payload = @{ args = $args; env = @{",
                "  OPENAI_API_KEY = BlankValue $env:OPENAI_API_KEY",
                "  OPENAI_STARTUP_API_KEY = BlankValue $env:OPENAI_STARTUP_API_KEY",
                "  LANGSMITH_API_KEY = BlankValue $env:LANGSMITH_API_KEY",
                "  LANGCHAIN_API_KEY = BlankValue $env:LANGCHAIN_API_KEY",
                "  LANGSMITH_TRACING = $env:LANGSMITH_TRACING",
                "  LANGCHAIN_TRACING = $env:LANGCHAIN_TRACING",
                "  LANGCHAIN_TRACING_V2 = $env:LANGCHAIN_TRACING_V2",
                "  DDA_LANGSMITH_TRACING = $env:DDA_LANGSMITH_TRACING",
                "  HF_HUB_OFFLINE = $env:HF_HUB_OFFLINE",
                "  TRANSFORMERS_OFFLINE = $env:TRANSFORMERS_OFFLINE",
                "  UV_OFFLINE = $env:UV_OFFLINE",
                "} }",
                f"$payload | ConvertTo-Json -Depth 4 | Set-Content -Path '{capture_path}' -Encoding UTF8",
                "exit 43",
            ]
        ),
        encoding="utf-8",
    )
    process_env = os.environ.copy()
    process_env.update(
        {
            "OPENAI_API_KEY": "caller-openai-key",
            "OPENAI_STARTUP_API_KEY": "caller-startup-key",
            "LANGSMITH_API_KEY": "caller-langsmith-key",
            "LANGCHAIN_API_KEY": "caller-langchain-key",
        }
    )

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutputDir",
            str(output_dir),
            "-FrozenPacket",
            str(inputs["frozen"]),
            "-PdfBrowserEvidence",
            str(inputs["pdf"]),
            "-LangSmithEvidence",
            str(inputs["langsmith"]),
            "-OpenAICompetitorEvidence",
            str(inputs["openai"]),
            "-FailureMatrix",
            str(inputs["failure_matrix"]),
            "-DemoScript",
            str(inputs["demo_script"]),
            "-CapstoneMap",
            str(inputs["capstone_map"]),
            "-UvExecutable",
            str(fake_uv),
        ],
        cwd=repo_root,
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 43, result.stderr
    captured = json.loads(capture_path.read_text(encoding="utf-8-sig"))
    assert captured["args"][-19:] == [
        "python",
        "-m",
        "due_diligence_agent.evals.queue5_verification",
        "--output-dir",
        str(output_dir),
        "--frozen-packet",
        str(inputs["frozen"]),
        "--pdf-browser-evidence",
        str(inputs["pdf"]),
        "--langsmith-evidence",
        str(inputs["langsmith"]),
        "--openai-competitor-evidence",
        str(inputs["openai"]),
        "--failure-matrix",
        str(inputs["failure_matrix"]),
        "--demo-script",
        str(inputs["demo_script"]),
        "--capstone-map",
        str(inputs["capstone_map"]),
    ]
    assert captured["env"] == {
        "OPENAI_API_KEY": "",
        "OPENAI_STARTUP_API_KEY": "",
        "LANGSMITH_API_KEY": "",
        "LANGCHAIN_API_KEY": "",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
        "DDA_LANGSMITH_TRACING": "false",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "UV_OFFLINE": "true",
    }


def _queue5_inputs(
    tmp_path: Path,
    paths: dict[str, Path],
    *,
    output_dir: Path | None = None,
) -> Queue5VerificationInputs:
    from due_diligence_agent.evals.queue5_verification import Queue5VerificationInputs

    return Queue5VerificationInputs(
        frozen_packet_path=paths["frozen"],
        pdf_browser_evidence_path=paths["pdf"],
        langsmith_evidence_path=paths["langsmith"],
        openai_competitor_evidence_path=paths["openai"],
        failure_matrix_path=paths["failure_matrix"],
        demo_script_path=paths["demo_script"],
        capstone_map_path=paths["capstone_map"],
        output_dir=output_dir or tmp_path / "summary",
    )


def _write_inputs(
    root: Path,
    *,
    frozen: dict[str, object] | None = None,
    pdf: dict[str, object] | None = None,
    langsmith: dict[str, object] | None = None,
    openai: dict[str, object] | None = None,
    failure_matrix: dict[str, object] | None = None,
) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "frozen": root / "sellable-demo-freeze-packet.json",
        "pdf": root / "browser-evidence.json",
        "langsmith": root / "langsmith-trace-evidence.json",
        "openai": root / "openai-competitor-smoke-evidence.json",
        "failure_matrix": root / "failure-matrix.json",
        "demo_script": root / "2026-08-16-sellable-demo-script.md",
        "capstone_map": root / "2026-08-16-capstone-requirement-evidence-map.md",
    }
    _write_json(paths["frozen"], _frozen_packet(frozen))
    _write_json(paths["pdf"], _pdf_evidence(pdf))
    _write_json(paths["langsmith"], _langsmith_evidence(langsmith))
    _write_json(paths["openai"], _openai_evidence(openai))
    _write_json(paths["failure_matrix"], _failure_matrix(failure_matrix))
    paths["demo_script"].write_text("# Queue 5 demo script\n", encoding="utf-8")
    paths["capstone_map"].write_text("# Queue 5 capstone map\n", encoding="utf-8")
    return paths


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _frozen_packet(overrides: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "sellable_demo_freeze_packet@1",
        "case_id": CASE_ID,
        "report_lineage": {
            "case_id": CASE_ID,
            "json": "report.json",
            "html": "report.html",
            "pdf": "sample-report.pdf",
        },
        "approved_report_lineage": {
            "report_checksum": "a" * 64,
            "report_html_hash": "sha256:" + "8" * 64,
            "report_id": REPORT_ID,
            "report_json_hash": "sha256:" + "7" * 64,
            "report_pdf_hash": "sha256:" + "9" * 64,
            "report_revision": "1",
        },
        "sellable_demo_passed": True,
        "packet_hash": PACKET_HASH,
        "gate_d_semantic_equivalence": True,
        "gates": {
            "gate_b": "pass",
            "gate_c": "pass",
            "gate_d_first": "pass",
            "gate_d_second": "pass",
            "gate_e": "pass",
        },
        "live_provider_smoke_status": "deferred_by_policy",
        "raw_file_hash": FROZEN_RAW_HASH,
        "privacy": {"privacy_leak_count": 0},
    }
    payload.update(overrides or {})
    return payload


def _pdf_evidence(overrides: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "founder_browser_smoke_evidence@1",
        "case_id": CASE_ID,
        "offline": True,
        "network_external_calls": 0,
        "gate4_status": "approved",
        "upload_mime_type": "application/pdf",
        "upload_bytes": 2048,
        "upload_sha256": "sha256:" + "c" * 64,
        "pdf_upload_journey": True,
        "intake_mode": "pdf_upload_only",
        "prompt_selection_used": False,
        "industry_selection_used": False,
        "screenshots": {
            "desktop": {"width": 1440, "height": 1000, "path": "founder-desktop.png"},
            "mobile": {"width": 390, "height": 844, "path": "founder-mobile.png"},
        },
        "admin_trace": {
            "case_id": CASE_ID,
            "run_id": RUN_ID,
            "langsmith_health": {
                "provider": "langsmith",
                "status": "disabled",
                "error_code": "tracing_disabled",
                "fallback_used": "local_audit",
            },
            "report_lineage": {
                "report_id": REPORT_ID,
                "report_revision": 1,
                "report_checksum": "a" * 64,
            },
        },
        "report_metadata": {
            "case_id": CASE_ID,
            "snapshot_id": REPORT_ID,
            "snapshot_hash": "sha256:" + "a" * 64,
            "snapshot_revision": 1,
        },
        "report_artifact_hashes": {
            "json": "sha256:" + "7" * 64,
            "html": "sha256:" + "8" * 64,
            "pdf": "sha256:" + "9" * 64,
        },
        "raw_file_hash": PDF_RAW_HASH,
        "privacy": {"privacy_leak_count": 0},
    }
    payload.update(overrides or {})
    return payload


def _langsmith_evidence(overrides: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "langsmith_trace_evidence@1",
        "status": "pass",
        "credential_present": True,
        "execute_live_requested": True,
        "live_call_attempted": True,
        "live_call_succeeded": True,
        "client_constructed": True,
        "workflow": {
            "case_id": CASE_ID,
            "run_id": RUN_ID,
            "node_count": 3,
            "node_names": ["ingest", "initialize", "report"],
            "admin_langsmith_health": {
                "provider": "langsmith",
                "status": "healthy",
                "error_code": "none",
                "fallback_used": "local_audit",
            },
            "report_lineage": {
                "source": "workflow_completed_state",
                "report_id": REPORT_ID,
                "report_revision": 1,
                "report_checksum": "a" * 64,
            },
        },
        "langsmith_trace": {
            "run_count": 4,
            "run_names": [
                "startup.ingest",
                "startup.initialize",
                "startup.report",
                "startup.workflow",
            ],
            "metadata_keys": [
                "agent_role",
                "case_id",
                "duration_ms",
                "error_code",
                "estimated_cost_usd",
                "gate",
                "node_name",
                "report_checksum",
                "report_id",
                "retry_count",
                "run_id",
                "status",
                "total_tokens",
            ],
            "export_errors": 0,
            "flush_count": 1,
            "remote_trace_id": "trace-a",
            "duration_ms": 123.4,
        },
        "raw_file_hash": LANGSMITH_RAW_HASH,
        "privacy": {
            "inputs_empty": True,
            "outputs_empty": True,
            "attachments_absent": True,
            "filesystem_disabled": True,
            "unsafe_capture_rejected": True,
            "privacy_leak_count": 0,
        },
    }
    updates = overrides or {}
    if updates.get("status") == "blocked_missing_credential":
        payload["live_call_attempted"] = False
        payload["live_call_succeeded"] = False
        payload["client_constructed"] = False
        workflow = payload["workflow"]
        assert isinstance(workflow, dict)
        health = workflow["admin_langsmith_health"]
        assert isinstance(health, dict)
        health["status"] = "blocked_missing_credential"
        health["error_code"] = "missing_credential"
        payload["langsmith_trace"] = {
            "run_count": 0,
            "run_names": [],
            "metadata_keys": [],
            "export_errors": 0,
            "flush_count": 0,
        }
    if "report_id" in updates:
        workflow = payload["workflow"]
        assert isinstance(workflow, dict)
        report_lineage = workflow["report_lineage"]
        assert isinstance(report_lineage, dict)
        report_lineage["report_id"] = updates["report_id"]
        updates = {key: value for key, value in updates.items() if key != "report_id"}
    if "remote_trace_id" in updates or "duration_ms" in updates:
        trace = payload["langsmith_trace"]
        assert isinstance(trace, dict)
        trace.update(
            {key: updates[key] for key in ("remote_trace_id", "duration_ms") if key in updates}
        )
        updates = {
            key: value
            for key, value in updates.items()
            if key not in {"remote_trace_id", "duration_ms"}
        }
    payload.update(updates)
    return payload


def _openai_evidence(overrides: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "openai_competitor_smoke_evidence@1",
        "status": "pass",
        "credential_present": True,
        "execute_live_requested": True,
        "live_call_attempted": True,
        "live_call_succeeded": True,
        "call_count": 1,
        "inference_label": "live_inference",
        "research_label": "not_live_web_research",
        "gate2": {
            "case_id": CASE_ID,
            "run_id": RUN_ID,
            "status": "approved",
            "decision": "approved",
            "destination": "openai.responses",
            "profile_hash": "sha256:" + "b" * 64,
        },
        "lineage": {
            "source": "deterministic_startup_composer",
            "case_id": CASE_ID,
            "run_id": RUN_ID,
            "gate2_decision": "approved",
            "profile_hash": "sha256:" + "b" * 64,
        },
        "result": {
            "competitors": [
                {"category": "direct", "evidence_refs": ["frozen:direct"]},
                {"category": "indirect", "evidence_refs": ["frozen:indirect"]},
                {"category": "substitute", "evidence_refs": ["frozen:substitute"]},
                {"category": "do_nothing", "evidence_refs": ["frozen:do_nothing"]},
                {
                    "category": "potential_entrant",
                    "evidence_refs": ["frozen:potential_entrant"],
                },
            ]
        },
        "source_summary_hashes": ["sha256:" + "d" * 64],
        "transport": {"timeout_seconds": "20.0", "max_retries": "0"},
        "budget": {
            "max_usd": "0.25",
            "worst_case_usd": "0.20",
            "reserved_usd": "0.20",
        },
        "usage": {
            "input_tokens": 400,
            "output_tokens": 180,
            "total_tokens": 580,
        },
        "cost_evidence": {
            "currency": "USD",
            "pricing_model": "gpt-5.6-luna",
            "calculation": "estimated_from_observed_usage",
            "input_usd_per_million_tokens": "1.00",
            "output_usd_per_million_tokens": "6.00",
            "actual_or_estimated_usd": "0.001480",
        },
        "raw_file_hash": OPENAI_RAW_HASH,
        "privacy": {
            "request_payload_checked": True,
            "response_payload_checked": True,
            "unsafe_payload_rejected": True,
            "privacy_leak_count": 0,
        },
    }
    if (overrides or {}).get("status") == "skipped_missing_credential":
        payload["live_call_attempted"] = False
        payload["live_call_succeeded"] = False
        payload["call_count"] = 0
        payload["result"] = None
        payload["usage"] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        payload["cost_evidence"] = {
            "currency": "USD",
            "pricing_model": "gpt-5.6-luna",
            "calculation": "estimated_from_observed_usage",
            "input_usd_per_million_tokens": "1.00",
            "output_usd_per_million_tokens": "6.00",
            "actual_or_estimated_usd": "0.000000",
        }
    payload.update(overrides or {})
    return payload


def _failure_matrix(overrides: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "queue5_failure_matrix@1",
        "commit_id": "64c3a70bb528f2f71b1930ad7d7a2ab57a4d62b6",
        "offline_no_live_calls": True,
        "live_provider_smoke_status": "deferred_by_policy",
        "matrix_passed": True,
        "matrix_hash": "",
        "rows": [
            {
                "id": "provider_unavailable_no_key",
                "category": "provider_unavailable",
                "expected_behavior": "Live startup provider remains unavailable when provider keys are blank.",
                "proof_tests": [PROOF_TESTS[0], PROOF_TESTS[2]],
                "status": "pass",
                "live_calls_made": 0,
                "fail_reasons": [],
            },
            {
                "id": "external_source_outage_partial",
                "category": "external_source_outage",
                "expected_behavior": "External-source outage yields a typed partial result without invented competitors.",
                "proof_tests": [PROOF_TESTS[1], PROOF_TESTS[2]],
                "status": "pass",
                "live_calls_made": 0,
                "fail_reasons": [],
            },
            {
                "id": "typed_retry_bounded",
                "category": "retry",
                "expected_behavior": "Typed transient failures retry at most three attempts with trace evidence.",
                "proof_tests": [PROOF_TESTS[3]],
                "status": "pass",
                "live_calls_made": 0,
                "fail_reasons": [],
            },
            {
                "id": "provider_outage_graph_replan",
                "category": "provider_outage_replanning",
                "expected_behavior": "Typed provider outage exhausts bounded retries, records a sanitized partial result, replans to cached local market evidence, and reaches same-case Gate 3, Gate 4, and report completion.",
                "proof_tests": [PROOF_TESTS[4]],
                "status": "pass",
                "live_calls_made": 0,
                "fail_reasons": [],
            },
            {
                "id": "budget_exhaustion_local_fallback_restart",
                "category": "budget_exhaustion",
                "expected_behavior": "Budget exhaustion prevents the over-budget provider call, replans to cached local evidence, and resumes the same Gate 4 checkpoint after restart without replaying provider calls.",
                "proof_tests": [PROOF_TESTS[5], PROOF_TESTS[6]],
                "status": "pass",
                "live_calls_made": 0,
                "fail_reasons": [],
            },
            {
                "id": "report_renderer_fallback",
                "category": "renderer_fallback",
                "expected_behavior": "ReportLab fallback preserves snapshot identity and renderer outage remains a typed API failure.",
                "proof_tests": [PROOF_TESTS[7], PROOF_TESTS[8]],
                "status": "pass",
                "live_calls_made": 0,
                "fail_reasons": [],
            },
        ],
        "supporting_validations": [
            {"id": "checkpoint_restart", "proof_tests": [PROOF_TESTS[9]], "status": "pass"},
            {"id": "checkpoint_privacy", "proof_tests": [PROOF_TESTS[10]], "status": "pass"},
            {"id": "report_trace_lineage", "proof_tests": [PROOF_TESTS[11]], "status": "pass"},
            {
                "id": "exporter_fallback_privacy",
                "proof_tests": [PROOF_TESTS[12]],
                "status": "pass",
            },
        ],
        "command_evidence": {
            "command_id": "queue5_failure_matrix_pytest",
            "proof_tests": list(PROOF_TESTS),
            "exit_code": 0,
            "timeout_seconds": 300,
            "timed_out": False,
            "stdout_log": "failure-matrix.pytest.stdout.log",
            "stderr_log": "failure-matrix.pytest.stderr.log",
        },
        "artifact_paths": {
            "failure_matrix": "failure-matrix.json",
            "pytest_stdout": "failure-matrix.pytest.stdout.log",
            "pytest_stderr": "failure-matrix.pytest.stderr.log",
        },
        "artifact_hashes": [
            "pytest_stdout:sha256:" + "a" * 64,
            "pytest_stderr:sha256:" + "b" * 64,
        ],
        "fail_reasons": [],
    }
    payload.update(overrides or {})
    if "matrix_hash" not in (overrides or {}):
        payload["matrix_hash"] = _queue5_failure_matrix_hash(payload)
    return payload


def _queue5_failure_matrix_hash(payload: dict[str, object]) -> str:
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

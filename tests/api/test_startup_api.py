from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from starlette.testclient import TestClient

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.startup.frozen_market_research import (
    FrozenStartupMarketResearchAdapter,
)
from due_diligence_agent.application.services.startup_trace_query_service import (
    StartupTraceQueryService,
)
from due_diligence_agent.application.startup_cases import (
    CanonicalReportSnapshot,
    FreezeStatus,
    PdfStatus,
    StartupCaseCoordinator,
    StartupGateConflict,
    StartupNotFound,
    StartupReportRendererUnavailable,
    StartupValidationError,
)
from due_diligence_agent.domain.startup.gtm import (
    StartupGtmDimension,
    StartupGtmDimensionName,
    StartupGtmDimensionStatus,
    StartupGtmHorizon,
    StartupGtmLaunchPhase,
    StartupGtmSnapshot,
    StartupGtmStatus,
)
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchPlan,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.evals.startup_trace_sidecar import (
    REQUIRED_PDF_JOURNEY_NODES,
    build_startup_trace_sidecar,
)
from due_diligence_agent.ports.startup_research import StartupResearchPort
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.presentation.api import dependencies as api_dependencies
from due_diligence_agent.presentation.api.app import create_app
from due_diligence_agent.presentation.api.dependencies import (
    get_startup_advisor_api_service,
    get_startup_case_coordinator,
)
from due_diligence_agent.presentation.streamlit.components.audit import (
    build_startup_trace_admin_snapshot,
)
from due_diligence_agent.workflows.startup.runtime import InMemoryStartupWorkflowRuntimeStore


def test_startup_api_shell_upload_gate_and_report_errors(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        deterministic_analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)

    created = client.post(
        "/api/v1/startup/cases",
        json={
            "fixture_mode": "deterministic_offline",
            "auto_start": True,
            "company_name": "FounderCo",
        },
        headers={"X-Actor-ID": "do-not-trust", "X-Workspace-ID": "also-do-not-trust"},
    )

    assert created.status_code == 201
    assert created.json()["case_status"] == "awaiting_upload"
    assert created.json()["auto_start_triggered"] is False
    case_id = created.json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={
            "auto_start": "true",
            "company_name": "Upload FounderCo",
            "website": "https://upload.example",
            "as_of": "2026-08-12",
            "document_class_hint": "pitch_deck",
        },
        files=[("files", ("pitch secret.pdf", b"ARR 100", "application/pdf"))],
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["accepted_document_ids"] == ["doc-0001"]
    assert "pitch secret.pdf" not in uploaded.text
    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["upload_metadata"] == {
        "company_name": "Upload FounderCo",
        "website": "https://upload.example",
        "as_of": "2026-08-12",
        "document_class_hint": "pitch_deck",
    }
    assert runtime["documents"][0]["declared_mime_type"] == "application/pdf"

    status = client.get(f"/api/v1/startup/cases/{case_id}")
    assert status.status_code == 200
    assert status.json()["analysis_status"] == "gate2_preview_ready"
    assert status.json()["data_revision"] == 1
    assert status.json()["active_analysis_thread_id"] == f"{case_id}:r1"
    assert set(status.json()) == {
        "case_id",
        "case_status",
        "analysis_status",
        "provider_status",
        "data_revision",
        "active_analysis_thread_id",
        "langgraph_checkpoint",
        "gate2_status",
        "gate3_status",
        "gate4_status",
        "report_status",
        "snapshot_hash",
        "snapshot_revision",
    }
    analysis = client.get(f"/api/v1/startup/cases/{case_id}/analysis")
    assert analysis.status_code == 200
    assert analysis.json()["data_revision"] == 1
    assert analysis.json()["active_analysis_thread_id"] == f"{case_id}:r1"
    assert analysis.json()["langgraph_checkpoint"] is None

    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    assert preview.json()["provider_mode"] == "deterministic_offline_fixture"
    token = preview.json()["resume_token"]

    mismatch = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": "wrong"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json() == {
        "code": "resume_token_invalid",
        "message": "resume_token_invalid",
    }

    approved = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": token, "reason": "ready"},
    )
    assert approved.status_code == 200
    assert approved.json()["analysis_status"] == "gate3_review_required"

    gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    assert gate3.status_code == 200
    assert gate3.json()["report_status"] == "not_ready"

    report = client.get(f"/api/v1/startup/cases/{case_id}/report")
    assert report.status_code == 404
    assert report.json()["code"] == "report_not_ready"
    pdf = client.get(f"/api/v1/startup/cases/{case_id}/report/pdf")
    assert pdf.status_code == 404
    assert pdf.json()["code"] == "report_not_ready"
    gate4 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
    )
    assert gate4.status_code == 404
    assert gate4.json()["code"] == "report_not_ready"


def test_startup_status_exposes_only_sanitized_current_langgraph_checkpoint(
    tmp_path: Path,
) -> None:
    checkpoint = {
        "checkpoint_hash": "d" * 64,
        "checkpoint_id": "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
        "data_revision": 2,
        "node_name": "market_research",
        "raw_state": {"secret": "do-not-expose"},
        "run_id": "private-run-id",
        "thread_id": "filled-after-create",
    }
    analysis_probe = AnalysisProbe(checkpoint_identity=checkpoint)
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis_probe,
        deterministic_analysis_service=analysis_probe,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)

    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    ).json()["case_id"]
    coordinator.seed_status_for_test(
        case_id,
        {
            "data_revision": 2,
            "active_analysis_thread_id": f"{case_id}:r2",
        },
    )
    checkpoint["thread_id"] = f"{case_id}:r2"

    status = client.get(f"/api/v1/startup/cases/{case_id}/analysis")

    assert status.status_code == 200
    checkpoint = status.json()["langgraph_checkpoint"]
    assert checkpoint == {
        "checkpoint_hash": "d" * 64,
        "checkpoint_id": "1f1a1fb3-c02e-6bb0-8008-d92ea1be1c4a",
        "data_revision": 2,
        "thread_id": f"{case_id}:r2",
    }
    assert set(checkpoint) == {
        "checkpoint_hash",
        "checkpoint_id",
        "data_revision",
        "thread_id",
    }
    assert "private-run-id" not in status.text
    assert "do-not-expose" not in status.text


def test_startup_api_serves_canonical_json_and_gate4_from_report_port(tmp_path: Path) -> None:
    reports = ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1))
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    report = client.get(f"/api/v1/startup/cases/{case_id}/report")
    assert report.status_code == 200
    assert report.json()["json_url"] == f"/api/v1/startup/cases/{case_id}/report/json"
    founder_json = client.get(f"/api/v1/startup/cases/{case_id}/report/json")
    assert founder_json.status_code == 200
    assert founder_json.headers["content-type"] == "application/json"
    founder_payload = founder_json.json()
    assert set(founder_payload) == {
        "title_ru",
        "subtitle_ru",
        "as_of_ru",
        "data_revision",
        "main_sections",
        "metric_cards",
        "improvement_proposals",
        "technical_appendix",
        "analytics",
    }
    assert founder_payload == _founder_safe_report_payload()

    mismatch = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "approved", "snapshot_hash": "wrong", "snapshot_revision": 1},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["code"] == "gate_4_snapshot_mismatch"
    assert reports.decisions == []

    rejected = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "rejected", "snapshot_hash": "hash-1", "snapshot_revision": 1},
    )
    assert rejected.status_code == 200
    assert rejected.json()["gate4_status"] == "completed"
    assert rejected.json()["snapshot_hash"] == "hash-1"
    assert rejected.json()["snapshot_revision"] == 1
    pdf = client.get(f"/api/v1/startup/cases/{case_id}/report/pdf")
    assert pdf.status_code == 409
    assert pdf.json()["code"] == "gate_4_freeze_required"


def test_startup_api_emits_report_lineage_trace_for_exact_gate4_decision(tmp_path: Path) -> None:
    snapshot_hash = "a" * 64
    reports = ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", snapshot_hash, 3))
    audit_spool = RecordingAuditSpool()
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
        audit_spool=audit_spool,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]
    run_id = f"startup-api-{case_id}"

    assert client.get(f"/api/v1/startup/cases/{case_id}/report").status_code == 200
    assert client.get(f"/api/v1/startup/cases/{case_id}/report").status_code == 200

    mismatch = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "approved", "snapshot_hash": "b" * 64, "snapshot_revision": 3},
    )
    assert mismatch.status_code == 409

    approved = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "approved", "snapshot_hash": snapshot_hash, "snapshot_revision": 3},
    )

    assert approved.status_code == 200
    event_types = [event.event_type for event in audit_spool.events]
    assert event_types == [
        "startup_report.canonical_snapshot",
        "startup_report.gate4_completed",
    ]

    view = StartupTraceQueryService(audit_spool).get_view(case_id, run_id)
    assert view.report_lineage.report_id == "snapshot-1"
    assert view.report_lineage.report_checksum == snapshot_hash
    assert view.report_lineage.report_revision == 3
    assert view.report_lineage.gate4_status == "completed"
    assert view.report_lineage.decision == "approved"


def test_startup_api_real_deterministic_composition_builds_uploaded_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    coordinator = get_startup_case_coordinator()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    fixture = (
        Path(__file__).parents[1]
        / "fixtures"
        / "startup_workspace_smoke_v1"
        / "documents"
        / "founder_metrics.csv"
    )

    created = client.post(
        "/api/v1/startup/cases",
        json={
            "fixture_mode": "deterministic_offline",
            "auto_start": False,
            "company_name": "FounderCo",
        },
    )
    case_id = created.json()["case_id"]
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true", "company_name": "FounderCo"},
        files=[("files", (fixture.name, fixture.read_bytes(), "text/csv"))],
    )

    assert uploaded.status_code == 200
    assert uploaded.json()["analysis_status"] == "gate2_preview_ready"
    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200
    gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    assert gate3.status_code == 200
    profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert profile.status_code == 200
    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert gtm.status_code == 200
    assert gtm.json()["profile_id"] == profile.json()["profile_id"]
    assert gtm.json()["schema_version"] == "startup_gtm@1"
    assert len(gtm.json()["dimensions"]) == 7
    assert len(gtm.json()["launch_plan"]) == 4
    assert "startup_gtm_artifact" not in coordinator.runtime_for_test(case_id)
    founder_json = client.get(f"/api/v1/startup/cases/{case_id}/report/json")
    assert founder_json.status_code == 200
    metric_cards = founder_json.json()["metric_cards"]
    assert "gross_margin" in metric_cards
    report_html = client.get(f"/api/v1/startup/cases/{case_id}/report/html")
    assert report_html.status_code == 200
    assert 'data-startup-chart="confirmed_metrics"' in report_html.text
    first_question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    assert first_question.status_code == 200
    assert first_question.json()["next_question"]["field_key"] == "revenue_pricing"
    skipped = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": first_question.json()["next_question"]["question_id"],
            "answer_type": "skip",
        },
    )
    assert skipped.status_code == 200
    public_question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question").json()[
        "next_question"
    ]
    blocked = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": public_question["question_id"],
            "answer_type": "public_research",
            "consent_public_research": False,
        },
    )
    assert blocked.status_code == 200
    assert blocked.json()["research_result"]["status"] == "blocked"
    improvements = client.get(f"/api/v1/startup/cases/{case_id}/advisor/improvements")
    assert improvements.status_code == 200
    assert improvements.json()["improvement_version"] == 1
    assert len(improvements.json()["proposals"]) == 6
    assert (data_root / "startup-api" / "inbox" / case_id / "doc-0001.csv").is_file()
    _clear_startup_dependency_cache()


def test_startup_api_file_advisor_answer_restarts_same_case_analysis_without_private_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    coordinator = get_startup_case_coordinator()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    fixture = (
        Path(__file__).parents[1]
        / "fixtures"
        / "startup_synthetic_v1"
        / "cases"
        / "saas"
        / "pitch.pdf"
    )
    private_filename = "private-founder-upload.pdf"

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[
            (
                "files",
                (private_filename, fixture.read_bytes(), "application/pdf"),
            )
        ],
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["accepted_document_ids"] == ["doc-0001"]

    question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    assert question.status_code == 200
    next_question = question.json()["next_question"]
    answered = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": next_question["question_id"],
            "answer_type": "file",
            "document_id": "doc-0001",
        },
    )

    assert answered.status_code == 200
    answer_payload = answered.json()
    assert answer_payload["status"] == "applied"
    assert answer_payload["recalculation_status"] == "started"
    assert answer_payload["recalculation_data_revision"] == 2
    assert answer_payload["recalculation_analysis_status"] == "gate2_preview_ready"
    assert private_filename not in answered.text
    assert str(fixture) not in answered.text

    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["data_revision"] == 2
    assert runtime["active_analysis_thread_id"] == f"{case_id}:r2"
    assert runtime["canonical_report_snapshot_id"] is None
    assert runtime["canonical_report_snapshot_hash"] is None
    assert runtime["canonical_report_snapshot_revision"] is None
    assert runtime["source_document_ids"] == ["doc-0001"]
    serialized_runtime = repr(runtime)
    assert private_filename not in serialized_runtime
    assert str(fixture) not in serialized_runtime
    assert "prompt" not in serialized_runtime.casefold()
    _clear_startup_dependency_cache()


def test_startup_api_real_deterministic_pdf_upload_journey_reaches_same_case_report_and_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    coordinator = get_startup_case_coordinator()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    fixture = (
        Path(__file__).parents[1]
        / "fixtures"
        / "startup_synthetic_v1"
        / "cases"
        / "saas"
        / "pitch.pdf"
    )

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[("files", ("upload.pdf", fixture.read_bytes(), "application/pdf"))],
    )

    assert uploaded.status_code == 200
    assert uploaded.json()["analysis_status"] == "gate2_preview_ready"
    assert "upload.pdf" not in uploaded.text
    runtime = coordinator.runtime_for_test(case_id)
    assert "prompt" not in runtime
    assert "industry" not in runtime
    assert "prompt" not in runtime.get("upload_metadata", {})
    assert "industry" not in runtime.get("upload_metadata", {})
    assert runtime["documents"][0]["declared_mime_type"] == "application/pdf"
    assert runtime["documents"][0]["byte_size"] == fixture.stat().st_size
    assert runtime["documents"][0]["content_sha256"] == sha256(fixture.read_bytes()).hexdigest()

    profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert profile.status_code == 200
    profile_payload = profile.json()
    assert profile_payload["analysis_stage"] == "primary"
    assert profile_payload["parent_profile_id"] is None
    one_line = profile_payload["fields"]["one_line_description"]
    assert one_line["status"] == "source_fact"
    assert one_line["values"] == ["SaaS case: backlog automation for finance teams."]
    assert one_line["evidence_refs"]

    advisor_question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    assert advisor_question.status_code == 200
    next_question = advisor_question.json()["next_question"]
    assert next_question["field_key"] == "burn_cash"
    manual_answer = (
        "Use finance forecast for July 2026: cash balance $250,000, monthly net "
        "burn $42,000, runway about 6 months."
    )
    advisor_answer = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": next_question["question_id"],
            "answer_type": "manual",
            "value": manual_answer,
        },
    )
    assert advisor_answer.status_code == 200
    assert advisor_answer.json()["recalculation_status"] == "started"
    assert advisor_answer.json()["recalculation_data_revision"] == 2
    assert advisor_answer.json()["recalculation_analysis_status"] == "gate2_preview_ready"
    assert manual_answer not in advisor_answer.text

    recalculated_runtime = coordinator.runtime_for_test(case_id)
    assert recalculated_runtime["data_revision"] == 2
    assert recalculated_runtime["active_analysis_thread_id"] == f"{case_id}:r2"
    assert recalculated_runtime["canonical_report_snapshot_id"] is None
    assert manual_answer not in repr(recalculated_runtime)

    _assert_public_research_deferred_without_mutation(
        client,
        coordinator=coordinator,
        case_id=case_id,
        expected_revision=2,
        expected_skipped=("problem", "stage", "revenue_pricing"),
    )

    early_improvements = client.get(f"/api/v1/startup/cases/{case_id}/advisor/improvements")
    assert early_improvements.status_code == 200
    assert early_improvements.json()["case_id"] == case_id
    assert early_improvements.json()["improvement_version"] == 1
    assert len(early_improvements.json()["proposals"]) == 6

    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200
    gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    assert gate3.status_code == 200

    enriched_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert enriched_profile.status_code == 200
    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert gtm.status_code == 200
    gtm_payload = gtm.json()
    assert gtm_payload["profile_id"] == enriched_profile.json()["profile_id"]
    assert len(gtm_payload["dimensions"]) == 7
    assert len(gtm_payload["launch_plan"]) == 4

    report = client.get(f"/api/v1/startup/cases/{case_id}/report")
    assert report.status_code == 200
    assert report.json()["case_id"] == case_id
    founder_json = client.get(f"/api/v1/startup/cases/{case_id}/report/json")
    assert founder_json.status_code == 200
    founder_payload = founder_json.json()
    sections = {section["key"]: section for section in founder_payload["main_sections"]}
    for key in (
        "metrics",
        "market_size",
        "competitors",
        "diligence_questions",
        "action_plan",
    ):
        assert key in sections
        assert sections[key]["status"] in {
            "confirmed",
            "partial",
            "needs_input",
            "contradiction",
        }
    action_plan = sections["action_plan"]
    assert action_plan["known_facts_ru"] or action_plan["next_data_ru"]
    assert (
        sections["diligence_questions"]["known_facts_ru"]
        or sections["diligence_questions"]["next_data_ru"]
    )
    market_size = sections["market_size"]
    market_unknowns = " ".join(
        [
            market_size["summary_ru"],
            *market_size["known_facts_ru"],
            *market_size["next_data_ru"],
        ]
    )
    assert (
        all(token in market_unknowns for token in ("TAM", "SAM", "SOM"))
        or market_size["status"] != "needs_input"
    )
    serialized_report = json.dumps(founder_payload, sort_keys=True)
    assert "source_mode=live" not in serialized_report
    assert "live_web_research" not in serialized_report

    html = client.get(f"/api/v1/startup/cases/{case_id}/report/html")
    assert html.status_code == 200
    assert html.headers["content-type"] == "text/html; charset=utf-8"
    decoded_html = html.content.decode("utf-8")
    assert html.text == decoded_html
    assert '<html lang="ru">' in decoded_html
    assert "<title>Отчёт для основателя</title>" in decoded_html
    assert "Краткий разбор проекта, блокеры и следующие шаги" in decoded_html
    for horizon_label in ("7 дней", "30 дней", "60 дней", "90 дней"):
        assert horizon_label in decoded_html

    improvements = client.get(f"/api/v1/startup/cases/{case_id}/advisor/improvements")
    assert improvements.status_code == 200
    assert len(improvements.json()["proposals"]) == 6
    accepted_proposal = improvements.json()["proposals"][0]
    accepted = client.post(
        (
            f"/api/v1/startup/cases/{case_id}/advisor/improvements/"
            f"{accepted_proposal['proposal_id']}/decision"
        ),
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["new_version"] == 2
    assert accepted.json()["recalculation_status"] == "started"
    assert accepted.json()["recalculation_data_revision"] == 3
    assert accepted.json()["recalculation_analysis_status"] == "gate2_preview_ready"
    assert accepted_proposal["recommendation_ru"] not in accepted.text

    improvement_runtime = coordinator.runtime_for_test(case_id)
    assert improvement_runtime["data_revision"] == 3
    assert improvement_runtime["active_analysis_thread_id"] == f"{case_id}:r3"
    assert improvement_runtime["canonical_report_snapshot_id"] is None
    assert accepted_proposal["recommendation_ru"] not in repr(improvement_runtime)
    improvement_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert improvement_profile.status_code == 200
    assert improvement_profile.json()["data_revision"] == 3
    assumptions = improvement_profile.json()["fields"]["assumptions"]
    assert manual_answer not in assumptions["values"]
    source_fact_values = [
        value
        for field in improvement_profile.json()["fields"].values()
        if field["status"] == "source_fact"
        for value in field.get("values", [])
    ]
    assert manual_answer not in source_fact_values
    assert accepted_proposal["recommendation_ru"] not in json.dumps(
        assumptions,
        ensure_ascii=False,
    )

    improvement_preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert improvement_preview.status_code == 200
    improvement_gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={
            "decision": "approved",
            "resume_token": improvement_preview.json()["resume_token"],
        },
    )
    assert improvement_gate2.status_code == 200
    improvement_gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    assert improvement_gate3.status_code == 200
    report = client.get(f"/api/v1/startup/cases/{case_id}/report")
    assert report.status_code == 200
    assert report.json()["snapshot_revision"] == 3
    revised_canonical = client.get(f"/api/v1/startup/cases/{case_id}/report/json")
    assert revised_canonical.status_code == 200
    revised_report_json = json.dumps(revised_canonical.json(), ensure_ascii=False)
    assert accepted_proposal["recommendation_ru"] not in revised_report_json
    assert "burn" in revised_report_json.casefold()

    assert client.get(f"/api/v1/startup/cases/{case_id}/report/pdf").status_code == 409
    gate4 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={
            "decision": "approved",
            "snapshot_hash": report.json()["snapshot_hash"],
            "snapshot_revision": report.json()["snapshot_revision"],
        },
    )
    assert gate4.status_code == 200
    pdf = client.get(f"/api/v1/startup/cases/{case_id}/report/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    deterministic_audit_spool = JsonlAuditSpool(
        data_root / "startup-api" / "deterministic" / "startup-audit-spool"
    )
    trace_view = StartupTraceQueryService(deterministic_audit_spool).get_view(
        case_id,
        f"startup-api-{case_id}",
    )
    assert trace_view.case_id == case_id
    assert trace_view.run_id == f"startup-api-{case_id}"
    assert {row.node for row in trace_view.node_rows} >= REQUIRED_PDF_JOURNEY_NODES
    assert trace_view.report_lineage.report_id == report.json()["snapshot_id"]
    assert trace_view.report_lineage.report_checksum == report.json()["snapshot_hash"].removeprefix(
        "sha256:"
    )
    assert trace_view.report_lineage.report_revision == report.json()["snapshot_revision"]
    assert trace_view.report_lineage.gate4_status == "completed"
    assert trace_view.report_lineage.decision == "approved"
    required_tool_boundaries = {
        "document_intelligence": "startup_document_intelligence",
        "metrics": "python_metrics",
    }
    successful_or_fallback_rows = {
        row.node: row
        for row in trace_view.node_rows
        if row.node in required_tool_boundaries
        and row.status in {"success", "completed", "partial"}
    }
    assert {
        node: row.tool for node, row in successful_or_fallback_rows.items()
    } == required_tool_boundaries
    assert all(
        row.latency_ms is not None
        and row.latency_ms >= 0
        and row.retry_count is not None
        and row.retry_count >= 0
        for row in successful_or_fallback_rows.values()
    )
    public_tool_row = next(
        row
        for row in trace_view.node_rows
        if row.node == "advisor_public_research"
        and row.tool == "public_web_search"
        and row.status == "deferred"
    )
    assert public_tool_row.timeout_ms == 15_000
    assert public_tool_row.evidence_count == 0
    assert public_tool_row.fallback_used == "none"
    assert public_tool_row.error_code == "provider_unconfigured"
    admin_snapshot = build_startup_trace_admin_snapshot(trace_view)
    assert any(
        row.get("node") == "advisor_public_research"
        and row.get("tool") == "public_web_search"
        and row.get("status") == "deferred"
        and row.get("timeout_ms") == 15_000
        and row.get("evidence_count") == 0
        and row.get("fallback_used") == "none"
        and row.get("error_code") == "provider_unconfigured"
        for row in admin_snapshot["node_timeline"]
    )
    serialized_trace = repr(trace_view)
    assert str(fixture) not in serialized_trace
    assert fixture.name not in serialized_trace
    assert "upload.pdf" not in serialized_trace
    sidecar = build_startup_trace_sidecar(
        audit_spool_root=data_root / "startup-api" / "deterministic" / "startup-audit-spool",
        case_id=case_id,
        run_id=f"startup-api-{case_id}",
    )
    assert {row["node"] for row in sidecar["node_rows"]} >= REQUIRED_PDF_JOURNEY_NODES
    assert {
        row["node"]: row["tool"]
        for row in sidecar["node_rows"]
        if row["node"] in required_tool_boundaries
        and row["status"] in {"success", "completed", "partial"}
    } == required_tool_boundaries
    assert any(
        row["node"] == "advisor_public_research"
        and row["tool"] == "public_web_search"
        and row["status"] == "deferred"
        and row["timeout_ms"] == 15_000
        and row["evidence_count"] == 0
        and row["fallback_used"] == "none"
        and row["error_code"] == "provider_unconfigured"
        for row in sidecar["node_rows"]
    )
    assert sidecar["report_lineage"]["report_id"] == report.json()["snapshot_id"]
    assert sidecar["langsmith_health"]["status"] == "disabled"
    _clear_startup_dependency_cache()


def test_startup_api_restart_resumes_revised_same_case_thread_without_duplicate_public_research(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches stale r3 report lineage or duplicate public research after r4 restart."""

    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"
    public_fallback_research_calls: list[StartupResearchPlan] = []

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container

    original_build_research_service = container.build_startup_advisor_research_service

    def build_counting_research_service(**kwargs: Any) -> object:
        fallback = _CountingStartupResearchPort(
            FrozenStartupMarketResearchAdapter.from_fixture_dir(
                Path(__file__).parents[1] / "fixtures" / "startup_market_research_v1"
            ),
            public_fallback_research_calls,
        )
        return original_build_research_service(
            **kwargs,
            fallback_research_port=fallback,
        )

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_startup_advisor_research_service",
        build_counting_research_service,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)
    fixture = (
        Path(__file__).parents[1]
        / "fixtures"
        / "startup_synthetic_v1"
        / "cases"
        / "saas"
        / "pitch.pdf"
    )

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[("files", ("upload.pdf", fixture.read_bytes(), "application/pdf"))],
    )
    assert uploaded.status_code == 200

    pricing_question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    assert pricing_question.status_code == 200
    assert pricing_question.json()["next_question"]["field_key"] == "burn_cash"
    pricing_answer = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": pricing_question.json()["next_question"]["question_id"],
            "answer_type": "manual",
            "value": (
                "Use finance forecast for July 2026: cash balance $250,000, monthly "
                "net burn $42,000, runway about 6 months."
            ),
        },
    )
    assert pricing_answer.status_code == 200
    assert pricing_answer.json()["recalculation_data_revision"] == 2

    _assert_public_research_deferred_without_mutation(
        client,
        coordinator=coordinator,
        case_id=case_id,
        expected_revision=2,
        expected_skipped=("problem", "stage", "revenue_pricing"),
    )
    assert len(public_fallback_research_calls) == 0

    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200
    gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    assert gate3.status_code == 200
    baseline_report = client.get(f"/api/v1/startup/cases/{case_id}/report")
    assert baseline_report.status_code == 200
    baseline_snapshot = baseline_report.json()
    assert baseline_snapshot["snapshot_revision"] == 2
    baseline_gate4 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={
            "decision": "approved",
            "snapshot_hash": baseline_snapshot["snapshot_hash"],
            "snapshot_revision": baseline_snapshot["snapshot_revision"],
        },
    )
    assert baseline_gate4.status_code == 200

    improvements = client.get(f"/api/v1/startup/cases/{case_id}/advisor/improvements")
    assert improvements.status_code == 200
    accepted_proposal = improvements.json()["proposals"][0]
    accepted = client.post(
        (
            f"/api/v1/startup/cases/{case_id}/advisor/improvements/"
            f"{accepted_proposal['proposal_id']}/decision"
        ),
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["recalculation_data_revision"] == 3
    assert len(public_fallback_research_calls) == 0

    invalidated_runtime = coordinator.runtime_for_test(case_id)
    assert invalidated_runtime["data_revision"] == 3
    assert invalidated_runtime["active_analysis_thread_id"] == f"{case_id}:r3"
    assert invalidated_runtime["canonical_report_snapshot_id"] is None
    assert invalidated_runtime["canonical_report_snapshot_hash"] is None
    assert invalidated_runtime["canonical_report_snapshot_revision"] is None

    _clear_startup_dependency_cache()
    restarted_coordinator = get_startup_case_coordinator()
    restarted_advisor_service = get_startup_advisor_api_service()
    restarted_app = create_app()
    restarted_app.dependency_overrides[get_startup_case_coordinator] = lambda: restarted_coordinator
    restarted_app.dependency_overrides[get_startup_advisor_api_service] = lambda: (
        restarted_advisor_service
    )
    restarted_client = TestClient(restarted_app)

    restarted_runtime = restarted_coordinator.runtime_for_test(case_id)
    assert restarted_runtime["data_revision"] == 3
    assert restarted_runtime["active_analysis_thread_id"] == f"{case_id}:r3"
    assert restarted_runtime["canonical_report_snapshot_id"] is None

    restarted_preview = restarted_client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert restarted_preview.status_code == 200
    restarted_gate2 = restarted_client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={
            "decision": "approved",
            "resume_token": restarted_preview.json()["resume_token"],
        },
    )
    assert restarted_gate2.status_code == 200
    restarted_gate3 = restarted_client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    assert restarted_gate3.status_code == 200
    revised_report = restarted_client.get(f"/api/v1/startup/cases/{case_id}/report")
    assert revised_report.status_code == 200
    revised_snapshot = revised_report.json()
    assert revised_snapshot["case_id"] == case_id
    assert revised_snapshot["snapshot_revision"] == 3
    assert revised_snapshot["snapshot_id"] != baseline_snapshot["snapshot_id"]
    assert revised_snapshot["snapshot_hash"] != baseline_snapshot["snapshot_hash"]

    revised_gate4 = restarted_client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={
            "decision": "approved",
            "snapshot_hash": revised_snapshot["snapshot_hash"],
            "snapshot_revision": revised_snapshot["snapshot_revision"],
        },
    )
    assert revised_gate4.status_code == 200
    assert len(public_fallback_research_calls) == 0

    trace_view = StartupTraceQueryService(
        JsonlAuditSpool(data_root / "startup-api" / "deterministic" / "startup-audit-spool")
    ).get_view(case_id, f"startup-api-{case_id}")
    assert trace_view.report_lineage.report_id == revised_snapshot["snapshot_id"]
    assert trace_view.report_lineage.report_checksum == revised_snapshot[
        "snapshot_hash"
    ].removeprefix("sha256:")
    assert trace_view.report_lineage.report_revision == 3
    assert trace_view.report_lineage.report_id != baseline_snapshot["snapshot_id"]
    assert trace_view.report_lineage.report_revision != baseline_snapshot["snapshot_revision"]
    _clear_startup_dependency_cache()


def test_startup_api_report_json_returns_founder_safe_projection_after_same_case_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches public JSON accidentally exposing canonical report internals."""

    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)
    fixture = (
        Path(__file__).parents[1]
        / "fixtures"
        / "startup_synthetic_v1"
        / "cases"
        / "saas"
        / "pitch.pdf"
    )

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[
            (
                "files",
                ("private-founder-upload.pdf", fixture.read_bytes(), "application/pdf"),
            )
        ],
    )
    assert uploaded.status_code == 200

    pricing_question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    assert pricing_question.status_code == 200
    assert pricing_question.json()["next_question"]["field_key"] == "burn_cash"
    pricing_answer = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": pricing_question.json()["next_question"]["question_id"],
            "answer_type": "manual",
            "value": (
                "Use finance forecast for July 2026: cash balance $250,000, monthly "
                "net burn $42,000, runway about 6 months."
            ),
        },
    )
    assert pricing_answer.status_code == 200
    assert pricing_answer.json()["recalculation_data_revision"] == 2

    _assert_public_research_deferred_without_mutation(
        client,
        coordinator=coordinator,
        case_id=case_id,
        expected_revision=2,
        expected_skipped=("problem", "stage", "revenue_pricing"),
    )

    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200
    gate3 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate3/decision",
        json={"decision": "continue", "exclusions": []},
    )
    assert gate3.status_code == 200
    report = client.get(f"/api/v1/startup/cases/{case_id}/report")
    assert report.status_code == 200, report.json()
    assert report.json()["snapshot_revision"] == 2

    public_json = client.get(f"/api/v1/startup/cases/{case_id}/report/json")
    assert public_json.status_code == 200
    payload = public_json.json()

    assert payload["data_revision"] == 2
    assert set(payload) == {
        "title_ru",
        "subtitle_ru",
        "as_of_ru",
        "data_revision",
        "main_sections",
        "metric_cards",
        "improvement_proposals",
        "technical_appendix",
        "analytics",
    }
    assert "main_sections" in payload
    assert {section["key"] for section in payload["main_sections"]} >= {
        "business_idea_summary",
        "problem_solution",
        "metrics",
        "risks",
        "action_plan",
    }
    assert "technical_appendix" in payload
    rendered = json.dumps(payload, ensure_ascii=False)
    for forbidden_key in (
        "document_text_block",
        "prompt_versions",
        "trace_ids",
        "source_hashes",
        "report_hash",
        "case_snapshot_hash",
        "snapshot_hash",
        "source_appendix",
        "evidence_refs",
        "calculation_ref",
        "dimension_ref",
        "formula_versions",
        "model_versions",
        "reproducibility",
        "sensitivity",
        "created_at",
    ):
        assert not _json_contains_key(payload, forbidden_key)
    for forbidden_token in (
        "MISSING",
        "sha256:",
        "private-founder-upload.pdf",
        str(fixture),
        "Provide primary support",
        "prompt_versions",
        "chain_of_thought",
        "reasoning_trace",
    ):
        assert forbidden_token not in rendered
    _clear_startup_dependency_cache()


def test_startup_api_upload_auto_start_returns_typed_error_when_workflow_fails(
    tmp_path: Path,
) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        deterministic_analysis_service=FailedStartAnalysisProbe("workflow_unexpected"),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path / "inbox",
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    ).json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[("files", ("pitch.csv", b"ARR,100\n", "text/csv"))],
    )

    assert uploaded.status_code == 409
    assert uploaded.json() == {
        "code": "workflow_unexpected",
        "message": "workflow_unexpected",
    }
    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["analysis_status"] == "failed"
    assert runtime["error_code"] == "workflow_unexpected"
    assert client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview").status_code == 404


def test_startup_api_upload_projects_budget_exhaustion_to_safe_typed_error(
    tmp_path: Path,
) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        deterministic_analysis_service=FailedStartAnalysisProbe("BUDGET_EXCEEDED"),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path / "inbox",
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    ).json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[("files", ("pitch.csv", b"ARR,100\n", "text/csv"))],
    )

    assert uploaded.status_code == 409
    assert uploaded.json() == {
        "code": "budget_exceeded",
        "message": "budget_exceeded",
    }
    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["analysis_status"] == "failed"
    assert runtime["error_code"] == "budget_exceeded"


def test_startup_api_upload_sanitizes_failed_workflow_error_code(
    tmp_path: Path,
) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        deterministic_analysis_service=FailedStartAnalysisProbe(
            "provider timeout: token abc",
        ),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path / "inbox",
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    ).json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[("files", ("pitch.csv", b"ARR,100\n", "text/csv"))],
    )

    assert uploaded.status_code == 409
    assert uploaded.json() == {
        "code": "workflow_failed",
        "message": "workflow_failed",
    }
    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["analysis_status"] == "failed"
    assert runtime["error_code"] == "workflow_failed"
    assert "provider timeout" not in repr(runtime)
    assert "token abc" not in repr(runtime)


def test_startup_api_upload_does_not_return_stale_failure_after_new_revision(
    tmp_path: Path,
) -> None:
    store = InMemoryStartupWorkflowRuntimeStore()
    stale_failure = StaleFailedStartAnalysisProbe(store)
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        deterministic_analysis_service=stale_failure,
        workflow_store=store,
        inbox_root=tmp_path / "inbox",
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    ).json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[("files", ("pitch.csv", b"ARR,100\n", "text/csv"))],
    )

    assert uploaded.status_code == 200
    assert uploaded.json()["analysis_status"] == "awaiting_start"
    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["data_revision"] == 2
    assert runtime["active_analysis_thread_id"] == f"{case_id}:r2"
    assert runtime["analysis_status"] == "awaiting_start"
    assert "error_code" not in runtime


def test_startup_api_rejects_boolean_gate4_snapshot_revision(tmp_path: Path) -> None:
    reports = ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1))
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": True},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "request_validation_error",
        "message": "request_validation_error",
    }
    assert reports.decisions == []


def test_startup_api_missing_report_port_snapshot_returns_typed_not_ready(
    tmp_path: Path,
) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=MissingReportFacadeProbe(),
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    for path in (
        f"/api/v1/startup/cases/{case_id}/report",
        f"/api/v1/startup/cases/{case_id}/report/json",
        f"/api/v1/startup/cases/{case_id}/report/html",
        f"/api/v1/startup/cases/{case_id}/report/pdf",
    ):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["code"] == "report_not_ready"
    gate4 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
    )
    assert gate4.status_code == 404
    assert gate4.json()["code"] == "report_not_ready"


def test_startup_api_renderer_failure_is_typed_503_after_gate4_approval(tmp_path: Path) -> None:
    reports = ReportFacadeProbe(
        snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1),
        pdf_error=StartupReportRendererUnavailable("report_renderer_unavailable"),
    )
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        report_port=reports,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]
    approved = client.post(
        f"/api/v1/startup/cases/{case_id}/gate4/decision",
        json={"decision": "approved", "snapshot_hash": "hash-1", "snapshot_revision": 1},
    )
    assert approved.status_code == 200

    pdf = client.get(f"/api/v1/startup/cases/{case_id}/report/pdf")

    assert pdf.status_code == 503
    assert pdf.json() == {
        "code": "report_renderer_unavailable",
        "message": "report_renderer_unavailable",
    }


def test_startup_api_dependency_wires_matching_live_and_deterministic_report_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"
    live_data_dir = data_root / "startup-api"
    deterministic_data_dir = live_data_dir / "deterministic"
    shared_inbox_root = live_data_dir / "inbox"
    analysis_dirs: list[Path] = []
    live_tracers: list[object] = []
    deterministic_analysis_calls: list[tuple[Path, Path | None, object]] = []
    report_dirs: list[Path] = []

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    def build_analysis(data_dir: Path, **kwargs: object) -> AnalysisProbe:
        analysis_dirs.append(data_dir)
        live_tracers.append(kwargs["external_node_tracer"])
        return AnalysisProbe()

    def build_deterministic_analysis(
        data_dir: Path,
        *,
        inbox_root: Path | None = None,
        external_node_tracer: object,
    ) -> AnalysisProbe:
        deterministic_analysis_calls.append((data_dir, inbox_root, external_node_tracer))
        return AnalysisProbe()

    def build_report_port(data_dir: Path) -> ReportFacadeProbe:
        report_dirs.append(data_dir)
        return ReportFacadeProbe(
            snapshot=CanonicalReportSnapshot(
                snapshot_id=f"snapshot-{data_dir.name}",
                snapshot_hash=sha256(data_dir.name.encode("utf-8")).hexdigest(),
                snapshot_revision=1,
            )
        )

    fake_bootstrap = ModuleType("due_diligence_agent.bootstrap")
    fake_container = ModuleType("due_diligence_agent.bootstrap.container")
    fake_container.build_startup_analysis_composer = build_analysis
    fake_container.build_deterministic_startup_analysis_composer = build_deterministic_analysis
    fake_container.build_startup_report_port = build_report_port
    fake_bootstrap.container = fake_container
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap.container", fake_container)
    monkeypatch.setattr("due_diligence_agent.presentation.api.dependencies.Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)

    coordinator = get_startup_case_coordinator()
    live_case = coordinator.create_case({"fixture_mode": "live", "auto_start": False})
    deterministic_case = coordinator.create_case(
        {"fixture_mode": "deterministic_offline", "auto_start": False}
    )

    assert coordinator.get_report(live_case.case_id).snapshot_id == "snapshot-startup-api"
    assert (
        coordinator.get_report(deterministic_case.case_id).snapshot_id == "snapshot-deterministic"
    )
    assert analysis_dirs == [live_data_dir]
    assert live_tracers[0] is not None
    assert deterministic_analysis_calls[0][:2] == (
        deterministic_data_dir,
        shared_inbox_root,
    )
    assert deterministic_analysis_calls[0][2] is not None
    assert report_dirs == [live_data_dir, deterministic_data_dir]
    _clear_startup_dependency_cache()


def test_startup_api_dependency_keeps_live_provider_unavailable_without_openai_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"
    analysis_kwargs: list[dict[str, object]] = []

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    def build_analysis(data_dir: Path, **kwargs: object) -> AnalysisProbe:
        analysis_kwargs.append(kwargs)
        return AnalysisProbe()

    fake_bootstrap = ModuleType("due_diligence_agent.bootstrap")
    fake_container = ModuleType("due_diligence_agent.bootstrap.container")
    fake_container.build_startup_analysis_composer = build_analysis
    fake_container.build_deterministic_startup_analysis_composer = lambda _data_dir, **_kwargs: AnalysisProbe()
    fake_container.build_startup_report_port = lambda _data_dir: ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1))
    fake_bootstrap.container = fake_container
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap.container", fake_container)
    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(
        api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings, raising=False
    )

    coordinator = get_startup_case_coordinator()
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    assert created.provider_status == "unavailable"
    assert len(analysis_kwargs) == 1
    assert analysis_kwargs[0]["external_node_tracer"] is not None
    _clear_startup_dependency_cache()


def test_startup_api_dependency_wires_enabled_live_and_disabled_deterministic_langsmith(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"
    live_kwargs: list[dict[str, object]] = []
    deterministic_kwargs: list[dict[str, object]] = []

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = True

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    def build_analysis(data_dir: Path, **kwargs: object) -> AnalysisProbe:
        assert data_dir == data_root / "startup-api"
        live_kwargs.append(kwargs)
        return AnalysisProbe()

    def build_deterministic_analysis(
        _data_dir: Path,
        **kwargs: object,
    ) -> AnalysisProbe:
        deterministic_kwargs.append(kwargs)
        return AnalysisProbe()

    fake_bootstrap = ModuleType("due_diligence_agent.bootstrap")
    fake_container = ModuleType("due_diligence_agent.bootstrap.container")
    fake_container.build_startup_analysis_composer = build_analysis
    fake_container.build_deterministic_startup_analysis_composer = build_deterministic_analysis
    fake_container.build_startup_report_port = lambda _data_dir: ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1))
    fake_bootstrap.container = fake_container
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap.container", fake_container)
    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(
        api_dependencies,
        "OpenAIStartupSettings",
        FakeOpenAIStartupSettings,
        raising=False,
    )
    monkeypatch.setenv("LANGSMITH_API_KEY", "present-but-never-logged")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    get_startup_case_coordinator()

    assert len(live_kwargs) == 1
    assert live_kwargs[0]["external_node_tracer"] is not None
    assert deterministic_kwargs[0]["inbox_root"] == data_root / "startup-api" / "inbox"
    assert deterministic_kwargs[0]["external_node_tracer"] is not None
    assert "present-but-never-logged" not in repr(live_kwargs)
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    _clear_startup_dependency_cache()


def test_startup_api_dependency_keeps_custom_langsmith_disabled_and_lazy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"
    live_kwargs: list[dict[str, object]] = []

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    def build_analysis(_data_dir: Path, **kwargs: object) -> AnalysisProbe:
        live_kwargs.append(kwargs)
        return AnalysisProbe()

    fake_bootstrap = ModuleType("due_diligence_agent.bootstrap")
    fake_container = ModuleType("due_diligence_agent.bootstrap.container")
    fake_container.build_startup_analysis_composer = build_analysis
    fake_container.build_deterministic_startup_analysis_composer = lambda _data_dir, **_kwargs: AnalysisProbe()
    fake_container.build_startup_report_port = lambda _data_dir: ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1))
    fake_bootstrap.container = fake_container
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap.container", fake_container)
    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(
        api_dependencies,
        "OpenAIStartupSettings",
        FakeOpenAIStartupSettings,
        raising=False,
    )
    monkeypatch.setenv("LANGSMITH_API_KEY", "present-but-never-logged")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    get_startup_case_coordinator()

    assert len(live_kwargs) == 1
    assert live_kwargs[0]["external_node_tracer"] is not None
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    _clear_startup_dependency_cache()


def test_startup_api_dependency_wires_live_openai_components_factory_when_key_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = tmp_path / "app-data"
    components_factory_calls: list[Path] = []

    class FakeSecret:
        def get_secret_value(self) -> str:
            return "sk-test-not-real"

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root

    class FakeOpenAIStartupSettings:
        openai_api_key = FakeSecret()

    def build_analysis(data_dir: Path, **kwargs: object) -> AnalysisProbe:
        components_factory = kwargs.get("ai_components_factory")
        assert callable(components_factory)
        components_factory_calls.append(data_dir)
        return AnalysisProbe()

    fake_bootstrap = ModuleType("due_diligence_agent.bootstrap")
    fake_container = ModuleType("due_diligence_agent.bootstrap.container")
    fake_container.build_startup_analysis_composer = build_analysis
    fake_container.build_deterministic_startup_analysis_composer = lambda _data_dir, **_kwargs: AnalysisProbe()
    fake_container.build_startup_report_port = lambda _data_dir: ReportFacadeProbe(snapshot=CanonicalReportSnapshot("snapshot-1", "hash-1", 1))
    fake_container.build_openai_startup_components = lambda **_kwargs: object()
    fake_bootstrap.container = fake_container
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap", fake_bootstrap)
    monkeypatch.setitem(sys.modules, "due_diligence_agent.bootstrap.container", fake_container)
    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(
        api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings, raising=False
    )

    coordinator = get_startup_case_coordinator()
    created = coordinator.create_case({"fixture_mode": "live", "auto_start": False})

    assert created.provider_status == "configured"
    assert components_factory_calls == [data_root / "startup-api"]
    _clear_startup_dependency_cache()


def test_startup_api_rejects_empty_upload_and_preserves_manual_start(tmp_path: Path) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    empty = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[],
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "empty_upload"

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "false"},
        files=[("files", ("secret deck.pdf", b"ARR 100", "application/pdf"))],
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["auto_start_triggered"] is False
    assert coordinator.get_status(case_id).analysis_status == "awaiting_start"
    assert analysis.starts == []


def test_startup_api_normalizes_declared_mime_from_multipart_upload(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "false"},
        files=[("files", ("deck.pdf", b"ARR 100", "Application/PDF; charset=utf-8"))],
    )

    assert response.status_code == 200
    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["documents"][0]["declared_mime_type"] == "application/pdf"


def test_startup_api_upload_passes_filename_into_private_metadata_without_public_echo(
    tmp_path: Path,
) -> None:
    analysis = AnalysisProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=analysis,
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true"},
        files=[("files", ("..\\secret\\Founder Pitch.PDF", b"ARR 100", "application/pdf"))],
    )

    assert response.status_code == 200
    assert response.json()["accepted_document_ids"] == ["doc-0001"]
    serialized_response = response.text
    assert "Founder Pitch" not in serialized_response
    assert "secret" not in serialized_response
    runtime = coordinator.runtime_for_test(case_id)
    assert runtime["documents"] == [
        {
            "document_id": "doc-0001",
            "private_name": "doc-0001.pdf",
            "declared_mime_type": "application/pdf",
            "byte_size": 7,
            "source_name_sha256": (
                "289745fce8583e22aaf424661e1e3a49fff67befd0b78fe8754047c478fc6e72"
            ),
            "content_sha256": ("4cd1e99af0121efb2531f05cda9c7c630721722da25af4b03a94a862a6f45ceb"),
        }
    ]
    assert "Founder Pitch" not in repr(runtime)
    assert str(tmp_path) not in repr(runtime)
    assert analysis.starts[0]["thread_id"] == f"{case_id}:r1"
    assert analysis.starts[0]["payload"]["source_document_ids"] == ["doc-0001"]
    assert analysis.starts[0]["payload"]["source_refs"] == [
        {
            "document_id": "doc-0001",
            "private_name": "doc-0001.pdf",
            "content_sha256": ("4cd1e99af0121efb2531f05cda9c7c630721722da25af4b03a94a862a6f45ceb"),
        }
    ]
    assert analysis.starts[0]["payload"]["data_revision"] == 1
    assert str(tmp_path) not in repr(analysis.starts[0]["payload"])
    assert "Founder Pitch" not in repr(analysis.starts[0]["payload"])


def test_startup_validation_errors_do_not_echo_sensitive_inputs(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    secret_company = "Secret FounderCo pitch.pdf token-abc123"

    response = client.post(
        "/api/v1/startup/cases",
        json={
            "fixture_mode": "deterministic_offline",
            "company_name": secret_company,
            "resume_token": "token-abc123",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "request_validation_error",
        "message": "request_validation_error",
    }
    serialized = response.text
    assert "Secret FounderCo" not in serialized
    assert "pitch.pdf" not in serialized
    assert "token-abc123" not in serialized
    assert "resume_token" not in serialized
    assert "input" not in serialized


def test_startup_api_serves_current_profile_without_private_runtime_material(
    tmp_path: Path,
) -> None:
    profiles = ProfileQueryProbe(_startup_profile())
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=profiles,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]
    profile = _startup_profile(case_id=UUID(case_id))
    profiles.profile = profile
    coordinator.seed_status_for_test(
        case_id,
        {
            "profile_id": str(profile.profile_id),
            "profile_hash": profile.profile_hash,
            "profile_revision": profile.data_revision,
            "private_path": str(tmp_path / "Founder Pitch Secret.pdf"),
            "raw_filename": "Founder Pitch Secret.pdf",
            "prompt": "summarize the secret deck",
            "excerpt": "raw founder excerpt should stay private",
        },
    )

    response = client.get(f"/api/v1/startup/cases/{case_id}/profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == case_id
    assert payload["profile_id"] == str(profile.profile_id)
    assert payload["profile_hash"] == profile.profile_hash
    assert payload["data_revision"] == 1
    assert payload["analysis_stage"] == "primary"
    assert payload["parent_profile_id"] is None
    assert set(payload["fields"]) == {field.value for field in StartupProfileFieldName}
    assert payload["fields"]["startup_name"] == {
        "status": "source_fact",
        "values": ["FounderCo"],
        "confidence": "0.95",
        "evidence_refs": [
            {
                "evidence_id": str(profile.fields["startup_name"].evidence_refs[0].evidence_id),
                "fragment_id": str(profile.fields["startup_name"].evidence_refs[0].fragment_id),
                "artifact_id": str(profile.fields["startup_name"].evidence_refs[0].artifact_id),
                "artifact_hash": f"sha256:{'1' * 64}",
                "locator_hash": f"sha256:{'2' * 64}",
                "page": 1,
                "table": None,
                "cell": None,
                "field_name": "startup_name",
                "confidence": "0.95",
            }
        ],
        "dependency_refs": [],
        "reason_code": None,
        "contradiction_ids": [],
    }
    assert payload["gaps"] == ["users"]
    assert payload["contradictions"] == []
    assert payload["parse_inventory"] == {
        "source_hashes": {"doc-0001": f"sha256:{'1' * 64}"},
        "parse_outcomes": {"doc-0001": "parsed"},
    }
    serialized = response.text
    assert str(tmp_path) not in serialized
    assert "Founder Pitch Secret.pdf" not in serialized
    assert "summarize the secret deck" not in serialized
    assert "raw founder excerpt" not in serialized


def test_startup_api_profile_not_ready_and_stale_are_stable_409_codes(
    tmp_path: Path,
) -> None:
    profiles = ProfileQueryProbe(_startup_profile())
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=profiles,
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    not_ready = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert not_ready.status_code == 409
    assert not_ready.json() == {
        "code": "startup_profile_not_ready",
        "message": "startup_profile_not_ready",
    }

    profile = _startup_profile(case_id=UUID(case_id))
    profiles.profile = profile
    coordinator.seed_status_for_test(
        case_id,
        {
            "profile_id": str(profile.profile_id),
            "profile_hash": f"sha256:{'9' * 64}",
            "profile_revision": profile.data_revision,
        },
    )

    stale = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert stale.status_code == 409
    assert stale.json() == {
        "code": "startup_profile_stale",
        "message": "startup_profile_stale",
    }


def test_startup_api_profile_unknown_case_is_404(tmp_path: Path) -> None:
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=ProfileQueryProbe(_startup_profile()),
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    response = TestClient(app).get(
        "/api/v1/startup/cases/00000000-0000-0000-0000-000000000000/profile"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "case_not_found"


def test_startup_api_serves_founder_safe_gtm_snapshot_without_private_runtime_material(
    tmp_path: Path,
) -> None:
    profiles = ProfileQueryProbe(_startup_profile())
    gtm_snapshots = GtmQueryProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=profiles,
        gtm_port=gtm_snapshots,
        case_revision_port=CaseRevisionQueryProbe(1),
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]
    profile = _startup_profile(case_id=UUID(case_id))
    profiles.profile = profile
    snapshot = _startup_gtm_snapshot(UUID(case_id), profile_id=profile.profile_id)
    gtm_snapshots.snapshot = snapshot
    coordinator.seed_status_for_test(
        case_id,
        {
            "data_revision": snapshot.data_revision,
            "profile_id": str(snapshot.profile_id),
            "profile_hash": profile.profile_hash,
            "profile_revision": snapshot.data_revision,
            "product_validation_snapshot_id": str(snapshot.product_validation_snapshot_id),
            "market_research_snapshot_id": str(snapshot.market_research_snapshot_id),
            "gtm_snapshot_id": str(snapshot.snapshot_id),
            "gtm_snapshot_hash": snapshot.snapshot_hash,
            "gtm_snapshot_revision": snapshot.data_revision,
            "private_path": str(tmp_path / "Founder Pitch Secret.pdf"),
            "raw_prompt": "summarize founder@example.com sk-live-secret",
        },
    )

    response = client.get(f"/api/v1/startup/cases/{case_id}/gtm")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "case_id",
        "schema_version",
        "snapshot_id",
        "snapshot_hash",
        "snapshot_revision",
        "status",
        "profile_id",
        "product_validation_snapshot_id",
        "market_research_snapshot_id",
        "dimensions",
        "launch_plan",
        "finding_ids",
        "built_at",
    }
    assert payload["schema_version"] == "startup_gtm@1"
    assert payload["snapshot_id"] == str(snapshot.snapshot_id)
    assert payload["snapshot_hash"] == snapshot.snapshot_hash
    assert payload["snapshot_revision"] == 1
    assert [item["name"] for item in payload["dimensions"]] == [
        item.value for item in StartupGtmDimensionName
    ]
    assert [item["horizon"] for item in payload["launch_plan"]] == [
        item.value for item in StartupGtmHorizon
    ]
    assert str(tmp_path) not in response.text
    assert "Founder Pitch Secret.pdf" not in response.text
    assert "founder@example.com" not in response.text
    assert "sk-live-secret" not in response.text


def test_startup_api_gtm_not_ready_and_stale_are_stable_409_codes(tmp_path: Path) -> None:
    profiles = ProfileQueryProbe(_startup_profile())
    gtm_snapshots = GtmQueryProbe()
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
        profile_port=profiles,
        gtm_port=gtm_snapshots,
        case_revision_port=CaseRevisionQueryProbe(1),
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    client = TestClient(app)
    case_id = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "live", "auto_start": False},
    ).json()["case_id"]

    not_ready = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert not_ready.status_code == 409
    assert not_ready.json() == {
        "code": "startup_gtm_not_ready",
        "message": "startup_gtm_not_ready",
    }

    profile = _startup_profile(case_id=UUID(case_id))
    profiles.profile = profile
    snapshot = _startup_gtm_snapshot(UUID(case_id), profile_id=profile.profile_id)
    gtm_snapshots.snapshot = snapshot
    coordinator.seed_status_for_test(
        case_id,
        {
            "data_revision": snapshot.data_revision,
            "profile_id": str(snapshot.profile_id),
            "profile_hash": profile.profile_hash,
            "profile_revision": snapshot.data_revision,
            "product_validation_snapshot_id": str(snapshot.product_validation_snapshot_id),
            "market_research_snapshot_id": str(snapshot.market_research_snapshot_id),
            "gtm_snapshot_id": str(snapshot.snapshot_id),
            "gtm_snapshot_hash": f"sha256:{'9' * 64}",
            "gtm_snapshot_revision": snapshot.data_revision,
        },
    )

    stale = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert stale.status_code == 409
    assert stale.json() == {
        "code": "startup_gtm_stale",
        "message": "startup_gtm_stale",
    }


def test_startup_api_rejects_gtm_when_runtime_profile_hash_is_stale(
    tmp_path: Path,
) -> None:
    case_id = uuid4()
    profile = _startup_profile(case_id=case_id)
    snapshot = _startup_gtm_snapshot(case_id, profile_id=profile.profile_id)
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(case_id), {"case_exists": True, "fixture_mode": "live"})
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=workflow_store,
        inbox_root=tmp_path,
        profile_port=ProfileQueryProbe(profile),
        gtm_port=GtmQueryProbe(snapshot),
        case_revision_port=CaseRevisionQueryProbe(snapshot.data_revision),
    )
    coordinator.seed_status_for_test(
        str(case_id),
        {
            "data_revision": snapshot.data_revision,
            "profile_id": str(snapshot.profile_id),
            "profile_hash": f"sha256:{'9' * 64}",
            "profile_revision": snapshot.data_revision,
            "product_validation_snapshot_id": str(snapshot.product_validation_snapshot_id),
            "market_research_snapshot_id": str(snapshot.market_research_snapshot_id),
            "gtm_snapshot_id": str(snapshot.snapshot_id),
            "gtm_snapshot_hash": snapshot.snapshot_hash,
            "gtm_snapshot_revision": snapshot.data_revision,
        },
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator

    response = TestClient(app).get(f"/api/v1/startup/cases/{case_id}/gtm")

    assert response.status_code == 409
    assert response.json() == {
        "code": "startup_gtm_stale",
        "message": "startup_gtm_stale",
    }


def test_startup_api_rejects_self_consistent_gtm_after_authoritative_revision_advances(
    tmp_path: Path,
) -> None:
    case_id = uuid4()
    previous_profile = _startup_profile(case_id=case_id, data_revision=1)
    current_profile = _startup_profile(case_id=case_id, data_revision=2)
    snapshot = _startup_gtm_snapshot(
        case_id,
        profile_id=previous_profile.profile_id,
        data_revision=1,
    )
    workflow_store = InMemoryStartupWorkflowRuntimeStore()
    workflow_store.save(str(case_id), {"case_exists": True, "fixture_mode": "live"})
    coordinator = StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=workflow_store,
        inbox_root=tmp_path,
        profile_port=ProfileHistoryQueryProbe(
            current=current_profile,
            history=(previous_profile, current_profile),
        ),
        gtm_port=GtmQueryProbe(snapshot),
        case_revision_port=CaseRevisionQueryProbe(2),
    )
    coordinator.seed_status_for_test(
        str(case_id),
        {
            "data_revision": snapshot.data_revision,
            "profile_id": str(snapshot.profile_id),
            "profile_hash": previous_profile.profile_hash,
            "profile_revision": snapshot.data_revision,
            "product_validation_snapshot_id": str(snapshot.product_validation_snapshot_id),
            "market_research_snapshot_id": str(snapshot.market_research_snapshot_id),
            "gtm_snapshot_id": str(snapshot.snapshot_id),
            "gtm_snapshot_hash": snapshot.snapshot_hash,
            "gtm_snapshot_revision": snapshot.data_revision,
        },
    )
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator

    response = TestClient(app).get(f"/api/v1/startup/cases/{case_id}/gtm")

    assert response.status_code == 409
    assert response.json() == {
        "code": "startup_gtm_stale",
        "message": "startup_gtm_stale",
    }


def test_startup_openapi_lists_all_v1_routes(tmp_path: Path) -> None:
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: StartupCaseCoordinator(
        analysis_service=AnalysisProbe(),
        workflow_store=InMemoryStartupWorkflowRuntimeStore(),
        inbox_root=tmp_path,
    )
    schema = TestClient(app).get("/openapi.json").json()

    for path in (
        "/api/v1/startup/cases",
        "/api/v1/startup/cases/{case_id}",
        "/api/v1/startup/cases/{case_id}/documents",
        "/api/v1/startup/cases/{case_id}/analysis",
        "/api/v1/startup/cases/{case_id}/profile",
        "/api/v1/startup/cases/{case_id}/gtm",
        "/api/v1/startup/cases/{case_id}/gate2/preview",
        "/api/v1/startup/cases/{case_id}/gate2/decision",
        "/api/v1/startup/cases/{case_id}/gate3/decision",
        "/api/v1/startup/cases/{case_id}/gate4/decision",
        "/api/v1/startup/cases/{case_id}/report",
        "/api/v1/startup/cases/{case_id}/report/json",
        "/api/v1/startup/cases/{case_id}/report/html",
        "/api/v1/startup/cases/{case_id}/report/pdf",
        "/api/v1/startup/cases/{case_id}/advisor/next-question",
        "/api/v1/startup/cases/{case_id}/advisor/answers",
        "/api/v1/startup/cases/{case_id}/advisor/improvements",
        "/api/v1/startup/cases/{case_id}/advisor/improvements/{proposal_id}/decision",
    ):
        assert path in schema["paths"]


def test_startup_advisor_api_returns_bounded_founder_dtos() -> None:
    case_id = str(uuid4())
    proposal_id = str(uuid4())
    facade = AdvisorApiFacadeProbe(case_id=case_id, proposal_id=proposal_id)
    app = create_app()
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: facade
    client = TestClient(app)

    question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    blocked = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": f"{case_id}:icp",
            "answer_type": "public_research",
            "consent_public_research": False,
        },
    )
    improvements = client.get(f"/api/v1/startup/cases/{case_id}/advisor/improvements")
    accepted = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/improvements/{proposal_id}/decision",
        json={"decision": "accepted"},
    )

    assert question.status_code == 200
    assert question.json()["next_question"]["question_ru"].startswith("Какая")
    assert question.json()["next_question"]["answer_mode_labels_ru"]["manual"] == "Вручную"
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["research_result"]["status"] == "blocked"
    assert improvements.status_code == 200
    assert improvements.json()["improvement_version"] == 1
    assert accepted.status_code == 200
    assert accepted.json()["new_version"] == 2
    serialized = f"{question.text} {blocked.text} {improvements.text} {accepted.text}"
    assert "MISSING" not in serialized
    assert "sha256:" not in serialized
    assert "C:\\" not in serialized
    assert "sk-live-secret" not in serialized
    assert "prompt" not in serialized.casefold()


def test_startup_advisor_answer_response_exposes_bounded_recalculation_delta() -> None:
    case_id = str(uuid4())
    facade = AdvisorApiFacadeWithDeltaProbe(case_id=case_id, proposal_id=str(uuid4()))
    app = create_app()
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: facade
    client = TestClient(app)

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": f"{case_id}:icp",
            "answer_type": "manual",
            "value": "FMCG distributors and procurement managers.",
        },
    )

    assert response.status_code == 200
    delta = response.json()["recalculation_delta"]
    assert delta == {
        "previous_revision": 1,
        "new_revision": 2,
        "fields_changed": ["icp"],
        "core_coverage_delta": 1,
        "conflicts_resolved": 0,
        "conflicts_remaining": 0,
        "calculations_recalculated": [],
        "calculations_pending": ["report"],
    }
    serialized = response.text
    assert "sha256:" not in serialized
    assert "C:\\" not in serialized
    assert "private" not in serialized.casefold()
    assert "prompt" not in serialized.casefold()


def test_startup_advisor_answer_maps_semantic_mismatch_to_422() -> None:
    case_id = str(uuid4())
    facade = AdvisorApiSemanticMismatchProbe(case_id=case_id, proposal_id=str(uuid4()))
    app = create_app()
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: facade

    response = TestClient(app).post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": f"{case_id}:revenue_pricing",
            "answer_type": "manual",
            "value": "60%",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "advisor_manual_answer_semantic_mismatch",
        "message": "advisor_manual_answer_semantic_mismatch",
    }


def test_startup_advisor_answer_request_enforces_file_binding_shape() -> None:
    case_id = str(uuid4())
    facade = AdvisorApiFacadeProbe(case_id=case_id, proposal_id=str(uuid4()))
    app = create_app()
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: facade
    client = TestClient(app)

    invalid = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": f"{case_id}:revenue_pricing",
            "answer_type": "file",
        },
    )
    manual = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": f"{case_id}:revenue_pricing",
            "answer_type": "manual",
            "value": "bounded founder answer",
        },
    )

    assert invalid.status_code == 422
    assert invalid.json()["code"] == "request_validation_error"
    assert manual.status_code == 200
    assert "bounded founder answer" not in manual.text
    assert facade.answer_requests[-1]["value"] == "bounded founder answer"


def test_startup_advisor_api_maps_unknown_case_to_stable_404() -> None:
    facade = AdvisorApiFacadeProbe(case_id=str(uuid4()), proposal_id=str(uuid4()))
    app = create_app()
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: facade

    response = TestClient(app).get(f"/api/v1/startup/cases/{uuid4()}/advisor/next-question")

    assert response.status_code == 404
    assert response.json() == {
        "code": "case_not_found",
        "message": "case_not_found",
    }


def test_capabilities_expose_delivered_startup_api_behavior() -> None:
    response = TestClient(create_app()).get("/api/v1/product/capabilities")

    assert response.status_code == 200
    by_key = {item["key"]: item for item in response.json()["capabilities"]}
    assert by_key["universal_upload"]["lifecycle_status"] == "available"
    assert by_key["primary_startup_analysis"]["lifecycle_status"] == "available"
    assert by_key["deep_startup_analysis"]["lifecycle_status"] == "planned"


class AnalysisProbe:
    def __init__(self, *, checkpoint_identity: dict[str, Any] | None = None) -> None:
        self.starts: list[dict[str, Any]] = []
        self.resumes: list[dict[str, Any]] = []
        self._checkpoint_identity = checkpoint_identity

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.starts.append({"payload": payload, "thread_id": thread_id})
        return {
            "status": "approval_required",
            "pending_gate": "startup_disclosure",
            "evidence_fact_ids": ["fact-1"],
        }

    def resume(self, approval: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.resumes.append({"approval": approval, "thread_id": thread_id})
        if approval.get("gate") == "startup_gate3_review":
            return {"status": "completed", "pending_gate": None}
        return {"status": "review_required", "pending_gate": "startup_gate3_review"}

    def checkpoint_identity(self, *, thread_id: str) -> dict[str, Any] | None:
        if self._checkpoint_identity is None:
            return None
        return {**self._checkpoint_identity, "thread_id": thread_id}


class AdvisorApiFacadeProbe:
    def __init__(self, *, case_id: str, proposal_id: str) -> None:
        self.case_id = case_id
        self.proposal_id = proposal_id
        self.answer_requests: list[dict[str, object]] = []

    def _require_case(self, case_id: str) -> None:
        if case_id != self.case_id:
            raise StartupNotFound("case_not_found")

    def get_next_question(self, case_id: str) -> dict[str, object]:
        self._require_case(case_id)
        return {
            "case_id": case_id,
            "status": "active",
            "next_question": {
                "question_id": f"{case_id}:icp",
                "field_key": "icp",
                "question_ru": "Какая целевая аудитория является основной?",
                "reason_ru": "Это уточняет позиционирование.",
                "unlocks_ru": "Позиционирование",
                "answer_modes": ["manual", "file", "public_research", "skip"],
                "answer_mode_labels_ru": {
                    "manual": "Вручную",
                    "file": "Файл",
                    "public_research": "Публичный поиск",
                    "skip": "Пропустить",
                },
            },
            "answered_count": 0,
            "total_count": 5,
        }

    def submit_answer(self, case_id: str, **request: object) -> dict[str, object]:
        self._require_case(case_id)
        self.answer_requests.append(dict(request))
        public_research = request.get("answer_type") == "public_research"
        consent = request.get("consent_public_research") is True
        return {
            "case_id": case_id,
            "question_id": str(request["question_id"]),
            "field_key": "icp",
            "answer_type": str(request["answer_type"]),
            "status": "applied" if not public_research or consent else "blocked",
            "confidence_delta": 0,
            "analysis_blocked": public_research and not consent,
            "answered_count": 1 if not public_research or consent else 0,
            "total_count": 5,
            "research_result": (
                {
                    "status": "partial" if consent else "blocked",
                    "summary_ru": (
                        "Использованы сохранённые публичные источники."
                        if consent
                        else "Публичный поиск заблокирован без согласия."
                    ),
                    "source_ids": [],
                    "fallback_used": consent,
                    "fail_reason_ru": None,
                }
                if public_research
                else None
            ),
        }

    def list_improvements(self, case_id: str) -> dict[str, object]:
        self._require_case(case_id)
        return {
            "case_id": case_id,
            "improvement_version": 1,
            "proposals": [
                {
                    "proposal_id": self.proposal_id,
                    "target_area": "positioning",
                    "recommendation_ru": "Уточните позиционирование стартапа.",
                    "rationale_ru": "Это повысит ясность ценности.",
                    "expected_effect_ru": "Инвестору будет проще оценить продукт.",
                    "evidence_kinds": ["public_fact"],
                    "confidence": "0.70",
                }
            ],
        }

    def decide_improvement(
        self,
        case_id: str,
        *,
        proposal_id: UUID,
        decision: str,
    ) -> dict[str, object]:
        self._require_case(case_id)
        return {
            "case_id": case_id,
            "proposal_id": str(proposal_id),
            "decision": decision,
            "previous_version": 1,
            "new_version": 2 if decision == "accepted" else 1,
            "changed_fields": ["positioning"] if decision == "accepted" else [],
        }


class AdvisorApiFacadeWithDeltaProbe(AdvisorApiFacadeProbe):
    def submit_answer(self, case_id: str, **request: object) -> dict[str, object]:
        response = super().submit_answer(case_id, **request)
        response.update(
            {
                "recalculation_status": "started",
                "recalculation_data_revision": 2,
                "recalculation_analysis_status": "gate2_preview_ready",
                "recalculation_delta": {
                    "previous_revision": 1,
                    "new_revision": 2,
                    "fields_changed": ["icp"],
                    "core_coverage_delta": 1,
                    "conflicts_resolved": 0,
                    "conflicts_remaining": 0,
                    "calculations_recalculated": [],
                    "calculations_pending": ["report"],
                },
            }
        )
        return response


class AdvisorApiSemanticMismatchProbe(AdvisorApiFacadeProbe):
    def submit_answer(self, case_id: str, **request: object) -> dict[str, object]:
        del request
        self._require_case(case_id)
        raise StartupValidationError("advisor_manual_answer_semantic_mismatch")


class RecordingAuditSpool:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> str:
        self.events.append(event)
        return "memory://startup-api-audit"

    def read_bounded(
        self,
        *,
        max_events: int = 100,
        max_files: int = 128,
        max_bytes: int = 1_048_576,
        max_line_chars: int = 8192,
        newest_first: bool = False,
    ) -> list[AuditEvent]:
        events = reversed(self.events) if newest_first else iter(self.events)
        return list(events)[:max_events]


class _CountingStartupResearchPort:
    def __init__(
        self,
        delegate: StartupResearchPort,
        calls: list[StartupResearchPlan],
    ) -> None:
        self.delegate = delegate
        self.calls = calls

    def collect(self, plan: StartupResearchPlan) -> StartupMarketResearchSnapshot:
        self.calls.append(plan)
        return self.delegate.collect(plan)


def _json_contains_key(value: object, forbidden_key: str) -> bool:
    if isinstance(value, dict):
        return any(
            key == forbidden_key or _json_contains_key(child, forbidden_key)
            for key, child in value.items()
        )
    if isinstance(value, list | tuple):
        return any(_json_contains_key(child, forbidden_key) for child in value)
    return False


def _assert_public_research_deferred_without_mutation(
    client: TestClient,
    *,
    coordinator: StartupCaseCoordinator,
    case_id: str,
    expected_revision: int,
    expected_skipped: tuple[str, ...],
) -> None:
    public_question = _skip_advisor_questions_until(
        client,
        case_id,
        target_field_key="icp",
        expected_skipped=expected_skipped,
    )
    public_answer = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": public_question["question_id"],
            "answer_type": "public_research",
            "consent_public_research": True,
        },
    )
    assert public_answer.status_code == 200
    public_payload = public_answer.json()
    assert public_payload["status"] == "blocked"
    assert public_payload["research_result"]["status"] == "deferred"
    assert public_payload["research_result"]["fallback_used"] is False
    assert public_payload["research_result"]["source_ids"] == []
    assert public_payload["recalculation_status"] == "not_requested"
    assert public_payload["recalculation_data_revision"] is None

    public_runtime = coordinator.runtime_for_test(case_id)
    assert public_runtime["data_revision"] == expected_revision
    skipped_public = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": public_question["question_id"],
            "answer_type": "skip",
        },
    )
    assert skipped_public.status_code == 200
    assert skipped_public.json()["recalculation_data_revision"] is None
    assert coordinator.runtime_for_test(case_id)["data_revision"] == expected_revision


def _skip_advisor_questions_until(
    client: TestClient,
    case_id: str,
    *,
    target_field_key: str,
    expected_skipped: tuple[str, ...],
) -> dict[str, object]:
    skipped: list[str] = []
    for _ in range(len(expected_skipped) + 1):
        question_response = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
        assert question_response.status_code == 200
        question = question_response.json()["next_question"]
        field_key = question["field_key"]
        if field_key == target_field_key:
            assert tuple(skipped) == expected_skipped
            return question
        skipped.append(field_key)
        skip_response = client.post(
            f"/api/v1/startup/cases/{case_id}/advisor/answers",
            json={
                "question_id": question["question_id"],
                "answer_type": "skip",
            },
        )
        assert skip_response.status_code == 200
        assert skip_response.json()["recalculation_data_revision"] is None
    pytest.fail(
        f"advisor question {target_field_key!r} not reached after skipping {tuple(skipped)!r}"
    )


class FailedStartAnalysisProbe(AnalysisProbe):
    def __init__(self, error_code: str) -> None:
        super().__init__()
        self.error_code = error_code

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.starts.append({"payload": payload, "thread_id": thread_id})
        return {
            "status": "failed",
            "pending_gate": None,
            "error_code": self.error_code,
        }


class StaleFailedStartAnalysisProbe(AnalysisProbe):
    def __init__(self, store: InMemoryStartupWorkflowRuntimeStore) -> None:
        super().__init__()
        self.store = store

    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]:
        self.starts.append({"payload": payload, "thread_id": thread_id})
        case_id = str(payload["case_id"])
        self.store.save(
            case_id,
            {
                "data_revision": 2,
                "active_analysis_thread_id": f"{case_id}:r2",
                "analysis_start_claim_thread_id": f"{case_id}:r2",
                "analysis_start_claim_data_revision": 2,
                "analysis_status": "awaiting_start",
            },
        )
        return {
            "status": "failed",
            "pending_gate": None,
            "error_code": "workflow_unexpected",
        }


class ReportFacadeProbe:
    def __init__(
        self,
        *,
        snapshot: CanonicalReportSnapshot,
        pdf_error: Exception | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.pdf_error = pdf_error
        self.decisions: list[dict[str, object]] = []
        self.latest_decision: str | None = None

    def current_snapshot(self, case_id: str) -> CanonicalReportSnapshot:
        return self.snapshot

    def canonical_json_bytes(self, case_id: str) -> bytes:
        return b'{"schema":"startup_report_snapshot.v1"}'

    def founder_json_bytes(self, case_id: str) -> bytes:
        return json.dumps(
            _founder_safe_report_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def html(self, case_id: str) -> str:
        return "<main>canonical draft</main>"

    def pdf(self, case_id: str) -> bytes:
        if self.latest_decision != "approved":
            raise StartupGateConflict("gate_4_freeze_required")
        if self.pdf_error is not None:
            raise self.pdf_error
        return b"%PDF-1.4\n"

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: str,
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot:
        if (
            snapshot_hash != self.snapshot.snapshot_hash
            or snapshot_revision != self.snapshot.snapshot_revision
        ):
            raise StartupGateConflict("gate_4_snapshot_mismatch")
        self.decisions.append(
            {
                "case_id": case_id,
                "decision": decision,
                "snapshot_hash": snapshot_hash,
                "snapshot_revision": snapshot_revision,
                "reason": reason,
            }
        )
        self.latest_decision = decision
        return self.snapshot

    def freeze_status(self, case_id: str) -> FreezeStatus:
        return "approved" if self.latest_decision == "approved" else "required"

    def pdf_status(self, case_id: str) -> PdfStatus:
        return (
            "ready"
            if self.latest_decision == "approved" and self.pdf_error is None
            else "freeze_required"
        )


def _founder_safe_report_payload() -> dict[str, object]:
    section_keys = (
        "business_idea_summary",
        "problem_solution",
        "market_size",
        "competitors",
        "moat",
        "go_to_market",
        "metrics",
        "financial_assumptions",
        "risks",
        "evidence_gaps",
        "diligence_questions",
        "action_plan",
    )
    return {
        "title_ru": "Отчёт для основателя",
        "subtitle_ru": "Краткий founder-safe отчёт",
        "as_of_ru": "Данные на 21.08.2026",
        "data_revision": 1,
        "main_sections": [
            {
                "key": key,
                "title_ru": key.replace("_", " "),
                "status": "needs_input",
                "status_label_ru": "Нужны данные",
                "summary_ru": "Раздел ожидает подтверждённые данные.",
                "content_heading_ru": "Что нужно уточнить",
                "known_facts_ru": [],
                "blockers_ru": [],
                "next_data_ru": [],
                "unlocks_ru": [],
            }
            for key in section_keys
        ],
        "metric_cards": {},
        "improvement_proposals": [],
        "technical_appendix": {
            "methodology_ru": [],
            "sources_ru": [],
        },
        "analytics": {
            "metric_points": [],
            "market_points": [],
            "readiness_dimensions": [],
        },
    }


class MissingReportFacadeProbe:
    def current_snapshot(self, case_id: str) -> CanonicalReportSnapshot:
        raise KeyError("report_not_ready")

    def canonical_json_bytes(self, case_id: str) -> bytes:
        raise KeyError("report_not_ready")

    def founder_json_bytes(self, case_id: str) -> bytes:
        raise KeyError("report_not_ready")

    def html(self, case_id: str) -> str:
        raise KeyError("report_not_ready")

    def pdf(self, case_id: str) -> bytes:
        raise KeyError("report_not_ready")

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: str,
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot:
        raise KeyError("report_not_ready")

    def freeze_status(self, case_id: str) -> FreezeStatus:
        raise KeyError("report_not_ready")

    def pdf_status(self, case_id: str) -> PdfStatus:
        raise KeyError("report_not_ready")


def _clear_startup_dependency_cache() -> None:
    for dependency in (
        get_startup_case_coordinator,
        get_startup_advisor_api_service,
    ):
        cache_clear = getattr(dependency, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


class ProfileQueryProbe:
    def __init__(self, profile: StartupProfile) -> None:
        self.profile = profile

    def get_current(self, case_id: UUID) -> StartupProfile:
        return self.profile

    def get(self, profile_id: UUID) -> StartupProfile:
        if profile_id != self.profile.profile_id:
            raise KeyError(f"startup_profile_not_found:{profile_id}")
        return self.profile


class ProfileHistoryQueryProbe:
    def __init__(
        self,
        *,
        current: StartupProfile,
        history: tuple[StartupProfile, ...],
    ) -> None:
        self.current = current
        self.history = {profile.profile_id: profile for profile in history}

    def get_current(self, case_id: UUID) -> StartupProfile:
        if case_id != self.current.case_id:
            raise KeyError(f"startup_profile_not_found:{case_id}")
        return self.current

    def get(self, profile_id: UUID) -> StartupProfile:
        try:
            return self.history[profile_id]
        except KeyError:
            raise KeyError(f"startup_profile_not_found:{profile_id}") from None


class GtmQueryProbe:
    def __init__(self, snapshot: StartupGtmSnapshot | None = None) -> None:
        self.snapshot = snapshot

    def get_current(self, case_id: str) -> StartupGtmSnapshot:
        if self.snapshot is None or str(self.snapshot.case_id) != case_id:
            raise KeyError(f"startup_gtm_not_found:{case_id}")
        return self.snapshot


class CaseRevisionQueryProbe:
    def __init__(self, revision: int) -> None:
        self.revision = revision

    def current_revision(self, case_id: str) -> int:
        UUID(case_id)
        return self.revision

    def advance_revision(
        self,
        case_id: str,
        *,
        expected_current_revision: int,
        document_ids: list[str],
        source_refs: list[dict[str, str]],
        metadata: dict[str, str],
    ) -> int:
        del case_id, document_ids, source_refs, metadata
        if expected_current_revision != self.revision:
            raise ValueError("case_revision_conflict")
        self.revision += 1
        return self.revision


def _startup_profile(
    *,
    case_id: UUID | None = None,
    data_revision: int = 1,
) -> StartupProfile:
    evidence_id = uuid4()
    artifact_id = uuid4()
    fragment_id = uuid4()
    fields: dict[str, StartupProfileField] = {}
    for field_name in StartupProfileFieldName:
        if field_name is StartupProfileFieldName.STARTUP_NAME:
            field = StartupProfileField(
                name=field_name,
                status=StartupProfileFieldStatus.SOURCE_FACT,
                values=("FounderCo",),
                confidence=Decimal("0.95"),
                evidence_refs=(
                    StartupProfileEvidenceRef(
                        evidence_id=evidence_id,
                        fragment_id=fragment_id,
                        artifact_id=artifact_id,
                        artifact_hash=f"sha256:{'1' * 64}",
                        locator_hash=f"sha256:{'2' * 64}",
                        page=1,
                        field_name=field_name,
                        confidence=Decimal("0.95"),
                    ),
                ),
            )
        else:
            field = StartupProfileField(
                name=field_name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal(0),
                reason_code=f"{field_name.value}_missing",
            )
        fields[field_name.value] = field
    return StartupProfile.build(
        case_id=case_id or uuid4(),
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="test-profile-query@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes={"doc-0001": f"sha256:{'1' * 64}"},
        parse_outcomes={"doc-0001": "parsed"},
        fields=fields,
        gap_codes=("users",),
        case_revision_at=datetime(2026, 8, 13, tzinfo=UTC),
    )


def _startup_gtm_snapshot(
    case_id: UUID,
    *,
    profile_id: UUID | None = None,
    data_revision: int = 1,
) -> StartupGtmSnapshot:
    return StartupGtmSnapshot.build(
        case_id=case_id,
        profile_id=profile_id or uuid4(),
        product_validation_snapshot_id=uuid4(),
        market_research_snapshot_id=uuid4(),
        data_revision=data_revision,
        status=StartupGtmStatus.INSUFFICIENT,
        dimensions=tuple(
            StartupGtmDimension(
                name=name,
                status=StartupGtmDimensionStatus.MISSING,
                reason_code="evidence_missing",
                gap_code=f"{name.value}_missing",
            )
            for name in StartupGtmDimensionName
        ),
        launch_plan=tuple(StartupGtmLaunchPhase(horizon=horizon) for horizon in StartupGtmHorizon),
        finding_ids=("finding-risk",),
        built_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

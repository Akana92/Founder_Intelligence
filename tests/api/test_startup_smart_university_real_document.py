from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import pytest
from pypdf import PdfReader
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from due_diligence_agent.application.services.startup_document_intelligence_service import (
    StartupDocumentIntelligenceService,
)
from due_diligence_agent.domain.startup.roles import StartupDocumentIntelligenceStatus
from due_diligence_agent.presentation.api import dependencies as api_dependencies
from due_diligence_agent.presentation.api.app import create_app
from due_diligence_agent.presentation.api.dependencies import (
    get_case_asset_service,
    get_case_copilot_service,
    get_startup_advisor_api_service,
    get_startup_case_coordinator,
)

SMART_UNIVERSITY_FIXTURE_PDF = (
    Path(__file__).parents[1]
    / "fixtures"
    / "startup_smart_university_minimized"
    / "smart_university_many_blocks_sanitized.pdf"
)
REAL_SMART_UNIVERSITY_PDF_ENV = "STARTUP_SMART_UNIVERSITY_REAL_PDF"
SMART_UNIVERSITY_GENERATOR = (
    Path(__file__).parents[2] / "scripts" / "generate_smart_university_sanitized_fixture.py"
)
_TEST_NAMESPACE = UUID("12345678-1234-5678-1234-567812345678")


def test_smart_university_fixture_pdf_auto_start_builds_source_linked_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert SMART_UNIVERSITY_FIXTURE_PDF.is_file()
    _assert_pdf_auto_start_builds_source_linked_profile(
        pdf_path=SMART_UNIVERSITY_FIXTURE_PDF,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )


def test_opt_in_real_smart_university_pdf_auto_start_builds_source_linked_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = os.environ.get(REAL_SMART_UNIVERSITY_PDF_ENV, "").strip()
    if not raw_path:
        pytest.skip(f"set {REAL_SMART_UNIVERSITY_PDF_ENV} to run the owner-local real PDF proof")
    pdf_path = Path(raw_path)
    assert pdf_path.is_file()
    _assert_pdf_auto_start_builds_source_linked_profile(
        pdf_path=pdf_path,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )


def test_portable_safe_ref_boundary_trigger_accepts_more_than_512_refs() -> None:
    evidence_fact_ids = tuple(
        str(uuid5(_TEST_NAMESPACE, f"smart-university-safe-ref:{index}")) for index in range(700)
    )

    snapshot = StartupDocumentIntelligenceService().analyze(
        case_id=uuid5(_TEST_NAMESPACE, "smart-university-safe-ref-case"),
        data_revision=1,
        inventory_id="smart-university-portable-fixture",
        source_document_ids=("doc-0001",),
        artifact_ids=("artifact-portable-fixture",),
        parsed_artifact_ids=("artifact-portable-fixture",),
        evidence_fact_ids=evidence_fact_ids,
        startup_claim_ids=(str(uuid5(_TEST_NAMESPACE, "smart-university-safe-ref-claim")),),
        quarantine_reason_codes=(),
    )

    assert snapshot.evidence_fact_count == 700
    assert set(snapshot.evidence_fact_ids) == set(evidence_fact_ids)
    assert snapshot.status is StartupDocumentIntelligenceStatus.COMPLETE


def test_smart_university_fixture_is_reproducibly_generated_without_private_actuals(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "smart_university_many_blocks_sanitized.pdf"

    subprocess.run(
        [
            sys.executable,
            "-B",
            str(SMART_UNIVERSITY_GENERATOR),
            "--output",
            str(generated),
        ],
        check=True,
        cwd=Path(__file__).parents[2],
    )

    generated_reader = PdfReader(str(generated))
    fixture_reader = PdfReader(str(SMART_UNIVERSITY_FIXTURE_PDF))
    text = "\n".join(page.extract_text() or "" for page in generated_reader.pages)
    fixture_text = "\n".join(page.extract_text() or "" for page in fixture_reader.pages)

    assert len(generated_reader.pages) == len(fixture_reader.pages)
    assert dict(generated_reader.metadata or {}) == dict(fixture_reader.metadata or {})
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == hashlib.sha256(
        fixture_text.encode("utf-8")
    ).hexdigest()
    assert text.count("Smart University sanitized source block") >= 700
    assert "35.2M KZT platform round" in text
    assert "8.0M KZT Housing Management pilot" in text
    assert "2027-2031 revenue and EBITDA are forecasts" in text
    assert "43.2M" not in text
    for invented_actual in ("ARR of $1.2M", "MRR of $100K", "120 pilot customers"):
        assert invented_actual not in text


def test_smart_university_same_case_api_journey_persists_public_research_and_launch_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert SMART_UNIVERSITY_FIXTURE_PDF.is_file()
    _clear_startup_dependency_cache()
    data_root = tmp_path / "same-case-data"
    provider = _AcceptedSmartUniversityBenchmarkProvider()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container

    real_build_case_copilot_service = container.build_case_copilot_service

    def build_case_copilot_service_with_provider(**kwargs: Any) -> Any:
        kwargs["research_provider"] = provider
        kwargs.setdefault("acquisition_mode", "deterministic_offline_fixture")
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )
    client = _startup_test_client()

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true", "company_name": "Smart University"},
        files=[
            (
                "files",
                (
                    SMART_UNIVERSITY_FIXTURE_PDF.name,
                    SMART_UNIVERSITY_FIXTURE_PDF.read_bytes(),
                    "application/pdf",
                ),
            )
        ],
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["analysis_status"] == "gate2_preview_ready"

    profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert profile.status_code == 200, profile.text
    _assert_smart_university_operating_model(profile.json(), require_portable_semantics=True)

    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200, preview.text
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200, gate2.text

    question = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    assert question.status_code == 200, question.text
    if question.json()["status"] == "active":
        skipped = client.post(
            f"/api/v1/startup/cases/{case_id}/advisor/answers",
            json={
                "question_id": question.json()["next_question"]["question_id"],
                "answer_type": "skip",
                "consent_public_research": False,
            },
        )
        assert skipped.status_code == 200, skipped.text
        assert skipped.json()["status"] == "applied"
        assert skipped.json()["answer_type"] == "skip"

    state_before_research = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    thread_before_research = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")
    assert state_before_research.status_code == 200
    assert thread_before_research.status_code == 200
    revision = state_before_research.json()["data_revision"]
    assert state_before_research.json()["stage"] == "first_sales"

    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market benchmarks for Smart University.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "task-e-smart-university-public-research",
            "consent_public_research": True,
            "acquisition_mode": "deterministic_offline_fixture",
        },
    )
    assert job_response.status_code == 202, job_response.text
    job = job_response.json()
    assert job["status"] == "completed"
    assert len(provider.calls) == 1
    assert job["accepted_entries"][0]["provenance"] == "public_benchmark"
    assert job["accepted_entries"][0]["source_refs"]
    assert job["source_refs"]
    assert job["citations"]
    assert job["old_revision"] == revision
    research_revision = revision + 1
    assert job["new_revision"] == research_revision

    research_status = client.get(f"/api/v1/startup/cases/{case_id}")
    assert research_status.status_code == 200, research_status.text
    assert research_status.json()["data_revision"] == research_revision
    assert research_status.json()["active_analysis_thread_id"] == f"{case_id}:r{research_revision}"
    assert research_status.json()["analysis_status"] == "gate2_preview_ready"
    assert research_status.json()["langgraph_checkpoint"]

    research_preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert research_preview.status_code == 200, research_preview.text
    research_gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={
            "decision": "approved",
            "resume_token": research_preview.json()["resume_token"],
        },
    )
    assert research_gate2.status_code == 200, research_gate2.text
    assert research_gate2.json()["analysis_status"] == "gate3_review_required"
    assert "gate2_resume_failed" not in research_gate2.text

    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    scenarios = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    assert state.status_code == 200, state.text
    assert scenarios.status_code == 200, scenarios.text
    _assert_no_private_public_promotion(state.json())
    assert set(scenarios.json()["scenarios"]) == {"conservative", "base", "optimistic"}
    assert all(
        metric["provenance"] != "source_fact"
        for variant in scenarios.json()["scenarios"].values()
        for metric in variant["metrics"].values()
    )
    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert gtm.status_code == 200, gtm.text
    gtm_payload = gtm.json()
    assert gtm_payload["case_id"] == case_id
    assert gtm_payload["snapshot_revision"] == research_revision
    assert {phase["horizon"] for phase in gtm_payload["launch_plan"]} == {
        "day_7",
        "day_30",
        "day_60",
        "day_90",
    }

    selected = client.post(
        f"/api/v1/startup/cases/{case_id}/scenarios/selection",
        json={
            "scenario_set_id": scenarios.json()["scenario_set_id"],
            "scenario_key": "base",
            "expected_case_revision": research_revision,
            "idempotency_key": "task-e-select-base",
        },
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["new_scenario_key"] == "base"

    launch_pack = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": research_revision,
            "idempotency_key": "task-e-smart-university-launch-pack",
        },
    )
    assert launch_pack.status_code == 201, launch_pack.text
    launch_payload = launch_pack.json()
    body = launch_payload["body_markdown"]
    assert launch_payload["case_id"] == case_id
    assert launch_payload["data_revision"] == research_revision
    assert launch_payload["selected_scenario_key"] == "base"
    _assert_smart_launch_pack_markers(body)
    markdown = client.get(
        f"/api/v1/startup/cases/{case_id}/assets/{launch_payload['asset_id']}/markdown"
    )
    provenance = client.get(
        f"/api/v1/startup/cases/{case_id}/assets/{launch_payload['asset_id']}/provenance"
    )
    csv = client.get(f"/api/v1/startup/cases/{case_id}/assets/{launch_payload['asset_id']}/csv")
    assert markdown.status_code == 200, markdown.text
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "attachment" in markdown.headers["content-disposition"]
    assert markdown.text == body
    assert provenance.status_code == 200, provenance.text
    assert provenance.headers["content-type"].startswith("text/markdown")
    assert "attachment" in provenance.headers["content-disposition"]
    assert "source_refs=" in provenance.text
    assert "dependency_refs=" in provenance.text
    assert "source_fact" not in provenance.text
    assert csv.status_code == 404

    get_case_copilot_service.cache_clear()
    get_case_asset_service.cache_clear()
    get_startup_case_coordinator.cache_clear()
    get_startup_advisor_api_service.cache_clear()
    restarted = _startup_test_client()
    persisted_state = restarted.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    persisted_thread = restarted.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")
    persisted_job = restarted.get(f"/api/v1/startup/cases/{case_id}/research/jobs/{job['job_id']}")
    persisted_scenarios = restarted.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    persisted_asset = restarted.get(
        f"/api/v1/startup/cases/{case_id}/assets/{launch_payload['asset_id']}"
    )
    persisted_assets = restarted.get(f"/api/v1/startup/cases/{case_id}/assets")

    for response in (
        persisted_state,
        persisted_thread,
        persisted_job,
        persisted_scenarios,
        persisted_asset,
        persisted_assets,
    ):
        assert response.status_code == 200, response.text
    assert persisted_state.json()["case_id"] == case_id
    assert persisted_state.json()["data_revision"] == research_revision
    assert persisted_thread.json()["thread_id"] == thread_before_research.json()["thread_id"]
    assert persisted_thread.json()["case_id"] == case_id
    assert persisted_job.json()["job_id"] == job["job_id"]
    assert persisted_job.json()["status"] == "completed"
    assert persisted_scenarios.json()["selected_scenario_key"] == "base"
    assert persisted_asset.json()["asset_id"] == launch_payload["asset_id"]
    assert persisted_asset.json()["body_markdown"] == body
    assert [item["asset_id"] for item in persisted_assets.json()["assets"]] == [
        launch_payload["asset_id"]
    ]
    _assert_no_private_public_promotion(persisted_state.json())


def _assert_pdf_auto_start_builds_source_linked_profile(
    *,
    pdf_path: Path,
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

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true", "company_name": "Smart University"},
        files=[
            (
                "files",
                (pdf_path.name, pdf_path.read_bytes(), "application/pdf"),
            )
        ],
    )

    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["analysis_status"] == "gate2_preview_ready"
    assert uploaded.json()["auto_start_triggered"] is True

    profile_response = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()
    assert profile["analysis_stage"] == "primary"
    source_linked_fields = _source_linked_fields(profile)
    assert source_linked_fields
    for field_key in source_linked_fields:
        field = profile["fields"][field_key]
        assert field["values"]
        assert field["evidence_refs"]
        for ref in field["evidence_refs"]:
            assert ref["artifact_id"]
            assert ref["artifact_hash"].startswith("sha256:")
            assert ref["locator_hash"].startswith("sha256:")

    is_portable_fixture = pdf_path == SMART_UNIVERSITY_FIXTURE_PDF
    _assert_smart_university_operating_model(
        profile, require_portable_semantics=is_portable_fixture
    )

    preview_response = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["provider_mode"] == "deterministic_offline_fixture"
    assert preview["resume_token"]
    assert preview["preview"]

    copilot_response = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert copilot_response.status_code == 200, copilot_response.text
    copilot = copilot_response.json()
    assert copilot["stage"] == "first_sales"
    question_descriptor = copilot["question_descriptor"]
    assert question_descriptor
    assert copilot["next_question"] == question_descriptor["question"]
    assert question_descriptor["field_key"]
    assert question_descriptor["input_schema"]["kind"] in {"text", "money"}
    assert any(
        action["action"] == "open_fact_input"
        and action["payload"]["field_key"] == question_descriptor["field_key"]
        for action in copilot["actions"]
    )
    _clear_startup_dependency_cache()


def _source_linked_fields(profile: dict[str, Any]) -> set[str]:
    return {
        field_key
        for field_key, field in profile["fields"].items()
        if field["status"] == "source_fact" and field["evidence_refs"]
    }


def _assert_smart_university_operating_model(
    profile: dict[str, Any],
    *,
    require_portable_semantics: bool,
) -> None:
    fields = profile["fields"]

    assert fields["stage"]["status"] == "source_fact"
    assert fields["stage"]["values"]
    stage_text = " | ".join(str(value) for value in fields["stage"]["values"])
    assert "pre-scale" in stage_text.casefold() or "рабоч" in stage_text.casefold()
    assert fields["stage"]["evidence_refs"]

    field_text = {key: " | ".join(str(value) for value in fields[key]["values"]) for key in fields}
    source_fact_text = " | ".join(
        " | ".join(str(value) for value in field["values"])
        for field in fields.values()
        if field["status"] == "source_fact"
    )
    _assert_smart_university_semantic_markers(source_fact_text)

    if not require_portable_semantics:
        assert fields["startup_name"]["status"] == "source_fact"
        assert fields["startup_name"]["values"] == ["SMART UNIVERSITY"]

        solution_text = field_text["solution"].casefold()
        assert "поступлен" in solution_text
        assert "рейтинг" in solution_text
        assert "break-even" not in solution_text
        assert "35,2" not in solution_text

        geography_text = field_text["geography"].casefold()
        assert "казахстан" in geography_text
        assert "алматы" in geography_text
        assert "формат" not in geography_text
        assert "партнёр" not in geography_text

        icp_text = field_text["icp"].casefold()
        assert "абитуриент" in icp_text
        assert "вуз" in icp_text
        return

    profile_text = " | ".join(field_text.values())

    assert "AI-powered platform for university program discovery" in field_text["solution"]
    assert "Housing Management vertical" in field_text["solution"]
    assert "universities and education agents" in field_text["icp"]
    assert "students and parents" in field_text["users"]
    assert "university admissions and agent partnership teams" in field_text["buyers"]
    assert "Kazakhstan launch" in field_text["geography"]
    assert "Starter 240 000 KZT/month" in field_text["pricing_revenue_model"]
    assert (
        "TAM = students applying abroad * serviceable platform fee"
        in field_text["metric_pack_candidates"]
    )
    assert "rating methodology combines program fit" in field_text["assumptions"]
    assert "35.2M KZT platform round" in field_text["assumptions"]
    assert "8.0M KZT Housing Management pilot" in field_text["assumptions"]
    assert "revenue and EBITDA are forecasts" in field_text["assumptions"]
    assert "privacy consent" in field_text["weaknesses"]
    assert "Housing Management no-go" in field_text["weaknesses"]

    assert "43.2M" not in profile_text
    private_actuals = ("ARR:", "MRR:", "Runway:", "gross margin", "120 pilot customers")
    for key in ("traction", "metric_pack_candidates"):
        values = " | ".join(str(value) for value in fields[key]["values"])
        assert not any(actual in values for actual in private_actuals)


def _assert_smart_university_semantic_markers(source_fact_text: str) -> None:
    normalized = source_fact_text.casefold()
    semantic_groups = {
        "platform_modules": ("platform", "платформ"),
        "housing_module": ("housing", "общежит", "жиль"),
        "customers": ("universit", "студент", "абитуриент", "родител", "agent", "агент"),
        "pricing": ("kzt/month", "kzt", "₸", "тенге", "тариф"),
        "market_formulas": ("tam", "sam", "som", "рынок"),
        "rating_methodology": ("rating", "рейтинг", "подбор", "fit"),
        "funding": ("35.2m", "финанс", "funding", "раунд", "инвест"),
        "roadmap_or_gates": ("gate", "roadmap", "go/no-go", "роадмап", "гейт"),
        "legal_privacy": ("privacy", "consent", "персональн", "соглас"),
        "housing_no_go": ("no-go", "стоп", "не запуск", "не продолж"),
        "forecasts": ("forecast", "прогноз", "2027", "2031"),
    }
    missing = [
        name
        for name, markers in semantic_groups.items()
        if not any(marker in normalized for marker in markers)
    ]
    if missing:
        pytest.fail(f"missing Smart University semantic markers: {missing}", pytrace=False)


def _startup_test_client() -> TestClient:
    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    return TestClient(app)


def _assert_smart_launch_pack_markers(body: str) -> None:
    headings = tuple(line for line in body.splitlines() if line.startswith("## "))
    assert len(headings) == 12
    required = (
        "## Executive summary",
        "## Problem / solution / ICP / buyer / purchase trigger",
        "## Market, competitors, alternatives and citations",
        "## Three-scenario unit economics",
        "## 7/30/60/90 actions",
        "## Provenance, assumptions and limitations",
        "Platform thesis",
        "Pricing/tariff economics",
        "Starter 240 000 KZT/month",
        "Lead/conversion economics",
        "acquisition_spend: range=120000-240000 KZT/month",
        "Rating methodology",
        "B2B pilot plan",
        "Housing decision tree",
        "Tranche plan",
        "Provenance appendix",
        "35.2M KZT platform round",
        "8.0M KZT Housing Management pilot",
        "2027-2031 revenue and EBITDA are forecasts",
        "2027, 2028, 2029, 2030 and 2031",
        "TAM",
        "commercial traction",
        "rating anti-fraud",
        "privacy/legal/tax",
        "provenance=public_benchmark",
        "provenance=ai_scenario",
        "day_7",
        "day_30",
        "day_60",
        "day_90",
    )
    for marker in required:
        assert marker in body
    assert "43.2M" not in body
    assert "provenance=source_fact" not in body


def _assert_no_private_public_promotion(payload: dict[str, Any]) -> None:
    for fact in payload["extracted_facts"]:
        if fact["source_type"] != "source_fact":
            continue
        normalized_value = str(fact.get("value", "")).casefold()
        assert "mrr" not in normalized_value
        assert "cash" not in normalized_value
        assert "burn" not in normalized_value
        assert "contract" not in normalized_value
        assert "invoice" not in normalized_value
        assert "bank" not in normalized_value
    for accepted in payload["accepted_inputs"]:
        assert not (
            accepted["kind"] == "source_fact"
            and accepted["field_key"]
            in {
                "monthly_recurring_revenue",
                "mrr",
                "revenue",
                "cash",
                "burn",
                "customer_count",
                "contracts",
                "invoices",
                "bank",
            }
        )


def _clear_startup_dependency_cache() -> None:
    for dependency in (
        get_case_asset_service,
        get_case_copilot_service,
        get_startup_case_coordinator,
        get_startup_advisor_api_service,
    ):
        cache_clear = getattr(dependency, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


class _AcceptedSmartUniversityBenchmarkProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def collect(self, plan: Any) -> list[dict[str, Any]]:
        source_ref = uuid5(_TEST_NAMESPACE, f"task-e-public-source:{plan.case_id}")
        self.calls.append(
            {
                "case_id": str(plan.case_id),
                "plan_hash": plan.plan_hash,
                "queries": tuple(plan.query_previews),
            }
        )
        return [
            {
                "input_key": "acquisition_spend",
                "provenance": "public_benchmark",
                "url": "https://example.com/smart-university-public-lead-cost",
                "publisher": "Example Public Market Research",
                "publication_date": "2026-08-01",
                "retrieval_date": "2026-08-26",
                "as_of": "2026-08-01",
                "source_class": "industry_report",
                "confidence": "medium",
                "range_low": "120000",
                "range_high": "240000",
                "unit": "KZT",
                "period": "month",
                "formula": "public education lead-cost benchmark range",
                "dependencies": ("public comparable education marketplaces",),
                "validation_plan": (
                    "Use only as external context until Smart University has "
                    "case-specific source evidence."
                ),
                "source_refs": (source_ref,),
                "rationale": (
                    "Cited public benchmark for education marketplace acquisition spend."
                ),
            }
        ]

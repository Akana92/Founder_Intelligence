from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from starlette.testclient import TestClient

from due_diligence_agent.presentation.api import dependencies as api_dependencies
from due_diligence_agent.presentation.api.app import create_app
from due_diligence_agent.presentation.api.dependencies import (
    get_case_copilot_service,
    get_startup_advisor_api_service,
    get_startup_case_coordinator,
)

_NOMADFLOW_PDF_TEXT = """Company: NomadFlow AI
Description: NomadFlow AI is a B2B SaaS platform for inventory planning and regional logistics.
Problem: Regional distributors lose control of stock and delivery status across disconnected tools.
Solution: A control tower connects accounting, warehouse, GPS, and order data with human approval.
ICP: Regional distributors and retail chains with multiple warehouses.
Geography: Kazakhstan, Uzbekistan, and Kyrgyzstan.
Stage: Seed.
Business Model: B2B SaaS subscription.
Pricing: Starter 240 KZT monthly; Growth 690 KZT monthly; Enterprise 1900 KZT monthly.
Channels: Direct sales and regional integration partners.
MRR CONTRADICTION: CRM 28.6 differs from invoices 27.9.
Customer count CONTRADICTION: CRM 31 differs from invoices 29.
Gross margin CONTRADICTION: operational 74 differs from fully loaded 70.
CAC payback CONTRADICTION: reported 4.3 differs from recalculated 5.5.
"""


def test_different_uploaded_pdfs_produce_different_profile_preview_and_advisor_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a static startup analysis shell ignoring the uploaded document."""

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

    nomadflow = _analyze_pdf(
        client,
        _write_nomadflow_pdf_fixture(tmp_path),
        company_name="NomadFlow AI",
    )
    pre_revenue = _analyze_pdf(
        client,
        Path("tests/fixtures/startup_synthetic_v1/cases/pre_revenue_service/concept.pdf"),
        company_name="Pre-revenue service",
    )

    assert nomadflow["startup_name_values"] == ["NomadFlow AI"]
    assert pre_revenue["startup_name_values"] != nomadflow["startup_name_values"]
    assert pre_revenue["one_line_values"] != nomadflow["one_line_values"]
    assert nomadflow["source_hashes"] != pre_revenue["source_hashes"]
    assert _confirmed_field_keys(nomadflow["profile"]) != _confirmed_field_keys(
        pre_revenue["profile"]
    )
    assert pre_revenue["profile"]["contradictions"] != nomadflow["profile"]["contradictions"]
    assert pre_revenue["advisor_field_key"] != nomadflow["advisor_field_key"]
    assert pre_revenue["advisor_origin"] in {
        "document_gap",
        "document_contradiction",
        "static",
    }
    assert pre_revenue["preview"] != nomadflow["preview"]

    pre_revenue_payload = json.dumps(pre_revenue, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "NomadFlow",
        "Kazakhstan",
        "Казахстан",
        "Uzbekistan",
        "Узбекистан",
        "Kyrgyzstan",
        "Кыргызстан",
        "27.9m",
        "28.6m",
        "690k",
        "1.9m",
    ):
        assert forbidden not in pre_revenue_payload

    _clear_startup_dependency_cache()


def test_nomadflow_mrr_clarification_stays_a_founder_statement_in_case_copilot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A founder answer stays provisional and visible without becoming a source fact."""

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
    fixture = _write_nomadflow_pdf_fixture(tmp_path)

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true", "company_name": "NomadFlow AI"},
        files=[("files", ("case.pdf", fixture.read_bytes(), "application/pdf"))],
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["analysis_status"] == "gate2_preview_ready"

    question_response = client.get(
        f"/api/v1/startup/cases/{case_id}/advisor/next-question"
    )
    assert question_response.status_code == 200
    question = question_response.json()["next_question"]
    assert question["origin"] == "document_contradiction"
    assert question["field_key"] == "revenue_pricing"
    answer_text = (
        "Use bank and invoice register for June 2026: recognized MRR is "
        "27.9m KZT; exclude CRM-only free-extension accounts."
    )
    answered = client.post(
        f"/api/v1/startup/cases/{case_id}/advisor/answers",
        json={
            "question_id": question["question_id"],
            "answer_type": "manual",
            "value": answer_text,
        },
    )
    assert answered.status_code == 200
    answer_payload = answered.json()
    assert answer_payload["recalculation_status"] == "started"
    assert answer_payload["recalculation_data_revision"] == 2
    assert answer_payload["recalculation_delta"]["fields_changed"] == []
    assert answer_payload["recalculation_delta"]["conflicts_resolved"] == 0
    assert answer_payload["recalculation_delta"]["conflicts_remaining"] == 4

    profile_response = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    pricing_values = profile["fields"]["pricing_revenue_model"]["values"]
    assert answer_text not in pricing_values
    assert any("Starter" in value and "240" in value for value in pricing_values)

    copilot_state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert copilot_state.status_code == 200
    copilot_payload = copilot_state.json()
    accepted_statement = next(
        row
        for row in copilot_payload["accepted_inputs"]
        if row["field_key"] == "pricing_revenue_model"
    )
    assert accepted_statement["kind"] == "founder_statement"
    assert accepted_statement["status"] == "accepted"
    assert accepted_statement["value"] == answer_text
    assert accepted_statement["declared_source"].startswith("advisor manual answer:")
    assert accepted_statement["declared_source"].endswith(":revenue_pricing")
    assert accepted_statement["validation_plan"] == (
        "Replace with eligible source evidence before treating this as source_fact."
    )
    assert accepted_statement["source_refs"]
    assert not any(
        fact["source_type"] == "source_fact" and answer_text in fact["value"]
        for fact in copilot_payload["extracted_facts"]
    )

    _clear_startup_dependency_cache()


def test_case_copilot_idea_fixtures_are_distinct_and_metric_free() -> None:
    """Catches cloned idea fixtures or hidden numeric operating answers."""

    fixture_root = Path("tests/fixtures/startup_case_copilot_v1")
    inventory = (fixture_root / "cases" / "idea_inventory" / "brief.txt").read_text(
        encoding="utf-8"
    )
    clinic = (fixture_root / "cases" / "idea_clinic" / "brief.txt").read_text(
        encoding="utf-8"
    )
    expected = json.loads((fixture_root / "expected_contracts.json").read_text(encoding="utf-8"))

    assert "SilkStock Planner" in inventory
    assert "CareLoop Recall" in clinic
    assert inventory != clinic
    assert "Kazakhstan and Uzbekistan" in inventory
    assert "Georgia and Armenia" in clinic
    assert expected["cases"]["idea_inventory"]["expected_question_field"] == "buyer"
    assert expected["cases"]["idea_clinic"]["expected_question_field"] == "buyer"
    assert expected["cases"]["idea_inventory"]["expected_extracted_facts"] != expected[
        "cases"
    ]["idea_clinic"]["expected_extracted_facts"]
    assert expected["cases"]["idea_inventory"]["prioritized_gaps"] != expected["cases"][
        "idea_clinic"
    ]["prioritized_gaps"]
    assert set(expected["source_type_contract"]) == {
        "source_fact",
        "founder_statement",
        "public_benchmark",
        "deterministic_calculation",
        "ai_scenario",
        "contradiction",
    }
    assert expected["research_contract"]["plan_endpoint"] == (
        "/api/v1/startup/cases/{case_id}/research/plans"
    )
    assert expected["research_contract"]["job_endpoint"] == (
        "/api/v1/startup/cases/{case_id}/research/jobs"
    )
    assert "copilot/research" not in json.dumps(expected, ensure_ascii=False)
    required_metric_fields = set(expected["scenario_contract"]["required_metric_fields"])
    for case_contract in expected["cases"].values():
        assert case_contract["expected_extracted_facts"]
        assert case_contract["prioritized_gaps"]
        assert {
            item["allowed_action"]
            for item in case_contract["prioritized_gaps"]
            if item["privacy_class"] == "public_market_context"
        } == {"prepare_public_research"}
        assert {
            item["allowed_action"]
            for item in case_contract["prioritized_gaps"]
            if item["privacy_class"] == "private_startup_metric"
        } == {"manual_fact_intake"}
        for metric in case_contract["scenario_metrics"]:
            assert set(metric) == required_metric_fields
            assert metric["value"] is None
            assert metric["range"] == {
                "conservative": None,
                "base": None,
                "optimistic": None,
            }
            assert metric["source_type"] == "ai_scenario"
            assert metric["source_refs"] == []
            assert metric["what_would_confirm"]
            assert metric["validation_plan"]

    combined = "\n".join(
        [
            inventory,
            clinic,
            json.dumps(expected, ensure_ascii=False, sort_keys=True),
        ]
    ).casefold()
    for forbidden in (
        "mrr 1000",
        "arr 12000",
        "monthly burn 500",
        "cash balance 10000",
        "customer count 25",
        "recognized mrr",
        "net burn is",
    ):
        assert forbidden not in combined


def _analyze_pdf(
    client: TestClient,
    fixture: Path,
    *,
    company_name: str,
) -> dict[str, Any]:
    assert fixture.is_file(), fixture
    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "true", "company_name": company_name},
        files=[("files", ("case.pdf", fixture.read_bytes(), "application/pdf"))],
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["analysis_status"] == "gate2_preview_ready"

    profile_response = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    advisor_response = client.get(f"/api/v1/startup/cases/{case_id}/advisor/next-question")
    assert advisor_response.status_code == 200
    next_question = advisor_response.json()["next_question"]
    assert next_question is not None
    preview_response = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview_response.status_code == 200

    return {
        "case_id": case_id,
        "profile": profile,
        "startup_name_values": profile["fields"]["startup_name"]["values"],
        "one_line_values": profile["fields"]["one_line_description"]["values"],
        "source_hashes": profile["parse_inventory"]["source_hashes"],
        "advisor_field_key": next_question["field_key"],
        "advisor_origin": next_question["origin"],
        "advisor_question": next_question["question_ru"],
        "preview": preview_response.json()["preview"],
    }


def _write_nomadflow_pdf_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "nomadflow-business-plan.pdf"
    document = pymupdf.open()
    try:
        page = document.new_page()
        for line_number, line in enumerate(_NOMADFLOW_PDF_TEXT.splitlines()):
            page.insert_text(
                pymupdf.Point(36, 50 + line_number * 28),
                line,
                fontname="helv",
                fontsize=10,
            )
        document.save(fixture)
    finally:
        document.close()
    return fixture


def _confirmed_field_keys(case_output: dict[str, Any]) -> set[str]:
    return {
        field_key
        for field_key, field in case_output["fields"].items()
        if field["status"] == "source_fact"
    }


def _clear_startup_dependency_cache() -> None:
    for dependency in (
        get_case_copilot_service,
        get_startup_case_coordinator,
        get_startup_advisor_api_service,
    ):
        cache_clear = getattr(dependency, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()

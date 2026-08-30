from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from starlette.testclient import TestClient

from due_diligence_agent.application.services.case_copilot_service import CaseCopilotService
from due_diligence_agent.application.startup_cases import StartupGateConflict
from due_diligence_agent.presentation.api import dependencies as api_dependencies
from due_diligence_agent.presentation.api.app import create_app
from due_diligence_agent.presentation.api.dependencies import (
    get_case_asset_service,
    get_case_copilot_service,
    get_startup_advisor_api_service,
    get_startup_case_coordinator,
)

FIXTURE_ROOT = Path("tests/fixtures/startup_case_copilot_v1")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task0_case_copilot_data") / uuid4().hex

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
    return TestClient(app)


def test_idea_only_cases_keep_distinct_evidence_and_structured_question_contracts(
    client: TestClient,
) -> None:
    """Catches cloned case evidence or a question that diverges from its input action."""

    inventory = upload_idea_case(client, "idea_inventory")
    clinic = upload_idea_case(client, "idea_clinic")

    inventory_state = client.get(f"/api/v1/startup/cases/{inventory}/copilot/state")
    clinic_state = client.get(f"/api/v1/startup/cases/{clinic}/copilot/state")

    _assert_no_private_operating_metrics(inventory_state.text)
    _assert_no_private_operating_metrics(clinic_state.text)
    _assert_no_private_metric_keys(inventory_state.json() if inventory_state.text else {})
    _assert_no_private_metric_keys(clinic_state.json() if clinic_state.text else {})
    assert inventory_state.status_code == 200
    assert clinic_state.status_code == 200
    expected = _expected_contracts()
    inventory_expected = expected["cases"]["idea_inventory"]
    clinic_expected = expected["cases"]["idea_clinic"]

    inventory_payload = inventory_state.json()
    clinic_payload = clinic_state.json()
    assert inventory_payload["stage"] == "idea"
    assert clinic_payload["stage"] == "idea"
    assert inventory_payload["fact_coverage"] != inventory_payload[
        "scenario_completeness"
    ]
    for payload, case_expected in (
        (inventory_payload, inventory_expected),
        (clinic_payload, clinic_expected),
    ):
        descriptor = payload["question_descriptor"]
        assert descriptor is not None
        assert payload["next_question"] == descriptor["question"]
        assert payload["next_question"] == case_expected["expected_next_question"]
        assert descriptor["field_key"] == case_expected["expected_question_field"]
        fact_action = next(
            action for action in payload["actions"] if action["action"] == "open_fact_input"
        )
        assert fact_action["payload"]["field_key"] == descriptor["field_key"]
        assert fact_action["payload"]["provenance"] == "founder_statement"
    assert inventory_payload["suggested_action"] == "prepare_public_research"
    assert clinic_payload["suggested_action"] == "prepare_public_research"
    assert inventory_payload["extracted_facts"] == inventory_expected[
        "expected_extracted_facts"
    ]
    assert clinic_payload["extracted_facts"] == clinic_expected["expected_extracted_facts"]
    assert inventory_payload["prioritized_gaps"] == inventory_expected["prioritized_gaps"]
    assert clinic_payload["prioritized_gaps"] == clinic_expected["prioritized_gaps"]
    assert inventory_payload["extracted_facts"] != clinic_payload["extracted_facts"]
    assert inventory_payload["prioritized_gaps"] != clinic_payload["prioritized_gaps"]
    _assert_scenario_metrics_contract(inventory_payload, inventory_expected)
    _assert_scenario_metrics_contract(clinic_payload, clinic_expected)


def test_task11_auto_started_idea_text_briefs_build_primary_profile_and_gate2(
    client: TestClient,
) -> None:
    """Catches the canonical .txt idea briefs failing before primary_profile."""

    expected = _expected_contracts()
    for case_name in ("idea_inventory", "idea_clinic"):
        case_id = upload_idea_case(client, case_name, auto_start=True)
        status = client.get(f"/api/v1/startup/cases/{case_id}/analysis")
        gate2 = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
        profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
        state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")

        assert status.status_code == 200
        assert status.json()["analysis_status"] == "gate2_preview_ready"
        assert status.json()["gate2_status"] == "required"
        assert gate2.status_code == 200
        assert profile.status_code == 200
        assert profile.json()["analysis_stage"] == "primary"
        assert profile.json()["fields"]["startup_name"]["status"] == "source_fact"
        assert state.status_code == 200
        state_payload = state.json()
        descriptor = state_payload["question_descriptor"]
        assert state_payload["stage"] == "idea"
        assert descriptor is not None
        assert state_payload["next_question"] == descriptor["question"]
        assert state_payload["next_question"] == expected["cases"][case_name][
            "expected_next_question"
        ]
        assert descriptor["field_key"] == expected["cases"][case_name][
            "expected_question_field"
        ]
        fact_action = next(
            action
            for action in state_payload["actions"]
            if action["action"] == "open_fact_input"
        )
        assert fact_action["payload"]["field_key"] == descriptor["field_key"]


def test_task11_founder_assumption_keeps_profile_backed_read_models_on_new_revision(
    client: TestClient,
) -> None:
    """Catches an accepted founder statement leaving the primary profile stale."""

    case_id = upload_idea_case(
        client,
        "idea_inventory",
        fixture_mode="deterministic_offline",
        auto_start=True,
    )
    before = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert before.status_code == 200
    original_revision = before.json()["data_revision"]
    coordinator = get_startup_case_coordinator()
    original_runtime = dict(coordinator.runtime_for_test(case_id))
    payload = {
        "requirement_key": "monthly_recurring_revenue",
        "value": {
            "kind": "money",
            "amount": "1850000",
            "scale": "ones",
            "currency": "KZT",
        },
        "period": {"kind": "month", "value": "2026-07"},
        "source": {
            "kind": "founder_statement",
            "declared_source": "Founder interview on 2026-08-22",
        },
        "rationale": "Founder stated July 2026 recognized MRR excludes unpaid pilots.",
        "validation_plan": "Verify against bank deposits and invoice register.",
        "expected_case_revision": original_revision,
        "idempotency_key": "task11-profile-backed-founder-mrr",
    }

    accepted = client.post(f"/api/v1/startup/cases/{case_id}/assumptions", json=payload)

    assert accepted.status_code == 200, accepted.text
    accepted_payload = accepted.json()
    assert accepted_payload["status"] == "accepted"
    assert accepted_payload["provenance"] == "founder_statement"
    new_revision = original_revision + 1
    assert accepted_payload["new_revision"] == new_revision

    profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")
    scenarios = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")

    assert profile.status_code == 200
    assert state.status_code == 200
    assert thread.status_code == 200
    assert scenarios.status_code == 200
    assert profile.json()["data_revision"] == new_revision
    assert state.json()["data_revision"] == new_revision
    assert thread.json()["data_revision"] == new_revision
    assert scenarios.json()["data_revision"] == new_revision
    assert any(
        row["field_key"] == "mrr"
        and row["kind"] == "founder_statement"
        and row["status"] == "accepted"
        for row in state.json()["accepted_inputs"]
    )
    assert not any(
        fact["source_type"] == "source_fact" and "1850000" in fact["value"]
        for fact in state.json()["extracted_facts"]
    )

    projected_profile = profile.json()
    projected_thread = thread.json()
    get_case_copilot_service.cache_clear()
    replay = client.post(f"/api/v1/startup/cases/{case_id}/assumptions", json=payload)
    replayed_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    replayed_thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")

    assert replay.status_code == 200
    assert replay.json() == accepted_payload
    assert replayed_profile.status_code == 200
    assert replayed_profile.json()["profile_id"] == projected_profile["profile_id"]
    assert replayed_profile.json()["profile_hash"] == projected_profile["profile_hash"]
    assert replayed_thread.status_code == 200
    assert replayed_thread.json() == projected_thread

    projected_runtime = dict(coordinator.runtime_for_test(case_id))
    coordinator.seed_status_for_test(
        case_id,
        {
            **projected_runtime,
            "data_revision": new_revision,
            "profile_id": original_runtime["profile_id"],
            "profile_hash": original_runtime["profile_hash"],
            "profile_revision": original_revision,
            "primary_profile_id": original_runtime["primary_profile_id"],
        },
    )
    get_case_copilot_service.cache_clear()
    repaired_replay = client.post(
        f"/api/v1/startup/cases/{case_id}/assumptions",
        json=payload,
    )
    repaired_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")

    assert repaired_replay.status_code == 200
    assert repaired_replay.json() == accepted_payload
    assert repaired_profile.status_code == 200
    assert repaired_profile.json()["profile_id"] == projected_profile["profile_id"]
    assert repaired_profile.json()["profile_hash"] == projected_profile["profile_hash"]


def test_task11_founder_assumption_after_gate2_enriched_runtime_updates_profile_state_thread_scenarios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task11_enriched_assumption_data") / uuid4().hex

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container
    from due_diligence_agent.domain.startup.profile import StartupProfileAnalysisStage
    from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(
        client,
        "idea_inventory",
        fixture_mode="deterministic_offline",
        auto_start=True,
    )
    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200

    before_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert before_profile.status_code == 200
    assert before_profile.json()["analysis_stage"] == "enriched"
    original_revision = before_profile.json()["data_revision"]
    runtime_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    before_runtime = runtime_store.load(case_id)
    assert before_runtime["profile_id"] == before_profile.json()["profile_id"]
    assert before_runtime["profile_hash"] == before_profile.json()["profile_hash"]
    assert before_runtime["gtm_snapshot_revision"] == original_revision
    profile_repository = container.build_local_repositories(
        data_root / "startup-api" / "deterministic" / "startup-metadata.sqlite3"
    ).startup_profile_repository
    old_profiles = profile_repository.list_for_case(UUID(case_id))
    old_enriched = next(
        item
        for item in old_profiles
        if str(item.profile_id) == before_profile.json()["profile_id"]
    )
    old_primary = next(
        item for item in old_profiles if item.profile_id == old_enriched.parent_profile_id
    )

    payload = {
        "requirement_key": "monthly_recurring_revenue",
        "value": {
            "kind": "money",
            "amount": "1850000",
            "scale": "ones",
            "currency": "KZT",
        },
        "period": {"kind": "month", "value": "2026-07"},
        "source": {
            "kind": "founder_statement",
            "declared_source": "Founder interview on 2026-08-22",
        },
        "rationale": "Founder stated July 2026 recognized MRR excludes unpaid pilots.",
        "validation_plan": "Verify against bank deposits and invoice register.",
        "expected_case_revision": original_revision,
        "idempotency_key": "task11-enriched-profile-founder-mrr",
    }

    accepted = client.post(f"/api/v1/startup/cases/{case_id}/assumptions", json=payload)

    assert accepted.status_code == 200, accepted.text
    accepted_payload = accepted.json()
    assert accepted_payload["status"] == "accepted"
    assert accepted_payload["provenance"] == "founder_statement"
    new_revision = original_revision + 1
    assert accepted_payload["new_revision"] == new_revision

    profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")
    scenarios = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")

    assert profile.status_code == 200
    assert state.status_code == 200
    assert thread.status_code == 200
    assert scenarios.status_code == 200
    assert gtm.status_code == 200, gtm.text
    assert gtm.json()["snapshot_revision"] == new_revision
    assert gtm.json()["profile_id"] == profile.json()["profile_id"]
    assert profile.json()["data_revision"] == new_revision
    assert profile.json()["analysis_stage"] == "enriched"
    assert state.json()["data_revision"] == new_revision
    assert thread.json()["data_revision"] == new_revision
    assert scenarios.json()["data_revision"] == new_revision
    assert any(
        row["field_key"] == "mrr"
        and row["kind"] == "founder_statement"
        and row["status"] == "accepted"
        for row in state.json()["accepted_inputs"]
    )
    assert not any(
        fact["source_type"] == "source_fact" and "1850000" in fact["value"]
        for fact in state.json()["extracted_facts"]
    )
    launch_pack = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": new_revision,
            "idempotency_key": "task11-founder-mutation-launch-pack",
        },
    )
    assert launch_pack.status_code == 201, launch_pack.text
    assert launch_pack.json()["data_revision"] == new_revision
    assert "provenance=source_fact" not in launch_pack.json()["body_markdown"]

    profiles = profile_repository.list_for_case(UUID(case_id))
    new_primary_profiles = [
        item
        for item in profiles
        if item.data_revision == new_revision
        and item.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    ]
    new_enriched_profiles = [
        item
        for item in profiles
        if item.data_revision == new_revision
        and item.analysis_stage is StartupProfileAnalysisStage.ENRICHED
    ]
    assert len(new_primary_profiles) == 1
    assert len(new_enriched_profiles) == 1
    new_primary = new_primary_profiles[0]
    new_enriched = new_enriched_profiles[0]
    assert new_primary.parent_profile_id is None
    assert new_enriched.parent_profile_id == new_primary.profile_id
    assert new_primary.fields == old_primary.fields
    assert new_enriched.fields == old_enriched.fields
    assert profile.json()["profile_id"] == str(new_enriched.profile_id)
    runtime = runtime_store.load(case_id)
    assert runtime["profile_id"] == str(new_enriched.profile_id)
    assert runtime["profile_hash"] == new_enriched.profile_hash
    assert runtime["profile_revision"] == new_revision
    assert runtime["primary_profile_id"] == str(new_primary.profile_id)
    assert runtime["gate3_status"] == "required"
    assert runtime["gate4_status"] == "not_ready"
    assert runtime["report_status"] == "not_ready"
    assert runtime["gtm_snapshot_revision"] == new_revision
    assert runtime["product_validation_snapshot_revision"] == new_revision
    assert runtime["market_research_snapshot_revision"] == new_revision
    assert runtime["readiness_snapshot_revision"] == new_revision

    read_model_runtime = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "deterministic" / "startup-runtime.sqlite3"
    ).load(case_id)
    assert read_model_runtime["data_revision"] == new_revision
    assert read_model_runtime["profile_id"] == str(new_enriched.profile_id)
    assert (
        read_model_runtime["startup_gtm_artifact"]["snapshot"]["profile_id"]
        == read_model_runtime["profile_id"]
    )
    assert read_model_runtime["gtm_snapshot_revision"] == new_revision
    assert read_model_runtime["product_validation_snapshot_revision"] == new_revision
    assert read_model_runtime["market_research_snapshot_revision"] == new_revision
    assert read_model_runtime["readiness_snapshot_revision"] == new_revision
    assert isinstance(read_model_runtime["startup_gtm_artifact"], dict)
    assert isinstance(read_model_runtime["startup_product_validation_artifact"], dict)
    assert isinstance(read_model_runtime["startup_market_research_artifact"], dict)


@pytest.mark.parametrize("mutation_kind", ("founder", "public_research"))
def test_task11_post_commit_projection_failure_keeps_accepted_mutation_visible(
    monkeypatch: pytest.MonkeyPatch,
    mutation_kind: str,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task11_projection_failure_data") / uuid4().hex
    provider = _AcceptedBenchmarkProvider()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container
    from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

    real_build_case_copilot_service = container.build_case_copilot_service

    def build_case_copilot_service_with_provider(**kwargs: Any) -> Any:
        kwargs["research_provider"] = provider
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(
        client,
        "idea_inventory",
        fixture_mode="live",
        auto_start=True,
    )
    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200
    original_revision = client.get(f"/api/v1/startup/cases/{case_id}/profile").json()[
        "data_revision"
    ]
    projection_attempts = 0

    def fail_after_commit(
        self: CaseCopilotService,
        case_id: UUID,
        *,
        old_revision: int,
        new_revision: int,
    ) -> None:
        nonlocal projection_attempts
        projection_attempts += 1
        raise StartupGateConflict("research_profile_projection_unavailable")

    monkeypatch.setattr(CaseCopilotService, "_sync_revision_read_models", fail_after_commit)
    payload = {
        "requirement_key": "monthly_recurring_revenue",
        "value": {
            "kind": "money",
            "amount": "1850000",
            "scale": "ones",
            "currency": "KZT",
        },
        "period": {"kind": "month", "value": "2026-07"},
        "source": {
            "kind": "founder_statement",
            "declared_source": "Founder interview on 2026-08-22",
        },
        "rationale": "Founder stated July 2026 recognized MRR excludes unpaid pilots.",
        "validation_plan": "Verify against bank deposits and invoice register.",
        "expected_case_revision": original_revision,
        "idempotency_key": "task11-post-commit-projection-failure",
    }

    if mutation_kind == "founder":
        accepted = client.post(f"/api/v1/startup/cases/{case_id}/assumptions", json=payload)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "accepted"
        assert provider.calls == []
    else:
        plan_response = client.post(
            f"/api/v1/startup/cases/{case_id}/research/plans",
            json={
                "focus": "market",
                "intent": "Prepare public market benchmarks.",
                "expected_case_revision": original_revision,
            },
        )
        assert plan_response.status_code == 201
        plan = plan_response.json()
        accepted = client.post(
            f"/api/v1/startup/cases/{case_id}/research/jobs",
            json={
                "plan_id": plan["plan_id"],
                "plan_hash": plan["plan_hash"],
                "expected_case_revision": original_revision,
                "idempotency_key": "task11-post-commit-public-projection-failure",
                "consent_public_research": True,
                "acquisition_mode": "live_public_research",
            },
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["status"] == "completed"
        assert len(provider.calls) == 1

    assert accepted.json()["new_revision"] == original_revision + 1
    assert projection_attempts == 2
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert state.status_code == 200
    assert state.json()["data_revision"] == original_revision + 1
    if mutation_kind == "founder":
        assert any(
            row["field_key"] == "mrr"
            and row["kind"] == "founder_statement"
            and row["status"] == "accepted"
            for row in state.json()["accepted_inputs"]
        )
        assert not any(
            fact["source_type"] == "source_fact" and "1850000" in fact["value"]
            for fact in state.json()["extracted_facts"]
        )
    else:
        assert any(
            row["field_key"] == "acquisition_spend"
            and row["kind"] == "public_benchmark"
            and row["status"] == "accepted"
            for row in state.json()["accepted_inputs"]
        )
        assert not any(
            row["field_key"] == "acquisition_spend" and row["kind"] == "source_fact"
            for row in state.json()["accepted_inputs"]
        )
    assert gtm.status_code == 409
    assert gtm.json()["code"] == "startup_gtm_not_ready"

    runtime_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    read_model_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    runtime = runtime_store.load(case_id)
    read_model_runtime = read_model_store.load(case_id)
    for stored_runtime in (runtime, read_model_runtime):
        assert stored_runtime["data_revision"] == original_revision + 1
        assert stored_runtime.get("gtm_snapshot_id") is None
        assert stored_runtime.get("gtm_snapshot_hash") is None
        assert stored_runtime.get("gtm_snapshot_revision") is None
    assert isinstance(read_model_runtime.get("startup_gtm_artifact"), dict)


def test_task11_public_research_rejects_foreign_market_snapshot_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task11_foreign_market_snapshot_data") / uuid4().hex
    provider = _AcceptedBenchmarkProvider()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container
    from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

    real_build_case_copilot_service = container.build_case_copilot_service

    def build_case_copilot_service_with_provider(**kwargs: Any) -> Any:
        kwargs["research_provider"] = provider
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(
        client,
        "idea_inventory",
        fixture_mode="live",
        auto_start=True,
    )
    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    gate2 = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert gate2.status_code == 200
    revision = client.get(f"/api/v1/startup/cases/{case_id}/profile").json()[
        "data_revision"
    ]
    runtime_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    read_model_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    runtime = runtime_store.load(case_id)
    read_model_runtime = read_model_store.load(case_id)
    assert runtime["gtm_snapshot_revision"] == revision
    assert read_model_runtime["market_research_snapshot_revision"] == revision
    foreign_market_artifact = dict(read_model_runtime["startup_market_research_artifact"])
    foreign_snapshot = dict(foreign_market_artifact["snapshot"])
    foreign_snapshot["case_id"] = str(uuid4())
    foreign_market_artifact["snapshot"] = foreign_snapshot
    read_model_store.save(
        case_id,
        {
            **read_model_runtime,
            "startup_market_research_artifact": foreign_market_artifact,
        },
    )

    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market benchmarks.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()

    rejected = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "task11-foreign-market-preflight",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )

    assert rejected.status_code == 409
    assert rejected.json()["code"] == "research_profile_projection_unavailable"
    assert provider.calls == []
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert state.status_code == 200
    assert state.json()["data_revision"] == revision
    assert not any(
        item["field_key"] == "acquisition_spend" and item["kind"] == "public_benchmark"
        for item in state.json()["accepted_inputs"]
    )
    assert gtm.status_code == 200
    assert gtm.json()["snapshot_revision"] == revision
    workflow_after = runtime_store.load(case_id)
    read_model_after = read_model_store.load(case_id)
    assert workflow_after["data_revision"] == revision
    assert read_model_after["data_revision"] == revision
    for marker in (
        "market_research_snapshot_id",
        "market_research_snapshot_hash",
        "market_research_snapshot_revision",
        "gtm_snapshot_id",
        "gtm_snapshot_hash",
        "gtm_snapshot_revision",
    ):
        assert workflow_after.get(marker) == runtime.get(marker)
        assert read_model_after.get(marker) == read_model_runtime.get(marker)


def test_task11_founder_assumption_rejects_corrupt_profile_projection_before_mutation(
    client: TestClient,
) -> None:
    """Catches founder-statement persistence before profile preflight succeeds."""

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    before = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert before.status_code == 200
    original_revision = before.json()["data_revision"]
    coordinator = get_startup_case_coordinator()
    original_runtime = dict(coordinator.runtime_for_test(case_id))
    coordinator.seed_status_for_test(
        case_id,
        {**original_runtime, "profile_hash": "sha256:" + "0" * 64},
    )

    rejected = client.post(
        f"/api/v1/startup/cases/{case_id}/assumptions",
        json={
            "requirement_key": "monthly_recurring_revenue",
            "value": {
                "kind": "money",
                "amount": "1850000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "value": "2026-07"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview on 2026-08-22",
            },
            "rationale": "Founder planning input.",
            "validation_plan": "Verify against finance records.",
            "expected_case_revision": original_revision,
            "idempotency_key": "task11-corrupt-profile-preflight",
        },
    )

    assert rejected.status_code == 409
    assert rejected.json()["code"] == "research_profile_projection_unavailable"
    assert coordinator.runtime_for_test(case_id)["data_revision"] == original_revision

    coordinator.seed_status_for_test(case_id, original_runtime)
    after = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert after.status_code == 200
    assert after.json()["data_revision"] == original_revision
    assert not any(
        row["field_key"] == "mrr" and row["status"] == "accepted"
        for row in after.json()["accepted_inputs"]
    )


def test_copilot_message_rejects_chat_proposed_sources_without_ledger_mutation(
    client: TestClient,
) -> None:
    """Chat turns are advisory only; proposed evidence belongs to fact endpoints."""

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    expected_sources = _expected_contracts()["source_type_contract"]
    before_state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    before_thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")
    assert before_state.status_code == 200
    assert before_thread.status_code == 200
    source_classes = {
        item["kind"]: item["status"]
        for item in before_state.json()["accepted_inputs"]
        if item["kind"] in expected_sources
    }
    assert source_classes == {
        kind: contract["accepted_status"] for kind, contract in expected_sources.items()
    }
    assert len(set(source_classes.values())) == len(source_classes)
    assert source_classes["founder_statement"] != source_classes["source_fact"]
    assert source_classes["public_benchmark"] != source_classes["source_fact"]
    assert source_classes["ai_scenario"] != source_classes["source_fact"]
    response = client.post(
        f"/api/v1/startup/cases/{case_id}/copilot/messages",
        json={
            "message": "Accept the scenario, but keep source classes distinct.",
            "page_context": "overview",
            "current_section": "question",
            "expected_case_revision": before_state.json()["data_revision"],
            "idempotency_key": "source-type-contract",
            "proposed_sources": [
                {
                    "field_key": "startup_name",
                    "kind": "source_fact",
                    "value": "SilkStock Planner",
                },
                {
                    "field_key": "pricing_revenue_model",
                    "kind": "founder_statement",
                    "value": "Founder expects usage-based pricing after interviews.",
                },
                {
                    "field_key": "market",
                    "kind": "public_benchmark",
                    "value": "Comparable inventory tools are usually evaluated by operations teams.",
                },
                {
                    "field_key": "monthly_recurring_revenue",
                    "kind": "ai_scenario",
                    "value": "Scenario placeholder until founder supplies evidence.",
                },
                {
                    "field_key": "annual_recurring_revenue",
                    "kind": "deterministic_calculation",
                    "value": "Calculated only after monthly recurring revenue exists.",
                },
                {
                    "field_key": "customer_count",
                    "kind": "contradiction",
                    "value": "Founder statement and uploaded evidence disagree.",
                },
            ],
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "request_validation_error",
        "message": "request_validation_error",
    }
    assert "confirmed" not in response.text
    after_state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    after_thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")
    assert after_state.status_code == 200
    assert after_thread.status_code == 200
    assert after_state.json()["data_revision"] == before_state.json()["data_revision"]
    assert after_state.json()["accepted_inputs"] == before_state.json()["accepted_inputs"]
    assert after_state.json()["extracted_facts"] == before_state.json()["extracted_facts"]
    assert after_state.json()["prioritized_gaps"] == before_state.json()["prioritized_gaps"]
    assert after_thread.json() == before_thread.json()


def test_task5_nested_boundary_payloads_are_strict_422(client: TestClient) -> None:
    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)

    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    malformed_source = client.post(
        f"/api/v1/startup/cases/{case_id}/copilot/messages",
        json={
            "message": "Malformed nested source should not be accepted.",
            "page_context": "overview",
            "current_section": "question",
            "expected_case_revision": state.json()["data_revision"],
            "idempotency_key": "malformed-source",
            "proposed_sources": [
                {
                    "field_key": "pricing_revenue_model",
                    "kind": "founder_statement",
                    "value": "Founder expects usage pricing.",
                    "unexpected": "reject",
                }
            ],
        },
    )
    assert malformed_source.status_code == 422

    malformed_research = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "public_pricing_analogs",
            "intent": "Prepare public pricing research.",
            "nested": {"private_value": "must not pass loose dict validation"},
        },
    )
    assert malformed_research.status_code == 422

    malformed_job = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": "task6-not-created",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
            "extra": "reject",
        },
    )
    assert malformed_job.status_code == 422


def test_public_research_plan_rejects_private_mrr_before_external_call(
    client: TestClient,
) -> None:
    """Catches private metric egress before a research planner/provider is invoked."""

    case_id = upload_idea_case(client, "idea_clinic")
    fake_planner = RecordingPublicResearchPlanner()
    cast(Any, client.app).state.case_public_research_planner = fake_planner

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "monthly_recurring_revenue",
            "requested_private_value": "monthly_recurring_revenue",
            "intent": "Find public evidence for the clinic service's private MRR.",
            "expected_case_revision": client.get(
                f"/api/v1/startup/cases/{case_id}/copilot/state"
            ).json()["data_revision"],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "private_public_research_rejected"
    assert fake_planner.calls == []


def test_consented_public_research_job_is_distinct_from_plan_creation(
    client: TestClient,
) -> None:
    """Catches collapsing plan preparation and consented execution into one call."""

    case_id = upload_idea_case(client, "idea_inventory", fixture_mode="live", auto_start=True)
    state_before_job = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()
    revision = state_before_job["data_revision"]
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "public_pricing_analogs",
            "intent": "Prepare public pricing-analog research for inventory SaaS.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    assert plan["status"] == "prepared"
    assert plan["case_id"] == case_id
    assert plan["data_revision"] == revision
    assert plan["plan_id"]
    assert plan["plan_hash"]
    assert plan["query_previews"]
    assert plan["manual_only_keys"] == [
        "monthly_recurring_revenue",
        "annual_recurring_revenue",
        "recognized_revenue",
        "monthly_net_burn",
        "cash",
        "cash_balance",
        "runway",
        "actual_customers",
        "private_churn",
        "private_retention",
        "private_cac",
        "private_margin",
        "contracts",
        "contract_register",
        "invoices",
        "invoice_register",
        "bank",
        "bank_data",
    ]
    assert "consent" in plan["consent_text"].casefold()
    assert plan["created_at"] < plan["expires_at"]

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "public-research-job-1",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert job_response.status_code == 202
    job = job_response.json()
    assert job["status"] == "deferred"
    assert job["reason"] == "provider_unconfigured"
    assert job["acquisition_mode"] == "provider_unconfigured"
    assert job["requested_acquisition_mode"] == "live_public_research"
    assert job["selected_acquisition_mode"] == "provider_unconfigured"
    assert job["job_id"]
    assert job["accepted_entries"] == []
    assert job["rejected_entries"] == []
    assert job["manual_only_keys"] == plan["manual_only_keys"]
    assert job["citations"] == []
    assert job["changed_blocks"] == []
    assert job["stale_scenario_ids"] == []
    assert job["old_revision"] == revision
    assert job["new_revision"] == revision

    replay = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "public-research-job-1",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert replay.status_code == 202
    assert replay.json() == job

    fetched = client.get(f"/api/v1/startup/cases/{case_id}/research/jobs/{job['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == job


def test_task6_configured_api_path_uses_shared_live_research_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches the Case Copilot container ignoring a configured public provider."""

    _clear_startup_dependency_cache()
    data_root = Path("pytest_task0_case_copilot_data") / uuid4().hex
    live_port = _RecordingLiveResearchPort()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class UnconfiguredOpenAIStartupSettings:
        openai_api_key = None

    class _FakeSecret:
        def get_secret_value(self) -> str:
            return "test-api-key"

    class ConfiguredOpenAIStartupSettings:
        openai_api_key = _FakeSecret()
        max_input_tokens = 200
        max_output_tokens = 100
        per_case_usd_cap = "0.01"

    from due_diligence_agent.bootstrap import container

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(
        api_dependencies,
        "OpenAIStartupSettings",
        UnconfiguredOpenAIStartupSettings,
    )
    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    monkeypatch.setattr(
        api_dependencies,
        "OpenAIStartupSettings",
        ConfiguredOpenAIStartupSettings,
    )
    monkeypatch.setattr(
        container,
        "build_openai_startup_research_port",
        lambda **_kwargs: live_port,
        raising=False,
    )

    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(client, "idea_inventory", fixture_mode="live", auto_start=True)
    state_before_job = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()
    revision = state_before_job["data_revision"]
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Research market benchmarks; do not include private MRR.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    assert live_port.calls == []
    plan = plan_response.json()

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "configured-live-port",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )

    assert job_response.status_code == 202
    job = job_response.json()
    assert live_port.calls
    assert job["status"] == "completed"
    assert job["acquisition_mode"] == "live_public_research"
    assert job["reason"] is None
    assert job["accepted_entries"][0]["provenance"] == "public_benchmark"
    assert job["accepted_entries"][0]["input_key"] == "arpa"
    assert job["accepted_entries"][0]["range"] == {"low": "18500", "high": "32500"}
    assert job["accepted_entries"][0]["unit"] == "KZT"
    assert job["accepted_entries"][0]["period"] == "month"
    assert job["accepted_entries"][0]["formula"] == (
        "reported public KZT ARPA benchmark range"
    )
    assert job["accepted_entries"][0]["dependencies"] == [
        "public comparable companies",
    ]
    assert job["accepted_entries"][0]["validation_plan"]
    assert job["accepted_entries"][0]["source_refs"]
    assert job["rejected_entries"] == []
    assert job["changed_blocks"] == ["public_benchmarks", "scenarios"]
    assert job["old_revision"] == revision
    assert job["new_revision"] == revision + 1
    state_after_job = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()
    assert state_after_job["data_revision"] == revision + 1
    assert state_after_job["scenario_completeness"]["accepted_input_count"] >= 1
    assert state_after_job["scenario_metrics"] != state_before_job["scenario_metrics"]
    before_metrics = {
        metric["metric_key"]: metric for metric in state_before_job["scenario_metrics"]
    }
    changed_metrics = [
        metric
        for metric in state_after_job["scenario_metrics"]
        if metric != before_metrics[metric["metric_key"]]
    ]
    assert changed_metrics
    assert any(metric["source_refs"] for metric in changed_metrics)
    for metric in changed_metrics:
        assert metric["source_type"] != "source_fact"
        assert metric["formula"]
        assert metric["dependencies"]
        assert metric["what_would_confirm"]
    assert "MRR" not in " ".join(live_port.calls[0]["queries"])
    assert "private" not in " ".join(live_port.calls[0]["queries"]).casefold()


def test_task5_live_research_snapshot_without_entries_materializes_market_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task5_live_snapshot_only_data") / uuid4().hex
    provider = _LiveSnapshotOnlyProvider()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container
    from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

    real_build_case_copilot_service = container.build_case_copilot_service

    def build_case_copilot_service_with_provider(**kwargs: Any) -> Any:
        kwargs["research_provider"] = provider
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(client, "idea_inventory", fixture_mode="live", auto_start=True)
    state_before_job = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()
    revision = state_before_job["data_revision"]
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Research public market context; do not include private MRR.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "task5-live-snapshot-only",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )

    assert job_response.status_code == 202
    job = job_response.json()
    assert len(provider.calls) == 1
    assert job["status"] == "completed"
    assert job["acquisition_mode"] == "live_public_research"
    assert job["requested_acquisition_mode"] == "live_public_research"
    assert job["selected_acquisition_mode"] == "live_public_research"
    assert job["accepted_entries"] == []
    assert job["rejected_entries"] == []
    assert job["citations"] == ["https://example.com/live-market-context"]
    assert job["changed_blocks"] == ["market_research", "scenarios"]
    assert job["old_revision"] == revision
    assert job["new_revision"] == revision + 1
    assert len(job["source_refs"]) == 1

    persisted_scenarios = json.loads(
        (data_root / "startup-api" / "case-copilot" / "scenarios.json").read_text(
            encoding="utf-8"
        )
    )
    current_scenario_key = persisted_scenarios["current_by_case"][case_id]
    assert persisted_scenarios["records"][current_scenario_key]["data_revision"] == revision + 1

    state_after_job = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state_after_job.status_code == 200
    assert state_after_job.json()["data_revision"] == revision + 1
    assert not any(
        item["kind"] == "source_fact" and item["field_key"] in {"mrr", "cash_balance", "net_burn"}
        for item in state_after_job.json()["accepted_inputs"]
    )

    runtime = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    ).load(case_id)
    assert runtime["data_revision"] == revision + 1
    assert runtime["market_research_snapshot_revision"] == revision + 1
    market_artifact = runtime["startup_market_research_artifact"]
    assert market_artifact["snapshot"]["data_revision"] == revision + 1
    assert market_artifact["snapshot"]["source_mode"] == "live"
    assert market_artifact["snapshot"]["sources"][0]["status"] == "inference"
    assert market_artifact["snapshot"]["sources"][0]["supports_primary_financial_metrics"] is False


def test_task5_current_live_market_snapshot_binds_without_frozen_recompute() -> None:
    """Catches downstream market research overwriting accepted live research."""

    from due_diligence_agent.workflows.startup.ports import (
        StartupMarketResearchWorkflowAdapter,
    )

    profile = _market_adapter_profile(data_revision=4)
    live_snapshot = _LiveSnapshotOnlyResult(profile.case_id, profile.data_revision).market_snapshot
    store = _InMemoryWorkflowStore(
        {
            "data_revision": profile.data_revision,
            "profile_id": str(profile.profile_id),
            "profile_hash": profile.profile_hash,
            "profile_revision": profile.data_revision,
            "market_research_snapshot_id": str(live_snapshot.snapshot_id),
            "market_research_snapshot_hash": live_snapshot.snapshot_hash,
            "market_research_snapshot_revision": live_snapshot.data_revision,
            "startup_market_research_artifact": {
                "schema_version": live_snapshot.schema_version,
                "snapshot": live_snapshot.model_dump(mode="json"),
            },
        }
    )
    research_port = _ExplodingStartupResearchPort()

    result = StartupMarketResearchWorkflowAdapter(
        startup_profile_repository=_SingleStartupProfileRepository(profile),
        workflow_store=store,
        research_port=research_port,
    ).research(
        case_id=str(profile.case_id),
        profile_id=str(profile.profile_id),
        profile_hash=profile.profile_hash,
        profile_revision=profile.data_revision,
    )

    assert result == {
        "market_research_snapshot_id": str(live_snapshot.snapshot_id),
        "market_research_snapshot_hash": live_snapshot.snapshot_hash,
        "market_research_snapshot_revision": live_snapshot.data_revision,
    }
    assert research_port.calls == []
    assert store.load(str(profile.case_id))["startup_market_research_artifact"]["snapshot"][
        "source_mode"
    ] == "live"


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ("case", "startup_market_research_live_snapshot_case_mismatch"),
        ("revision", "startup_market_research_live_snapshot_revision_mismatch"),
        ("hash_marker", "startup_market_research_live_snapshot_marker_mismatch"),
    ],
)
def test_task5_live_market_snapshot_mismatch_fails_closed_without_frozen_recompute(
    mutation: str,
    error_code: str,
) -> None:
    """Catches stale live research falling back to frozen public fixtures."""

    from due_diligence_agent.workflows.startup.ports import (
        StartupIntelligenceBindingError,
        StartupMarketResearchWorkflowAdapter,
    )

    profile = _market_adapter_profile(data_revision=4)
    snapshot_case_id = uuid4() if mutation == "case" else profile.case_id
    snapshot_revision = 3 if mutation == "revision" else profile.data_revision
    live_snapshot = _LiveSnapshotOnlyResult(snapshot_case_id, snapshot_revision).market_snapshot
    marker_hash = (
        "sha256:" + "f" * 64
        if mutation == "hash_marker"
        else live_snapshot.snapshot_hash
    )
    store = _InMemoryWorkflowStore(
        {
            "data_revision": profile.data_revision,
            "profile_id": str(profile.profile_id),
            "profile_hash": profile.profile_hash,
            "profile_revision": profile.data_revision,
            "market_research_snapshot_id": str(live_snapshot.snapshot_id),
            "market_research_snapshot_hash": marker_hash,
            "market_research_snapshot_revision": live_snapshot.data_revision,
            "startup_market_research_artifact": {
                "schema_version": live_snapshot.schema_version,
                "snapshot": live_snapshot.model_dump(mode="json"),
            },
        }
    )
    research_port = _ExplodingStartupResearchPort()
    adapter = StartupMarketResearchWorkflowAdapter(
        startup_profile_repository=_SingleStartupProfileRepository(profile),
        workflow_store=store,
        research_port=research_port,
    )

    with pytest.raises(StartupIntelligenceBindingError) as exc_info:
        adapter.research(
            case_id=str(profile.case_id),
            profile_id=str(profile.profile_id),
            profile_hash=profile.profile_hash,
            profile_revision=profile.data_revision,
        )

    assert exc_info.value.code == error_code
    assert research_port.calls == []


def test_task2_deterministic_api_path_does_not_receive_configured_live_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task2_deterministic_research_mode") / uuid4().hex
    live_port = _RecordingLiveResearchPort()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class UnconfiguredOpenAIStartupSettings:
        openai_api_key = None

    class _FakeSecret:
        def get_secret_value(self) -> str:
            return "test-api-key"

    class ConfiguredOpenAIStartupSettings:
        openai_api_key = _FakeSecret()
        max_input_tokens = 200
        max_output_tokens = 100
        per_case_usd_cap = "0.01"

    from due_diligence_agent.bootstrap import container

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(
        api_dependencies,
        "OpenAIStartupSettings",
        UnconfiguredOpenAIStartupSettings,
    )
    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    monkeypatch.setattr(
        api_dependencies,
        "OpenAIStartupSettings",
        ConfiguredOpenAIStartupSettings,
    )

    monkeypatch.setattr(
        container,
        "build_openai_startup_research_port",
        lambda **_kwargs: live_port,
        raising=False,
    )

    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(
        client,
        "idea_inventory",
        fixture_mode="deterministic_offline",
        auto_start=True,
    )
    revision = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ]
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare deterministic offline benchmark context.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    assert live_port.calls == []
    plan = plan_response.json()

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "deterministic-offline-mode",
            "consent_public_research": True,
            "acquisition_mode": "deterministic_offline_fixture",
        },
    )

    assert job_response.status_code == 202
    job = job_response.json()
    assert live_port.calls == []
    assert job["status"] == "completed"
    assert job["acquisition_mode"] == "deterministic_offline_fixture"
    assert job["requested_acquisition_mode"] == "deterministic_offline_fixture"
    assert job["selected_acquisition_mode"] == "deterministic_offline_fixture"
    assert job["accepted_entries"][0]["publisher"] == "Deterministic Case Copilot Fixture"


def test_research_job_api_requires_explicit_acquisition_mode_before_offline_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task1_explicit_acquisition_mode_data") / uuid4().hex

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container

    class RecordingDeterministicProvider(container.DeterministicCaseCopilotBenchmarkProvider):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def collect(self, plan: Any) -> list[dict[str, object]]:
            self.calls.append(str(plan.plan_id))
            return super().collect(plan)

    deterministic_provider = RecordingDeterministicProvider()
    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "DeterministicCaseCopilotBenchmarkProvider",
        lambda: deterministic_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(
        client,
        "idea_inventory",
        fixture_mode="deterministic_offline",
        auto_start=True,
    )
    revision = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ]
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "public_pricing_analogs",
            "intent": "Prepare public pricing-analog research.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()

    missing_mode = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "missing-external-mode",
            "consent_public_research": True,
        },
    )

    assert missing_mode.status_code == 422
    assert missing_mode.json()["code"] == "research_acquisition_mode_required"
    assert deterministic_provider.calls == []


def test_task6_configured_api_accepts_public_benchmark_once_without_double_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task6_configured_api_data") / uuid4().hex
    provider = _AcceptedBenchmarkProvider()

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
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    revision = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ]
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market benchmarks.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "configured-accepted-benchmark",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )

    assert job_response.status_code == 202
    job = job_response.json()
    assert len(provider.calls) == 1
    assert job["status"] == "completed"
    assert job["accepted_entries"][0]["provenance"] == "public_benchmark"
    assert job["accepted_entries"][0]["formula"] == "public benchmark range"
    assert job["accepted_entries"][0]["dependencies"] == ["public comparable companies"]
    assert job["rejected_entries"] == []
    assert job["changed_blocks"] == ["public_benchmarks", "scenarios"]
    assert job["old_revision"] == revision
    assert job["new_revision"] == revision + 1

    state_after_job = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state_after_job.status_code == 200
    assert state_after_job.json()["data_revision"] == revision + 1
    accepted_inputs = state_after_job.json()["accepted_inputs"]
    legend_rows = [
        item
        for item in accepted_inputs
        if item["field_key"] == "public_benchmark"
        and item["kind"] == "public_benchmark"
        and item["status"] == "external_context"
    ]
    benchmark_rows = [
        item
        for item in accepted_inputs
        if item["field_key"] == "acquisition_spend"
        and item["kind"] == "public_benchmark"
    ]
    assert len(legend_rows) == 1
    assert len(benchmark_rows) == 1
    assert {key: value for key, value in benchmark_rows[0].items() if key != "source_refs"} == {
        "field_key": "acquisition_spend",
        "kind": "public_benchmark",
        "status": "accepted",
        "value": "1000-2000 KZT",
        "period": "month",
        "rationale": "Cited public benchmark for comparable acquisition spend.",
        "validation_plan": (
            "Use only as external context until founder-specific evidence exists."
        ),
        "declared_source": None,
    }
    assert len(benchmark_rows[0]["source_refs"]) == 2
    assert UUID(benchmark_rows[0]["source_refs"][0])
    assert benchmark_rows[0]["source_refs"][1:] == job["accepted_entries"][0]["source_refs"]
    assert state_after_job.json()["scenario_completeness"]["accepted_input_count"] == 1
    assert not any(
        item["field_key"] == "acquisition_spend" and item["kind"] == "source_fact"
        for item in accepted_inputs
    )

    replay = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "configured-accepted-benchmark",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )

    assert replay.status_code == 202
    assert replay.json() == job
    assert len(provider.calls) == 1
    state_after_replay = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state_after_replay.status_code == 200
    assert state_after_replay.json()["data_revision"] == revision + 1


def test_task11_accepted_public_research_keeps_backend_read_models_on_same_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task11_research_readmodel_data") / uuid4().hex
    provider = _AcceptedBenchmarkProvider()

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
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    before_state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    before_thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")
    before_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert before_state.status_code == 200
    assert before_thread.status_code == 200
    assert before_profile.status_code == 200
    revision = before_state.json()["data_revision"]
    assert before_thread.json()["data_revision"] == revision
    assert before_profile.json()["data_revision"] == revision

    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market benchmarks.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "configured-accepted-benchmark-readmodels",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert job_response.status_code == 202
    job = job_response.json()
    assert job["status"] == "completed"
    assert job["old_revision"] == revision
    assert job["new_revision"] == revision + 1

    responses = {
        "profile": client.get(f"/api/v1/startup/cases/{case_id}/profile"),
        "state": client.get(f"/api/v1/startup/cases/{case_id}/copilot/state"),
        "thread": client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread"),
        "scenarios": client.get(f"/api/v1/startup/cases/{case_id}/scenarios"),
    }

    for label, response in responses.items():
        assert response.status_code == 200, (label, response.text)
        payload = response.json()
        assert payload["case_id"] == case_id, label
        assert payload["data_revision"] == revision + 1, label

    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert gtm.status_code == 409, gtm.text
    assert gtm.json()["code"] == "startup_gtm_not_ready"

    launch_pack = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": revision + 1,
            "idempotency_key": "task11-public-benchmark-launch-pack",
        },
    )
    assert launch_pack.status_code == 201, launch_pack.text
    assert launch_pack.json()["data_revision"] == revision + 1
    assert "provenance=source_fact" not in launch_pack.json()["body_markdown"]


def test_task11_public_research_replay_does_not_rewrite_read_model_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task11_research_replay_readmodel_data") / uuid4().hex
    provider = _AcceptedBenchmarkProvider()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container
    from due_diligence_agent.domain.startup.profile import StartupProfileAnalysisStage
    from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

    real_build_case_copilot_service = container.build_case_copilot_service

    def build_case_copilot_service_with_provider(**kwargs: Any) -> Any:
        kwargs["research_provider"] = provider
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    revision = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ]
    assert client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread").status_code == 200
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market benchmarks.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    job_request = {
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
        "expected_case_revision": revision,
        "idempotency_key": "configured-accepted-benchmark-replay-readmodels",
        "consent_public_research": True,
        "acquisition_mode": "live_public_research",
    }

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json=job_request,
    )
    assert job_response.status_code == 202
    job = job_response.json()
    profile = client.get(f"/api/v1/startup/cases/{case_id}/profile").json()
    thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread").json()
    runtime_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    runtime = runtime_store.load(case_id)
    profile_repository = container.build_local_repositories(
        data_root / "startup-api" / "deterministic" / "startup-metadata.sqlite3"
    ).startup_profile_repository
    same_revision_primary_profiles = [
        item
        for item in profile_repository.list_for_case(UUID(case_id))
        if item.data_revision == revision + 1
        and item.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    ]
    assert len(same_revision_primary_profiles) == 1

    replay_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json=job_request,
    )

    assert replay_response.status_code == 202
    assert replay_response.json() == job
    assert len(provider.calls) == 1
    replayed_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile").json()
    replayed_thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread").json()
    replayed_runtime = runtime_store.load(case_id)
    replayed_same_revision_primary_profiles = [
        item
        for item in profile_repository.list_for_case(UUID(case_id))
        if item.data_revision == revision + 1
        and item.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    ]
    assert replayed_profile["profile_id"] == profile["profile_id"]
    assert replayed_profile["profile_hash"] == profile["profile_hash"]
    assert len(replayed_thread["messages"]) == len(thread["messages"])
    assert replayed_thread["messages"] == thread["messages"]
    for key in (
        "profile_id",
        "profile_hash",
        "profile_revision",
        "primary_profile_id",
        "analysis_status",
        "active_analysis_thread_id",
        "analysis_start_claim_data_revision",
        "analysis_start_claim_thread_id",
    ):
        assert replayed_runtime.get(key) == runtime.get(key), key
    assert len(replayed_same_revision_primary_profiles) == 1
    assert replayed_same_revision_primary_profiles[0].profile_id == same_revision_primary_profiles[0].profile_id


def test_task11_public_research_replay_repairs_stale_thread_without_rewriting_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task11_research_replay_thread_repair_data") / uuid4().hex
    provider = _AcceptedBenchmarkProvider()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container
    from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

    real_build_case_copilot_service = container.build_case_copilot_service

    def build_case_copilot_service_with_provider(**kwargs: Any) -> Any:
        kwargs["research_provider"] = provider
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    revision = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ]
    assert client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread").status_code == 200
    thread_store_path = (
        data_root
        / "startup-api"
        / "deterministic"
        / "case-copilot"
        / "copilot-threads.json"
    )
    stale_thread_store = thread_store_path.read_text(encoding="utf-8")
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market benchmarks.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    job_request = {
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
        "expected_case_revision": revision,
        "idempotency_key": "configured-accepted-benchmark-thread-repair",
        "consent_public_research": True,
        "acquisition_mode": "live_public_research",
    }
    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json=job_request,
    )
    assert job_response.status_code == 202
    profile = client.get(f"/api/v1/startup/cases/{case_id}/profile").json()
    runtime_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    runtime = runtime_store.load(case_id)

    thread_store_path.write_text(stale_thread_store, encoding="utf-8")
    stale_thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread").json()
    assert stale_thread["data_revision"] == revision

    replay_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json=job_request,
    )

    assert replay_response.status_code == 202
    repaired_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile").json()
    repaired_runtime = runtime_store.load(case_id)
    repaired_thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread").json()
    assert repaired_profile["profile_id"] == profile["profile_id"]
    assert repaired_profile["profile_hash"] == profile["profile_hash"]
    assert repaired_runtime["profile_id"] == runtime["profile_id"]
    assert repaired_runtime["profile_hash"] == runtime["profile_hash"]
    assert repaired_thread["data_revision"] == revision + 1
    assert len(repaired_thread["messages"]) == len(stale_thread["messages"]) + 1
    assert repaired_thread["messages"][-1]["role"] == "system_event"


def test_task11_founder_then_public_research_projects_gtm_on_current_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_startup_dependency_cache()
    data_root = Path("pytest_task11_combined_enriched_research_data") / uuid4().hex
    provider = _AcceptedBenchmarkProvider()

    class FakeSettings:
        def __init__(self) -> None:
            self.data_dir = data_root
            self.langsmith_tracing = False

    class FakeOpenAIStartupSettings:
        openai_api_key = None

    from due_diligence_agent.bootstrap import container
    from due_diligence_agent.domain.startup.profile import StartupProfileAnalysisStage
    from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

    real_build_case_copilot_service = container.build_case_copilot_service

    def build_case_copilot_service_with_provider(**kwargs: Any) -> Any:
        kwargs["research_provider"] = provider
        kwargs["acquisition_mode"] = "live_public_research"
        return real_build_case_copilot_service(**kwargs)

    monkeypatch.setattr(api_dependencies, "Settings", FakeSettings)
    monkeypatch.setattr(api_dependencies, "OpenAIStartupSettings", FakeOpenAIStartupSettings)
    monkeypatch.setattr(
        container,
        "build_case_copilot_service",
        build_case_copilot_service_with_provider,
    )

    coordinator = get_startup_case_coordinator()
    advisor_service = get_startup_advisor_api_service()
    app = create_app()
    app.dependency_overrides[get_startup_case_coordinator] = lambda: coordinator
    app.dependency_overrides[get_startup_advisor_api_service] = lambda: advisor_service
    client = TestClient(app)

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    preview = client.get(f"/api/v1/startup/cases/{case_id}/gate2/preview")
    assert preview.status_code == 200
    approved = client.post(
        f"/api/v1/startup/cases/{case_id}/gate2/decision",
        json={"decision": "approved", "resume_token": preview.json()["resume_token"]},
    )
    assert approved.status_code == 200

    before_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert before_profile.status_code == 200
    assert before_profile.json()["analysis_stage"] == "enriched"
    original_revision = before_profile.json()["data_revision"]

    founder = client.post(
        f"/api/v1/startup/cases/{case_id}/assumptions",
        json={
            "requirement_key": "monthly_recurring_revenue",
            "value": {
                "kind": "money",
                "amount": "1850000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "value": "2026-07"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview on 2026-08-22",
            },
            "rationale": "Founder stated July 2026 recognized MRR excludes unpaid pilots.",
            "validation_plan": "Verify against bank deposits and invoice register.",
            "expected_case_revision": original_revision,
            "idempotency_key": "task11-combined-founder-mrr",
        },
    )
    assert founder.status_code == 200, founder.text
    founder_revision = original_revision + 1
    assert founder.json()["new_revision"] == founder_revision

    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market benchmarks.",
            "expected_case_revision": founder_revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": founder_revision,
            "idempotency_key": "task11-combined-public-benchmark",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert job_response.status_code == 202
    research_revision = founder_revision + 1
    assert job_response.json()["status"] == "completed"
    assert job_response.json()["new_revision"] == research_revision

    responses = {
        "profile": client.get(f"/api/v1/startup/cases/{case_id}/profile"),
        "state": client.get(f"/api/v1/startup/cases/{case_id}/copilot/state"),
        "thread": client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread"),
        "scenarios": client.get(f"/api/v1/startup/cases/{case_id}/scenarios"),
    }
    for label, response in responses.items():
        assert response.status_code == 200, (label, response.text)
        assert response.json()["data_revision"] == research_revision, label

    state_payload = responses["state"].json()
    assert not any(
        fact["source_type"] == "source_fact" and "1850000" in fact["value"]
        for fact in state_payload["extracted_facts"]
    )
    assert not any(
        item["field_key"] == "acquisition_spend" and item["kind"] == "source_fact"
        for item in state_payload["accepted_inputs"]
    )

    gtm = client.get(f"/api/v1/startup/cases/{case_id}/gtm")
    assert gtm.status_code == 200, gtm.text
    gtm_payload = gtm.json()
    assert gtm_payload["snapshot_revision"] == research_revision

    launch_pack = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": research_revision,
            "idempotency_key": "task11-combined-launch-pack",
        },
    )
    assert launch_pack.status_code == 201, launch_pack.text
    assert launch_pack.json()["data_revision"] == research_revision
    assert "provenance=source_fact" not in launch_pack.json()["body_markdown"]

    runtime_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "startup-runtime.sqlite3"
    )
    read_model_store = SQLiteStartupWorkflowRuntimeStore(
        data_root / "startup-api" / "deterministic" / "startup-runtime.sqlite3"
    )
    runtime = runtime_store.load(case_id)
    read_model_runtime = read_model_store.load(case_id)
    for label, stored_runtime in {
        "workflow": runtime,
        "read_model": read_model_runtime,
    }.items():
        assert stored_runtime["data_revision"] == research_revision, label
        assert stored_runtime["profile_revision"] == research_revision, label
        assert stored_runtime["product_validation_snapshot_revision"] == research_revision, label
        assert stored_runtime["market_research_snapshot_revision"] == research_revision, label
        assert stored_runtime["readiness_snapshot_revision"] == research_revision, label
        assert stored_runtime["gtm_snapshot_revision"] == research_revision, label
        assert stored_runtime["gtm_snapshot_id"] == gtm_payload["snapshot_id"], label
        assert (
            stored_runtime["product_validation_snapshot_id"]
            == gtm_payload["product_validation_snapshot_id"]
        ), label
        assert (
            stored_runtime["market_research_snapshot_id"]
            == gtm_payload["market_research_snapshot_id"]
        ), label

    profile_repository = container.build_local_repositories(
        data_root / "startup-api" / "deterministic" / "startup-metadata.sqlite3"
    ).startup_profile_repository
    profiles = profile_repository.list_for_case(UUID(case_id))
    current_primary = [
        item
        for item in profiles
        if item.data_revision == research_revision
        and item.analysis_stage is StartupProfileAnalysisStage.PRIMARY
    ]
    current_enriched = [
        item
        for item in profiles
        if item.data_revision == research_revision
        and item.analysis_stage is StartupProfileAnalysisStage.ENRICHED
    ]
    assert len(current_primary) == 1
    assert len(current_enriched) == 1
    assert current_enriched[0].parent_profile_id == current_primary[0].profile_id
    assert gtm_payload["profile_id"] == str(current_enriched[0].profile_id)


def test_task6_research_plan_and_job_lifecycle_conflicts_are_safe(
    client: TestClient,
) -> None:
    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    other_case_id = upload_idea_case(client, "idea_clinic", auto_start=True)
    revision = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ]
    other_revision = client.get(f"/api/v1/startup/cases/{other_case_id}/copilot/state").json()[
        "data_revision"
    ]
    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "market",
            "intent": "Prepare public market research.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()

    no_consent = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": other_revision,
            "idempotency_key": "public-research-no-consent",
            "consent_public_research": False,
            "acquisition_mode": "live_public_research",
        },
    )
    assert no_consent.status_code == 422
    assert no_consent.json()["code"] == "public_research_consent_required"

    hash_mismatch = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": "wrong-hash",
            "expected_case_revision": revision,
            "idempotency_key": "public-research-wrong-hash",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert hash_mismatch.status_code == 409
    assert hash_mismatch.json()["code"] == "stale_research_plan"

    stale_revision = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision + 1,
            "idempotency_key": "public-research-stale-revision",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert stale_revision.status_code == 409
    assert stale_revision.json()["code"] == "stale_research_plan"

    foreign_plan = client.post(
        f"/api/v1/startup/cases/{other_case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "public-research-foreign-plan",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert foreign_plan.status_code == 404
    assert foreign_plan.json()["code"] == "research_plan_not_found"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "extracted_facts": [
                {
                    "fact_key": "mrr",
                    "source_type": "source_fact",
                    "value": 1000,
                    "unit": "USD/month",
                }
            ]
        },
        {
            "accepted_inputs": [
                {
                    "field_key": "monthly_recurring_revenue",
                    "kind": "founder_statement",
                    "value": 1000,
                }
            ]
        },
        {
            "scenario_actuals": [
                {
                    "metric_key": "annual_recurring_revenue",
                    "source_type": "deterministic_calculation",
                    "value": 12000,
                }
            ]
        },
        {
            "metrics": {
                "cash_balance": {
                    "source_type": "source_fact",
                    "value": 10000,
                }
            }
        },
        {
            "financials": [
                {
                    "field_name": "recognized_revenue",
                    "source_type": "source_fact",
                    "amount": 2500,
                }
            ]
        },
        {
            "runway": [
                {
                    "metric_name": "net_burn",
                    "kind": "founder_statement",
                    "current_value": 500,
                }
            ]
        },
        {
            "profile": [
                {
                    "metric_id": "customer_count",
                    "source_type": "source_fact",
                    "value": 25,
                }
            ]
        },
    ],
)
def test_private_metric_guard_rejects_actual_operating_metric_identifier_shapes(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(
        pytest.fail.Exception,
        match="idea-only response exposed private actual metric",
    ):
        _assert_no_private_metric_keys(payload)


def test_private_metric_guard_allows_missing_gap_and_scenario_metadata() -> None:
    _assert_no_private_metric_keys(
        {
            "prioritized_gaps": [
                {
                    "field_key": "monthly_recurring_revenue",
                    "gap_type": "missing_founder_input",
                    "status": "missing",
                    "allowed_action": "manual_fact_intake",
                    "reason": "Founder has not supplied a verified value.",
                },
                {
                    "field_key": "cash_balance",
                    "gap_type": "missing_founder_input",
                    "status": "missing",
                    "allowed_action": "manual_fact_intake",
                    "reason": "Cash runway cannot be inferred from an idea brief.",
                },
            ],
            "scenario_metrics": [
                {
                    "metric_key": "monthly_recurring_revenue",
                    "source_type": "ai_scenario",
                    "value": None,
                    "range": {
                        "conservative": None,
                        "base": None,
                        "optimistic": None,
                    },
                    "formula": "founder_supplied_mrr_or_accepted_scenario_range",
                    "dependencies": ["customer_count", "cash_balance"],
                    "unit": "USD/month",
                    "period": "launch_month",
                    "confidence": "low",
                    "source_refs": [],
                    "what_would_confirm": "Founder provides actual billing records.",
                    "validation_plan": ["Request source documents before upgrading provenance."],
                }
            ],
            "research_contract": {
                "private_focus_keys": [
                    "mrr",
                    "monthly_recurring_revenue",
                    "arr",
                    "annual_recurring_revenue",
                    "recognized_revenue",
                    "monthly_net_burn",
                    "cash_balance",
                    "customer_count",
                ],
                "next_action": "reject_before_provider_call",
            },
        }
    )


def test_task5_unknown_fact_field_returns_422_without_mutating_state(client: TestClient) -> None:
    """Catches accepting loose fact payloads or mutating before request validation."""

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    before = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert before.status_code == 200

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            "requirement_key": "monthly_price",
            "value": {
                "kind": "money",
                "amount": "35000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {
                "kind": "month",
                "start": "2026-07-01",
                "end": "2026-07-31",
            },
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview",
            },
            "expected_case_revision": before.json()["data_revision"],
            "idempotency_key": "fact-unknown-field",
            "unexpected": "must fail",
        },
    )

    after = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert response.status_code == 422
    assert after.status_code == 200
    assert after.json()["data_revision"] == before.json()["data_revision"]
    assert after.json()["accepted_inputs"] == before.json()["accepted_inputs"]


def test_task5_arbitrary_idea_brief_state_is_derived_from_same_case_content(
    client: TestClient,
) -> None:
    """Catches falling back to SilkStock/CareLoop fixture literals for unknown idea briefs."""

    case_id = upload_custom_idea_case(
        client,
        company_name="LedgerLaunch",
        brief=(
            "LedgerLaunch helps freelance architects turn messy invoice emails "
            "into project-level cash collection reminders. Buyers are studio "
            "owners; users are office managers. The first launch wedge is "
            "two-person design studios in Poland."
        ),
    )

    response = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload, sort_keys=True)
    assert "LedgerLaunch" in serialized
    assert "architect" in serialized.casefold()
    assert "SilkStock" not in serialized
    assert "CareLoop" not in serialized
    assert payload["case_id"] == case_id


def test_task5_fact_save_returns_canonical_intake_delta_not_parallel_runtime_delta(
    client: TestClient,
) -> None:
    """Catches bypassing CaseFactIntakeService.save_founder_statement()."""

    case_id = upload_idea_case(client, "idea_inventory", auto_start=True)
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    original_revision = state.json()["data_revision"]

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            "requirement_key": "monthly_price",
            "value": {
                "kind": "money",
                "amount": "35000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "start": "2026-07-01", "end": "2026-07-31"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview",
            },
            "expected_case_revision": original_revision,
            "idempotency_key": "fact-canonical-intake",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["delta"]["accepted"] is True
    assert payload["delta"]["metric_after"] == {"monthly_price": "founder_statement"}
    assert payload["delta"]["readiness_after"]["answered"] == 1
    assert payload["delta"]["stale_scenario_ids"]
    assert payload["delta"]["stale_report_ids"]
    projected_profile = client.get(f"/api/v1/startup/cases/{case_id}/profile")
    assert projected_profile.status_code == 200
    assert projected_profile.json()["data_revision"] == original_revision + 1

    replay = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            "requirement_key": "monthly_price",
            "value": {
                "kind": "money",
                "amount": "35000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "start": "2026-07-01", "end": "2026-07-31"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview",
            },
            "expected_case_revision": original_revision,
            "idempotency_key": "fact-canonical-intake",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["delta"] == payload["delta"]


def test_task5_typed_money_fact_requires_amount_scale_currency_period_and_declared_source(
    client: TestClient,
) -> None:
    """Catches falling back to the old flat free-text fact contract."""

    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    original_revision = state.json()["data_revision"]

    incomplete = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            "requirement_key": "monthly_price",
            "value": {"kind": "money", "amount": "35000"},
            "period": {"kind": "month", "start": "2026-07-01", "end": "2026-07-31"},
            "source": {"kind": "founder_statement"},
            "expected_case_revision": original_revision,
            "idempotency_key": "fact-money-invalid",
        },
    )
    assert incomplete.status_code == 422
    assert {item["field"] for item in incomplete.json()["errors"]} == {
        "scale",
        "currency",
        "declared_source",
    }

    accepted = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            "requirement_key": "monthly_price",
            "value": {
                "kind": "money",
                "amount": "35000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "start": "2026-07-01", "end": "2026-07-31"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview",
            },
            "note": "Launch pricing hypothesis",
            "expected_case_revision": original_revision,
            "idempotency_key": "fact-money-accepted",
        },
    )

    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["accepted"] is True
    assert payload["old_revision"] == original_revision
    assert payload["new_revision"] == original_revision + 1
    assert payload["changed_keys"] == ["monthly_price"]
    assert payload["provenance"] == "founder_statement"
    assert payload["source_type"] == "founder_statement"


def test_task5_stale_fact_and_idempotency_conflict_happen_before_mutation(
    client: TestClient,
) -> None:
    """Catches stale writes or reused idempotency keys changing case state."""

    case_id = upload_idea_case(client, "idea_clinic")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    original_revision = state.json()["data_revision"]
    valid_payload = {
        "requirement_key": "monthly_price",
        "value": {
            "kind": "money",
            "amount": "45",
            "scale": "ones",
            "currency": "USD",
        },
        "period": {"kind": "month", "start": "2026-09-01", "end": "2026-09-30"},
        "source": {
            "kind": "founder_statement",
            "declared_source": "Founder interview",
        },
        "expected_case_revision": original_revision,
        "idempotency_key": "clinic-price",
    }

    stale = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={**valid_payload, "expected_case_revision": original_revision + 99},
    )
    assert stale.status_code == 409
    assert client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ] == original_revision

    first = client.post(f"/api/v1/startup/cases/{case_id}/facts", json=valid_payload)
    assert first.status_code == 200
    replay = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={**valid_payload, "expected_case_revision": original_revision},
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()

    conflict = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            **valid_payload,
            "value": {
                "kind": "money",
                "amount": "99",
                "scale": "ones",
                "currency": "USD",
            },
            "expected_case_revision": original_revision + 1,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_conflict"
    assert client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ] == original_revision + 1


def test_task5_fact_save_preserves_uploaded_runtime_record(client: TestClient) -> None:
    """Catches replacing the workflow runtime with a revision-only record."""

    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    original_revision = state.json()["data_revision"]

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            "requirement_key": "monthly_price",
            "value": {
                "kind": "money",
                "amount": "35000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "start": "2026-07-01", "end": "2026-07-31"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview",
            },
            "expected_case_revision": original_revision,
            "idempotency_key": "runtime-preserve-price",
        },
    )

    assert response.status_code == 200
    status = client.get(f"/api/v1/startup/cases/{case_id}")
    assert status.status_code == 200
    assert status.json()["analysis_status"] == "awaiting_start"
    state_after = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    serialized = json.dumps(state_after.json(), sort_keys=True)
    assert "SilkStock Planner" in serialized


def test_task5_fact_save_rejects_workflow_runtime_revision_divergence_before_mutation(
    client: TestClient,
) -> None:
    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    original_revision = state.json()["data_revision"]
    coordinator = get_startup_case_coordinator()
    coordinator.seed_status_for_test(
        case_id,
        {
            "data_revision": original_revision + 1,
            "documents": coordinator.runtime_for_test(case_id)["documents"],
            "case_exists": True,
        },
    )

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/facts",
        json={
            "requirement_key": "monthly_price",
            "value": {
                "kind": "money",
                "amount": "35000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "start": "2026-07-01", "end": "2026-07-31"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview",
            },
            "expected_case_revision": original_revision,
            "idempotency_key": "runtime-divergence-price",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "case_revision_conflict"
    refreshed = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    assert refreshed.status_code == 200
    assert refreshed.json()["data_revision"] == original_revision


def test_task5_scenarios_expose_three_decimal_safe_variants_and_stale_selection_is_safe(
    client: TestClient,
) -> None:
    """Catches incomplete scenario projection, JSON floats, or stale selected-scenario mutation."""

    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    revision = state.json()["data_revision"]

    scenarios = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    assert scenarios.status_code == 200
    payload = scenarios.json()
    assert set(payload["scenarios"]) == {"conservative", "base", "optimistic"}
    assert payload["selected_scenario_key"] == "base"
    for variant in payload["scenarios"].values():
        metric = variant["metrics"]["mrr"]
        assert isinstance(metric["value_range"]["lower"], str)
        assert isinstance(metric["value_range"]["upper"], str)
        assert metric["formula_key"] == "mrr"
        assert metric["dependency_refs"]
        assert metric["period"] == "month"
        assert metric["validation_plan"]
        assert metric["what_would_confirm"]
        assert metric["provenance"] in {
            "ai_scenario",
            "founder_statement",
            "public_benchmark",
            "deterministic_calculation",
        }

    stale = client.post(
        f"/api/v1/startup/cases/{case_id}/scenarios/selection",
        json={
            "scenario_key": "optimistic",
            "expected_case_revision": revision + 1,
            "idempotency_key": "select-stale",
        },
    )
    assert stale.status_code == 409
    assert client.get(f"/api/v1/startup/cases/{case_id}/scenarios").json()[
        "selected_scenario_key"
    ] == "base"


def test_task5_scenarios_expose_full_task4_graph_and_selection_persists(
    client: TestClient,
) -> None:
    """Catches replacing StartupScenarioService with a two-metric shortcut."""

    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    revision = state.json()["data_revision"]

    scenarios = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    assert scenarios.status_code == 200
    payload = scenarios.json()
    assert set(payload["scenarios"]) == {"conservative", "base", "optimistic"}
    for variant in payload["scenarios"].values():
        assert set(variant["metrics"]) == {
            "mrr",
            "arr",
            "gross_margin",
            "net_burn",
            "runway",
            "cac",
            "ltv",
            "ltv_cac",
            "cac_payback",
        }
        assert set(variant["inputs"]) >= {
            "monthly_price",
            "paying_customers",
            "cash_balance",
            "acquisition_spend",
            "arpa",
        }

    selected = client.post(
        f"/api/v1/startup/cases/{case_id}/scenarios/selection",
        json={
            "scenario_set_id": payload["scenario_set_id"],
            "scenario_key": "optimistic",
            "expected_case_revision": revision,
            "idempotency_key": "select-canonical-optimistic",
        },
    )
    assert selected.status_code == 200
    assert selected.json()["new_scenario_key"] == "optimistic"
    assert client.get(f"/api/v1/startup/cases/{case_id}/scenarios").json()[
        "selected_scenario_key"
    ] == "optimistic"


def test_task5_state_projects_canonical_task4_scenario_graph_and_selection(
    client: TestClient,
) -> None:
    case_id = upload_idea_case(client, "idea_inventory")
    state_before = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state_before.status_code == 200
    scenarios = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    assert scenarios.status_code == 200
    scenario_payload = scenarios.json()
    selected = client.post(
        f"/api/v1/startup/cases/{case_id}/scenarios/selection",
        json={
            "scenario_set_id": scenario_payload["scenario_set_id"],
            "scenario_key": "optimistic",
            "expected_case_revision": scenario_payload["data_revision"],
            "idempotency_key": "state-select-optimistic",
        },
    )
    assert selected.status_code == 200

    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    payload = state.json()
    assert payload["selected_scenario_key"] == "optimistic"
    metrics = {item["metric_key"]: item for item in payload["scenario_metrics"]}
    assert set(metrics) == {
        "mrr",
        "arr",
        "gross_margin",
        "net_burn",
        "runway",
        "cac",
        "ltv",
        "ltv_cac",
        "cac_payback",
    }
    for metric in metrics.values():
        assert set(metric["range"]) == {"conservative", "base", "optimistic"}
        assert all(value is None or isinstance(value, str) for value in metric["range"].values())
        assert metric["formula"]
        assert metric["dependencies"]
        assert metric["period"]
        assert metric["validation_plan"]
        assert metric["what_would_confirm"]


def test_task5_cross_case_thread_and_scenario_ids_do_not_leak(client: TestClient) -> None:
    """Catches accepting foreign ids just because revisions or UUID shapes match."""

    inventory = upload_idea_case(client, "idea_inventory")
    clinic = upload_idea_case(client, "idea_clinic")

    inventory_thread = client.get(f"/api/v1/startup/cases/{inventory}/copilot/thread")
    clinic_state = client.get(f"/api/v1/startup/cases/{clinic}/copilot/state")
    assert inventory_thread.status_code == 200
    assert clinic_state.status_code == 200

    foreign_thread = client.get(
        f"/api/v1/startup/cases/{clinic}/copilot/thread",
        params={"thread_id": inventory_thread.json()["thread_id"]},
    )
    assert foreign_thread.status_code == 404

    scenarios = client.get(f"/api/v1/startup/cases/{inventory}/scenarios")
    assert scenarios.status_code == 200
    foreign_selection = client.post(
        f"/api/v1/startup/cases/{clinic}/scenarios/selection",
        json={
            "scenario_set_id": scenarios.json()["scenario_set_id"],
            "scenario_key": "optimistic",
            "expected_case_revision": clinic_state.json()["data_revision"],
            "idempotency_key": "foreign-scenario",
        },
    )
    assert foreign_selection.status_code == 404


def test_task7_copilot_message_persists_history_and_typed_actions_after_restart(
    client: TestClient,
) -> None:
    """Catches echo-only message handling, non-durable history, and loose action cards."""

    case_id = upload_idea_case(client, "idea_inventory")
    local_path = r"C:\Users\Akana\secret\founder_deck.pdf"
    response = _post_copilot_message(
        client,
        case_id,
        message=(
            "Help me decide the next step, but do not leak this local path "
            f"{local_path} or private MRR notes."
        ),
        idempotency_key="history-actions",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert local_path not in response.text
    assert "founder_deck.pdf" not in response.text
    actions = {action["action"]: action for action in payload["available_actions"]}
    assert set(actions) == {
        "open_fact_input",
        "open_document_upload",
        "prepare_public_research",
        "explain_metric",
        "navigate",
        "prepare_asset",
        "review_improvements",
    }
    assert actions["prepare_public_research"]["status"] == "requires_consent"
    assert actions["prepare_public_research"]["payload"]["available_acquisition_modes"] == [
        "deterministic_offline_fixture"
    ]
    assert actions["prepare_public_research"]["payload"]["unavailable_acquisition_modes"] == [
        "live_public_research"
    ]
    assert (
        actions["prepare_public_research"]["payload"]["default_acquisition_mode"]
        == "deterministic_offline_fixture"
    )
    assert actions["open_fact_input"]["status"] == "requires_input"
    assert actions["prepare_asset"]["status"] == "blocked"
    for action in actions.values():
        assert action["effect_preview"]
        assert isinstance(action["payload"], dict)
        assert action["status"] != "available" or action["handler"]

    get_case_copilot_service.cache_clear()
    thread = client.get(f"/api/v1/startup/cases/{case_id}/copilot/thread")

    assert thread.status_code == 200
    serialized_thread = json.dumps(thread.json(), sort_keys=True)
    assert local_path not in serialized_thread
    assert "founder_deck.pdf" not in serialized_thread
    roles = [message["role"] for message in thread.json()["messages"]]
    assert roles[-2:] == ["user", "assistant"]
    assert payload["message"] == thread.json()["messages"][-1]["content"]


def test_task7_copilot_messages_are_case_specific_without_llm(client: TestClient) -> None:
    """Catches shared fallback advice across different idea-only cases."""

    inventory = upload_idea_case(client, "idea_inventory")
    clinic = upload_idea_case(client, "idea_clinic")

    inventory_response = _post_copilot_message(
        client,
        inventory,
        message="What should I do next?",
        idempotency_key="case-specific",
    )
    clinic_response = _post_copilot_message(
        client,
        clinic,
        message="What should I do next?",
        idempotency_key="case-specific",
    )

    assert inventory_response.status_code == 200
    assert clinic_response.status_code == 200
    assert inventory_response.json()["message"] != clinic_response.json()["message"]
    assert inventory_response.json()["available_actions"] != clinic_response.json()[
        "available_actions"
    ]


def test_task5_state_keeps_fact_coverage_separate_from_scenario_completeness(
    client: TestClient,
) -> None:
    """Catches idea-case state fabricating private actuals to make scenario cards look complete."""

    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")

    assert state.status_code == 200
    payload = state.json()
    assert payload["fact_coverage"] != payload["scenario_completeness"]
    assert payload["fact_coverage"]["measure"] == "evidence-backed"
    assert payload["scenario_completeness"]["measure"] == "planning-model"
    assert all(
        action["status"] in {"available", "blocked", "requires_input", "requires_consent"}
        for action in payload["actions"]
    )
    assert all(
        action["status"] != "available" or action["handler"]
        for action in payload["actions"]
    )
    _assert_no_private_metric_keys(payload)


def test_task5_non_founder_assumptions_are_blocked_without_mutating_revision(
    client: TestClient,
) -> None:
    """Catches relabeling ai_scenario/public_benchmark assumptions as founder facts."""

    case_id = upload_idea_case(client, "idea_inventory")
    before = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert before.status_code == 200

    for provenance in ("ai_scenario", "public_benchmark"):
        response = client.post(
            f"/api/v1/startup/cases/{case_id}/assumptions",
            json={
                "requirement_key": "monthly_price",
                "value": {
                    "kind": "money",
                    "amount": "35000",
                    "scale": "ones",
                    "currency": "KZT",
                },
                "source": {
                    "kind": provenance,
                    "declared_source": "Planning context",
                },
                "rationale": "Planning-only assumption.",
                "validation_plan": "Replace with founder statement or source fact.",
                "expected_case_revision": before.json()["data_revision"],
                "idempotency_key": f"blocked-{provenance}",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "blocked"
        assert payload["provenance"] == provenance
        assert payload["reason"]
        assert payload["old_revision"] == before.json()["data_revision"]
        assert payload["new_revision"] == before.json()["data_revision"]

    after = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert after.status_code == 200
    assert after.json()["data_revision"] == before.json()["data_revision"]


def test_task5_founder_money_assumption_preserves_period_plan_and_replay_after_restart(
    client: TestClient,
) -> None:
    """Catches dropping founder metadata or promoting accepted assumptions to source_fact."""

    case_id = upload_idea_case(client, "idea_inventory")
    before = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert before.status_code == 200
    original_revision = before.json()["data_revision"]
    payload = {
        "requirement_key": "monthly_recurring_revenue",
        "value": {
            "kind": "money",
            "amount": "1850000",
            "scale": "ones",
            "currency": "KZT",
        },
        "period": {"kind": "month", "value": "2026-07"},
        "source": {
            "kind": "founder_statement",
            "declared_source": "Founder interview on 2026-08-22",
        },
        "rationale": "Founder stated July 2026 recognized MRR excludes unpaid pilots.",
        "validation_plan": "Verify against bank deposits and invoice register before source_fact upgrade.",
        "expected_case_revision": original_revision,
        "idempotency_key": "founder-mrr-assumption-with-plan",
    }

    accepted = client.post(f"/api/v1/startup/cases/{case_id}/assumptions", json=payload)

    assert accepted.status_code == 200
    accepted_payload = accepted.json()
    assert accepted_payload["status"] == "accepted"
    assert accepted_payload["provenance"] == "founder_statement"
    assert accepted_payload["accepted_input"]["kind"] == "founder_statement"
    assert accepted_payload["accepted_input"]["status"] == "accepted"
    assert accepted_payload["accepted_input"]["field_key"] == "mrr"
    assert accepted_payload["accepted_input"]["value"] == "1850000; scale=ones; currency=KZT; period=2026-07"
    assert accepted_payload["accepted_input"]["period"] == "2026-07"
    assert accepted_payload["accepted_input"]["declared_source"] == "Founder interview on 2026-08-22"
    assert accepted_payload["accepted_input"]["rationale"] == payload["rationale"]
    assert accepted_payload["accepted_input"]["validation_plan"] == payload["validation_plan"]
    assert accepted_payload["accepted_input"]["source_refs"]

    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    state_payload = state.json()
    assert not any(
        fact["source_type"] == "source_fact" and "1850000" in fact["value"]
        for fact in state_payload["extracted_facts"]
    )
    accepted_rows = [
        row for row in state_payload["accepted_inputs"] if row["field_key"] == "mrr"
    ]
    assert accepted_rows
    assert accepted_rows[-1]["kind"] == "founder_statement"
    assert accepted_rows[-1]["validation_plan"] == payload["validation_plan"]

    scenarios = client.get(f"/api/v1/startup/cases/{case_id}/scenarios")
    assert scenarios.status_code == 200
    mrr_input = scenarios.json()["scenarios"]["base"]["inputs"]["monthly_revenue"]
    assert mrr_input["provenance"] == "founder_statement"
    assert mrr_input["period"] == "2026-07"
    assert mrr_input["rationale"] == payload["rationale"]
    assert mrr_input["validation_plan"] == payload["validation_plan"]

    get_case_copilot_service.cache_clear()
    replay = client.post(f"/api/v1/startup/cases/{case_id}/assumptions", json=payload)

    assert replay.status_code == 200
    assert replay.json() == accepted_payload

    conflict = client.post(
        f"/api/v1/startup/cases/{case_id}/assumptions",
        json={**payload, "validation_plan": "Different validation plan."},
    )
    assert conflict.status_code == 409


def test_task6_unconfigured_public_research_job_is_truthfully_deferred_not_fake_success(
    client: TestClient,
) -> None:
    """Catches synthesizing provider success when no public research provider is configured."""

    case_id = upload_idea_case(
        client,
        "idea_inventory",
        fixture_mode="live",
        auto_start=True,
    )
    revision = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state").json()[
        "data_revision"
    ]

    plan_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/plans",
        json={
            "focus": "public_pricing_analogs",
            "intent": "Prepare public pricing-analog research.",
            "expected_case_revision": revision,
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()
    assert plan["status"] == "prepared"
    assert plan["plan_id"]
    assert plan["plan_hash"]

    job_response = client.post(
        f"/api/v1/startup/cases/{case_id}/research/jobs",
        json={
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "expected_case_revision": revision,
            "idempotency_key": "unconfigured-public-research",
            "consent_public_research": True,
            "acquisition_mode": "live_public_research",
        },
    )
    assert job_response.status_code == 202
    assert job_response.json()["status"] == "deferred"
    assert job_response.json()["reason"] == "provider_unconfigured"
    assert job_response.json()["requested_acquisition_mode"] == "live_public_research"
    assert job_response.json()["selected_acquisition_mode"] == "provider_unconfigured"
    assert job_response.json()["accepted_entries"] == []
    assert job_response.json()["source_refs"] == []


def test_task5_novel_sector_like_briefs_do_not_inherit_fixture_literals(
    client: TestClient,
) -> None:
    """Catches clinic/retail branch literals leaking into unrelated same-sector briefs."""

    case_id = upload_custom_idea_case(
        client,
        company_name="MediQueue Shift",
        brief=(
            "Founder idea brief: MediQueue Shift\n\n"
            "Concept:\n"
            "MediQueue Shift is a shift handoff tool for dental practices that "
            "lose treatment-plan context between reception, hygienists, and dentists.\n\n"
            "Buyer:\n"
            "Practice owners and operations leads who need fewer missed follow-ups.\n\n"
            "User:\n"
            "Reception teams and hygienists who coordinate patient callbacks.\n\n"
            "Geography:\n"
            "Initial launch is planned for dental groups in Romania and Bulgaria.\n\n"
            "Pricing hypothesis:\n"
            "The founder is testing whether practices prefer a monthly clinic-seat "
            "package or a per-location setup fee.\n\n"
            "Launch constraints:\n"
            "The product cannot launch until dental consent scripts and staff "
            "handoff workflow are reviewed with local advisors."
        ),
    )

    response = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")

    assert response.status_code == 200
    facts = response.json()["extracted_facts"]
    serialized = json.dumps(facts, sort_keys=True)
    normalized = serialized.casefold()
    assert "MediQueue Shift" in serialized
    assert "dental practices" in normalized
    assert "Practice owners and operations leads" in serialized
    assert "Romania and Bulgaria" in serialized
    assert "Outpatient clinics" not in serialized
    assert "Clinic administrators and medical directors" not in serialized
    assert "Patient-consent language, clinic staff workflow" not in serialized


def test_task5_routes_have_strict_response_models(client: TestClient) -> None:
    """Catches untyped dict responses or response_model=None on Task 5 routes."""

    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    task5_routes = {
        ("get", "/api/v1/startup/cases/{case_id}/copilot/state"),
        ("get", "/api/v1/startup/cases/{case_id}/copilot/thread"),
        ("post", "/api/v1/startup/cases/{case_id}/copilot/messages"),
        ("post", "/api/v1/startup/cases/{case_id}/facts"),
        ("post", "/api/v1/startup/cases/{case_id}/assumptions"),
        ("get", "/api/v1/startup/cases/{case_id}/scenarios"),
        ("post", "/api/v1/startup/cases/{case_id}/scenarios/selection"),
    }
    for method, path in task5_routes:
        schema = paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]
        assert "$ref" in schema or schema.get("properties")
        assert schema.get("additionalProperties") is not True


def test_task10_case_assets_generate_list_get_and_content_without_evidence_promotion(
    client: TestClient,
) -> None:
    case_id = upload_idea_case(client, "idea_inventory")
    other_case_id = upload_idea_case(client, "idea_clinic")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200

    generated = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": state.json()["data_revision"],
            "idempotency_key": "launch-pack-1",
        },
    )

    assert generated.status_code == 201
    payload = generated.json()
    assert payload["case_id"] == case_id
    assert payload["data_revision"] == state.json()["data_revision"]
    assert payload["selected_scenario_key"] == "base"
    assert payload["asset_key"] == "gtm_launch_pack"
    assert payload["asset_revision"] == 1
    assert payload["status"] == "draft"
    assert payload["csv_url"] is None
    assert payload["markdown_url"].startswith(f"/api/startup/cases/{case_id}/assets/")
    assert "## Three-scenario unit economics" in payload["body_markdown"]
    assert "provenance=ai_scenario" in payload["body_markdown"]
    assert "provenance=source_fact" not in payload["body_markdown"]

    replay = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": state.json()["data_revision"],
            "idempotency_key": "launch-pack-1",
        },
    )
    assert replay.status_code == 201
    assert replay.json() == payload

    listed = client.get(f"/api/v1/startup/cases/{case_id}/assets")
    assert listed.status_code == 200
    assert listed.json()["data_revision"] == state.json()["data_revision"]
    assert [item["asset_id"] for item in listed.json()["assets"]] == [payload["asset_id"]]

    fetched = client.get(f"/api/v1/startup/cases/{case_id}/assets/{payload['asset_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == payload

    markdown = client.get(f"/api/v1/startup/cases/{case_id}/assets/{payload['asset_id']}/markdown")
    appendix = client.get(f"/api/v1/startup/cases/{case_id}/assets/{payload['asset_id']}/provenance")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "attachment" in markdown.headers["content-disposition"]
    assert ".md" in markdown.headers["content-disposition"]
    assert markdown.text == payload["body_markdown"]
    assert appendix.status_code == 200
    assert appendix.headers["content-type"].startswith("text/markdown")
    assert "attachment" in appendix.headers["content-disposition"]
    assert ".md" in appendix.headers["content-disposition"]
    assert "status=draft" in appendix.text
    assert "source_fact" not in appendix.text

    blank_key = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": state.json()["data_revision"],
            "idempotency_key": "   ",
        },
    )
    assert blank_key.status_code == 422
    assert blank_key.json()["code"] == "request_validation_error"

    stale = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": state.json()["data_revision"] + 1,
            "idempotency_key": "launch-pack-stale",
        },
    )
    assert stale.status_code == 409

    foreign = client.get(f"/api/v1/startup/cases/{other_case_id}/assets/{payload['asset_id']}")
    assert foreign.status_code == 404


def test_task10_weekly_funnel_csv_download_headers(client: TestClient) -> None:
    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200

    generated = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "weekly_funnel_template",
            "selected_scenario_key": "base",
            "expected_case_revision": state.json()["data_revision"],
            "idempotency_key": "weekly-funnel-csv",
        },
    )
    assert generated.status_code == 201
    payload = generated.json()
    assert payload["csv_url"].endswith("/csv")

    csv_response = client.get(f"/api/v1/startup/cases/{case_id}/assets/{payload['asset_id']}/csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_response.headers["content-disposition"]
    assert ".csv" in csv_response.headers["content-disposition"]
    assert csv_response.text.startswith("week_start,visitors,signups,qualified_conversations")


def test_task10_asset_generation_rejects_non_string_idempotency_key(
    client: TestClient,
) -> None:
    case_id = upload_idea_case(client, "idea_inventory")
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200

    response = client.post(
        f"/api/v1/startup/cases/{case_id}/assets",
        json={
            "asset_type": "gtm_launch_pack",
            "selected_scenario_key": "base",
            "expected_case_revision": state.json()["data_revision"],
            "idempotency_key": 123,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


def test_task5_private_metric_guard_rejects_missing_status_with_actual_value() -> None:
    """Catches the Task 0 helper loophole where missing metadata hid a real value."""

    with pytest.raises(
        pytest.fail.Exception,
        match="idea-only response exposed private actual metric",
    ):
        _assert_no_private_metric_keys(
            {
                "field_key": "mrr",
                "status": "missing",
                "value": 1000,
                "metadata": {"source_type": "ai_scenario"},
            }
        )


def upload_idea_case(
    client: TestClient,
    case_name: str,
    *,
    fixture_mode: str = "deterministic_offline",
    auto_start: bool = False,
) -> str:
    fixture = FIXTURE_ROOT / "cases" / case_name / "brief.txt"
    assert fixture.is_file(), fixture
    fixture_text = fixture.read_text(encoding="utf-8")
    _assert_no_private_operating_metrics(fixture_text)
    expected_case = _expected_contracts()["cases"][case_name]

    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": fixture_mode, "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    _assert_no_private_operating_metrics(created.text)

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={
            "auto_start": "true" if auto_start else "false",
            "company_name": expected_case["company_name"],
        },
        files=[("files", ("brief.txt", fixture.read_bytes(), "text/plain"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["analysis_status"] == (
        "gate2_preview_ready" if auto_start else "awaiting_start"
    )
    assert uploaded.json()["auto_start_triggered"] is auto_start
    _assert_no_private_operating_metrics(uploaded.text)
    return cast(str, case_id)


def _post_copilot_message(
    client: TestClient,
    case_id: str,
    *,
    message: str,
    idempotency_key: str,
    page_context: str = "overview",
    current_section: str = "question",
    focus_key: str | None = None,
) -> Any:
    state = client.get(f"/api/v1/startup/cases/{case_id}/copilot/state")
    assert state.status_code == 200
    payload: dict[str, Any] = {
        "message": message,
        "page_context": page_context,
        "current_section": current_section,
        "expected_case_revision": state.json()["data_revision"],
        "idempotency_key": idempotency_key,
    }
    if focus_key is not None:
        payload["focus_key"] = focus_key
    return client.post(
        f"/api/v1/startup/cases/{case_id}/copilot/messages",
        json=payload,
    )


def upload_custom_idea_case(
    client: TestClient,
    *,
    company_name: str,
    brief: str,
) -> str:
    _assert_no_private_operating_metrics(brief)
    created = client.post(
        "/api/v1/startup/cases",
        json={"fixture_mode": "deterministic_offline", "auto_start": False},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    uploaded = client.post(
        f"/api/v1/startup/cases/{case_id}/documents",
        data={"auto_start": "false", "company_name": company_name},
        files=[("files", ("brief.txt", brief.encode("utf-8"), "text/plain"))],
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["analysis_status"] == "awaiting_start"
    return cast(str, case_id)


def _expected_contracts() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((FIXTURE_ROOT / "expected_contracts.json").read_text(encoding="utf-8")),
    )


def _assert_no_private_operating_metrics(payload: str) -> None:
    forbidden = (
        "MRR 1000",
        "ARR 12000",
        "monthly burn 500",
        "cash balance 10000",
        "customer count 25",
        "recognized MRR",
        "annual recurring revenue",
        "monthly recurring revenue is",
        "net burn is",
    )
    normalized = payload.casefold()
    for value in forbidden:
        assert value.casefold() not in normalized


def _assert_no_private_metric_keys(payload: object) -> None:
    forbidden_metric_identifiers = {
        "mrr",
        "monthly_recurring_revenue",
        "arr",
        "annual_recurring_revenue",
        "actual_revenue",
        "recognized_revenue",
        "revenue_actual",
        "burn",
        "net_burn",
        "monthly_burn",
        "monthly_net_burn",
        "cash",
        "cash_balance",
        "cash_on_hand",
        "customer_count",
        "factual_customer_count",
        "active_customer_count",
        "paying_customer_count",
    }
    identifier_keys = {
        "fact_key",
        "field_key",
        "metric_key",
        "metric_id",
        "field_id",
        "fact_id",
        "field_name",
        "metric_name",
        "fact_name",
        "requested_metric_key",
        "key",
        "name",
    }

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = _normalize_private_metric_identifier(key)
                if normalized_key in forbidden_metric_identifiers and _is_actual_metric_payload(
                    child
                ):
                    pytest.fail(
                        "idea-only response exposed private actual metric "
                        f"direct key: {key}"
                    )
                if (
                    normalized_key in identifier_keys
                    and _normalize_private_metric_identifier(child)
                    in forbidden_metric_identifiers
                    and _is_actual_metric_payload(value)
                ):
                    pytest.fail(
                        "idea-only response exposed private actual metric "
                        f"identifier: {key}={child}"
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)


def _normalize_private_metric_identifier(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().casefold())
    return normalized.strip("_")


def _is_actual_metric_payload(value: object) -> bool:
    if isinstance(value, dict):
        if _is_allowed_private_metric_metadata(value):
            return False
        actual_value_keys = {
            "value",
            "actual_value",
            "amount",
            "numeric_value",
            "current_value",
            "confirmed_value",
            "reported_value",
        }
        if any(key in value and value[key] is not None for key in actual_value_keys):
            return True
        source_kind = _normalize_private_metric_identifier(
            value.get("source_type", value.get("kind", ""))
        )
        if source_kind in {
            "source_fact",
            "founder_statement",
            "deterministic_calculation",
        }:
            return True
        status = _normalize_private_metric_identifier(value.get("status", ""))
        return status in {"confirmed", "actual", "observed", "calculated", "source_fact"}
    return value is not None


def _is_allowed_private_metric_metadata(value: dict[str, Any]) -> bool:
    actual_value_keys = {
        "value",
        "actual_value",
        "amount",
        "numeric_value",
        "current_value",
        "confirmed_value",
        "reported_value",
    }
    has_actual_value = any(key in value and value[key] is not None for key in actual_value_keys)
    source_kind = _normalize_private_metric_identifier(
        value.get("source_type", value.get("kind", ""))
    )
    if source_kind in {
        "ai_scenario",
        "founder_statement",
        "public_benchmark",
        "deterministic_calculation",
    } and not has_actual_value:
        return True

    status = _normalize_private_metric_identifier(value.get("status", ""))
    gap_type = _normalize_private_metric_identifier(value.get("gap_type", ""))
    allowed_action = _normalize_private_metric_identifier(value.get("allowed_action", ""))
    if (status == "missing" or gap_type.startswith("missing")) and not has_actual_value:
        return True
    return (
        allowed_action in {"manual_fact_intake", "request_founder_input"}
        and not has_actual_value
    )


def _assert_scenario_metrics_contract(
    state: dict[str, Any],
    expected_case: dict[str, Any],
) -> None:
    assert expected_case["scenario_metrics"]
    required_fields = set(_expected_contracts()["scenario_contract"]["required_metric_fields"])
    metrics = {metric["metric_key"]: metric for metric in state["scenario_metrics"]}
    assert set(metrics) == {
        "mrr",
        "arr",
        "gross_margin",
        "net_burn",
        "runway",
        "cac",
        "ltv",
        "ltv_cac",
        "cac_payback",
    }
    for metric in state["scenario_metrics"]:
        assert set(metric) == required_fields
        assert metric["source_type"] in {
            "ai_scenario",
            "founder_statement",
            "public_benchmark",
            "deterministic_calculation",
        }
        assert metric["value"] is None
        assert set(metric["range"]) == {"conservative", "base", "optimistic"}
        assert all(value is None or isinstance(value, str) for value in metric["range"].values())
        assert metric["formula"]
        assert metric["dependencies"]
        assert metric["unit"]
        assert metric["period"]
        assert metric["confidence"] in {"low", "medium", "high"}
        assert isinstance(metric["source_refs"], list)
        assert metric["what_would_confirm"]
        assert metric["validation_plan"]


class RecordingPublicResearchPlanner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        return {"status": "prepared", "sources": []}


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


class _RecordingLiveResearchPort:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def collect(self, plan: Any) -> Any:
        self.calls.append(
            {
                "case_id": str(plan.case_id),
                "queries": tuple(plan.queries),
            }
        )
        return _SnapshotWithPublicSource(plan.case_id)


class _SnapshotWithPublicSource:
    def __init__(self, case_id: Any) -> None:
        from due_diligence_agent.domain.startup.market import StartupPublicBenchmarkCandidate

        source_id = uuid4()
        self.case_id = case_id
        self.sources = (
            _PublicSource(
                source_id=source_id,
                source_url="https://example.com/public-benchmark",
            ),
        )
        self.public_benchmark_candidates = (
            StartupPublicBenchmarkCandidate(
                input_key="arpa",
                source_url="https://example.com/public-benchmark",
                publisher="Example Research",
                publication_date="2026-08-01",
                retrieval_date="2026-08-22",
                as_of="2026-08-01",
                source_class="industry_report",
                confidence="medium",
                range_low="18500",
                range_high="32500",
                unit="KZT",
                period="month",
                formula="reported public KZT ARPA benchmark range",
                dependencies=("public comparable companies",),
                validation_plan="Use only as external context until case evidence confirms fit.",
                source_ref=source_id,
                rationale="Cited public range for comparable SaaS ARPA.",
            ),
        )


class _PublicSource:
    def __init__(self, *, source_id: Any, source_url: str) -> None:
        self.source_id = source_id
        self.source_url = source_url


class _AcceptedBenchmarkProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def collect(self, plan: Any) -> list[dict[str, Any]]:
        source_ref = uuid4()
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
                "url": "https://example.com/public-benchmark",
                "publisher": "Example Research",
                "publication_date": "2026-08-01",
                "retrieval_date": "2026-08-22",
                "as_of": "2026-08-01",
                "source_class": "industry_report",
                "confidence": "medium",
                "range_low": "1000",
                "range_high": "2000",
                "unit": "KZT",
                "period": "month",
                "formula": "public benchmark range",
                "dependencies": ("public comparable companies",),
                "validation_plan": (
                    "Use only as external context until founder-specific evidence exists."
                ),
                "source_refs": (source_ref,),
                "rationale": "Cited public benchmark for comparable acquisition spend.",
            }
        ]


class _LiveSnapshotOnlyProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def collect(self, plan: Any) -> Any:
        self.calls.append(
            {
                "case_id": str(plan.case_id),
                "plan_hash": plan.plan_hash,
                "queries": tuple(plan.query_previews),
            }
        )
        return _LiveSnapshotOnlyResult(plan.case_id, plan.data_revision)


class _LiveSnapshotOnlyResult:
    def __init__(self, case_id: UUID, revision: int) -> None:
        from datetime import UTC, datetime

        from due_diligence_agent.domain.startup.market import (
            StartupMarketResearchSnapshot,
            StartupResearchSource,
            StartupResearchSourceMode,
            StartupResearchSourceStatus,
        )

        source_id = uuid4()
        retrieved_at = datetime(2026, 8, 22, tzinfo=UTC)
        self.market_snapshot = StartupMarketResearchSnapshot.build(
            case_id=case_id,
            as_of=retrieved_at,
            source_mode=StartupResearchSourceMode.LIVE,
            research_id=uuid4(),
            competitors=(),
            sources=(
                StartupResearchSource(
                    source_id=source_id,
                    source_mode=StartupResearchSourceMode.LIVE,
                    source_hash="sha256:" + ("1" * 64),
                    source_url="https://example.com/live-market-context",
                    source_label="Example Live Research",
                    as_of=retrieved_at.date(),
                    retrieved_at=retrieved_at,
                    query="smart university public market",
                    provenance="public_benchmark",
                    confidence="0.6",
                    supports_primary_financial_metrics=False,
                    status=StartupResearchSourceStatus.INFERENCE,
                ),
            ),
            sentiment_signals=(),
            assumptions=(),
            sizing=None,
            labels=("live_public_research",),
            data_revision=revision,
            public_benchmark_candidates=(),
        )


class _InMemoryWorkflowStore:
    def __init__(self, runtime: dict[str, Any]) -> None:
        self._runtime = dict(runtime)

    def load(self, _case_id: str) -> dict[str, Any]:
        return dict(self._runtime)

    def save(self, _case_id: str, update: dict[str, Any]) -> None:
        self._runtime.update(update)

    def update(self, _case_id: str, update: Any) -> None:
        self._runtime.update(update(dict(self._runtime)))


class _SingleStartupProfileRepository:
    def __init__(self, profile: Any) -> None:
        self._profile = profile

    def get(self, profile_id: UUID) -> Any:
        if profile_id != self._profile.profile_id:
            raise KeyError(profile_id)
        return self._profile

    def get_current(self, case_id: UUID) -> Any:
        if case_id != self._profile.case_id:
            raise KeyError(case_id)
        return self._profile


class _ExplodingStartupResearchPort:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def collect(self, plan: Any) -> Any:
        self.calls.append(plan)
        raise AssertionError("frozen startup research port should not be called")


def _market_adapter_profile(*, data_revision: int) -> Any:
    from datetime import UTC, datetime

    from due_diligence_agent.domain.startup.profile import (
        StartupProfile,
        StartupProfileAnalysisStage,
        StartupProfileField,
        StartupProfileFieldName,
        StartupProfileFieldStatus,
    )

    fields = {
        field_name.value: StartupProfileField(
            name=field_name,
            status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
            values=(),
            confidence="0",
            evidence_refs=(),
            dependency_refs=(),
            reason_code=None,
            contradiction_ids=(),
        )
        for field_name in StartupProfileFieldName
    }
    return StartupProfile.build(
        case_id=uuid4(),
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="test-profile@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes={"brief": "sha256:" + "a" * 64},
        parse_outcomes={"brief": "parsed"},
        fields=fields,
        gap_codes=("market_size_missing",),
        contradiction_ids=(),
        case_revision_at=datetime(2026, 8, 22, tzinfo=UTC),
    )

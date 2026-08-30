from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps as json_dumps
from json import loads as json_loads
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.adapters.local_storage.case_copilot_repositories import (
    LocalCaseCopilotThreadRepository,
)
from due_diligence_agent.application.case_copilot_contracts import (
    PostCopilotMessageRequest,
    QueueResearchJobRequest,
    ResearchJobResponse,
    SaveAssumptionRequest,
    SaveFounderFactRequest,
)
from due_diligence_agent.application.services.case_copilot_service import (
    CaseCopilotService,
    _FactValidationFailure,
    _profile_projection_matches_revision,
)
from due_diligence_agent.application.services.case_fact_intake_service import (
    CaseMutationDelta,
)
from due_diligence_agent.application.services.case_question_service import (
    CaseQuestionService,
)
from due_diligence_agent.application.startup_cases import StartupGateConflict
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, CaseStatus, SensitivityClass
from due_diligence_agent.domain.startup.case_intake import CaseValueKind, FounderStatement
from due_diligence_agent.domain.startup.market import (
    MarketSizingAssumption,
    MarketSizingEstimate,
    StartupCompetitor,
    StartupCompetitorCategory,
    StartupMarketResearchSnapshot,
    StartupMarketSizing,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.scenario import ScenarioInput, ScenarioRange

CASE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CASE_B_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CASE_C_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


@pytest.fixture
def workspace_tmp_path() -> Iterator[Path]:
    root = Path("tmp") / "task7_case_copilot_service"
    path = root / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        if resolved_path.parent != resolved_root:
            raise RuntimeError(f"refusing to clean unexpected test path: {resolved_path}")
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def test_post_message_persists_sanitized_turn_and_restores_from_repository(
    workspace_tmp_path: Path,
) -> None:
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda _case_id: 1,
    )
    service = _service(workspace_tmp_path, threads=threads)

    response = service.post_message(
        CASE_ID,
        PostCopilotMessageRequest(
            message=r"Use C:\Users\Akana\secret\deck.pdf but do not leak it.",
            page_context="overview",
            current_section="question",
            expected_case_revision=1,
            idempotency_key="turn-legacy",
        ),
    )

    assert response.status == "accepted"
    assert {action.action for action in response.available_actions} == {
        "open_fact_input",
        "open_document_upload",
        "prepare_public_research",
        "explain_metric",
        "navigate",
        "prepare_asset",
        "review_improvements",
    }

    restored_service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 1,
        ),
    )
    thread = restored_service.thread(CASE_ID)
    serialized = thread.model_dump_json()

    assert [message.role for message in thread.messages][-2:] == ["user", "assistant"]
    assert response.message == thread.messages[-1].content
    assert "C:\\Users\\Akana" not in serialized
    assert "deck.pdf" not in serialized


def test_state_uses_one_structured_question_descriptor_for_visible_question_and_fact_action(
    workspace_tmp_path: Path,
) -> None:
    """Catches selecting next_question copy separately from open_fact_input."""

    case_repository = _CaseRepository({CASE_ID: 1})
    profile_repository = _QuestionProfileRepository(stage="first sales")
    assumptions = _FieldStatementsRepository(
        {
            "problem": "Inventory planning is painful.",
            "solution": "AI replenishment planner.",
            "icp": "Pharmacy chains.",
            "buyer": "Operations directors.",
            "purchase_trigger": "Stock-out risk.",
            "pricing_revenue_model": "Monthly subscription.",
            "monthly_price": "35000 KZT/month.",
            "launch_date": "Q1 2027.",
            "team_capacity": "2 founders.",
            "available_budget": "5000000 KZT.",
            "channel": "Direct sales.",
            "funnel": "Founder-led outbound.",
            "revenue": "unknown",
        }
    )
    question_service = CaseQuestionService(
        case_repository=case_repository,
        profile_repository=profile_repository,
        assumption_repository=assumptions,
        contradiction_repository=_NoContradictionsRepository(),
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 1,
        ),
        case_repository=case_repository,
        profile_repository=profile_repository,
        assumption_repository=assumptions,
        question_service=question_service,
    )

    state = service.state(CASE_ID)

    descriptor = state.question_descriptor
    assert descriptor is not None
    assert state.next_question == descriptor.question
    assert descriptor.field_key == "mrr"
    assert descriptor.input_schema.kind == "money"
    assert [field.field_key for field in descriptor.input_schema.fields] == [
        "amount",
        "scale",
        "currency",
        "period",
        "declared_source",
        "rationale",
        "validation_plan",
    ]
    assert descriptor.label
    assert descriptor.description
    assert descriptor.why_needed
    assert descriptor.unlocks
    assert descriptor.example
    assert descriptor.validation_guidance
    fact_action = next(action for action in state.actions if action.action == "open_fact_input")
    assert fact_action.payload == {
        "field_key": "mrr",
        "provenance": "founder_statement",
    }


def test_task7_post_message_uses_case_specific_bounded_context_and_deterministic_fallback(
    workspace_tmp_path: Path,
) -> None:
    inventory_brief = (
        "Founder idea brief: Inventory Pilot\n"
        "Concept: AI replenishment planner for Central Asian pharmacy groups.\n"
        "Buyer: Operations directors at regional pharmacy chains.\n"
        "User: Store managers who reconcile stock-outs.\n"
        "Geography: planned for Kazakhstan.\n"
        "Pricing hypothesis: paid monthly subscription after pilot.\n"
        "Launch window: Q1 2027 pilot.\n"
        r"Internal path: C:\Users\Akana\secret\inventory-plan.pdf."
    )
    clinic_brief = (
        "Founder idea brief: Clinic Follow-up\n"
        "Concept: WhatsApp follow-up workflow for dental clinics.\n"
        "Buyer: Clinic owners who need repeat visits.\n"
        "User: Reception staff coordinating follow-up.\n"
        "Geography: planned for UAE clinics.\n"
        "Pricing hypothesis: per-location service fee.\n"
        "Launch constraints: nurse staff workflow must be reviewed.\n"
    )
    (workspace_tmp_path / str(CASE_ID)).mkdir()
    (workspace_tmp_path / str(CASE_B_ID)).mkdir()
    (workspace_tmp_path / str(CASE_ID) / "inventory.txt").write_text(inventory_brief, encoding="utf-8")
    (workspace_tmp_path / str(CASE_B_ID) / "clinic.txt").write_text(clinic_brief, encoding="utf-8")
    runtimes = {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 3,
                "company_name": "Inventory Pilot",
                "documents": [
                    {
                        "private_name": "inventory.txt",
                        "declared_mime_type": "text/plain",
                    }
                ],
            },
            CASE_B_ID: {
                "case_exists": True,
                "data_revision": 5,
                "company_name": "Clinic Follow-up",
                "documents": [
                    {
                        "private_name": "clinic.txt",
                        "declared_mime_type": "text/plain",
                    }
                ],
            },
    }
    revisions = {CASE_ID: 3, CASE_B_ID: 5}
    workflow_store = _WorkflowStore(runtimes)
    question_service = _QuestionService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: revisions[case_id],
    )
    service = _service(
        workspace_tmp_path,
        workflow_store=workflow_store,
        case_repository=_CaseRepository(
            revisions,
            names={CASE_ID: "Inventory Pilot", CASE_B_ID: "Clinic Follow-up"},
        ),
        threads=threads,
        question_service=question_service,
        research_service=_ResearchService(),
    )

    inventory = service.post_message(
        CASE_ID,
        PostCopilotMessageRequest(
            message=(
                r"Use C:\Users\Akana\private\raw.txt and research_private_mrr; "
                "send_email; I need market advice."
            ),
            page_context="market",
            current_section="benchmarks",
            expected_case_revision=3,
            focus_key="public_pricing_analogs",
            idempotency_key="turn-1",
        ),
    )
    clinic = service.post_message(
        CASE_B_ID,
        PostCopilotMessageRequest(
            message="Which assumption should the clinic validate first?",
            page_context="overview",
            current_section="question",
            expected_case_revision=5,
            idempotency_key="turn-1",
        ),
    )

    assert inventory.case_id == CASE_ID
    assert inventory.data_revision == 3
    assert inventory.page_context == "market"
    assert inventory.current_section == "benchmarks"
    assert "Inventory Pilot" in inventory.message
    assert "pharmacy" in inventory.message
    assert "Clinic Follow-up" in clinic.message
    assert inventory.message != clinic.message
    assert question_service.calls == [
        (CASE_ID, "market", "public_pricing_analogs"),
        (CASE_B_ID, "overview", None),
    ]
    assert {action.action for action in inventory.available_actions} == {
        "open_fact_input",
        "open_document_upload",
        "prepare_public_research",
        "explain_metric",
        "navigate",
        "prepare_asset",
        "review_improvements",
    }
    research_action = next(
        action for action in inventory.available_actions if action.action == "prepare_public_research"
    )
    assert research_action.payload["focus"] == "public_pricing_analogs"
    assert research_action.payload["available_acquisition_modes"] == (
        "deterministic_offline_fixture",
    )
    assert research_action.payload["unavailable_acquisition_modes"] == (
        "live_public_research",
    )
    assert research_action.payload["default_acquisition_mode"] == "deterministic_offline_fixture"
    assert "mrr" not in str(research_action.payload).casefold()
    assert all(action.action not in {"send_email", "research_private_mrr"} for action in inventory.available_actions)

    runtimes[CASE_ID]["data_revision"] = 4
    revisions[CASE_ID] = 4
    replay = service.post_message(
        CASE_ID,
        PostCopilotMessageRequest(
            message=(
                r"Use C:\Users\Akana\private\raw.txt and research_private_mrr; "
                "send_email; I need market advice."
            ),
            page_context="market",
            current_section="benchmarks",
            expected_case_revision=3,
            focus_key="public_pricing_analogs",
            idempotency_key="turn-1",
        ),
    )
    assert replay == inventory

    with pytest.raises(StartupGateConflict):
        service.post_message(
            CASE_ID,
            PostCopilotMessageRequest(
                message="A different draft must conflict because the idempotency key was already used.",
                page_context="market",
                current_section="benchmarks",
                expected_case_revision=3,
                focus_key="public_pricing_analogs",
                idempotency_key="turn-1",
            ),
        )

    with pytest.raises(StartupGateConflict):
        service.post_message(
            CASE_ID,
            PostCopilotMessageRequest(
                message=(
                    r"Use C:\Users\Akana\private\raw.txt and research_private_mrr; "
                    "send_email; I need market advice."
                ),
                page_context="market",
                current_section="benchmarks",
                expected_case_revision=3,
                focus_key="public_pricing_analogs",
                idempotency_key="turn-stale-new-key",
            ),
        )

    same_text_new_key = service.post_message(
        CASE_ID,
        PostCopilotMessageRequest(
            message=(
                r"Use C:\Users\Akana\private\raw.txt and research_private_mrr; "
                "send_email; I need market advice."
            ),
            page_context="market",
            current_section="benchmarks",
            expected_case_revision=4,
            focus_key="public_pricing_analogs",
            idempotency_key="turn-2",
        ),
    )
    assert same_text_new_key.message == inventory.message

    thread = service.thread(CASE_ID)
    serialized = thread.model_dump_json()
    assert [message.role for message in thread.messages] == [
        "system_event",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert len({message.message_id for message in thread.messages}) == len(thread.messages)
    assert thread.messages[-2].page_context == "market"
    assert thread.messages[-2].current_section == "benchmarks"
    assert thread.messages[-2].related_evidence_refs == ()
    assert set(thread.messages[2].action_refs) == {action.action_id for action in inventory.available_actions}
    assert set(thread.messages[-1].action_refs) == {
        action.action_id for action in same_text_new_key.available_actions
    }
    assert r"C:\Users\Akana" not in serialized
    assert "inventory-plan.pdf" not in serialized
    assert "raw.txt" not in serialized

    before_stale = service.thread(CASE_ID)
    with pytest.raises(StartupGateConflict):
        service.post_message(
            CASE_ID,
            PostCopilotMessageRequest(
                message="This stale turn must not append.",
                page_context="market",
                current_section="benchmarks",
                expected_case_revision=3,
                idempotency_key="turn-stale",
            ),
        )
    after_stale = service.thread(CASE_ID)
    assert after_stale.messages == before_stale.messages


def test_uploaded_brief_projection_rejects_private_name_path_traversal(
    workspace_tmp_path: Path,
) -> None:
    outside = workspace_tmp_path / "outside.txt"
    outside.write_text(
        "Founder idea brief: Leaked Startup\nConcept: private outside case data.",
        encoding="utf-8",
    )
    (workspace_tmp_path / str(CASE_C_ID)).mkdir()
    service = _service(
        workspace_tmp_path,
        workflow_store=_WorkflowStore(
            {
                CASE_C_ID: {
                    "case_exists": True,
                    "data_revision": 1,
                    "company_name": "Traversal Guard",
                    "documents": [
                        {
                            "private_name": "../outside.txt",
                            "declared_mime_type": "text/plain",
                        }
                    ],
                }
            }
        ),
        case_repository=_CaseRepository({CASE_C_ID: 1}, names={CASE_C_ID: "Traversal Guard"}),
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 1,
        ),
    )

    projection = service._same_case_projection(service._ensure_case(CASE_C_ID))

    assert all(fact.value != "Leaked Startup" for fact in projection.facts)
    assert all("outside case data" not in fact.value for fact in projection.facts)


def test_advice_provider_gets_bounded_context_and_cannot_override_deterministic_actions(
    workspace_tmp_path: Path,
) -> None:
    brief = (
        "Founder idea brief: Inventory Pilot\n"
        "Concept: AI replenishment planner for pharmacy groups.\n"
        "Buyer: Operations directors.\n"
        r"Private note C:\Users\Akana\secret\deck.pdf says MRR 123000."
    )
    (workspace_tmp_path / str(CASE_ID)).mkdir()
    (workspace_tmp_path / str(CASE_ID) / "brief.txt").write_text(brief, encoding="utf-8")
    provider = _AdviceProvider()
    service = _service(
        workspace_tmp_path,
        workflow_store=_WorkflowStore(
            {
                CASE_ID: {
                    "case_exists": True,
                    "data_revision": 1,
                    "company_name": "Inventory Pilot",
                    "documents": [
                        {
                            "private_name": "brief.txt",
                            "declared_mime_type": "text/plain",
                        }
                    ],
                }
            }
        ),
        case_repository=_CaseRepository({CASE_ID: 1}, names={CASE_ID: "Inventory Pilot"}),
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 1,
        ),
        advice_provider=provider,
    )

    response = service.post_message(
        CASE_ID,
        PostCopilotMessageRequest(
            message=r"Use C:\Users\Akana\secret\deck.pdf and research private MRR.",
            page_context="market",
            current_section="benchmarks",
            expected_case_revision=1,
            focus_key="public_pricing_analogs",
            idempotency_key="provider-turn",
        ),
    )

    assert response.message == "Provider advice: validate the pharmacy operations buyer."
    assert len(provider.calls) == 1
    serialized_context = json_dumps(provider.calls[0])
    assert "Founder idea brief" not in serialized_context
    assert r"C:\Users\Akana" not in serialized_context
    assert "deck.pdf" not in serialized_context
    assert "123000" not in serialized_context
    assert "private MRR" not in serialized_context
    assert {action.action for action in response.available_actions} == {
        "open_fact_input",
        "open_document_upload",
        "prepare_public_research",
        "explain_metric",
        "navigate",
        "prepare_asset",
        "review_improvements",
    }
    research_action = next(
        action for action in response.available_actions if action.action == "prepare_public_research"
    )
    assert research_action.payload["focus"] == "public_pricing_analogs"
    assert all(str(action.action) != "send_email" for action in response.available_actions)


def test_advice_provider_failure_returns_deterministic_fallback_without_exception_leak(
    workspace_tmp_path: Path,
) -> None:
    (workspace_tmp_path / str(CASE_ID)).mkdir()
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 1,
        ),
        advice_provider=_RaisingAdviceProvider(),
    )

    response = service.post_message(
        CASE_ID,
        PostCopilotMessageRequest(
            message="What should I validate next?",
            page_context="overview",
            current_section="question",
            expected_case_revision=1,
            idempotency_key="provider-failure",
        ),
    )

    assert response.status == "accepted"
    assert "provider timeout" not in response.message.casefold()
    assert "Which first customer segment" in response.message
    thread = service.thread(CASE_ID)
    assert thread.messages[-1].content == response.message


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_action",
        "extra_action",
        "duplicate_action",
        "action_refs_mismatch",
        "prepare_public_research_wrong_status",
        "prepare_public_research_wrong_positive_revision",
        "prepare_public_research_private_focus",
        "prepare_public_research_invalid_revision",
        "open_fact_input_source_fact",
        "open_fact_input_public_field",
        "open_document_upload_foreign_case",
        "blocked_with_handler",
        "available_without_handler",
        "handler_non_string",
        "review_improvements_available_with_low_count",
        "review_improvements_blocked_with_enough_count",
        "empty_effect_preview",
        "wrong_action_id",
    ],
)
def test_idempotent_replay_fails_closed_when_persisted_action_snapshot_is_corrupt(
    workspace_tmp_path: Path,
    corruption: str,
) -> None:
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda _case_id: 1,
    )
    service = _service(workspace_tmp_path, threads=threads)
    request = PostCopilotMessageRequest(
        message="What should I validate next?",
        page_context="overview",
        current_section="question",
        expected_case_revision=1,
        idempotency_key=f"corrupt-snapshot-{corruption}",
    )
    original = service.post_message(CASE_ID, request)
    assert len(original.available_actions) == 7

    store_path = workspace_tmp_path / "case-copilot" / "copilot-threads.json"
    state = json_loads(store_path.read_text(encoding="utf-8"))
    record_key = state["current_by_case"][str(CASE_ID)]
    messages = state["records"][record_key]["messages"]
    assistant = next(message for message in reversed(messages) if message["role"] == "assistant")
    assert len(assistant["action_refs"]) == 7
    _corrupt_action_replay_snapshot(assistant, corruption)
    store_path.write_text(json_dumps(state), encoding="utf-8")
    before_replay = service.thread(CASE_ID)

    with pytest.raises(StartupGateConflict, match="copilot_action_snapshot_corrupt"):
        service.post_message(CASE_ID, request)
    after_replay = service.thread(CASE_ID)
    assert after_replay == before_replay


def test_public_research_rejects_profile_backed_runtime_when_old_primary_profile_is_missing(
    workspace_tmp_path: Path,
) -> None:
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(uuid4()),
                "profile_hash": "sha256:" + "1" * 64,
                "profile_revision": 1,
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    research_service = _ResearchService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda _case_id: 1,
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=_MissingRepository(),
        research_service=research_service,
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.queue_research_job(
            CASE_ID,
            QueueResearchJobRequest(
                plan_id=uuid4(),
                plan_hash="sha256:" + "2" * 64,
                expected_case_revision=1,
                idempotency_key="missing-profile",
                consent_public_research=True,
            ),
        )

    assert research_service.calls == []
    assert runtime.load(str(CASE_ID))["data_revision"] == 1
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


@pytest.mark.parametrize(
    "marker_overrides",
    [
        {"profile_id": 123},
        {"profile_hash": 123},
        {"profile_revision": True},
        {"primary_profile_id": 123},
    ],
)
def test_public_research_rejects_malformed_non_null_profile_markers_before_provider(
    workspace_tmp_path: Path,
    marker_overrides: dict[str, Any],
) -> None:
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "analysis_status": "awaiting_start",
                **marker_overrides,
            }
        }
    )
    research_service = _ResearchService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda _case_id: 1,
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=_MissingRepository(),
        research_service=research_service,
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.queue_research_job(
            CASE_ID,
            QueueResearchJobRequest(
                plan_id=uuid4(),
                plan_hash="sha256:" + "3" * 64,
                expected_case_revision=1,
                idempotency_key=f"malformed-marker-{next(iter(marker_overrides))}",
                consent_public_research=True,
            ),
        )

    assert research_service.calls == []
    assert runtime.load(str(CASE_ID))["data_revision"] == 1
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


@pytest.mark.parametrize(
    "runtime_overrides",
    [
        {"profile_id": "not-the-primary-profile-id"},
        {"profile_hash": "sha256:" + "9" * 64},
        {"profile_revision": 2},
        {"profile_hash": "sha256:" + "8" * 64, "profile_revision": 1},
    ],
)
def test_public_research_rejects_runtime_profile_projection_mismatch_before_provider(
    workspace_tmp_path: Path,
    runtime_overrides: dict[str, Any],
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    profiles = _MutableProfileRepository(old_profile)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
                **runtime_overrides,
            }
        }
    )
    research_service = _ResearchService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda _case_id: 1,
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        research_service=research_service,
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.queue_research_job(
            CASE_ID,
            QueueResearchJobRequest(
                plan_id=uuid4(),
                plan_hash="sha256:" + "4" * 64,
                expected_case_revision=1,
                idempotency_key=f"mismatched-runtime-profile-{next(iter(runtime_overrides))}",
                consent_public_research=True,
            ),
        )

    assert research_service.calls == []
    assert runtime.load(str(CASE_ID))["data_revision"] == 1
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


def test_public_research_accepts_profile_projection_without_primary_profile_pointer(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    profiles = _MutableProfileRepository(old_profile)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": None,
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    research_service = _ResearchService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        research_service=research_service,
    )

    response = service.queue_research_job(
        CASE_ID,
        QueueResearchJobRequest(
            plan_id=uuid4(),
            plan_hash="sha256:" + "5" * 64,
            expected_case_revision=1,
            idempotency_key="profile-primary-pointer-compatible",
            consent_public_research=True,
        ),
    )

    assert response.status == "completed"
    assert len(research_service.calls) == 1
    updated_runtime = runtime.load(str(CASE_ID))
    assert updated_runtime["data_revision"] == 2
    assert updated_runtime["primary_profile_id"] == updated_runtime["profile_id"]


def test_public_research_materializes_market_research_artifact_from_public_benchmarks(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    entry_id = UUID("11111111-1111-4111-8111-111111111111")
    source_ref = UUID("22222222-2222-4222-8222-222222222222")
    research_service = _ResearchService(
        response_overrides={
            "accepted_entries": [
                {
                    "entry_id": entry_id,
                    "provenance": "public_benchmark",
                    "input_key": "monthly_price",
                    "url": "https://example.com/pricing",
                    "publisher": "Example Pricing",
                    "publication_date": None,
                    "retrieval_date": "2026-08-22",
                    "as_of": "2026-08-22",
                    "source_class": "public_pricing",
                    "confidence": "medium",
                    "value": None,
                    "range": {"low": "1000", "high": "2000"},
                    "unit": "KZT",
                    "period": "month",
                    "formula": "public comparable pricing range",
                    "dependencies": ["public pricing page"],
                    "validation_plan": "Use only as external context until founder-specific evidence exists.",
                    "source_refs": [str(source_ref)],
                }
            ],
            "citations": ["https://example.com/pricing"],
            "source_refs": [str(entry_id)],
        }
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
        ),
        workflow_store=runtime,
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=research_service,
    )

    response = service.queue_research_job(
        CASE_ID,
        QueueResearchJobRequest(
            plan_id=uuid4(),
            plan_hash="sha256:" + "6" * 64,
            expected_case_revision=1,
            idempotency_key="public-research-market-artifact",
            consent_public_research=True,
        ),
    )

    assert response.status == "completed"
    updated_runtime = runtime.load(str(CASE_ID))
    assert updated_runtime["data_revision"] == 2
    assert updated_runtime["market_research_snapshot_revision"] == 2
    raw_artifact = updated_runtime["startup_market_research_artifact"]
    snapshot = StartupMarketResearchSnapshot.model_validate(raw_artifact["snapshot"])
    assert snapshot.case_id == CASE_ID
    assert snapshot.data_revision == 2
    assert snapshot.source_mode.value == "live"
    assert snapshot.sources[0].source_url.unicode_string() == "https://example.com/pricing"
    assert snapshot.sources[0].status is StartupResearchSourceStatus.INFERENCE
    assert snapshot.sources[0].supports_primary_financial_metrics is False
    assert snapshot.public_benchmark_candidates[0].input_key == "monthly_price"
    assert snapshot.public_benchmark_candidates[0].provenance == "public_benchmark"


def test_completed_live_source_only_research_fails_closed_when_internal_job_getter_errors(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
        ),
        workflow_store=runtime,
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=_FailingInternalJobResearchService(),
    )

    with pytest.raises(StartupGateConflict, match="research_job_snapshot_unavailable"):
        service.queue_research_job(
            CASE_ID,
            QueueResearchJobRequest(
                plan_id=uuid4(),
                plan_hash="sha256:" + "7" * 64,
                expected_case_revision=1,
                idempotency_key="source-only-getter-fails",
                consent_public_research=True,
            ),
        )

    assert runtime.load(str(CASE_ID))["data_revision"] == 1


def test_completed_live_source_only_research_materializes_persisted_snapshot_without_source_fact(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    research_service = _PersistedSnapshotResearchService(
        _live_market_snapshot(
            case_id=CASE_ID,
            data_revision=2,
            source_status=StartupResearchSourceStatus.SOURCE_FACT,
        )
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
        ),
        workflow_store=runtime,
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=research_service,
    )

    response = service.queue_research_job(
        CASE_ID,
        QueueResearchJobRequest(
            plan_id=uuid4(),
            plan_hash="sha256:" + "8" * 64,
            expected_case_revision=1,
            idempotency_key="source-only-persisted-snapshot",
            consent_public_research=True,
        ),
    )

    assert response.status == "completed"
    raw_artifact = runtime.load(str(CASE_ID))["startup_market_research_artifact"]
    snapshot = StartupMarketResearchSnapshot.model_validate(raw_artifact["snapshot"])
    assert snapshot.public_benchmark_candidates == ()
    assert snapshot.sources[0].source_url.unicode_string() == "https://example.com/public-market"
    assert snapshot.sources[0].status is StartupResearchSourceStatus.INFERENCE


def test_completed_live_research_projection_normalizes_full_public_research_graph(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    research_service = _PersistedSnapshotResearchService(
        _live_source_fact_graph_snapshot(case_id=CASE_ID, data_revision=2)
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
        ),
        workflow_store=runtime,
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=research_service,
    )

    response = service.queue_research_job(
        CASE_ID,
        QueueResearchJobRequest(
            plan_id=uuid4(),
            plan_hash="sha256:" + "9" * 64,
            expected_case_revision=1,
            idempotency_key="full-source-fact-public-research-projection",
            consent_public_research=True,
        ),
    )

    assert response.status == "completed"
    raw_artifact = runtime.load(str(CASE_ID))["startup_market_research_artifact"]
    snapshot = StartupMarketResearchSnapshot.model_validate(raw_artifact["snapshot"])
    assert {source.status for source in snapshot.sources} == {StartupResearchSourceStatus.INFERENCE}
    assert {competitor.status for competitor in snapshot.competitors} == {
        StartupResearchSourceStatus.INFERENCE
    }
    assert all(competitor.reason_code for competitor in snapshot.competitors)
    assert {assumption.status for assumption in snapshot.assumptions} == {
        StartupResearchSourceStatus.INFERENCE
    }
    assert all(assumption.reason_code for assumption in snapshot.assumptions)
    assert snapshot.sizing is not None
    assert snapshot.sizing.tam.level is StartupResearchSourceStatus.INFERENCE
    assert snapshot.sizing.sam.level is StartupResearchSourceStatus.INFERENCE
    assert snapshot.sizing.som.level is StartupResearchSourceStatus.INFERENCE


def test_completed_live_public_research_seeds_current_revision_analysis_checkpoint_once(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    source_refs = [
        {
            "document_id": "doc-0001",
            "private_name": "doc-0001.pdf",
            "content_sha256": "1" * 64,
        }
    ]
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "document_ids": ["doc-0001"],
                "source_document_ids": ["doc-0001"],
                "source_refs": source_refs,
                "source_refs_revision": 1,
                "fixture_mode": "live",
                "provider_status": "configured",
                "active_analysis_thread_id": f"{CASE_ID}:r1",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    research_service = _ResearchService(
        response_overrides={"changed_blocks": ["public_benchmarks"]}
    )
    service = _service(
        workspace_tmp_path,
        service_cls=_AnalysisSeedCapturingCaseCopilotService,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
        ),
        workflow_store=runtime,
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=research_service,
    )
    assert isinstance(service, _AnalysisSeedCapturingCaseCopilotService)

    response = service.queue_research_job(
        CASE_ID,
        QueueResearchJobRequest(
            plan_id=uuid4(),
            plan_hash="sha256:" + "2" * 64,
            expected_case_revision=1,
            idempotency_key="seed-current-revision-analysis-checkpoint",
            consent_public_research=True,
        ),
    )
    service._sync_revision_read_models_after_commit(
        CASE_ID,
        old_revision=1,
        new_revision=2,
    )

    assert response.status == "completed"
    assert service.analysis_seed_calls == [
        {
            "thread_id": f"{CASE_ID}:r2",
            "payload": {
                "case_id": str(CASE_ID),
                "run_id": f"startup-api-{CASE_ID}",
                "correlation_id": str(CASE_ID),
                "source_document_ids": ["doc-0001"],
                "source_refs": source_refs,
                "data_revision": 2,
                "fixture_mode": "live",
                "execution_mode": "configured",
            },
        }
    ]


def test_profile_backed_revision_without_analysis_starter_marks_visible_retryable_failure(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "document_ids": ["doc-0001"],
                "source_document_ids": ["doc-0001"],
                "source_refs": [
                    {
                        "document_id": "doc-0001",
                        "private_name": "doc-0001.pdf",
                        "content_sha256": "1" * 64,
                    }
                ],
                "source_refs_revision": 1,
                "fixture_mode": "live",
                "provider_status": "configured",
                "active_analysis_thread_id": f"{CASE_ID}:r1",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
                "gate2_status": "required",
                "gate2_preview": {"revision": 1},
                "gate2_resume_token_digest": "stale-revision-one-token",
                "gate2_resume_token_used": False,
            }
        }
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
        ),
        workflow_store=runtime,
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=_ResearchService(
            response_overrides={"changed_blocks": ["public_benchmarks"]}
        ),
    )

    response = service.queue_research_job(
        CASE_ID,
        QueueResearchJobRequest(
            plan_id=uuid4(),
            plan_hash="sha256:" + "3" * 64,
            expected_case_revision=1,
            idempotency_key="missing-analysis-revision-starter",
            consent_public_research=True,
        ),
    )

    assert response.status == "completed"
    current = runtime.load(str(CASE_ID))
    assert current["analysis_status"] == "failed"
    assert current["analysis_revision_seed_status"] == "retryable"
    assert current["error_code"] == "analysis_revision_starter_unavailable"
    assert current["gate2_status"] == "not_ready"
    assert current["gate2_preview"] is None
    assert current["gate2_resume_token_digest"] is None
    assert current["gate2_resume_token_used"] is False


def test_public_research_without_profile_backed_runtime_advances_revision_without_profile_projection(
    workspace_tmp_path: Path,
) -> None:
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "analysis_status": "awaiting_start",
                "profile_id": None,
                "profile_hash": None,
                "profile_revision": None,
                "primary_profile_id": None,
            }
        }
    )
    research_service = _ResearchService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=_MissingRepository(),
        research_service=research_service,
    )

    response = service.queue_research_job(
        CASE_ID,
        QueueResearchJobRequest(
            plan_id=uuid4(),
            plan_hash="sha256:" + "3" * 64,
            expected_case_revision=1,
            idempotency_key="profile-not-required-for-idea-runtime",
            consent_public_research=True,
        ),
    )

    assert response.status == "completed"
    assert len(research_service.calls) == 1
    assert runtime.load(str(CASE_ID)) == {
        "case_exists": True,
        "data_revision": 2,
        "company_name": "UnitCase",
        "analysis_status": "awaiting_start",
        "profile_id": None,
        "profile_hash": None,
        "profile_revision": None,
        "primary_profile_id": None,
    }
    thread = threads.get_current(CASE_ID)
    assert thread.data_revision == 2
    assert len([message for message in thread.messages if message.role == "system_event"]) == 1


def test_public_research_replay_rejects_new_revision_runtime_when_new_primary_profile_is_missing(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    missing_new_profile = _build_primary_profile(data_revision=2)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 2,
                "company_name": "UnitCase",
                "profile_id": str(missing_new_profile.profile_id),
                "profile_hash": missing_new_profile.profile_hash,
                "profile_revision": 2,
                "primary_profile_id": str(missing_new_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    initial_runtime = dict(runtime.load(str(CASE_ID)))
    assert _profile_projection_matches_revision(initial_runtime, 2)
    research_service = _ResearchService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        case_repository=_CaseRepository(revisions={CASE_ID: 2}),
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=research_service,
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.queue_research_job(
            CASE_ID,
            QueueResearchJobRequest(
                plan_id=uuid4(),
                plan_hash="sha256:" + "6" * 64,
                expected_case_revision=1,
                idempotency_key="replayed-missing-new-primary-profile",
                consent_public_research=True,
            ),
        )

    assert len(research_service.calls) == 1
    assert runtime.load(str(CASE_ID)) == initial_runtime
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


def test_public_research_replay_rejects_new_revision_runtime_when_new_primary_profile_mismatches(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    stored_new_profile = _build_primary_profile(data_revision=2)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 2,
                "company_name": "UnitCase",
                "profile_id": str(uuid4()),
                "profile_hash": "sha256:" + "9" * 64,
                "profile_revision": 2,
                "primary_profile_id": None,
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    initial_runtime = dict(runtime.load(str(CASE_ID)))
    assert _profile_projection_matches_revision(initial_runtime, 2)
    research_service = _ResearchService()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        case_repository=_CaseRepository(revisions={CASE_ID: 2}),
        profile_repository=_MutableProfileRepository(old_profile, stored_new_profile),
        research_service=research_service,
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.queue_research_job(
            CASE_ID,
            QueueResearchJobRequest(
                plan_id=uuid4(),
                plan_hash="sha256:" + "7" * 64,
                expected_case_revision=1,
                idempotency_key="replayed-mismatched-new-primary-profile",
                consent_public_research=True,
            ),
        )

    assert len(research_service.calls) == 1
    assert runtime.load(str(CASE_ID)) == initial_runtime
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


@pytest.mark.parametrize("missing_revision", ["old_revision", "new_revision"])
def test_public_research_missing_job_revision_fails_closed_without_read_model_mutation(
    workspace_tmp_path: Path,
    missing_revision: str,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    research_service = _ResearchService(response_overrides={missing_revision: None})
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda _case_id: 1,
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=_MutableProfileRepository(old_profile),
        research_service=research_service,
    )

    with pytest.raises(StartupGateConflict, match="research_revision_unavailable"):
        service.queue_research_job(
            CASE_ID,
            QueueResearchJobRequest(
                plan_id=uuid4(),
                plan_hash="sha256:" + "4" * 64,
                expected_case_revision=1,
                idempotency_key=f"missing-{missing_revision}",
                consent_public_research=True,
            ),
        )

    assert len(research_service.calls) == 1
    assert runtime.load(str(CASE_ID)) == {
        "case_exists": True,
        "data_revision": 1,
        "company_name": "UnitCase",
        "profile_id": str(old_profile.profile_id),
        "profile_hash": old_profile.profile_hash,
        "profile_revision": 1,
        "primary_profile_id": str(old_profile.profile_id),
        "analysis_status": "gate2_preview_ready",
    }
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


def test_public_research_replay_after_profile_add_crash_reuses_new_revision_primary_profile(
    workspace_tmp_path: Path,
) -> None:
    old_profile = _build_primary_profile(data_revision=1)
    profiles = _MutableProfileRepository(old_profile)
    runtime = _CrashOnceWorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_profile.profile_id),
                "profile_hash": old_profile.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_profile.profile_id),
                "analysis_status": "gate2_preview_ready",
            }
        }
    )
    research_service = _ResearchService(response_overrides={"job_id": UUID("11111111-1111-4111-8111-111111111111")})
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        research_service=research_service,
    )
    request = QueueResearchJobRequest(
        plan_id=uuid4(),
        plan_hash="sha256:" + "5" * 64,
        expected_case_revision=1,
        idempotency_key="crash-after-profile-add",
        consent_public_research=True,
    )

    with pytest.raises(RuntimeError, match="crash_after_profile_add"):
        service.queue_research_job(CASE_ID, request)
    crashed_profiles = profiles.primary_profiles_for_revision(2)
    assert len(crashed_profiles) == 1
    crashed_profile = crashed_profiles[0]
    assert runtime.load(str(CASE_ID))["data_revision"] == 1
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)

    service.queue_research_job(CASE_ID, request)

    replayed_profiles = profiles.primary_profiles_for_revision(2)
    assert len(replayed_profiles) == 1
    assert replayed_profiles[0].profile_id == crashed_profile.profile_id
    assert replayed_profiles[0].profile_hash == crashed_profile.profile_hash
    replayed_runtime = runtime.load(str(CASE_ID))
    assert replayed_runtime["data_revision"] == 2
    assert replayed_runtime["profile_id"] == str(crashed_profile.profile_id)
    assert replayed_runtime["profile_hash"] == crashed_profile.profile_hash
    assert replayed_runtime["profile_revision"] == 2
    assert replayed_runtime["primary_profile_id"] == str(crashed_profile.profile_id)
    thread = threads.get_current(CASE_ID)
    assert thread.data_revision == 2
    assert len([message for message in thread.messages if message.role == "system_event"]) == 1


def test_assumption_sync_projects_enriched_profile_with_new_primary_parent_and_replays(
    workspace_tmp_path: Path,
) -> None:
    old_primary = _build_primary_profile(data_revision=1)
    old_enriched = _build_enriched_profile(
        data_revision=1,
        parent_profile_id=old_primary.profile_id,
    )
    profiles = _MutableProfileRepository(old_primary, old_enriched)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_enriched.profile_id),
                "profile_hash": old_enriched.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": None,
                "analysis_status": "gate3_review_required",
            }
        }
    )
    fact_intake = _AcceptedFactIntake()
    statements = _ReplayStatementsRepository()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        assumption_repository=statements,
        fact_intake_service=fact_intake,
    )
    request = SaveAssumptionRequest.model_validate(
        {
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
            "rationale": "Founder stated recognized MRR excludes unpaid pilots.",
            "validation_plan": "Verify against bank deposits and invoice register.",
            "expected_case_revision": 1,
            "idempotency_key": "enriched-assumption-stage-aware-sync",
        }
    )

    response = service.save_assumption(CASE_ID, request)

    assert response.status == "accepted"
    assert len(fact_intake.calls) == 1
    new_primary_profiles = profiles.profiles_for_revision(
        2,
        StartupProfileAnalysisStage.PRIMARY,
    )
    new_enriched_profiles = profiles.profiles_for_revision(
        2,
        StartupProfileAnalysisStage.ENRICHED,
    )
    assert len(new_primary_profiles) == 1
    assert len(new_enriched_profiles) == 1
    new_primary = new_primary_profiles[0]
    new_enriched = new_enriched_profiles[0]
    assert new_enriched.parent_profile_id == new_primary.profile_id
    updated_runtime = runtime.load(str(CASE_ID))
    assert updated_runtime["data_revision"] == 2
    assert updated_runtime["profile_id"] == str(new_enriched.profile_id)
    assert updated_runtime["profile_hash"] == new_enriched.profile_hash
    assert updated_runtime["profile_revision"] == 2
    assert updated_runtime["primary_profile_id"] == str(new_primary.profile_id)

    statements.replay = True
    replay = service.save_assumption(CASE_ID, request)

    assert replay.status == response.status
    assert replay.old_revision == response.old_revision
    assert replay.new_revision == response.new_revision
    assert replay.accepted_input is not None
    assert len(fact_intake.calls) == 2
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.PRIMARY) == [
        new_primary
    ]
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.ENRICHED) == [
        new_enriched
    ]
    assert runtime.load(str(CASE_ID))["profile_id"] == str(new_enriched.profile_id)


def test_assumption_submit_normalizes_legacy_net_burn_alias(
    workspace_tmp_path: Path,
) -> None:
    fact_intake = _AcceptedFactIntake()
    runtime = _WorkflowStore()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        fact_intake_service=fact_intake,
    )
    request = SaveAssumptionRequest.model_validate(
        {
            "requirement_key": "net_burn",
            "value": {
                "kind": "money",
                "amount": "700000",
                "scale": "ones",
                "currency": "KZT",
            },
            "period": {"kind": "month", "value": "2026-07"},
            "source": {
                "kind": "founder_statement",
                "declared_source": "Founder interview on 2026-08-22",
            },
            "rationale": "Founder stated monthly cash burn.",
            "validation_plan": "Verify against finance export.",
            "expected_case_revision": 1,
            "idempotency_key": "legacy-net-burn-alias",
        }
    )

    service.save_assumption(CASE_ID, request)

    assert fact_intake.calls[0].requirement_key == "burn"


def test_money_assumption_period_validation_follows_canonical_schema(
    workspace_tmp_path: Path,
) -> None:
    fact_intake = _AcceptedFactIntake()
    runtime = _WorkflowStore()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        fact_intake_service=fact_intake,
    )

    accepted = service.save_assumption(
        CASE_ID,
        SaveAssumptionRequest.model_validate(
            {
                "requirement_key": "available_budget",
                "value": {
                    "kind": "money",
                    "amount": "5000000",
                    "scale": "ones",
                    "currency": "KZT",
                },
                "period": None,
                "source": {
                    "kind": "founder_statement",
                    "declared_source": "Founder interview on 2026-08-22",
                },
                "rationale": "Founder stated current budget.",
                "validation_plan": "Verify against finance plan.",
                "expected_case_revision": 1,
                "idempotency_key": "budget-without-period",
            }
        ),
    )

    assert accepted.status == "accepted"
    assert fact_intake.calls[0].requirement_key == "available_budget"
    assert fact_intake.calls[0].period is None

    with pytest.raises(_FactValidationFailure) as error:
        service.save_assumption(
            CASE_ID,
            SaveAssumptionRequest.model_validate(
                {
                    "requirement_key": "monthly_price",
                    "value": {
                        "kind": "money",
                        "amount": "35000",
                        "scale": "ones",
                        "currency": "KZT",
                    },
                    "period": None,
                    "source": {
                        "kind": "founder_statement",
                        "declared_source": "Founder interview on 2026-08-22",
                    },
                    "rationale": "Founder stated monthly price.",
                    "validation_plan": "Verify against invoices.",
                    "expected_case_revision": 2,
                    "idempotency_key": "monthly-price-without-period",
                }
            ),
        )

    assert any(item.field == "period" for item in error.value.errors)


def test_assumption_preflight_rejects_primary_runtime_when_current_profile_is_enriched(
    workspace_tmp_path: Path,
) -> None:
    old_primary = _build_primary_profile(data_revision=1)
    old_enriched = _build_enriched_profile(
        data_revision=1,
        parent_profile_id=old_primary.profile_id,
    )
    profiles = _MutableProfileRepository(old_primary, old_enriched)
    runtime = _WorkflowStore(
        {
            CASE_ID: {
                "case_exists": True,
                "data_revision": 1,
                "company_name": "UnitCase",
                "profile_id": str(old_primary.profile_id),
                "profile_hash": old_primary.profile_hash,
                "profile_revision": 1,
                "primary_profile_id": str(old_primary.profile_id),
                "analysis_status": "gate3_review_required",
            }
        }
    )
    fact_intake = _AcceptedFactIntake()
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        fact_intake_service=fact_intake,
    )
    request = SaveAssumptionRequest.model_validate(
        {
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
            "rationale": "Founder stated recognized MRR excludes unpaid pilots.",
            "validation_plan": "Verify against bank deposits and invoice register.",
            "expected_case_revision": 1,
            "idempotency_key": "reject-primary-runtime-when-current-enriched",
        }
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.save_assumption(CASE_ID, request)

    assert fact_intake.calls == []
    assert runtime.load(str(CASE_ID))["data_revision"] == 1
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.PRIMARY) == []
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.ENRICHED) == []
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


def test_assumption_replay_rejects_foreign_runtime_profile_before_projection(
    workspace_tmp_path: Path,
) -> None:
    foreign_primary = _build_primary_profile(
        case_id=CASE_B_ID,
        data_revision=1,
    )
    profiles = _MutableProfileRepository(foreign_primary)
    initial_runtime = {
        "case_exists": True,
        "data_revision": 1,
        "company_name": "UnitCase",
        "profile_id": str(foreign_primary.profile_id),
        "profile_hash": foreign_primary.profile_hash,
        "profile_revision": 1,
        "primary_profile_id": str(foreign_primary.profile_id),
        "analysis_status": "gate2_preview_ready",
    }
    runtime = _WorkflowStore({CASE_ID: dict(initial_runtime)})
    fact_intake = _AcceptedFactIntake()
    statements = _ReplayStatementsRepository()
    statements.replay = True
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        assumption_repository=statements,
        fact_intake_service=fact_intake,
    )
    request = SaveAssumptionRequest.model_validate(
        {
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
            "rationale": "Founder stated recognized MRR excludes unpaid pilots.",
            "validation_plan": "Verify against bank deposits and invoice register.",
            "expected_case_revision": 1,
            "idempotency_key": "reject-foreign-runtime-profile-replay",
        }
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.save_assumption(CASE_ID, request)

    assert runtime.load(str(CASE_ID)) == initial_runtime
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.PRIMARY) == []
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.ENRICHED) == []
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


def test_save_fact_replay_rejects_foreign_runtime_profile_before_projection(
    workspace_tmp_path: Path,
) -> None:
    foreign_primary = _build_primary_profile(
        case_id=CASE_B_ID,
        data_revision=1,
    )
    profiles = _MutableProfileRepository(foreign_primary)
    initial_runtime = {
        "case_exists": True,
        "data_revision": 1,
        "company_name": "UnitCase",
        "profile_id": str(foreign_primary.profile_id),
        "profile_hash": foreign_primary.profile_hash,
        "profile_revision": 1,
        "primary_profile_id": str(foreign_primary.profile_id),
        "analysis_status": "gate2_preview_ready",
    }
    runtime = _WorkflowStore({CASE_ID: dict(initial_runtime)})
    fact_intake = _AcceptedFactIntake()
    statements = _ReplayStatementsRepository()
    statements.replay = True
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        assumption_repository=statements,
        fact_intake_service=fact_intake,
    )
    request = SaveFounderFactRequest.model_validate(
        {
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
            "note": "Founder stated recognized MRR excludes unpaid pilots.",
            "expected_case_revision": 1,
            "idempotency_key": "reject-foreign-runtime-profile-fact-replay",
        }
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.save_fact(CASE_ID, request)

    assert runtime.load(str(CASE_ID)) == initial_runtime
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.PRIMARY) == []
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.ENRICHED) == []
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


def test_assumption_replay_rejects_corrupt_existing_new_revision_profile(
    workspace_tmp_path: Path,
) -> None:
    old_primary = _build_primary_profile(data_revision=1)
    corrupt_new_primary = _build_primary_profile(
        data_revision=2,
        source_hashes={"brief": "sha256:" + "b" * 64},
    )
    profiles = _MutableProfileRepository(old_primary, corrupt_new_primary)
    initial_runtime = {
        "case_exists": True,
        "data_revision": 1,
        "company_name": "UnitCase",
        "profile_id": str(old_primary.profile_id),
        "profile_hash": old_primary.profile_hash,
        "profile_revision": 1,
        "primary_profile_id": str(old_primary.profile_id),
        "analysis_status": "gate2_preview_ready",
    }
    runtime = _WorkflowStore({CASE_ID: dict(initial_runtime)})
    fact_intake = _AcceptedFactIntake()
    statements = _ReplayStatementsRepository()
    statements.replay = True
    threads = LocalCaseCopilotThreadRepository(
        workspace_tmp_path,
        current_revision=lambda case_id: int(runtime.load(str(case_id))["data_revision"]),
    )
    service = _service(
        workspace_tmp_path,
        threads=threads,
        workflow_store=runtime,
        profile_repository=profiles,
        assumption_repository=statements,
        fact_intake_service=fact_intake,
    )
    request = SaveAssumptionRequest.model_validate(
        {
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
            "rationale": "Founder stated recognized MRR excludes unpaid pilots.",
            "validation_plan": "Verify against bank deposits and invoice register.",
            "expected_case_revision": 1,
            "idempotency_key": "reject-corrupt-existing-new-revision-profile",
        }
    )

    with pytest.raises(StartupGateConflict, match="research_profile_projection_unavailable"):
        service.save_assumption(CASE_ID, request)

    assert runtime.load(str(CASE_ID)) == initial_runtime
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.PRIMARY) == [
        corrupt_new_primary
    ]
    assert profiles.profiles_for_revision(2, StartupProfileAnalysisStage.ENRICHED) == []
    with pytest.raises(KeyError):
        threads.get_current(CASE_ID)


def test_state_projects_accepted_public_benchmark_without_source_fact_promotion(
    workspace_tmp_path: Path,
) -> None:
    benchmark_ref = UUID("22222222-2222-4222-8222-222222222222")
    benchmark = ScenarioInput(
        input_id=UUID("11111111-1111-4111-8111-111111111111"),
        case_id=CASE_ID,
        data_revision=1,
        input_key="monthly_price",
        value_range=ScenarioRange(lower=Decimal(1000), upper=Decimal(2000)),
        unit="USD/month",
        period="month",
        provenance=CaseValueKind.PUBLIC_BENCHMARK,
        source_refs=(benchmark_ref, benchmark_ref),
        dependency_refs=(UUID("33333333-3333-4333-8333-333333333333"),),
        confidence="medium",
        rationale="Cited public pricing benchmark for comparable SaaS tools.",
        validation_plan="Use only as external context until founder-specific evidence exists.",
        acceptance="accepted",
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 1,
        ),
        public_benchmarks=_PublicBenchmarksRepository((benchmark,)),
    )

    state = service.state(CASE_ID)

    projected = [
        item for item in state.accepted_inputs if item.field_key == "monthly_price"
    ]
    assert len(projected) == 1
    assert projected[0].kind is CaseValueKind.PUBLIC_BENCHMARK
    assert projected[0].status == "accepted"
    assert projected[0].value == "1000-2000 USD/month"
    assert projected[0].period == "month"
    assert projected[0].rationale == "Cited public pricing benchmark for comparable SaaS tools."
    assert projected[0].validation_plan == (
        "Use only as external context until founder-specific evidence exists."
    )
    assert projected[0].source_refs == (
        benchmark.input_id,
        benchmark_ref,
    )
    assert state.scenario_completeness.accepted_input_count == 1
    assert not any(
        item.field_key == "monthly_price" and item.kind is CaseValueKind.SOURCE_FACT
        for item in state.accepted_inputs
    )
    assert not any(
        fact.field_key == "monthly_price"
        and fact.source_type is CaseValueKind.SOURCE_FACT
        for fact in state.extracted_facts
    )


def test_state_dedupes_public_benchmarks_with_research_key_normalization(
    workspace_tmp_path: Path,
) -> None:
    old_ref = UUID("44444444-4444-4444-8444-444444444444")
    middle_ref = UUID("55555555-5555-4555-8555-555555555555")
    latest_ref = UUID("66666666-6666-4666-8666-666666666666")
    old = _public_benchmark(
        input_id=UUID("11111111-1111-4111-8111-111111111111"),
        source_ref=old_ref,
        data_revision=1,
        input_key="Monthly Price",
        lower="1000",
        upper="2000",
        rationale="Older public pricing benchmark.",
    )
    middle = _public_benchmark(
        input_id=UUID("22222222-2222-4222-8222-222222222222"),
        source_ref=middle_ref,
        data_revision=2,
        input_key="monthly-price",
        lower="1200",
        upper="2200",
        rationale="Middle public pricing benchmark.",
    )
    latest = _public_benchmark(
        input_id=UUID("33333333-3333-4333-8333-333333333333"),
        source_ref=latest_ref,
        data_revision=3,
        input_key="monthly_price",
        lower="1500",
        upper="2500",
        rationale="Latest public pricing benchmark.",
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 3,
        ),
        case_repository=_CaseRepository({CASE_ID: 3}),
        public_benchmarks=_PublicBenchmarksRepository((old, latest, middle)),
    )

    state = service.state(CASE_ID)

    projected = [
        item
        for item in state.accepted_inputs
        if item.field_key in {"Monthly Price", "monthly-price", "monthly_price"}
    ]
    assert len(projected) == 1
    assert projected[0].field_key == "monthly_price"
    assert projected[0].value == "1500-2500 USD/month"
    assert projected[0].rationale == "Latest public pricing benchmark."
    assert projected[0].source_refs == (latest.input_id, latest_ref)
    assert state.scenario_completeness.accepted_input_count == 1


def test_state_rejects_public_benchmarks_without_exact_same_case_id(
    workspace_tmp_path: Path,
) -> None:
    none_case = _public_benchmark(
        input_id=UUID("11111111-1111-4111-8111-111111111111"),
        source_ref=UUID("77777777-7777-4777-8777-777777777777"),
        case_id=None,
        input_key="monthly_price",
    )
    wrong_case = _public_benchmark(
        input_id=UUID("22222222-2222-4222-8222-222222222222"),
        source_ref=UUID("88888888-8888-4888-8888-888888888888"),
        case_id=CASE_B_ID,
        input_key="acquisition_spend",
    )
    service = _service(
        workspace_tmp_path,
        threads=LocalCaseCopilotThreadRepository(
            workspace_tmp_path,
            current_revision=lambda _case_id: 1,
        ),
        public_benchmarks=_LeakyPublicBenchmarksRepository((none_case, wrong_case)),
    )

    state = service.state(CASE_ID)

    assert state.scenario_completeness.accepted_input_count == 0
    assert not any(
        item.field_key in {"monthly_price", "acquisition_spend"}
        for item in state.accepted_inputs
    )


def _public_benchmark(
    *,
    input_id: UUID,
    source_ref: UUID,
    case_id: UUID | None = CASE_ID,
    data_revision: int = 1,
    input_key: str,
    lower: str = "1000",
    upper: str = "2000",
    rationale: str = "Cited public benchmark for comparable SaaS tools.",
) -> ScenarioInput:
    return ScenarioInput(
        input_id=input_id,
        case_id=case_id,
        data_revision=data_revision,
        input_key=input_key,
        value_range=ScenarioRange(lower=Decimal(lower), upper=Decimal(upper)),
        unit="USD/month",
        period="month",
        provenance=CaseValueKind.PUBLIC_BENCHMARK,
        source_refs=(source_ref,),
        dependency_refs=(UUID("33333333-3333-4333-8333-333333333333"),),
        confidence="medium",
        rationale=rationale,
        validation_plan="Use only as external context until founder-specific evidence exists.",
        acceptance="accepted",
    )


def _service(
    root: Path,
    *,
    service_cls: type[CaseCopilotService] = CaseCopilotService,
    threads: LocalCaseCopilotThreadRepository,
    workflow_store: Any | None = None,
    case_repository: Any | None = None,
    profile_repository: Any | None = None,
    assumption_repository: Any | None = None,
    fact_intake_service: Any | None = None,
    question_service: Any | None = None,
    advice_provider: Any | None = None,
    research_service: Any | None = None,
    public_benchmarks: Any | None = None,
) -> CaseCopilotService:
    resolved_workflow_store = workflow_store or _WorkflowStore()
    resolved_case_repository = case_repository or _CaseRepository()
    bind_case_repository = getattr(research_service, "bind_case_repository", None)
    if callable(bind_case_repository):
        bind_case_repository(resolved_case_repository)
    return service_cls(
        workflow_store=resolved_workflow_store,
        inbox_root=root,
        case_repository=resolved_case_repository,
        profile_repository=profile_repository or _MissingRepository(),
        assumption_repository=assumption_repository or _StatementsRepository(),
        thread_repository=threads,
        fact_intake_service=fact_intake_service or _MissingRepository(),
        question_service=question_service or _QuestionService(),
        scenario_service=_ScenarioService(),
        scenario_repository=_MissingRepository(),
        research_service=research_service,
        copilot_advice_provider=advice_provider,
        public_benchmark_repository=public_benchmarks,
    )


class _WorkflowStore:
    def __init__(self, runtimes: dict[UUID, dict[str, Any]] | None = None) -> None:
        self._runtimes = runtimes or {
            CASE_ID: {"case_exists": True, "data_revision": 1, "company_name": "UnitCase"}
        }

    def load(self, case_id: str) -> dict[str, Any]:
        return self._runtimes[UUID(case_id)]

    def update(self, case_id: str, mutator: Any) -> dict[str, Any]:
        current = dict(self._runtimes[UUID(case_id)])
        values = mutator(dict(current))
        current.update(values)
        self._runtimes[UUID(case_id)] = current
        return dict(current)


class _AnalysisSeedCapturingCaseCopilotService(CaseCopilotService):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.analysis_seed_calls: list[dict[str, Any]] = []
        self._seeded_analysis_threads: set[str] = set()

    def _start_startup_analysis_revision(self, payload: dict[str, Any], *, thread_id: str) -> None:
        if thread_id in self._seeded_analysis_threads:
            return
        self._seeded_analysis_threads.add(thread_id)
        self.analysis_seed_calls.append({"payload": dict(payload), "thread_id": thread_id})


class _CrashOnceWorkflowStore(_WorkflowStore):
    def __init__(self, runtimes: dict[UUID, dict[str, Any]]) -> None:
        super().__init__(runtimes)
        self._crash_next_update = True

    def update(self, case_id: str, mutator: Any) -> dict[str, Any]:
        if self._crash_next_update:
            self._crash_next_update = False
            raise RuntimeError("crash_after_profile_add")
        return super().update(case_id, mutator)


class _CaseRepository:
    def __init__(
        self,
        revisions: dict[UUID, int] | None = None,
        *,
        names: dict[UUID, str] | None = None,
    ) -> None:
        self._revisions = revisions or {CASE_ID: 1}
        self._names = names or {CASE_ID: "UnitCase"}

    def get(self, case_id: UUID) -> DueDiligenceCase:
        revision = self._revisions[case_id]
        timestamp = datetime(2026, 8, 22, tzinfo=UTC)
        return DueDiligenceCase(
            case_id=case_id,
            mode=AnalysisMode.STARTUP,
            entity_name=self._names.get(case_id, str(case_id)),
            entity_identifier=str(case_id),
            jurisdiction="unknown",
            scope=("startup_case_copilot",),
            as_of=timestamp,
            base_currency="USD",
            privacy_policy="startup_local_private",
            budget_policy="offline_deterministic",
            status=CaseStatus.AWAITING_EVIDENCE,
            sensitivity=SensitivityClass.CONFIDENTIAL,
            created_at=timestamp,
            updated_at=timestamp,
            workflow_version="startup-case-copilot-v1",
            data_revision=revision,
        )

    def set_revision(self, case_id: UUID, data_revision: int) -> None:
        self._revisions[case_id] = data_revision


class _MissingRepository:
    def get_current(self, _case_id: UUID) -> Any:
        raise KeyError


class _PrimaryProfileRepository:
    def get_current(self, _case_id: UUID) -> Any:
        raise KeyError

    def get_for_stage(self, _case_id: UUID, data_revision: int, _stage: Any) -> Any:
        if data_revision != 1:
            raise KeyError
        return object()


class _MutableProfileRepository:
    def __init__(self, *profiles: StartupProfile) -> None:
        self._profiles = list(profiles)

    def add(self, profile: StartupProfile) -> None:
        self._profiles.append(profile)

    def get(self, profile_id: UUID) -> StartupProfile:
        matches = [profile for profile in self._profiles if profile.profile_id == profile_id]
        if not matches:
            raise KeyError
        return matches[-1]

    def get_current(self, case_id: UUID) -> StartupProfile:
        matches = [profile for profile in self._profiles if profile.case_id == case_id]
        if not matches:
            raise KeyError
        return matches[-1]

    def get_for_stage(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile:
        matches = [
            profile
            for profile in self._profiles
            if profile.case_id == case_id
            and profile.data_revision == data_revision
            and profile.analysis_stage is stage
        ]
        if not matches:
            raise KeyError
        return matches[-1]

    def primary_profiles_for_revision(self, data_revision: int) -> list[StartupProfile]:
        return self.profiles_for_revision(data_revision, StartupProfileAnalysisStage.PRIMARY)

    def profiles_for_revision(
        self,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> list[StartupProfile]:
        return [
            profile
            for profile in self._profiles
            if profile.case_id == CASE_ID
            and profile.data_revision == data_revision
            and profile.analysis_stage is stage
        ]


def _build_primary_profile(
    *,
    data_revision: int,
    case_id: UUID = CASE_ID,
    source_hashes: dict[str, str] | None = None,
) -> StartupProfile:
    built_at = datetime(2026, 8, 22, 12, data_revision, tzinfo=UTC)
    return StartupProfile.build(
        case_id=case_id,
        schema_version="startup-profile-schema-v1",
        profile_version="startup-profile-v1",
        extractor_version="test-extractor-v1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes=source_hashes or {"brief": "sha256:" + "a" * 64},
        parse_outcomes={"brief": "parsed"},
        fields={
            field_name.value: StartupProfileField(
                name=field_name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                values=(),
                confidence=Decimal(0),
                reason_code="unit_test_fixture",
            )
            for field_name in StartupProfileFieldName
        },
        gap_codes=(),
        contradiction_ids=(),
        case_revision_at=built_at,
    )


def _build_enriched_profile(
    *,
    data_revision: int,
    parent_profile_id: UUID,
) -> StartupProfile:
    primary_like = _build_primary_profile(data_revision=data_revision)
    return StartupProfile.build(
        case_id=CASE_ID,
        schema_version=primary_like.schema_version,
        profile_version=primary_like.profile_version,
        extractor_version=primary_like.extractor_version,
        analysis_stage=StartupProfileAnalysisStage.ENRICHED,
        parent_profile_id=parent_profile_id,
        data_revision=data_revision,
        source_hashes=primary_like.source_hashes,
        parse_outcomes=primary_like.parse_outcomes,
        fields=primary_like.fields,
        gap_codes=primary_like.gap_codes,
        contradiction_ids=primary_like.contradiction_ids,
        case_revision_at=datetime(2026, 8, 22, 13, data_revision, tzinfo=UTC),
    )


class _AcceptedFactIntake:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def save_founder_statement(self, command: Any) -> CaseMutationDelta:
        self.calls.append(command)
        return CaseMutationDelta(
            accepted=True,
            old_revision=1,
            new_revision=2,
            changed_keys=("mrr",),
            metric_after={"mrr": "founder_statement"},
        )


class _StatementsRepository:
    def get_current(self, _case_id: UUID) -> tuple[()]:
        return ()


class _FieldStatementsRepository:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get_current(self, case_id: UUID) -> tuple[FounderStatement, ...]:
        return tuple(
            FounderStatement(
                statement_id=UUID(f"00000000-0000-4000-8000-{index + 1:012d}"),
                case_id=case_id,
                data_revision=1,
                field_key=key,
                value=value,
                confidence=Decimal("0.6"),
                period=None,
                declared_source="founder",
                rationale="Founder supplied test value.",
                validation_plan="Validate against founder-controlled evidence.",
            )
            for index, (key, value) in enumerate(self._values.items())
        )


class _NoContradictionsRepository:
    def list_for_case(self, _case_id: UUID) -> tuple[()]:
        return ()


class _QuestionProfileRepository:
    def __init__(self, *, stage: str) -> None:
        self._stage = stage

    def get_current(self, case_id: UUID) -> StartupProfile:
        profile = _build_primary_profile(data_revision=1, case_id=case_id)
        fields = dict(profile.fields)
        fields[StartupProfileFieldName.STAGE.value] = StartupProfileField(
            name=StartupProfileFieldName.STAGE,
            status=StartupProfileFieldStatus.SOURCE_FACT,
            values=(self._stage,),
            confidence=Decimal("0.8"),
        )
        return profile.model_copy(update={"fields": fields})


class _ReplayStatementsRepository(_StatementsRepository):
    replay = False

    def get_by_idempotency(
        self,
        case_id: UUID,
        _idempotency_key: str,
    ) -> FounderStatement | None:
        if not self.replay:
            return None
        return FounderStatement(
            statement_id=UUID("11111111-1111-4111-8111-111111111111"),
            case_id=case_id,
            data_revision=2,
            field_key="mrr",
            value="1850000",
            confidence=Decimal("0.6"),
            period="2026-07",
            declared_source="Founder interview on 2026-08-22",
            rationale="Founder stated recognized MRR excludes unpaid pilots.",
            validation_plan="Verify against bank deposits and invoice register.",
        )


class _PublicBenchmarksRepository:
    def __init__(self, items: tuple[ScenarioInput, ...]) -> None:
        self._items = items

    def get_current(self, case_id: UUID) -> tuple[ScenarioInput, ...]:
        return tuple(item for item in self._items if item.case_id == case_id)


class _LeakyPublicBenchmarksRepository:
    def __init__(self, items: tuple[ScenarioInput, ...]) -> None:
        self._items = items

    def get_current(self, _case_id: UUID) -> tuple[ScenarioInput, ...]:
        return self._items


class _ScenarioSet:
    selected_scenario_key = "base"
    scenarios: ClassVar[dict[str, Any]] = {}

    def __init__(self, *, data_revision: int) -> None:
        self.data_revision = data_revision


class _ScenarioService:
    def build(self, *_args: Any, **kwargs: Any) -> _ScenarioSet:
        return _ScenarioSet(data_revision=int(kwargs["expected_case_revision"]))


class _Question:
    prompt = "Which first customer segment should the founder validate next?"


class _QuestionService:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, str, str | None]] = []

    def next_question(self, case_id: UUID, *, page_context: str, focus_key: str | None) -> _Question:
        self.calls.append((case_id, page_context, focus_key))
        return _Question()


class _AdviceProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def advise(self, context: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(context)
        return {
            "message": "Provider advice: validate the pharmacy operations buyer.",
            "actions": [
                {"action": "send_email", "status": "available"},
                {
                    "action": "prepare_public_research",
                    "payload": {"focus": "private_mrr"},
                },
            ],
        }


class _RaisingAdviceProvider:
    def advise(self, _context: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("provider timeout contains implementation detail")


class _ResearchService:
    def __init__(self, response_overrides: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[UUID, QueueResearchJobRequest]] = []
        self._response_overrides = response_overrides or {}
        self._case_repository: _CaseRepository | None = None

    def bind_case_repository(self, case_repository: _CaseRepository) -> None:
        self._case_repository = case_repository

    def available_acquisition_modes(self) -> dict[str, tuple[str, ...] | str]:
        return {
            "available": ("deterministic_offline_fixture",),
            "unavailable": ("live_public_research",),
            "default": "deterministic_offline_fixture",
        }

    def queue_job(self, case_id: UUID, request: QueueResearchJobRequest) -> ResearchJobResponse:
        self.calls.append((case_id, request))
        payload = {
            "case_id": case_id,
            "job_id": uuid4(),
            "data_revision": 2,
            "status": "completed",
            "acquisition_mode": "live_public_research",
            "requested_acquisition_mode": "live_public_research",
            "selected_acquisition_mode": "live_public_research",
            "plan_id": request.plan_id,
            "plan_hash": request.plan_hash,
            "reason": None,
            "updated_at": "2026-08-22T00:00:00Z",
            "accepted_entries": [],
            "rejected_entries": [],
            "citations": [],
            "manual_only_keys": [],
            "changed_blocks": ["public_benchmarks", "scenarios"],
            "stale_scenario_ids": [],
            "old_revision": 1,
            "new_revision": 2,
            "source_refs": [],
        }
        payload.update(self._response_overrides)
        response = ResearchJobResponse.model_validate(payload)
        if (
            self._case_repository is not None
            and response.status in {"completed", "partial"}
            and type(response.new_revision) is int
        ):
            self._case_repository.set_revision(case_id, response.new_revision)
        return response


class _FailingInternalJobResearchService(_ResearchService):
    def __init__(self) -> None:
        super().__init__(
            response_overrides={
                "changed_blocks": ["market_research", "scenarios"],
                "accepted_entries": [],
                "citations": ["https://example.com/public-market"],
            }
        )

    def get_internal_job(self, _case_id: UUID, _job_id: UUID) -> object:
        raise RuntimeError("job-store-down")


class _PersistedSnapshotResearchService(_ResearchService):
    def __init__(self, snapshot: StartupMarketResearchSnapshot) -> None:
        super().__init__(
            response_overrides={
                "changed_blocks": ["market_research", "scenarios"],
                "accepted_entries": [],
                "citations": ["https://example.com/public-market"],
            }
        )
        self._snapshot = snapshot

    def get_internal_job(self, _case_id: UUID, _job_id: UUID) -> object:
        return type("PersistedResearchJob", (), {"live_market_research_snapshot": self._snapshot})()


def _live_market_snapshot(
    *,
    case_id: UUID,
    data_revision: int,
    source_status: StartupResearchSourceStatus = StartupResearchSourceStatus.INFERENCE,
) -> StartupMarketResearchSnapshot:
    source = StartupResearchSource.model_validate(
        {
            "source_id": UUID("55555555-5555-4555-8555-555555555555"),
            "source_mode": StartupResearchSourceMode.LIVE,
            "source_hash": "sha256:" + "1" * 64,
            "source_url": "https://example.com/public-market",
            "source_label": "Example Public Market",
            "as_of": datetime(2026, 8, 1, tzinfo=UTC).date(),
            "retrieved_at": datetime(2026, 8, 22, tzinfo=UTC),
            "query": "public market context",
            "provenance": "public_research",
            "confidence": Decimal("0.7"),
            "supports_primary_financial_metrics": False,
            "status": source_status,
        }
    )
    return StartupMarketResearchSnapshot.build(
        case_id=case_id,
        as_of=datetime(2026, 8, 22, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=UUID("77777777-7777-4777-8777-777777777777"),
        competitors=(),
        sources=(source,),
        sentiment_signals=(),
        assumptions=(),
        sizing=None,
        labels=("live_public_research",),
        data_revision=data_revision,
        public_benchmark_candidates=(),
    )


def _live_source_fact_graph_snapshot(
    *,
    case_id: UUID,
    data_revision: int,
) -> StartupMarketResearchSnapshot:
    source_id = UUID("11111111-1111-4111-8111-111111111111")
    assumption_id = UUID("33333333-3333-4333-8333-333333333333")
    source = StartupResearchSource.model_validate(
        {
            "source_id": source_id,
            "source_mode": StartupResearchSourceMode.LIVE,
            "source_hash": "sha256:" + "1" * 64,
            "source_url": "https://example.com/public-market",
            "source_label": "Example Public Market",
            "as_of": datetime(2026, 8, 1, tzinfo=UTC).date(),
            "retrieved_at": datetime(2026, 8, 22, tzinfo=UTC),
            "query": "public market context",
            "provenance": "public_research",
            "confidence": Decimal("0.7"),
            "supports_primary_financial_metrics": False,
            "status": StartupResearchSourceStatus.SOURCE_FACT,
        }
    )
    competitor = StartupCompetitor.model_validate(
        {
            "name": "Example Competitor",
            "category": StartupCompetitorCategory.DIRECT,
            "status": StartupResearchSourceStatus.SOURCE_FACT,
            "confidence": Decimal("0.7"),
            "source_ids": (source_id,),
        }
    )
    assumption = MarketSizingAssumption.model_validate(
        {
            "assumption_id": assumption_id,
            "text": "Comparable public category demand supports market sizing.",
            "status": StartupResearchSourceStatus.SOURCE_FACT,
            "confidence": Decimal("0.7"),
            "as_of": datetime(2026, 8, 1, tzinfo=UTC).date(),
            "source_mode": StartupResearchSourceMode.LIVE,
            "source_ids": (source_id,),
        }
    )
    sizing = StartupMarketSizing(
        tam=_market_size_estimate(
            estimate_id=UUID("44444444-4444-4444-8444-444444444444"),
            value=Decimal(1000000),
            source_id=source_id,
            assumption_id=assumption_id,
        ),
        sam=_market_size_estimate(
            estimate_id=UUID("55555555-5555-4555-8555-555555555555"),
            value=Decimal(500000),
            source_id=source_id,
            assumption_id=assumption_id,
        ),
        som=_market_size_estimate(
            estimate_id=UUID("66666666-6666-4666-8666-666666666666"),
            value=Decimal(100000),
            source_id=source_id,
            assumption_id=assumption_id,
        ),
    )
    return StartupMarketResearchSnapshot.build(
        case_id=case_id,
        as_of=datetime(2026, 8, 22, tzinfo=UTC),
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=UUID("77777777-7777-4777-8777-777777777777"),
        competitors=(competitor,),
        sources=(source,),
        sentiment_signals=(),
        assumptions=(assumption,),
        sizing=sizing,
        labels=("live_public_research",),
        data_revision=data_revision,
        public_benchmark_candidates=(),
    )


def _market_size_estimate(
    *,
    estimate_id: UUID,
    value: Decimal,
    source_id: UUID,
    assumption_id: UUID,
) -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=estimate_id,
        level=StartupResearchSourceStatus.SOURCE_FACT,
        value=value,
        unit="tenge",
        currency="kzt",
        as_of=datetime(2026, 8, 1, tzinfo=UTC).date(),
        source_mode=StartupResearchSourceMode.LIVE,
        formula_version="test@1",
        assumption_refs=(assumption_id,),
        source_refs=(source_id,),
        confidence=Decimal("0.7"),
    )


def _corrupt_action_replay_snapshot(assistant: dict[str, Any], corruption: str) -> None:
    snapshots = assistant["action_snapshots"]
    by_action = {snapshot["action"]: snapshot for snapshot in snapshots}
    if corruption == "missing_action":
        assistant["action_snapshots"] = snapshots[:-1]
    elif corruption == "extra_action":
        assistant["action_snapshots"] = [*snapshots, dict(snapshots[0])]
    elif corruption == "duplicate_action":
        assistant["action_snapshots"] = [dict(snapshots[0]), *snapshots[:-1]]
    elif corruption == "action_refs_mismatch":
        assistant["action_refs"] = assistant["action_refs"][:-1]
    elif corruption == "prepare_public_research_wrong_status":
        by_action["prepare_public_research"]["status"] = "available"
    elif corruption == "prepare_public_research_wrong_positive_revision":
        by_action["prepare_public_research"]["payload"]["expected_case_revision"] = 2
    elif corruption == "prepare_public_research_private_focus":
        by_action["prepare_public_research"]["payload"]["focus"] = "private_mrr"
    elif corruption == "prepare_public_research_invalid_revision":
        by_action["prepare_public_research"]["payload"]["expected_case_revision"] = 0
    elif corruption == "open_fact_input_source_fact":
        by_action["open_fact_input"]["payload"]["provenance"] = "source_fact"
    elif corruption == "open_fact_input_public_field":
        by_action["open_fact_input"]["payload"]["field_key"] = "public_pricing_analogs"
    elif corruption == "open_document_upload_foreign_case":
        by_action["open_document_upload"]["payload"]["case_id"] = str(CASE_B_ID)
    elif corruption == "blocked_with_handler":
        by_action["prepare_asset"]["handler"] = "prepareAsset"
    elif corruption == "available_without_handler":
        by_action["navigate"]["handler"] = None
    elif corruption == "handler_non_string":
        by_action["navigate"]["handler"] = 123
    elif corruption == "review_improvements_available_with_low_count":
        by_action["review_improvements"]["status"] = "available"
        by_action["review_improvements"]["handler"] = "openImprovementReview"
        by_action["review_improvements"]["reason"] = None
        by_action["review_improvements"]["payload"]["same_case_fact_count"] = 1
    elif corruption == "review_improvements_blocked_with_enough_count":
        by_action["review_improvements"]["status"] = "blocked"
        by_action["review_improvements"]["handler"] = None
        by_action["review_improvements"]["reason"] = "Corrupted blocker."
        by_action["review_improvements"]["payload"]["same_case_fact_count"] = 2
    elif corruption == "empty_effect_preview":
        by_action["navigate"]["effect_preview"] = ""
    elif corruption == "wrong_action_id":
        by_action["navigate"]["action_id"] = str(uuid4())
    else:
        raise AssertionError(f"unhandled corruption case: {corruption}")

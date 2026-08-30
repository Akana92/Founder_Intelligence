from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from due_diligence_agent.domain.startup.assets import CaseAssetDraft
from due_diligence_agent.domain.startup.copilot import (
    CopilotAction,
    CopilotMessage,
    CopilotQuestion,
    CopilotThread,
)


def test_copilot_question_action_and_message_are_case_revision_scoped_and_typed() -> None:
    case_id = uuid4()
    question = CopilotQuestion(
        question_id=uuid4(),
        case_id=case_id,
        data_revision=4,
        question_key="pricing_basis",
        prompt="What proof supports the monthly price range?",
        blocks_analysis=True,
    )
    action = CopilotAction(
        action_id=uuid4(),
        case_id=case_id,
        data_revision=4,
        action_key="open_fact_input",
        status="requires_input",
        effect_preview="Opens the source-fact input panel for pricing evidence.",
        payload={"question_id": str(question.question_id), "required_kind": "source_fact"},
    )
    message = CopilotMessage(
        message_id=uuid4(),
        case_id=case_id,
        data_revision=4,
        role="assistant",
        content="Please attach source evidence for pricing.",
        question_refs=(question.question_id,),
        action_refs=(action.action_id,),
    )

    assert action.status == "requires_input"
    assert action.action_key == "open_fact_input"
    assert action.effect_preview == "Opens the source-fact input panel for pricing evidence."
    assert message.role == "assistant"

    with pytest.raises(ValidationError, match="payload"):
        CopilotAction(
            action_id=uuid4(),
            case_id=case_id,
            data_revision=4,
            action_key="open_fact_input",
            status="requires_input",
            effect_preview="Opens the source-fact input panel for pricing evidence.",
            payload=(),
        )


def test_copilot_action_uses_exact_action_types_statuses_and_effect_preview() -> None:
    case_id = uuid4()

    allowed_actions = (
        "open_fact_input",
        "open_document_upload",
        "prepare_public_research",
        "explain_metric",
        "navigate",
        "prepare_asset",
        "review_improvements",
    )
    allowed_statuses = (
        "available",
        "requires_input",
        "requires_consent",
        "blocked",
    )

    for action_key in allowed_actions:
        for status in allowed_statuses:
            action = CopilotAction(
                action_id=uuid4(),
                case_id=case_id,
                data_revision=4,
                action_key=action_key,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                effect_preview="Shows the next visible case effect before execution.",
                payload={"target": action_key, "enabled": True},
            )
            assert action.action_key == action_key
            assert action.status == status

    with pytest.raises(ValidationError):
        CopilotAction(
            action_id=uuid4(),
            case_id=case_id,
            data_revision=4,
            action_key="request_pricing_evidence",  # type: ignore[arg-type]
            status="requires_input",
            effect_preview="Shows the next visible case effect before execution.",
            payload={"target": "pricing"},
        )

    with pytest.raises(ValidationError):
        CopilotAction(
            action_id=uuid4(),
            case_id=case_id,
            data_revision=4,
            action_key="open_fact_input",
            status="proposed",  # type: ignore[arg-type]
            effect_preview="Shows the next visible case effect before execution.",
            payload={"target": "pricing"},
        )

    with pytest.raises(ValidationError, match="effect preview"):
        CopilotAction(
            action_id=uuid4(),
            case_id=case_id,
            data_revision=4,
            action_key="open_fact_input",
            status="requires_input",
            effect_preview="",
            payload={"target": "pricing"},
        )


def test_copilot_thread_preserves_immutable_case_lifetime_history() -> None:
    case_id = uuid4()
    historical_message = CopilotMessage(
        message_id=uuid4(),
        case_id=case_id,
        data_revision=3,
        role="user",
        content="We only have an idea and no paid pilots yet.",
    )
    thread = CopilotThread(
        thread_id=uuid4(),
        case_id=case_id,
        data_revision=5,
        messages=(historical_message,),
    )

    assert thread.messages == (historical_message,)

    with pytest.raises(ValidationError, match="frozen_instance"):
        thread.data_revision = 6  # type: ignore[misc]

    with pytest.raises(ValidationError, match="same case_id"):
        CopilotThread(
            thread_id=uuid4(),
            case_id=case_id,
            data_revision=5,
            messages=(
                CopilotMessage(
                    message_id=uuid4(),
                    case_id=uuid4(),
                    data_revision=5,
                    role="user",
                    content="Different case",
                ),
            ),
        )

    with pytest.raises(ValidationError, match="future revisions"):
        CopilotThread(
            thread_id=uuid4(),
            case_id=case_id,
            data_revision=5,
            messages=(
                CopilotMessage(
                    message_id=uuid4(),
                    case_id=case_id,
                    data_revision=6,
                    role="user",
                    content="Future revision",
                ),
            ),
        )


def test_case_asset_draft_is_bound_to_revision_and_scenario_but_is_never_evidence() -> None:
    draft = CaseAssetDraft(
        draft_id=uuid4(),
        case_id=uuid4(),
        data_revision=6,
        scenario_set_id=uuid4(),
        draft_version=1,
        asset_key="investor_update",
        body_markdown="# Draft\n\nValidate pricing before sharing.",
        source_refs=(),
        dependency_refs=(uuid4(),),
    )

    assert draft.is_evidence is False

    with pytest.raises(ValidationError, match="never evidence"):
        CaseAssetDraft.model_validate({**draft.model_dump(), "is_evidence": True})

    with pytest.raises(ValidationError):
        CaseAssetDraft.model_validate({**draft.model_dump(), "draft_version": 0})


def test_case_asset_draft_preserves_markdown_body_verbatim() -> None:
    markdown = """
# GTM launch pack

Founder-visible draft.

- Keep provenance labels.
- Keep scenario validation plan.
""".strip()

    draft = CaseAssetDraft(
        draft_id=uuid4(),
        case_id=uuid4(),
        data_revision=6,
        scenario_set_id=uuid4(),
        draft_version=1,
        asset_key="gtm_launch_pack",
        body_markdown=markdown,
        source_refs=(),
        dependency_refs=(),
    )

    assert draft.body_markdown == markdown

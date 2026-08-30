from __future__ import annotations

from uuid import UUID

import pytest

from due_diligence_agent.application.services.startup_advisor_service import (
    StartupAdvisorService,
    advisor_field_key_for_contradiction,
    safe_contradiction_context,
)
from due_diligence_agent.domain.startup.advisor import AdvisorAnswer


CASE_A = UUID("00000000-0000-0000-0000-000000000001")
CASE_B = UUID("00000000-0000-0000-0000-000000000002")


def test_next_question_returns_only_the_highest_priority_missing_question() -> None:
    service = StartupAdvisorService()

    question = service.next_question(CASE_A)

    assert question is not None
    assert question.question_id == f"{CASE_A}:revenue_pricing"
    assert question.field_key == "revenue_pricing"
    assert "MRR" in question.unlocks_ru


def test_next_question_uses_profile_gaps_instead_of_fixed_revenue_first() -> None:
    service = StartupAdvisorService()

    question = service.next_question(
        CASE_A,
        profile_field_statuses={
            "revenue_pricing": "source_fact",
            "icp": "insufficient_data",
            "traction": "source_fact",
            "burn_cash": "insufficient_data",
            "gtm_channel": "insufficient_data",
        },
    )

    assert question is not None
    assert question.question_id == f"{CASE_A}:icp"
    assert question.field_key == "icp"
    assert question.origin == "document_gap"


def test_missing_core_profile_fields_outrank_secondary_metric_gaps() -> None:
    service = StartupAdvisorService()

    question = service.next_question(
        CASE_A,
        profile_field_statuses={
            "product": "insufficient_data",
            "problem": "source_fact",
            "stage": "source_fact",
            "revenue_pricing": "source_fact",
            "icp": "source_fact",
            "traction": "insufficient_data",
            "burn_cash": "insufficient_data",
            "gtm_channel": "insufficient_data",
        },
    )

    assert question is not None
    assert question.field_key == "product"
    assert question.origin == "document_gap"


def test_open_document_contradiction_outranks_generic_gap_question() -> None:
    service = StartupAdvisorService()

    question = service.next_question(
        CASE_A,
        profile_field_statuses={
            "product": "source_fact",
            "problem": "source_fact",
            "stage": "source_fact",
            "revenue_pricing": "source_fact",
            "icp": "insufficient_data",
        },
        contradiction_contexts=(
            {
                "field_key": "revenue_pricing",
                "metric_label": "MRR",
                "source_labels": ("CRM", "invoices", "bank"),
                "value_labels": ("28.6m ₸", "27.9m ₸"),
            },
        ),
    )

    assert question is not None
    assert question.field_key == "revenue_pricing"
    assert question.origin == "document_contradiction"
    assert "MRR" in question.question_ru
    assert "CRM" in question.question_ru
    assert "invoice" in question.question_ru or "bank" in question.question_ru
    assert "public_research" not in question.answer_modes


def test_safe_icp_contradiction_context_generates_icp_question_not_revenue_fallback() -> None:
    service = StartupAdvisorService()
    context = safe_contradiction_context(
        field_key=advisor_field_key_for_contradiction(
            conflict_type="explicit_source_conflict_signal",
            explanation=(
                "A source document explicitly flags a contradiction or conflict signal. "
                "Safe context: field=icp; metric=ICP; sources=agencies|enterprises."
            ),
        ),
        conflict_type="explicit_source_conflict_signal",
        explanation=(
            "A source document explicitly flags a contradiction or conflict signal. "
            "Safe context: field=icp; metric=ICP; sources=agencies|enterprises."
        ),
        status="open",
    )

    question = service.next_question(
        CASE_A,
        profile_field_statuses={
            "product": "source_fact",
            "problem": "source_fact",
            "stage": "source_fact",
            "revenue_pricing": "source_fact",
            "icp": "source_fact",
        },
        contradiction_contexts=(context,),
    )

    assert question is not None
    assert question.field_key == "icp"
    assert question.origin == "document_contradiction"
    assert "ICP" in question.question_ru
    assert "выруч" not in question.question_ru.casefold()
    assert "за какой период" not in question.question_ru.casefold()


def test_document_contradiction_priority_selects_mrr_before_lower_value_metric_contexts() -> None:
    service = StartupAdvisorService()
    contexts = (
        safe_contradiction_context(
            field_key="traction",
            conflict_type="explicit_source_conflict_signal",
            explanation=(
                "A source document explicitly flags a contradiction or conflict signal. "
                "Safe context: field=traction; metric=CAC payback; sources=crm|finance; values=4.3m|5.5m."
            ),
            status="open",
        ),
        safe_contradiction_context(
            field_key="revenue_pricing",
            conflict_type="explicit_source_conflict_signal",
            explanation=(
                "A source document explicitly flags a contradiction or conflict signal. "
                "Safe context: field=revenue_pricing; metric=MRR; sources=crm|invoices|bank; "
                "values=28.6m KZT|27.9m KZT."
            ),
            status="open",
        ),
    )

    question = service.next_question(
        CASE_A,
        profile_field_statuses={
            "product": "source_fact",
            "problem": "source_fact",
            "stage": "source_fact",
            "revenue_pricing": "source_fact",
            "icp": "source_fact",
            "traction": "source_fact",
        },
        contradiction_contexts=contexts,
    )

    assert question is not None
    assert question.field_key == "revenue_pricing"
    assert "MRR" in question.question_ru
    assert "28.6m KZT" in question.question_ru
    assert "27.9m KZT" in question.question_ru


def test_answered_dynamic_gap_is_skipped_even_when_ranking_changes() -> None:
    service = StartupAdvisorService()
    first = service.next_question(
        CASE_A,
        profile_field_statuses={
            "revenue_pricing": "source_fact",
            "icp": "insufficient_data",
        },
    )
    assert first is not None
    assert first.field_key == "icp"
    service.apply_answer(
        CASE_A,
        first.question_id,
        AdvisorAnswer(answer_type="skip", value=None),
        profile_field_statuses={"revenue_pricing": "source_fact", "icp": "insufficient_data"},
    )

    next_question = service.next_question(
        CASE_A,
        profile_field_statuses={
            "product": "source_fact",
            "problem": "source_fact",
            "stage": "source_fact",
            "revenue_pricing": "source_fact",
            "icp": "insufficient_data",
            "traction": "insufficient_data",
        },
    )

    assert next_question is not None
    assert next_question.field_key == "traction"


def test_answering_each_question_advances_in_hand_derived_priority_order() -> None:
    service = StartupAdvisorService()
    expected_field_keys = (
        "revenue_pricing",
        "icp",
        "traction",
        "burn_cash",
        "gtm_channel",
    )

    seen: list[str] = []
    for field_key in expected_field_keys:
        question = service.next_question(CASE_A)
        assert question is not None
        assert question.field_key == field_key
        seen.append(question.field_key)
        service.apply_answer(
            CASE_A,
            question.question_id,
            AdvisorAnswer(answer_type="manual", value="подтверждено"),
        )

    assert tuple(seen) == expected_field_keys
    assert service.next_question(CASE_A) is None


def test_skip_advances_analysis_and_reduces_confidence() -> None:
    service = StartupAdvisorService()

    delta = service.apply_answer(
        CASE_A,
        f"{CASE_A}:revenue_pricing",
        AdvisorAnswer(answer_type="skip", value=None),
    )

    assert delta.question_id == f"{CASE_A}:revenue_pricing"
    assert delta.field_key == "revenue_pricing"
    assert delta.confidence_delta == -1
    assert delta.analysis_blocked is False
    next_question = service.next_question(CASE_A)
    assert next_question is not None
    assert next_question.question_id == f"{CASE_A}:icp"


def test_answer_updates_only_the_current_question_for_its_case() -> None:
    service = StartupAdvisorService()

    with pytest.raises(ValueError, match="текущ"):
        service.apply_answer(
            CASE_A,
            f"{CASE_A}:icp",
            AdvisorAnswer(answer_type="manual", value="B2B SaaS"),
        )

    assert service.next_question(CASE_A) is not None
    assert service.next_question(CASE_A).question_id == f"{CASE_A}:revenue_pricing"
    assert service.next_question(CASE_B) is not None
    assert service.next_question(CASE_B).question_id == f"{CASE_B}:revenue_pricing"


def test_public_research_answer_with_consent_is_applied_without_running_research() -> None:
    service = StartupAdvisorService()
    first_question = service.next_question(CASE_A)
    assert first_question is not None
    service.apply_answer(
        CASE_A,
        first_question.question_id,
        AdvisorAnswer(answer_type="manual", value="подтверждено"),
    )
    question = service.next_question(CASE_A)
    assert question is not None
    assert question.field_key == "icp"

    delta = service.apply_answer(
        CASE_A,
        question.question_id,
        AdvisorAnswer(
            answer_type="public_research",
            value="ООО Пример",
            consent_public_research=True,
        ),
    )

    assert delta.answer_type == "public_research"
    assert delta.analysis_blocked is False


def test_private_questions_do_not_offer_public_research() -> None:
    service = StartupAdvisorService()

    for expected_field_key in ("revenue_pricing", "traction", "burn_cash"):
        question = service.next_question(CASE_A)
        assert question is not None
        assert question.field_key == expected_field_key or question.field_key == "icp"
        if question.field_key == "icp":
            service.apply_answer(
                CASE_A,
                question.question_id,
                AdvisorAnswer(answer_type="skip", value=None),
            )
            question = service.next_question(CASE_A)
            assert question is not None
        assert question.field_key == expected_field_key
        assert "public_research" not in question.answer_modes
        service.apply_answer(
            CASE_A,
            question.question_id,
            AdvisorAnswer(answer_type="skip", value=None),
        )


def test_private_public_research_is_rejected_in_russian_without_changing_state() -> None:
    service = StartupAdvisorService()
    question = service.next_question(CASE_A)
    assert question is not None

    with pytest.raises(ValueError, match="Публичный поиск.*недоступен"):
        service.apply_answer(
            CASE_A,
            question.question_id,
            AdvisorAnswer(
                answer_type="public_research",
                value="ООО Пример",
                consent_public_research=True,
            ),
        )

    assert service.next_question(CASE_A) == question


def test_question_from_another_case_is_rejected_without_changing_that_case() -> None:
    service = StartupAdvisorService()
    question_for_case_a = service.next_question(CASE_A)
    question_for_case_b = service.next_question(CASE_B)
    assert question_for_case_a is not None
    assert question_for_case_b is not None
    assert question_for_case_a.question_id != question_for_case_b.question_id

    with pytest.raises(ValueError, match="текущ"):
        service.apply_answer(
            CASE_B,
            question_for_case_a.question_id,
            AdvisorAnswer(answer_type="manual", value="B2B SaaS"),
        )

    assert service.next_question(CASE_B) == question_for_case_b


def test_stale_question_is_rejected_after_the_case_advances() -> None:
    service = StartupAdvisorService()
    first_question = service.next_question(CASE_A)
    assert first_question is not None
    service.apply_answer(
        CASE_A,
        first_question.question_id,
        AdvisorAnswer(answer_type="manual", value="подтверждено"),
    )
    current_question = service.next_question(CASE_A)
    assert current_question is not None

    with pytest.raises(ValueError, match="текущ"):
        service.apply_answer(
            CASE_A,
            first_question.question_id,
            AdvisorAnswer(answer_type="manual", value="устаревший ответ"),
        )

    assert service.next_question(CASE_A) == current_question

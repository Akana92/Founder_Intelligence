from __future__ import annotations

import pytest

from due_diligence_agent.domain.startup.advisor import AdvisorAnswer, AdvisorQuestion


def test_question_exposes_one_actionable_prompt_with_all_supported_answer_modes() -> None:
    question = AdvisorQuestion(
        question_id="revenue_pricing",
        field_key="revenue_pricing",
        question_ru="Какая у вас текущая выручка и модель ценообразования?",
        reason_ru="Это открывает расчёт MRR, ARR и валовой маржи.",
        unlocks_ru="MRR, ARR и валовая маржа",
        answer_modes=("manual", "file", "public_research", "skip"),
    )

    assert question.question_id == "revenue_pricing"
    assert question.answer_modes == ("manual", "file", "public_research", "skip")


def test_public_research_answer_preserves_missing_consent_for_service_policy() -> None:
    answer = AdvisorAnswer(answer_type="public_research")

    assert answer.consent_public_research is False
    assert answer.value is None


@pytest.mark.parametrize("answer_type", ["manual", "file", "public_research", "skip"])
def test_answer_accepts_each_supported_answer_mode(answer_type: str) -> None:
    answer = AdvisorAnswer(
        answer_type=answer_type,  # type: ignore[arg-type]
        value="данные" if answer_type != "skip" else None,
        consent_public_research=answer_type == "public_research",
    )

    assert answer.answer_type == answer_type


def test_question_exposes_a_russian_label_for_public_research() -> None:
    question = AdvisorQuestion(
        question_id="case-bound-question",
        field_key="icp",
        question_ru="Кто ваш основной клиентский сегмент и ICP?",
        reason_ru="Это уточняет позиционирование и круг конкурентов.",
        unlocks_ru="Позиционирование и конкуренты",
        answer_modes=("manual", "file", "public_research", "skip"),
    )

    assert question.answer_mode_labels_ru["public_research"] == "Публичный поиск"


def test_question_answer_mode_labels_are_deep_copied_between_instances() -> None:
    first = AdvisorQuestion(
        question_id="first",
        field_key="icp",
        question_ru="Кто ваш ICP?",
        reason_ru="Уточняет рынок.",
        unlocks_ru="Рынок",
        answer_modes=("public_research",),
    )
    second = AdvisorQuestion(
        question_id="second",
        field_key="gtm_channel",
        question_ru="Какой публичный GTM-канал релевантен?",
        reason_ru="Уточняет канал.",
        unlocks_ru="GTM",
        answer_modes=("public_research",),
    )

    first.answer_mode_labels_ru["public_research"] = "Изменено"

    assert second.answer_mode_labels_ru["public_research"] == "Публичный поиск"

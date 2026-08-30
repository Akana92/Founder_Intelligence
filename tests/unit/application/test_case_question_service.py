from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.application.services.case_question_service import (
    APPROVED_REQUIREMENT_KEYS,
    CaseQuestionService,
    RankedCopilotQuestion,
    _description_for,
    _label_for,
    _why_needed_for,
    requirement_registry,
)
from due_diligence_agent.domain.common import ContradictionStatus, FindingSeverity
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.domain.startup.case_intake import CaseStage
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)


CASE_ID = uuid5(NAMESPACE_URL, "case-question-service")
AS_OF = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def test_registry_covers_exact_approved_keys_with_required_boundaries() -> None:
    registry = requirement_registry()

    assert tuple(registry) == APPROVED_REQUIREMENT_KEYS
    for key, requirement in registry.items():
        assert requirement.key == key
        assert requirement.input_schema
        assert requirement.answer_modes
        assert requirement.privacy_class in {"manual_only", "public_context"}
        assert isinstance(requirement.researchable_public_context, bool)
        assert requirement.metric_dependencies is not None
        assert requirement.metric_impacts is not None
        assert requirement.stage_relevance
        assert requirement.validation_copy


def test_registry_copy_is_russian_and_hides_internal_requirement_codes() -> None:
    registry = requirement_registry()

    for key, requirement in registry.items():
        question = RankedCopilotQuestion(
            question_id=uuid5(CASE_ID, f"question:{key}"),
            case_id=CASE_ID,
            data_revision=1,
            question_key=f"startup_requirement:{key}",
            prompt=f"Уточните поле «{_label_for(key)}».",
            requirement_key=key,
            ranking_reason="stage_gap",
            answer_modes=requirement.answer_modes,
            privacy_class=requirement.privacy_class,
            blocks_analysis=False,
            unlocks=requirement.metric_impacts,
            validation_copy=requirement.validation_copy,
            input_schema=requirement.input_schema,
            label=_label_for(key),
            description=_description_for(key),
            why_needed=_why_needed_for(key),
            example="Пример",
        ).descriptor()
        visible_copy = " ".join(
            [
                requirement.validation_copy,
                question.label,
                question.description,
                question.why_needed,
                question.unlocks_copy,
                question.validation_guidance,
            ]
        )

        assert any("а" <= char.casefold() <= "я" or char in "ёЁ" for char in visible_copy)
        assert key not in visible_copy
        assert "icp_decision" not in visible_copy
        assert "scenario_metrics" not in visible_copy


def test_descriptor_includes_backend_owned_unlocks_copy_without_raw_codes() -> None:
    service = _service()

    cases = [
        ("gtm", "buyer", ("icp_decision", "purchase_trigger")),
        ("pricing", "monthly_price", ("mrr", "revenue", "scenario_pricing")),
        ("gtm", "channel", ("public_research_plan", "funnel")),
    ]
    for page_context, focus_key, raw_unlocks in cases:
        question = service.next_question_descriptor(
            CASE_ID,
            page_context=page_context,
            focus_key=focus_key,
        )

        assert question is not None
        assert question.unlocks == raw_unlocks
        assert question.unlocks_copy
        assert "icp_decision" not in question.unlocks_copy
        assert "scenario_pricing" not in question.unlocks_copy
        assert "public_research_plan" not in question.unlocks_copy


def test_idea_stage_ranks_buyer_before_actual_churn() -> None:
    question = _service().next_question(CASE_ID, page_context="overview", focus_key=None)

    assert question is not None
    question = cast(RankedCopilotQuestion, question)
    assert question.requirement_key == "buyer"
    assert "churn" not in question.unlocks


def test_page_focus_changes_question_priority() -> None:
    question = _service().next_question(
        CASE_ID,
        page_context="pricing",
        focus_key="monthly_price",
    )

    assert question is not None
    question = cast(RankedCopilotQuestion, question)
    assert question.requirement_key == "monthly_price"
    assert "mrr" in question.unlocks


def test_descriptor_copy_explains_selected_field_and_money_inputs() -> None:
    descriptor = _service().next_question_descriptor(
        CASE_ID,
        page_context="metrics",
        focus_key="mrr",
    )

    assert descriptor is not None
    assert descriptor.field_key == "mrr"
    assert "MRR" in descriptor.question
    assert "регулярную выручку" in descriptor.question
    assert "Публичный поиск не может подтвердить" in descriptor.description
    assert "ответ основателя" in descriptor.validation_guidance
    assert "подтверждённый факт" in descriptor.validation_guidance

    labels = {field.field_key: field.label for field in descriptor.input_schema.fields}
    placeholders = {
        field.field_key: field.placeholder for field in descriptor.input_schema.fields
    }
    assert labels["amount"] == "Сумма: MRR"
    assert labels["scale"] == "Масштаб суммы"
    assert labels["period"] == "Месяц, к которому относится сумма"
    assert labels["declared_source"] == "Источник суммы"
    assert "Введите только число" in placeholders["amount"]
    assert "единицы" in placeholders["scale"]
    assert "договор" in placeholders["validation_plan"]


def test_descriptor_copy_explains_text_answer_target_without_generic_label() -> None:
    descriptor = _service().next_question_descriptor(
        CASE_ID,
        page_context="gtm",
        focus_key="buyer",
    )

    assert descriptor is not None
    assert descriptor.field_key == "buyer"
    assert "кто принимает решение" in descriptor.question
    labels = {field.field_key: field.label for field in descriptor.input_schema.fields}
    assert labels["value"] == "Ответ по полю «Экономический покупатель»"
    assert labels["declared_source"] == "Источник ответа"
    assert labels["rationale"] == "Почему этот ответ подходит для кейса"
    assert labels["validation_plan"] == "Как владелец сможет проверить ответ"


def test_unresolved_contradiction_outranks_ordinary_gap() -> None:
    service = _service(
        contradictions=[
            _contradiction(
                "startup_explicit_metric_mrr",
                "MRR contradiction: CRM says 28.6m KZT and invoices say 27.9m KZT.",
            )
        ]
    )

    question = service.next_question(CASE_ID, page_context="overview", focus_key=None)

    assert question is not None
    question = cast(RankedCopilotQuestion, question)
    assert question.requirement_key == "mrr"
    assert question.ranking_reason == "unresolved_contradiction"
    assert "public_research" not in question.answer_modes


def test_skip_or_unknown_answer_routes_to_safe_next_gap() -> None:
    service = _service(answers={"buyer": "не знаю"})

    question = service.next_question(CASE_ID, page_context="overview", focus_key=None)

    assert question is not None
    question = cast(RankedCopilotQuestion, question)
    assert question.requirement_key == "purchase_trigger"
    assert question.ranking_reason == "safe_unknown_route"


def test_private_actuals_are_manual_only_but_market_context_can_prepare_research() -> None:
    service = _service()

    private_question = service.next_question(CASE_ID, page_context="metrics", focus_key="mrr")
    public_question = service.next_question(CASE_ID, page_context="gtm", focus_key="channel")

    assert private_question is not None
    private_question = cast(RankedCopilotQuestion, private_question)
    assert private_question.requirement_key == "mrr"
    assert private_question.privacy_class == "manual_only"
    assert "public_research" not in private_question.answer_modes
    assert public_question is not None
    public_question = cast(RankedCopilotQuestion, public_question)
    assert public_question.requirement_key == "channel"
    assert public_question.privacy_class == "public_context"
    assert "public_research" in public_question.answer_modes


def _service(
    *,
    answers: dict[str, str] | None = None,
    contradictions: list[Contradiction] | None = None,
) -> CaseQuestionService:
    return CaseQuestionService(
        case_repository=_CaseRepository(),
        profile_repository=_ProfileRepository(),
        assumption_repository=_AssumptionRepository(answers or {}),
        contradiction_repository=_ContradictionRepository(contradictions or []),
    )


class _CaseRepository:
    def get(self, case_id: UUID) -> object:
        assert case_id == CASE_ID
        return type("Case", (), {"case_id": CASE_ID, "data_revision": 1})()


class _ProfileRepository:
    def get_current(self, case_id: UUID) -> StartupProfile:
        assert case_id == CASE_ID
        return _profile()


class _AssumptionRepository:
    def __init__(self, answers: dict[str, str]) -> None:
        self._answers = answers

    def get_current(self, case_id: UUID) -> tuple[object, ...]:
        assert case_id == CASE_ID
        return tuple(
            type("Statement", (), {"field_key": key, "value": value})()
            for key, value in self._answers.items()
        )


class _ContradictionRepository:
    def __init__(self, contradictions: list[Contradiction]) -> None:
        self._contradictions = contradictions

    def list_for_case(self, case_id: UUID) -> list[Contradiction]:
        assert case_id == CASE_ID
        return list(self._contradictions)


def _profile() -> StartupProfile:
    source_values = {
        StartupProfileFieldName.PROBLEM: ("Inventory mismatch pain",),
        StartupProfileFieldName.SOLUTION: ("Planning copilot",),
        StartupProfileFieldName.ICP: ("FMCG distributors",),
        StartupProfileFieldName.STAGE: (CaseStage.IDEA.value,),
    }
    fields = {
        name.value: (
            StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.SOURCE_FACT,
                values=source_values[name],
                confidence=Decimal("0.8"),
                evidence_refs=(
                    StartupProfileEvidenceRef(
                        evidence_id=uuid5(CASE_ID, f"evidence:{name.value}"),
                        artifact_id=uuid5(CASE_ID, "artifact:profile"),
                        artifact_hash="sha256:" + "a" * 64,
                        locator_hash="sha256:" + "b" * 64,
                        field_name=name,
                        confidence=Decimal("0.8"),
                    ),
                ),
            )
            if name in source_values
            else StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal("0"),
                reason_code=f"{name.value}_missing",
            )
        )
        for name in StartupProfileFieldName
    }
    return StartupProfile.build(
        case_id=CASE_ID,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="deterministic-profile@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=1,
        source_hashes={"deck": "sha256:" + "a" * 64},
        parse_outcomes={"deck": "parsed"},
        fields=fields,
        gap_codes=("idea_case_gap",),
        case_revision_at=AS_OF,
    )


def _contradiction(conflict_type: str, explanation: str) -> Contradiction:
    return Contradiction(
        id=uuid5(CASE_ID, f"contradiction:{conflict_type}"),
        case_id=CASE_ID,
        conflict_type=conflict_type,
        fact_ids=(),
        explanation=explanation,
        severity=FindingSeverity.HIGH,
        status=ContradictionStatus.OPEN,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        detected_at=AS_OF,
    )

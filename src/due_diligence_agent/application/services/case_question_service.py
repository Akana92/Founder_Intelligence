from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field

from due_diligence_agent.application.case_copilot_contracts import (
    CaseQuestionDescriptorProjection,
    QuestionInputFieldProjection,
    QuestionInputSchemaProjection,
)
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.case_intake import CaseStage
from due_diligence_agent.domain.startup.copilot import CopilotQuestion

PrivacyClass = Literal["manual_only", "public_context"]
QuestionInputKind = Literal["text", "decimal", "select", "month"]
RankingReason = Literal[
    "unresolved_contradiction",
    "focused_context",
    "safe_unknown_route",
    "stage_gap",
]

APPROVED_REQUIREMENT_KEYS = (
    "problem",
    "solution",
    "icp",
    "buyer",
    "purchase_trigger",
    "pricing_revenue_model",
    "monthly_price",
    "launch_date",
    "team_capacity",
    "available_budget",
    "channel",
    "funnel",
    "revenue",
    "mrr",
    "burn",
    "cash_balance",
    "cogs",
    "gross_margin",
    "cac",
    "churn",
    "retention",
    "customer_count",
    "time_to_value",
)

_PRIVATE_ACTUAL_KEYS = frozenset(
    {
        "revenue",
        "mrr",
        "burn",
        "cash_balance",
        "customer_count",
        "churn",
        "retention",
        "cac",
        "cogs",
        "gross_margin",
    }
)
_PUBLIC_CONTEXT_KEYS = frozenset(
    {"icp", "buyer", "purchase_trigger", "channel", "funnel", "pricing_revenue_model"}
)
_IDEA_PRIORITY = (
    "buyer",
    "purchase_trigger",
    "monthly_price",
    "channel",
    "funnel",
    "launch_date",
    "team_capacity",
    "available_budget",
    "revenue",
    "mrr",
    "burn",
    "cash_balance",
    "customer_count",
    "churn",
)
_PAGE_CONTEXT_PRIORITY = {
    "pricing": ("monthly_price", "pricing_revenue_model", "revenue", "mrr"),
    "metrics": ("mrr", "revenue", "burn", "cash_balance", "customer_count"),
    "gtm": ("channel", "funnel", "purchase_trigger", "buyer"),
}
_UNLOCKS_BY_KEY = {
    "buyer": ("icp_decision", "purchase_trigger"),
    "purchase_trigger": ("channel", "funnel"),
    "monthly_price": ("mrr", "revenue", "scenario_pricing"),
    "channel": ("public_research_plan", "funnel"),
    "mrr": ("runway", "arr", "scenario_metrics"),
}
_REQUIREMENT_LABELS = {
    "problem": "Проблема клиента",
    "solution": "Решение",
    "icp": "Целевой сегмент клиентов",
    "buyer": "Экономический покупатель",
    "purchase_trigger": "Причина покупки сейчас",
    "pricing_revenue_model": "Модель цены и выручки",
    "monthly_price": "Средняя месячная цена",
    "launch_date": "Дата запуска",
    "team_capacity": "Ресурс команды",
    "available_budget": "Доступный бюджет",
    "channel": "Канал продаж",
    "funnel": "Воронка продаж",
    "revenue": "Выручка",
    "mrr": "MRR",
    "burn": "Месячный расход денег",
    "cash_balance": "Остаток денег",
    "cogs": "Себестоимость",
    "gross_margin": "Валовая маржа",
    "cac": "Стоимость привлечения клиента",
    "churn": "Отток клиентов",
    "retention": "Удержание клиентов",
    "customer_count": "Количество клиентов",
    "time_to_value": "Время до первой ценности",
}
_QUESTION_PROMPTS = {
    "problem": "Опишите проблему клиента: какую боль или потерю проект обещает убрать.",
    "solution": "Опишите продукт в одну строку: что именно получает клиент.",
    "icp": "Уточните целевой сегмент: для каких клиентов этот проект считается лучшим первым рынком.",
    "buyer": "Уточните экономического покупателя: кто принимает решение об оплате и бюджете.",
    "purchase_trigger": (
        "Уточните причину покупки сейчас: какое событие или боль заставляет клиента платить."
    ),
    "pricing_revenue_model": (
        "Опишите модель цены и выручки: за что клиент платит и как часто."
    ),
    "monthly_price": (
        "Укажите среднюю месячную цену: сколько один клиент платит или должен платить в месяц."
    ),
    "launch_date": "Укажите дату запуска или пилота: к какому месяцу относится план.",
    "team_capacity": "Уточните ресурс команды: кто и сколько времени реально может выполнять план.",
    "available_budget": "Укажите доступный бюджет: сколько денег можно направить на этот план.",
    "channel": "Уточните канал продаж: как проект будет находить первых клиентов.",
    "funnel": "Опишите воронку продаж: какие шаги ведут клиента от контакта до оплаты.",
    "revenue": "Укажите выручку: подтверждённую сумму за конкретный период.",
    "mrr": "Укажите MRR: регулярную выручку за один месяц.",
    "burn": "Укажите месячный расход денег: сколько проект тратит за один месяц.",
    "cash_balance": "Укажите остаток денег: сколько средств доступно на выбранный месяц.",
    "cogs": "Укажите себестоимость: прямые расходы на оказание услуги или продукт.",
    "gross_margin": "Укажите валовую маржу: долю выручки после прямых расходов.",
    "cac": "Укажите CAC: сколько стоит привлечение одного платящего клиента.",
    "churn": "Укажите отток клиентов: какая доля клиентов уходит за период.",
    "retention": "Укажите удержание клиентов: какая доля клиентов остаётся за период.",
    "customer_count": "Укажите количество клиентов: сколько платящих клиентов подтверждено.",
    "time_to_value": "Укажите время до первой ценности: когда клиент получает первый результат.",
}
_UNLOCK_LABELS = {
    "icp_decision": "выбор целевого сегмента",
    "purchase_trigger": "причину покупки сейчас",
    "channel": "канал продаж",
    "funnel": "воронку продаж",
    "mrr": "MRR",
    "revenue": "выручку",
    "scenario_pricing": "ценовой сценарий",
    "public_research_plan": "план публичного поиска",
    "runway": "запас времени до нехватки денег",
    "arr": "ARR",
    "scenario_metrics": "сценарные метрики",
    "ltv": "LTV",
    "cac": "стоимость привлечения клиента",
    "churn": "отток клиентов",
}
_CONTRADICTION_KEYWORDS = {
    "mrr": ("mrr", "monthly_recurring_revenue"),
    "revenue": ("revenue", "выруч"),
    "burn": ("burn",),
    "cash_balance": ("cash",),
    "customer_count": ("customer",),
    "gross_margin": ("margin",),
    "cac": ("cac",),
    "churn": ("churn",),
}
_UNKNOWN_VALUES = frozenset({"не знаю", "unknown", "dont know", "don't know", "skip"})


@dataclass(frozen=True)
class CaseRequirementDefinition:
    key: str
    input_schema: dict[str, str]
    answer_modes: tuple[str, ...]
    privacy_class: PrivacyClass
    searchable_public_context: bool
    metric_dependencies: tuple[str, ...]
    metric_impacts: tuple[str, ...]
    stage_relevance: tuple[CaseStage, ...]
    validation_copy: str

    @property
    def researchable_public_context(self) -> bool:
        return self.searchable_public_context


class RankedCopilotQuestion(CopilotQuestion):
    requirement_key: str
    input_schema: dict[str, str]
    label: str
    description: str
    why_needed: str
    example: str
    unlocks: tuple[str, ...] = Field(default_factory=tuple)
    ranking_reason: RankingReason
    privacy_class: PrivacyClass
    answer_modes: tuple[str, ...] = Field(default_factory=tuple)
    validation_copy: str

    def descriptor(self) -> CaseQuestionDescriptorProjection:
        return CaseQuestionDescriptorProjection(
            question_id=self.question_id,
            field_key=self.requirement_key,
            question=self.prompt,
            label=self.label,
            description=self.description,
            why_needed=self.why_needed,
            unlocks=self.unlocks,
            unlocks_copy=_unlocks_copy_for(self.unlocks),
            example=self.example,
            validation_guidance=self.validation_copy,
            provenance=CaseValueKind.FOUNDER_STATEMENT,
            input_schema=_question_input_schema(self.requirement_key, self.input_schema),
        )


class CaseQuestionService:
    def __init__(
        self,
        *,
        case_repository: Any,
        profile_repository: Any,
        assumption_repository: Any,
        contradiction_repository: Any,
    ) -> None:
        self._case_repository = case_repository
        self._profile_repository = profile_repository
        self._assumption_repository = assumption_repository
        self._contradiction_repository = contradiction_repository
        self._registry = requirement_registry()

    def next_question(
        self,
        case_id: UUID,
        *,
        page_context: str,
        focus_key: str | None,
    ) -> CopilotQuestion | None:
        case = self._case_repository.get(case_id)
        revision = int(getattr(case, "data_revision", 1))
        answered = self._answered_values(case_id)
        contradiction_key = self._unresolved_contradiction_key(case_id)
        if contradiction_key is not None:
            return self._question(
                case_id,
                revision,
                contradiction_key,
                ranking_reason="unresolved_contradiction",
            )

        if focus_key in self._registry and focus_key not in answered:
            return self._question(
                case_id,
                revision,
                focus_key,
                ranking_reason="focused_context",
            )

        page_keys = _PAGE_CONTEXT_PRIORITY.get(page_context.casefold(), ())
        for key in page_keys:
            if key not in answered:
                return self._question(
                    case_id,
                    revision,
                    key,
                    ranking_reason="focused_context",
                )

        skipped_unknowns = {
            key for key, value in answered.items() if _normalize_answer(value) in _UNKNOWN_VALUES
        }
        if "buyer" in skipped_unknowns and "purchase_trigger" not in answered:
            return self._question(
                case_id,
                revision,
                "purchase_trigger",
                ranking_reason="safe_unknown_route",
            )

        stage = self._stage(case_id)
        priority = _IDEA_PRIORITY if stage is CaseStage.IDEA else APPROVED_REQUIREMENT_KEYS
        for key in priority:
            if key not in answered and not self._is_source_supported(case_id, key):
                return self._question(case_id, revision, key, ranking_reason="stage_gap")
        return None

    def next_question_descriptor(
        self,
        case_id: UUID,
        *,
        page_context: str,
        focus_key: str | None,
    ) -> CaseQuestionDescriptorProjection | None:
        question = self.next_question(case_id, page_context=page_context, focus_key=focus_key)
        if question is None:
            return None
        if isinstance(question, RankedCopilotQuestion):
            return question.descriptor()
        return None

    def stage(self, case_id: UUID) -> CaseStage:
        return self._stage(case_id)

    def _question(
        self,
        case_id: UUID,
        revision: int,
        key: str,
        *,
        ranking_reason: RankingReason,
    ) -> RankedCopilotQuestion:
        requirement = self._registry[key]
        return RankedCopilotQuestion(
            question_id=uuid5(NAMESPACE_URL, f"case-question:{case_id}:{revision}:{key}"),
            case_id=case_id,
            data_revision=revision,
            question_key=key,
            requirement_key=key,
            input_schema=requirement.input_schema,
            prompt=_question_text_for(key),
            label=_label_for(key),
            description=_description_for(key),
            why_needed=_why_needed_for(key),
            example=_example_for(key),
            blocks_analysis=key in _PRIVATE_ACTUAL_KEYS,
            unlocks=_UNLOCKS_BY_KEY.get(key, ()),
            ranking_reason=ranking_reason,
            privacy_class=requirement.privacy_class,
            answer_modes=requirement.answer_modes,
            validation_copy=requirement.validation_copy,
        )

    def _answered_values(self, case_id: UUID) -> dict[str, str]:
        try:
            statements = self._assumption_repository.get_current(case_id)
        except (KeyError, ValueError):
            return {}
        return {
            str(statement.field_key): str(statement.value)
            for statement in statements
            if getattr(statement, "field_key", None) is not None
        }

    def _stage(self, case_id: UUID) -> CaseStage:
        return resolve_case_stage(self._profile_repository, case_id)

    def _is_source_supported(self, case_id: UUID, key: str) -> bool:
        profile_field = {
            "problem": "problem",
            "solution": "solution",
            "icp": "icp",
            "buyer": "buyers",
            "pricing_revenue_model": "pricing_revenue_model",
            "channel": "channels_gtm",
        }.get(key)
        if profile_field is None:
            return False
        try:
            profile = self._profile_repository.get_current(case_id)
        except (KeyError, ValueError):
            return False
        field = getattr(profile, "fields", {}).get(profile_field)
        return str(getattr(field, "status", "")).casefold() == "source_fact"

    def _unresolved_contradiction_key(self, case_id: UUID) -> str | None:
        try:
            contradictions = self._contradiction_repository.list_for_case(case_id)
        except (KeyError, ValueError):
            return None
        for contradiction in contradictions:
            status = str(getattr(contradiction, "status", "")).casefold()
            if status not in {"open", "awaiting_evidence", "unresolved"}:
                continue
            haystack = (
                f"{getattr(contradiction, 'conflict_type', '')} "
                f"{getattr(contradiction, 'explanation', '')}"
            ).casefold()
            for key, needles in _CONTRADICTION_KEYWORDS.items():
                if any(needle in haystack for needle in needles):
                    return key
        return None


def requirement_registry() -> dict[str, CaseRequirementDefinition]:
    return {
        key: CaseRequirementDefinition(
            key=key,
            input_schema=_input_schema_for(key),
            answer_modes=_answer_modes_for(key),
            privacy_class=_privacy_class_for(key),
            searchable_public_context=key in _PUBLIC_CONTEXT_KEYS,
            metric_dependencies=_metric_dependencies_for(key),
            metric_impacts=_metric_impacts_for(key),
            stage_relevance=_stage_relevance_for(key),
            validation_copy=(
                f"Ответ сохранится как ответ основателя для поля «{_label_for(key)}», "
                "а не как подтверждённый факт. Укажите источник ответа и способ проверки. "
                "Пример служит только подсказкой и не сохраняется как значение."
            ),
        )
        for key in APPROVED_REQUIREMENT_KEYS
    }


def _answer_modes_for(key: str) -> tuple[str, ...]:
    modes = ["manual", "file", "skip"]
    if key in _PUBLIC_CONTEXT_KEYS:
        modes.append("public_research")
    return tuple(modes)


def _privacy_class_for(key: str) -> PrivacyClass:
    return "manual_only" if key in _PRIVATE_ACTUAL_KEYS else "public_context"


def _input_schema_for(key: str) -> dict[str, str]:
    if key in _PRIVATE_ACTUAL_KEYS or key == "monthly_price":
        return {
            "amount": "required",
            "scale": "required",
            "currency": "required",
            "period": "required",
            "declared_source": "required",
            "rationale": "required",
            "validation_plan": "required",
        }
    if key == "available_budget":
        return {
            "amount": "required",
            "scale": "required",
            "currency": "required",
            "period": "optional",
            "declared_source": "required",
            "rationale": "required",
            "validation_plan": "required",
        }
    return {
        "value": "required",
        "declared_source": "required",
        "rationale": "required",
        "validation_plan": "required",
    }


def _question_input_schema(
    key: str,
    input_schema: dict[str, str],
) -> QuestionInputSchemaProjection:
    money = "amount" in input_schema
    label = _label_for(key)
    money_field_specs: tuple[tuple[str, str, QuestionInputKind, str], ...] = (
        (
            "amount",
            f"Сумма: {label}",
            "decimal",
            "Введите только число, например: 1850000",
        ),
        (
            "scale",
            "Масштаб суммы",
            "select",
            "Выберите единицы, тысячи или миллионы",
        ),
        ("currency", "Валюта суммы", "text", "Например: KZT или USD"),
        ("period", "Месяц, к которому относится сумма", "month", "Например: 2026-07"),
        (
            "declared_source",
            "Источник суммы",
            "text",
            "Например: интервью с основателем, счёт, CRM или банк",
        ),
        (
            "rationale",
            "Почему эта сумма подходит для сценария",
            "text",
            "Например: это регулярная выручка без разовых платежей",
        ),
        (
            "validation_plan",
            "Как владелец сможет проверить сумму",
            "text",
            "Например: сверить с договорами, счетами, CRM или банковской выпиской",
        ),
    )
    fields = (
        tuple(
            _input_field(
                field_key,
                field_label,
                input_kind,
                placeholder,
                input_schema[field_key] == "required",
            )
            for field_key, field_label, input_kind, placeholder in money_field_specs
            if field_key in input_schema
        )
        if money
        else (
            _input_field(
                "value",
                f"Ответ по полю «{label}»",
                "text",
                f"Например: {_example_for(key)}",
            ),
            _input_field(
                "declared_source",
                "Источник ответа",
                "text",
                "Например: интервью с основателем или загруженный документ",
            ),
            _input_field(
                "rationale",
                "Почему этот ответ подходит для кейса",
                "text",
                "Например: это тот сегмент, который указан владельцем как первый рынок",
            ),
            _input_field(
                "validation_plan",
                "Как владелец сможет проверить ответ",
                "text",
                "Например: подтвердить документом, CRM, письмом клиента или интервью",
            ),
        )
    )
    return QuestionInputSchemaProjection(kind="money" if money else "text", fields=fields)


def _input_field(
    field_key: str,
    label: str,
    input_kind: QuestionInputKind,
    placeholder: str,
    required: bool = True,
) -> QuestionInputFieldProjection:
    return QuestionInputFieldProjection(
        field_key=field_key,
        label=label,
        input_kind=input_kind,
        required=required,
        placeholder=placeholder,
    )


def _question_text_for(key: str) -> str:
    return _QUESTION_PROMPTS.get(
        key,
        f"Уточните поле «{_label_for(key)}» для текущего кейса.",
    )


def _label_for(key: str) -> str:
    return _REQUIREMENT_LABELS[key]


def _description_for(key: str) -> str:
    if key in _PRIVATE_ACTUAL_KEYS or key in {"monthly_price", "available_budget"}:
        return (
            "Введите ручную сумму от основателя или из его документов. "
            "Публичный поиск не может подтвердить внутреннюю регулярную выручку, "
            "остаток денег, расходы, клиентов, договоры, счета или банк."
        )
    return "Короткий текстовый ответ основателя, привязанный к текущему кейсу."


def _why_needed_for(key: str) -> str:
    unlocks = ", ".join(
        _UNLOCK_LABELS.get(unlock, "следующий шаг анализа")
        for unlock in _UNLOCKS_BY_KEY.get(key, ())
    ) or "следующий шаг анализа"
    return f"Это нужно, чтобы безопасно открыть: {unlocks}."


def _unlocks_copy_for(unlocks: tuple[str, ...]) -> str:
    if not unlocks:
        return "Этот ответ помогает продолжить анализ без предположений."
    visible_unlocks = ", ".join(
        _UNLOCK_LABELS.get(unlock, "следующий шаг анализа") for unlock in unlocks
    )
    return f"Этот ответ открывает: {visible_unlocks}."


def _example_for(key: str) -> str:
    examples = {
        "buyer": "операционный директор сети университетов",
        "purchase_trigger": "ручная подготовка отчётов занимает слишком много времени",
        "channel": "прямые продажи через пилот с одним факультетом",
        "mrr": "1850000 KZT за июль 2026",
        "monthly_price": "35000 KZT за организацию в месяц",
    }
    return examples.get(key, "ответ основателя с указанием источника")


def _metric_dependencies_for(key: str) -> tuple[str, ...]:
    dependencies = {
        "mrr": ("monthly_price", "customer_count"),
        "revenue": ("monthly_price", "customer_count"),
        "gross_margin": ("revenue", "cogs"),
        "burn": ("team_capacity", "available_budget"),
        "cash_balance": ("available_budget",),
        "churn": ("retention",),
    }
    return dependencies.get(key, ())


def _metric_impacts_for(key: str) -> tuple[str, ...]:
    impacts = {
        "monthly_price": ("mrr", "arr", "ltv"),
        "customer_count": ("mrr", "cac", "churn"),
        "mrr": ("arr", "runway"),
        "burn": ("runway",),
        "cash_balance": ("runway",),
        "channel": ("cac", "funnel"),
    }
    return impacts.get(key, ())


def _stage_relevance_for(key: str) -> tuple[CaseStage, ...]:
    if key in {"churn", "retention", "customer_count", "mrr", "revenue"}:
        return (CaseStage.FIRST_SALES, CaseStage.GROWTH)
    return (CaseStage.IDEA, CaseStage.FIRST_SALES, CaseStage.GROWTH)


def resolve_case_stage(profile_repository: Any, case_id: UUID) -> CaseStage:
    try:
        profile = profile_repository.get_current(case_id)
    except (KeyError, ValueError):
        return CaseStage.IDEA
    field = getattr(profile, "fields", {}).get("stage")
    values = tuple(getattr(field, "values", ()) or ())
    normalized = " ".join(str(value) for value in values).casefold()
    if "growth" in normalized:
        return CaseStage.GROWTH
    if (
        "sale" in normalized
        or "revenue" in normalized
        or "pre-scale" in normalized
        or "pre scale" in normalized
        or "working product" in normalized
        or "launched product" in normalized
    ):
        return CaseStage.FIRST_SALES
    return CaseStage.IDEA


def _normalize_answer(value: str) -> str:
    return " ".join(value.strip().casefold().split())


__all__ = [
    "APPROVED_REQUIREMENT_KEYS",
    "CaseQuestionService",
    "CaseRequirementDefinition",
    "RankedCopilotQuestion",
    "requirement_registry",
    "resolve_case_stage",
]

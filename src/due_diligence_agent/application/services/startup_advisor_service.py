from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Final
from uuid import UUID

from due_diligence_agent.domain.startup.advisor import AdvisorAnswer, AdvisorDelta, AdvisorQuestion


_QUESTION_PRIORITY: Final[tuple[AdvisorQuestion, ...]] = (
    AdvisorQuestion(
        question_id="product",
        field_key="product",
        question_ru="Опишите продукт в одну строку.",
        reason_ru="Это фиксирует, что именно анализирует команда.",
        unlocks_ru="Профиль продукта",
        answer_modes=("manual", "file", "skip"),
    ),
    AdvisorQuestion(
        question_id="problem",
        field_key="problem",
        question_ru="Какую ключевую проблему клиента вы решаете?",
        reason_ru="Это связывает продукт с болью клиента и доказательствами спроса.",
        unlocks_ru="Проблема клиента",
        answer_modes=("manual", "file", "skip"),
    ),
    AdvisorQuestion(
        question_id="stage",
        field_key="stage",
        question_ru="На какой стадии сейчас стартап?",
        reason_ru="Это калибрует метрики, риски и ожидания инвестора.",
        unlocks_ru="Стадия и критерии оценки",
        answer_modes=("manual", "file", "skip"),
    ),
    AdvisorQuestion(
        question_id="revenue_pricing",
        field_key="revenue_pricing",
        question_ru="Какая у вас текущая выручка и модель ценообразования?",
        reason_ru="Это открывает расчёт MRR, ARR и валовой маржи.",
        unlocks_ru="MRR, ARR и валовая маржа",
        answer_modes=("manual", "file", "skip"),
    ),
    AdvisorQuestion(
        question_id="icp",
        field_key="icp",
        question_ru="Кто ваш основной клиентский сегмент и ICP?",
        reason_ru="Это уточняет позиционирование и круг конкурентов.",
        unlocks_ru="Позиционирование и конкуренты",
        answer_modes=("manual", "file", "public_research", "skip"),
    ),
    AdvisorQuestion(
        question_id="traction",
        field_key="traction",
        question_ru="Какая у стартапа текущая traction?",
        reason_ru="Это позволяет оценить готовность бизнеса.",
        unlocks_ru="Оценка готовности",
        answer_modes=("manual", "file", "skip"),
    ),
    AdvisorQuestion(
        question_id="burn_cash",
        field_key="burn_cash",
        question_ru="Каковы текущие burn и остаток денежных средств?",
        reason_ru="Это открывает расчёт runway.",
        unlocks_ru="Runway",
        answer_modes=("manual", "file", "skip"),
    ),
    AdvisorQuestion(
        question_id="gtm_channel",
        field_key="gtm_channel",
        question_ru="Какой GTM-канал является основным?",
        reason_ru="Это помогает сформировать план действий.",
        unlocks_ru="План действий",
        answer_modes=("manual", "file", "public_research", "skip"),
    ),
)
_LEGACY_STATIC_FIELD_KEYS: Final[frozenset[str]] = frozenset(
    {"revenue_pricing", "icp", "traction", "burn_cash", "gtm_channel"}
)
_OPEN_CONTRADICTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"open", "awaiting_evidence", "unresolved"}
)
_ORIGIN_LABELS_RU: Final[dict[str, str]] = {
    "static": "Базовый сценарий",
    "document_gap": "Пробел в документе",
    "document_contradiction": "Противоречие в документе",
    "answered_state": "Уже отвечено",
}
_SAFE_TOKEN_RE = re.compile(r"[\w.%$€₸₽-]+", re.IGNORECASE)
_METRIC_FIELD_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("icp", "field=icp"),
    ("icp", "metric=icp"),
    ("icp", "customer segment"),
    ("icp", "client segment"),
    ("icp", "agencies"),
    ("icp", "enterprises"),
    ("revenue_pricing", "field=revenue_pricing"),
    ("revenue_pricing", "mrr"),
    ("revenue_pricing", "arr"),
    ("revenue_pricing", "выруч"),
    ("revenue_pricing", "pricing"),
    ("revenue_pricing", "тариф"),
    ("revenue_pricing", "customer"),
    ("revenue_pricing", "клиент"),
    ("burn_cash", "burn"),
    ("burn_cash", "runway"),
    ("traction", "traction"),
    ("traction", "cac"),
    ("traction", "margin"),
)
_SAFE_CONTEXT_VALUE_RE = re.compile(r"(?i)(?:^|[;\s])(?P<key>field|metric|sources|values)=(?P<value>[^;]+)")
_CONTRADICTION_PRIORITY: Final[dict[str, int]] = {
    "MRR": 0,
    "ARR": 1,
    "ICP": 10,
    "customer count": 20,
    "CAC payback": 30,
    "gross margin": 40,
    "валовой марже": 40,
}


class StartupAdvisorService:
    """Keeps the smallest in-memory state needed for a progressive question loop."""

    def __init__(self) -> None:
        self._answered_question_ids_by_case: dict[UUID, set[str]] = {}

    def next_question(
        self,
        case_id: UUID,
        *,
        profile_field_statuses: Mapping[str, str] | None = None,
        contradiction_contexts: tuple[Mapping[str, object], ...] = (),
    ) -> AdvisorQuestion | None:
        answered_question_ids = self._answered_question_ids_by_case.get(case_id, set())
        contradiction_question = _question_for_contradiction(
            case_id=case_id,
            answered_question_ids=answered_question_ids,
            contradiction_contexts=contradiction_contexts,
        )
        if contradiction_question is not None:
            return contradiction_question
        candidates = (
            _QUESTION_PRIORITY
            if profile_field_statuses is not None
            else tuple(
                question
                for question in _QUESTION_PRIORITY
                if question.field_key in _LEGACY_STATIC_FIELD_KEYS
            )
        )
        question = next(
            (
                question
                for question in candidates
                if question.question_id not in answered_question_ids
                and _question_needs_answer(question, profile_field_statuses)
            ),
            None,
        )
        if question is None:
            return None
        origin = "static" if profile_field_statuses is None else "document_gap"
        return _with_case_and_origin(question, case_id=case_id, origin=origin)

    def total_count(
        self,
        *,
        profile_field_statuses: Mapping[str, str] | None = None,
        contradiction_contexts: tuple[Mapping[str, object], ...] = (),
    ) -> int:
        return len(
            self.total_field_keys(
                profile_field_statuses=profile_field_statuses,
                contradiction_contexts=contradiction_contexts,
            )
        )

    def total_field_keys(
        self,
        *,
        profile_field_statuses: Mapping[str, str] | None = None,
        contradiction_contexts: tuple[Mapping[str, object], ...] = (),
    ) -> frozenset[str]:
        candidates = (
            _QUESTION_PRIORITY
            if profile_field_statuses is not None
            else tuple(
                question
                for question in _QUESTION_PRIORITY
                if question.field_key in _LEGACY_STATIC_FIELD_KEYS
            )
        )
        needed = {
            question.field_key
            for question in candidates
            if _question_needs_answer(question, profile_field_statuses)
        }
        for context in contradiction_contexts:
            status = (_safe_string(context.get("status")) or "open").casefold()
            field_key = _safe_string(context.get("field_key")) or "revenue_pricing"
            if status in _OPEN_CONTRADICTION_STATUSES:
                needed.add(field_key)
        return frozenset(needed)

    def apply_answer(
        self,
        case_id: UUID,
        question_id: str,
        answer: AdvisorAnswer,
        *,
        profile_field_statuses: Mapping[str, str] | None = None,
        contradiction_contexts: tuple[Mapping[str, object], ...] = (),
    ) -> AdvisorDelta:
        question = self.next_question(
            case_id,
            profile_field_statuses=profile_field_statuses,
            contradiction_contexts=contradiction_contexts,
        )
        if question is None or question.question_id != question_id:
            raise ValueError("Ответ можно применить только к текущему вопросу.")
        if answer.answer_type == "public_research" and answer.answer_type not in question.answer_modes:
            raise ValueError("Публичный поиск недоступен для этого внутреннего вопроса.")

        self._answered_question_ids_by_case.setdefault(case_id, set()).add(question.field_key)
        return AdvisorDelta(
            case_id=case_id,
            question_id=question.question_id,
            field_key=question.field_key,
            answer_type=answer.answer_type,
            confidence_delta=-1 if answer.answer_type == "skip" else 0,
            analysis_blocked=False,
        )

    def mark_answered(self, case_id: UUID, field_key: str) -> None:
        if field_key not in {question.field_key for question in _QUESTION_PRIORITY}:
            raise ValueError("advisor_progress_invalid")
        self._answered_question_ids_by_case.setdefault(case_id, set()).add(field_key)


def _question_needs_answer(
    question: AdvisorQuestion,
    profile_field_statuses: Mapping[str, str] | None,
) -> bool:
    if profile_field_statuses is None:
        return True
    status = profile_field_statuses.get(question.field_key)
    if status is None:
        return False
    return status not in {"source_fact", "inference"}


def _with_case_and_origin(
    question: AdvisorQuestion,
    *,
    case_id: UUID,
    origin: str,
    context_ru: str | None = None,
) -> AdvisorQuestion:
    return question.model_copy(
        update={
            "question_id": f"{case_id}:{question.field_key}",
            "origin": origin,
            "origin_label_ru": _ORIGIN_LABELS_RU[origin],
            "context_ru": context_ru,
        }
    )


def _question_for_contradiction(
    *,
    case_id: UUID,
    answered_question_ids: set[str],
    contradiction_contexts: tuple[Mapping[str, object], ...],
) -> AdvisorQuestion | None:
    for context in sorted(contradiction_contexts, key=_contradiction_priority):
        field_key = _safe_string(context.get("field_key")) or "revenue_pricing"
        status = (_safe_string(context.get("status")) or "open").casefold()
        if field_key in answered_question_ids or status not in _OPEN_CONTRADICTION_STATUSES:
            continue
        base = next(
            (question for question in _QUESTION_PRIORITY if question.field_key == field_key),
            None,
        )
        if base is None:
            continue
        metric_label = _safe_string(context.get("metric_label")) or "метрике"
        source_labels = _safe_list(context.get("source_labels"))
        value_labels = _safe_list(context.get("value_labels"))
        bound_contradiction_id = _safe_uuid(context.get("contradiction_id"))
        source_text = " и ".join(source_labels[:3]) if source_labels else "источниками"
        value_text = " и ".join(value_labels[:2]) if value_labels else "разными значениями"
        if field_key == "icp":
            question_ru = (
                f"В документе есть противоречие по {metric_label}: {source_text} "
                "описаны как разные целевые сегменты. Какой сегмент считать основным ICP?"
            )
            context_ru = f"Нужно сверить {metric_label} между {source_text}."
            unlocks_ru = "ICP, позиционирование и конкуренты"
        else:
            question_ru = (
                f"В документе есть противоречие по {metric_label}: {source_text} "
                f"показывают {value_text}. Какое значение считать рабочим и за какой период?"
            )
            context_ru = f"Нужно сверить {metric_label} между {source_text}."
            unlocks_ru = "Сверка метрик и пересчёт"
        return _with_case_and_origin(
            base.model_copy(
                update={
                    "question_ru": question_ru,
                    "reason_ru": "Это снимает противоречие в исходном документе перед расчётами.",
                    "unlocks_ru": unlocks_ru,
                    "answer_modes": ("manual", "file", "skip"),
                    "bound_contradiction_id": bound_contradiction_id,
                }
            ),
            case_id=case_id,
            origin="document_contradiction",
            context_ru=context_ru,
        )
    return None


def _safe_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def advisor_field_key_for_contradiction(*, conflict_type: str, explanation: str) -> str:
    normalized = f"{conflict_type} {explanation}".casefold()
    for field_key, marker in _METRIC_FIELD_HINTS:
        if marker in normalized:
            return field_key
    return "revenue_pricing"


def safe_contradiction_context(
    *,
    field_key: str,
    conflict_type: str,
    explanation: str,
    status: str,
) -> dict[str, object]:
    parsed = _parse_safe_context(explanation)
    parsed_field_key = _safe_context_field(parsed.get("field"))
    tokens = _safe_tokens(explanation)
    metric_label = _metric_label(conflict_type=conflict_type, tokens=tokens)
    if parsed.get("metric"):
        metric_label = _clean_public_token(parsed["metric"])
    return {
        "field_key": parsed_field_key or field_key,
        "status": status,
        "metric_label": metric_label,
        "source_labels": _split_safe_context_list(parsed.get("sources")) or tuple(_source_labels(tokens)),
        "value_labels": _split_safe_context_list(parsed.get("values")) or tuple(_value_labels(tokens)),
    }


def _contradiction_priority(context: Mapping[str, object]) -> tuple[int, str]:
    metric_label = _safe_string(context.get("metric_label")) or ""
    field_key = _safe_string(context.get("field_key")) or ""
    priority = _CONTRADICTION_PRIORITY.get(metric_label, 90)
    if field_key == "revenue_pricing":
        priority = min(priority, 50)
    return (priority, field_key)


def _safe_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_list(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (_clean_public_token(value),)
    if not isinstance(value, tuple | list):
        return ()
    return tuple(
        cleaned
        for item in value
        if isinstance(item, str)
        for cleaned in (_clean_public_token(item),)
        if cleaned
    )


def _parse_safe_context(explanation: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for match in _SAFE_CONTEXT_VALUE_RE.finditer(explanation):
        parsed[match.group("key").casefold()] = match.group("value").strip().strip(".")
    return parsed


def _safe_context_field(value: str | None) -> str | None:
    if value in {"product", "problem", "stage", "revenue_pricing", "icp", "traction", "burn_cash", "gtm_channel"}:
        return value
    return None


def _split_safe_context_list(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(
        cleaned
        for item in value.split("|")
        for cleaned in (_clean_public_token(item),)
        if cleaned
    )


def _safe_tokens(text: str) -> tuple[str, ...]:
    return tuple(_clean_public_token(match.group(0)) for match in _SAFE_TOKEN_RE.finditer(text))


def _clean_public_token(value: str) -> str:
    cleaned = value.strip().strip(";:,.()[]{}")
    if not cleaned or "\\" in cleaned or "/" in cleaned or "@" in cleaned:
        return ""
    return cleaned[:40]


def _metric_label(*, conflict_type: str, tokens: tuple[str, ...]) -> str:
    joined = f"{conflict_type} {' '.join(tokens)}".casefold()
    if "mrr" in joined:
        return "MRR"
    if "customer" in joined or "клиент" in joined:
        return "количеству клиентов"
    if "margin" in joined or "марж" in joined:
        return "валовой марже"
    if "cac" in joined:
        return "CAC payback"
    return "метрике"


def _source_labels(tokens: tuple[str, ...]) -> tuple[str, ...]:
    candidates = []
    for token in tokens:
        lowered = token.casefold()
        if lowered in {"crm", "invoices", "invoice", "bank", "банк", "сrm"}:
            candidates.append(token)
    return tuple(dict.fromkeys(candidates))


def _value_labels(tokens: tuple[str, ...]) -> tuple[str, ...]:
    values = []
    for token in tokens:
        if any(char.isdigit() for char in token) and (
            "." in token or "," in token or token.casefold().endswith(("m", "k"))
        ):
            values.append(token)
    return tuple(dict.fromkeys(values))

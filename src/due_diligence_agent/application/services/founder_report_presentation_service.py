from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.application.services.founder_advisor_presentation_service import (
    FounderAdvisorCard,
    FounderAdvisorPresentationService,
)
from due_diligence_agent.application.services.report_canonical import (
    STARTUP_REPORT_SCHEMA,
    STARTUP_REPORT_SECTION_KEYS,
)
from due_diligence_agent.domain.reports.models import ReportSnapshot


FounderReportStatus = Literal[
    "confirmed",
    "partial",
    "needs_input",
    "contradiction",
]
FounderImprovementArea = Literal[
    "positioning",
    "monetization",
    "metrics",
    "gtm",
    "risk_reduction",
    "investor_readiness",
]
FounderReportPointStatus = Literal["confirmed", "calculated", "estimated", "contradiction"]
FounderReadinessStatus = Literal["ready", "provisional", "blocked"]


class FounderReportSection(BaseModel):
    """One bounded Russian section derived from a canonical report section."""

    model_config = ConfigDict(frozen=True)

    key: str
    title_ru: str
    status: FounderReportStatus
    status_label_ru: str
    summary_ru: str
    content_heading_ru: str = "Что уже известно"
    known_facts_ru: tuple[str, ...] = ()
    blockers_ru: tuple[str, ...] = ()
    next_data_ru: tuple[str, ...] = ()
    unlocks_ru: tuple[str, ...] = ()


class FounderReportImprovementProposal(BaseModel):
    """A deterministic recommendation, explicitly separate from source facts."""

    model_config = ConfigDict(frozen=True)

    target_area: FounderImprovementArea
    title_ru: str
    recommendation_ru: str
    rationale_ru: str
    expected_effect_ru: str
    provenance: Literal["ai_recommendation"] = "ai_recommendation"


class FounderReportTechnicalAppendix(BaseModel):
    """Privacy-safe methodology summary without raw lineage identifiers."""

    model_config = ConfigDict(frozen=True)

    methodology_ru: tuple[str, ...]
    sources_ru: tuple[str, ...]


class FounderReportDataPoint(BaseModel):
    """Numeric founder-facing point with internal calculation lineage removed."""

    model_config = ConfigDict(frozen=True)

    key: str
    label_ru: str
    value: float = Field(ge=0)
    unit: str | None = None
    period_ru: str | None = None
    status: FounderReportPointStatus


class FounderReportReadinessDimension(BaseModel):
    """Sanitized readiness explanation without dimension ids or technical refs."""

    model_config = ConfigDict(frozen=True)

    key: str
    label_ru: str
    status: FounderReadinessStatus
    status_label_ru: str
    explanation_ru: str


class FounderReportAnalytics(BaseModel):
    """Safe structured data used by founder charts and readiness panels."""

    model_config = ConfigDict(frozen=True)

    metric_points: tuple[FounderReportDataPoint, ...] = ()
    market_points: tuple[FounderReportDataPoint, ...] = ()
    readiness_dimensions: tuple[FounderReportReadinessDimension, ...] = ()


class FounderStartupReportView(BaseModel):
    """Founder-safe render model built without changing the canonical snapshot."""

    model_config = ConfigDict(frozen=True)

    title_ru: str = "Отчёт для основателя"
    subtitle_ru: str = "Краткий разбор проекта, блокеры и следующие шаги"
    as_of_ru: str
    data_revision: int = Field(ge=0)
    main_sections: tuple[FounderReportSection, ...]
    metric_cards: Mapping[str, FounderAdvisorCard] = Field(default_factory=dict)
    improvement_proposals: tuple[FounderReportImprovementProposal, ...]
    technical_appendix: FounderReportTechnicalAppendix
    analytics: FounderReportAnalytics = Field(default_factory=FounderReportAnalytics)


class FounderStartupReportPresentationService:
    """Builds a deterministic Russian view over a canonical startup snapshot."""

    def __init__(
        self,
        *,
        advisor_presentation: FounderAdvisorPresentationService | None = None,
    ) -> None:
        self._advisor_presentation = advisor_presentation or FounderAdvisorPresentationService()

    def build(self, snapshot: ReportSnapshot) -> FounderStartupReportView:
        advisor_view = self._advisor_presentation.build(snapshot)
        metric_cards = {
            key: card
            for key, card in advisor_view.metric_cards.items()
            if key.casefold() in _SAFE_ADVISOR_CARD_IDS
        }
        sections = tuple(
            _section_view(
                key,
                _section(snapshot.sections, key),
                all_sections=snapshot.sections,
                metric_cards=metric_cards,
            )
            for key in STARTUP_REPORT_SECTION_KEYS[:12]
        )
        return FounderStartupReportView(
            as_of_ru=snapshot.as_of.date().isoformat(),
            data_revision=snapshot.data_revision,
            main_sections=sections,
            metric_cards=metric_cards,
            improvement_proposals=_improvement_proposals(sections),
            technical_appendix=_technical_appendix(snapshot, sections),
            analytics=_analytics(snapshot),
        )


_SECTION_TITLES_RU = {
    "business_idea_summary": "Кратко о проекте",
    "problem_solution": "Проблема и решение",
    "market_size": "Размер рынка",
    "competitors": "Конкуренты и альтернативы",
    "moat": "Защитимость и преимущества",
    "go_to_market": "Выход на рынок",
    "metrics": "Ключевые метрики",
    "financial_assumptions": "Финансовые допущения",
    "risks": "Риски",
    "evidence_gaps": "Пробелы в подтверждениях",
    "diligence_questions": "Вопросы для уточнения",
    "action_plan": "План действий",
}

_SECTION_SUMMARIES_RU = {
    "business_idea_summary": "Сводка показывает, насколько ясно описаны проект и бизнес-модель.",
    "problem_solution": "Раздел связывает заявленную проблему с предлагаемым решением.",
    "market_size": "Оценка рынка учитывается только при наличии источников и воспроизводимого расчёта.",
    "competitors": "Сравнение охватывает названных конкурентов и доступные альтернативы.",
    "moat": "Преимущества отделены от гипотез, которые ещё нужно подтвердить.",
    "go_to_market": "Проверяются целевая аудитория, география и рабочие каналы привлечения.",
    "metrics": "Показатели берутся из подтверждённых данных и локальных расчётов.",
    "financial_assumptions": "Финансовые допущения остаются гипотезами до появления первичных данных.",
    "risks": "Риски собраны отдельно от фактов и требуют явного решения владельца.",
    "evidence_gaps": "Здесь собраны области, где вывод пока нельзя уверенно защитить.",
    "diligence_questions": "Ответьте сначала на вопросы, которые сильнее всего меняют выводы.",
    "action_plan": "Шаги расположены от устранения блокеров к фиксации версии отчёта.",
}

_NEXT_DATA_RU = {
    "business_idea_summary": "Добавьте короткое описание проекта и способ монетизации.",
    "problem_solution": "Добавьте подтверждение проблемы и пример результата решения.",
    "market_size": "Добавьте источники и расчёт для TAM, SAM и SOM.",
    "competitors": "Добавьте список альтернатив и критерии сравнения с ними.",
    "moat": "Добавьте доказательство устойчивого преимущества, которое трудно повторить.",
    "go_to_market": "Укажите ICP, географию и проверенный канал привлечения.",
    "metrics": "Добавьте значения метрик, период и первичный источник.",
    "financial_assumptions": "Добавьте исходные данные для выручки, затрат и маржинальности.",
    "risks": "Добавьте владельца риска, вероятность, влияние и меру снижения.",
    "evidence_gaps": "Закройте первичными данными самые значимые пробелы.",
    "diligence_questions": "Дайте один проверяемый ответ на вопрос с наивысшим приоритетом.",
    "action_plan": "Зафиксируйте ответственных и сроки по ближайшим шагам.",
}

_UNLOCKS_RU = {
    "business_idea_summary": "Это сделает позиционирование понятнее для инвестора и команды.",
    "problem_solution": "Это позволит проверить ценность решения без догадок.",
    "market_size": "Это откроет защищаемую оценку масштаба возможности.",
    "competitors": "Это позволит обосновать отличия и риски замещения.",
    "moat": "Это усилит аргумент о долгосрочной защитимости проекта.",
    "go_to_market": "Это откроет реалистичный план привлечения первых клиентов.",
    "metrics": "Это позволит пересчитать готовность проекта и динамику бизнеса.",
    "financial_assumptions": "Это позволит проверить экономику и потребность в капитале.",
    "risks": "Это позволит приоритизировать меры снижения риска.",
    "evidence_gaps": "Это повысит доверие к выводам и уменьшит число блокеров.",
    "diligence_questions": "Это обновит соответствующие разделы без длинной анкеты.",
    "action_plan": "Это подготовит проект к осознанной фиксации следующей версии.",
}

_SAFE_ROW_LABELS = {
    "business_idea_summary": frozenset(
        {"startup_name", "one_line_description", "business_model"}
    ),
    "problem_solution": frozenset({"problem_statement", "solution"}),
    "competitors": frozenset({"competitors"}),
    "moat": frozenset({"strengths"}),
    "go_to_market": frozenset({"icp", "users", "buyers", "geography", "channels_gtm"}),
    "financial_assumptions": frozenset({"assumptions"}),
    "risks": frozenset({"weaknesses"}),
}

_ROW_LABELS_RU = {
    "startup_name": "Название",
    "one_line_description": "Описание",
    "business_model": "Бизнес-модель",
    "problem_statement": "Проблема",
    "solution": "Решение",
    "competitors": "Альтернативы",
    "strengths": "Сильные стороны",
    "icp": "Целевой клиент",
    "users": "Пользователи",
    "buyers": "Покупатели",
    "geography": "География",
    "channels_gtm": "Каналы",
    "assumptions": "Допущения",
    "weaknesses": "Слабые стороны",
}

_ACTION_PLAN_HORIZONS_RU = {
    "day_7": "7 дней",
    "day_30": "30 дней",
    "day_60": "60 дней",
    "day_90": "90 дней",
}

_ACTION_PLAN_EXPERIMENTS_RU = {
    "resolve_contradictions": "разрешить ключевые противоречия",
    "clarify_audience": "уточнить целевую аудиторию",
    "validate_geography": "проверить приоритетную географию",
    "validate_channel": "проверить канал привлечения",
    "validate_offer": "проверить ценность и условия предложения",
    "validate_product_proof": "подтвердить результат продукта первичными данными",
    "validate_market_positioning": "проверить позиционирование на фоне альтернатив",
    "validate_adoption_risk": "проверить риск внедрения",
    "measure_channel_signal": "измерить подтверждённый сигнал канала",
    "review_launch_evidence": "пересмотреть накопленные доказательства запуска",
}

_SAFE_ADVISOR_CARD_IDS = frozenset(
    {
        "mrr",
        "monthly_recurring_revenue",
        "arr",
        "annual_recurring_revenue",
        "revenue",
        "gross_margin",
        "burn",
        "cash_balance",
        "runway",
        "monthly_net_burn",
        "retention",
        "growth_rate",
        "cac",
        "ltv",
        "tam",
        "sam",
        "som",
    }
)
_ANALYTICS_METRIC_LABELS_RU = {
    "mrr": "MRR",
    "monthly_recurring_revenue": "MRR",
    "arr": "ARR",
    "annual_recurring_revenue": "ARR",
    "revenue": "Выручка",
    "gross_margin": "Валовая маржа",
    "gross_margin_ratio": "Валовая маржа",
    "burn": "Burn rate",
    "burn_rate": "Burn rate",
    "monthly_burn": "Burn rate",
    "net_burn": "Net burn",
    "monthly_net_burn": "Net burn",
    "runway": "Runway",
    "runway_months": "Runway",
    "retention": "Удержание",
    "logo_retention": "Удержание",
    "net_revenue_retention": "NRR",
    "nrr": "NRR",
    "cac": "CAC",
    "ltv": "LTV",
    "growth_rate": "Темп роста",
}
_SOURCE_BACKED_DIRECT_METRIC_KEYS = frozenset(
    {
        "mrr",
        "monthly_recurring_revenue",
        "gross_margin",
        "gross_margin_ratio",
        "runway",
        "runway_months",
        "burn",
        "burn_rate",
        "net_burn",
        "monthly_net_burn",
    }
)
_READINESS_LABELS_RU = {
    "arr": "ARR",
    "burn_multiple": "Burn multiple",
    "business_model": "Бизнес-модель",
    "cac_payback_months": "Окупаемость CAC",
    "cac": "CAC",
    "cohort_retention": "Удержание по когортам",
    "gross_margin": "Валовая маржа",
    "gtm_evidence": "Доказательства GTM",
    "logo_churn": "Logo churn",
    "ltv_cac": "LTV/CAC",
    "ltv": "LTV",
    "market_evidence": "Доказательства рынка",
    "mrr": "MRR",
    "net_burn": "Net burn",
    "nrr": "NRR",
    "period_growth": "Рост за период",
    "revenue_churn": "Revenue churn",
    "risk_disclosure": "Раскрытие рисков",
    "rule_of_40": "Rule of 40",
    "runway_months": "Runway",
    "traction": "Трекшн",
    "unit_economics": "Юнит-экономика",
}
_MISSING_METRIC_GUIDANCE_RU = {
    "monthly_recurring_revenue": "Добавьте MRR или ARR за последний месяц и период сравнения.",
    "cohort_retention": "Добавьте cohort retention по сопоставимым периодам.",
    "cash": "Добавьте текущий остаток денежных средств и средний burn за месяц.",
    "revenue": "Добавьте выручку за период и себестоимость.",
    "net_burn": "Добавьте net burn и net new ARR за один период.",
    "sales_marketing_spend": "Добавьте расходы на продажи и маркетинг и число новых клиентов.",
    "cac": "Добавьте CAC и валовую маржу или средний чек.",
    "starting_cohort_customers": "Добавьте размер стартовой когорты и число оставшихся клиентов.",
    "lost_customers": "Добавьте число ушедших клиентов и размер стартовой базы.",
    "churned_mrr": "Добавьте потерянный MRR и стартовый MRR.",
    "opening_mrr": "Добавьте opening MRR, expansion, contraction и churn.",
    "current_value": "Добавьте текущий и предыдущий показатель за сопоставимые периоды.",
}
_UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    flags=re.IGNORECASE,
)
_BARE_HASH_PATTERN = re.compile(r"\b[0-9a-f]{64}\b", flags=re.IGNORECASE)
_SAFE_ANALYTICS_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_ANALYTICS_UNIT_PATTERN = re.compile(
    r"^[A-Za-zА-Яа-яЁё₸$€¥%]+(?:/[A-Za-zА-Яа-яЁё%]+)?$"
)
_NON_NEGATIVE_NUMBER_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")


def _section_view(
    key: str,
    section: Mapping[str, object],
    *,
    all_sections: Mapping[str, object],
    metric_cards: Mapping[str, FounderAdvisorCard],
) -> FounderReportSection:
    status = _founder_status(str(section.get("status", "")))
    facts = _known_facts(key, section, metric_cards)
    content_heading = "Что уже известно"
    if key == "evidence_gaps":
        content_heading = "Текущие блокеры"
        gap_count = len(_items(section))
        facts = (f"Открытых областей для подтверждения: {gap_count}.",) if gap_count else ()
    elif key == "diligence_questions":
        content_heading = "Ключевые вопросы"
        facts = _russian_questions(all_sections)
    elif key == "action_plan":
        content_heading = "Ближайшие шаги"
        facts = _action_plan_facts(section)
    blockers = _blockers(key, status)
    return FounderReportSection(
        key=key,
        title_ru=_SECTION_TITLES_RU[key],
        status=status,
        status_label_ru=_status_label(status),
        summary_ru=_SECTION_SUMMARIES_RU[key],
        content_heading_ru=content_heading,
        known_facts_ru=facts,
        blockers_ru=blockers,
        next_data_ru=() if status == "confirmed" else (_NEXT_DATA_RU[key],),
        unlocks_ru=() if status == "confirmed" else (_UNLOCKS_RU[key],),
    )


def _known_facts(
    key: str,
    section: Mapping[str, object],
    metric_cards: Mapping[str, FounderAdvisorCard],
) -> tuple[str, ...]:
    if key == "market_size":
        market_facts = _market_size_public_facts(section)
        if market_facts:
            return market_facts
        return tuple(
            card.summary_ru
            for card_id, card in metric_cards.items()
            if card_id in {"tam", "sam", "som"}
        )[:3]
    if key == "metrics":
        return tuple(
            card.summary_ru
            for card_id, card in metric_cards.items()
            if card_id not in {"tam", "sam", "som"}
        )[:4]
    if key == "competitors":
        public_competitors = _competitor_public_facts(section)
        if public_competitors:
            return public_competitors
    allowed = _SAFE_ROW_LABELS.get(key, frozenset())
    facts: list[str] = []
    for row in _rows(section):
        if len(row) < 3 or row[0] not in allowed:
            continue
        value = _safe_founder_value(row[2])
        if value is None:
            continue
        facts.append(f"{_ROW_LABELS_RU[row[0]]}: {value}")
        if len(facts) >= 3:
            break
    return tuple(facts)


def _market_size_public_facts(section: Mapping[str, object]) -> tuple[str, ...]:
    facts: list[str] = []
    for row in _rows(section):
        if len(row) < 4:
            continue
        key = row[0].strip().casefold()
        if key not in {"tam", "sam", "som"}:
            continue
        value = _safe_founder_value(row[2])
        unit = _safe_founder_value(row[3])
        if value is None:
            continue
        label = key.upper()
        amount = f"{value} {unit}" if unit else value
        status = _public_research_status_label(row[1])
        as_of = _row_value(row, "as_of=")
        suffix = f", на дату {as_of}" if as_of else ""
        facts.append(f"{label}: {amount} ({status}{suffix}).")
        if len(facts) >= 3:
            break
    facts.extend(_public_benchmark_item_facts(section))
    return tuple(facts)


def _public_benchmark_item_facts(section: Mapping[str, object]) -> tuple[str, ...]:
    facts: list[str] = []
    for item in _structured_items(section):
        if len(item) < 8 or item[0] != "public_benchmark":
            continue
        input_key = _safe_founder_value(item[1])
        publisher = _safe_founder_value(item[2])
        value = _format_public_benchmark_value(item[3])
        unit = _safe_founder_value(item[4])
        period = _safe_founder_value(item[5])
        as_of = _row_value(item, "as_of=")
        status = _public_research_status_label(_row_value(item, "status=") or "")
        if publisher is None or value is None or unit is None or period is None:
            continue
        scope = f"{unit}/{period}"
        label = f" для {input_key}" if input_key else ""
        suffix = f", на дату {as_of}" if as_of else ""
        facts.append(
            f"Публичный ориентир{label}: {publisher} {value} {scope} ({status}{suffix})."
        )
        if len(facts) >= 5:
            break
    return tuple(facts)


def _structured_items(section: Mapping[str, object]) -> tuple[tuple[str, ...], ...]:
    value = section.get("items", ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result: list[tuple[str, ...]] = []
    for item in value:
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            result.append(tuple(str(cell) for cell in item))
    return tuple(result)


def _format_public_benchmark_value(value: str) -> str | None:
    safe = _safe_founder_value(value)
    if safe is None:
        return None
    if ".." not in safe:
        return _format_number(safe)
    low, high = safe.split("..", 1)
    return f"{_format_number(low)}..{_format_number(high)}"


def _format_number(value: str) -> str:
    normalized = value.strip()
    try:
        number = float(normalized)
    except ValueError:
        return normalized
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _competitor_public_facts(section: Mapping[str, object]) -> tuple[str, ...]:
    facts: list[str] = []
    for row in _rows(section):
        if len(row) < 3 or not _row_has_source_mode(row):
            continue
        name = _safe_founder_value(row[0])
        if name is None:
            continue
        category = _competitor_category_label(row[1])
        status = _public_research_status_label(row[2])
        facts.append(f"Публичный ориентир: {name} ({category}; {status}).")
        if len(facts) >= 5:
            break
    return tuple(facts)


def _public_research_status_label(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized == "source_fact":
        return "подтверждённый публичный ориентир"
    if normalized == "contradiction":
        return "противоречивый публичный сигнал"
    if normalized == "insufficient_data":
        return "недостаточно данных"
    return "Публичная гипотеза"


def _competitor_category_label(value: str) -> str:
    return {
        "direct": "прямой конкурент",
        "indirect": "косвенная альтернатива",
        "substitute": "заменитель",
        "category": "категорийный ориентир",
    }.get(value.strip().casefold(), "рыночная альтернатива")


def _row_value(row: tuple[str, ...], prefix: str) -> str | None:
    for cell in row:
        if cell.startswith(prefix):
            return _safe_founder_value(cell.removeprefix(prefix))
    return None


def _row_has_source_mode(row: tuple[str, ...]) -> bool:
    return any(cell.startswith("source_mode=") for cell in row)


def _action_plan_facts(section: Mapping[str, object]) -> tuple[str, ...]:
    facts: list[str] = []
    for row in _rows(section):
        if len(row) < 2:
            continue
        horizon = _ACTION_PLAN_HORIZONS_RU.get(row[0])
        if horizon is None or not row[1].startswith("experiment_codes="):
            continue
        codes = tuple(
            code
            for code in row[1].removeprefix("experiment_codes=").split(",")
            if code in _ACTION_PLAN_EXPERIMENTS_RU
        )
        if not codes:
            continue
        actions = "; ".join(_ACTION_PLAN_EXPERIMENTS_RU[code] for code in codes)
        facts.append(f"{horizon} — {actions}.")
    return tuple(facts[:4])


def _blockers(key: str, status: FounderReportStatus) -> tuple[str, ...]:
    if status == "confirmed":
        return ()
    if status == "contradiction":
        return (
            f"В разделе «{_SECTION_TITLES_RU[key]}» есть противоречивые сведения; "
            "сначала выберите подтверждённый источник.",
        )
    if status == "partial":
        return (
            f"Раздел «{_SECTION_TITLES_RU[key]}» подтверждён только частично.",
        )
    return (
        f"Для раздела «{_SECTION_TITLES_RU[key]}» пока недостаточно проверяемых данных.",
    )


def _russian_questions(sections: Mapping[str, object]) -> tuple[str, ...]:
    candidates = (
        (
            "market_size",
            "Какими источниками и расчётом подтверждаются TAM, SAM и SOM?",
        ),
        (
            "metrics",
            "Какие значения ключевых метрик, период и первичный источник можно подтвердить?",
        ),
        (
            "go_to_market",
            "Кто ваш приоритетный клиент и какой канал привлечения уже проверен?",
        ),
        (
            "risks",
            "Какой риск сильнее всего влияет на ближайший план и как вы его снижаете?",
        ),
    )
    questions = tuple(
        question
        for key, question in candidates
        if _founder_status(str(_section(sections, key).get("status", ""))) != "confirmed"
    )
    return questions[:3] or (
        "Какие новые первичные данные могут сильнее всего изменить текущий вывод?",
    )


def _improvement_proposals(
    sections: Sequence[FounderReportSection],
) -> tuple[FounderReportImprovementProposal, ...]:
    by_key = {section.key: section for section in sections}
    definitions: tuple[
        tuple[FounderImprovementArea, str, str, str, str], ...
    ] = (
        (
            "positioning",
            "Позиционирование",
            "Сведите проблему, целевого клиента и измеримый результат в одну проверяемую формулировку.",
            "problem_solution",
            "Команде и инвестору будет проще одинаково понимать ценность продукта.",
        ),
        (
            "monetization",
            "Монетизация",
            "Свяжите модель оплаты с подтверждённой ценностью для покупателя и единым периодом расчёта.",
            "financial_assumptions",
            "Это упростит проверку выручки, маржинальности и потребности в капитале.",
        ),
        (
            "metrics",
            "Метрики",
            "Выберите небольшой набор ключевых метрик и закрепите для каждой источник, период и владельца.",
            "metrics",
            "Следующая версия анализа станет сравнимой и воспроизводимой.",
        ),
        (
            "gtm",
            "Выход на рынок",
            "Сфокусируйте ближайший тест на одном ICP, одном канале и измеримом критерии успеха.",
            "go_to_market",
            "Это превратит общую стратегию в проверяемый план привлечения.",
        ),
        (
            "risk_reduction",
            "Снижение рисков",
            "Назначьте владельца и проверяемую меру снижения для самого значимого открытого риска.",
            "risks",
            "Это уменьшит неопределённость и сделает решение по риску наблюдаемым.",
        ),
        (
            "investor_readiness",
            "Готовность к инвестору",
            "Закройте сначала подтверждения, которые одновременно разблокируют несколько разделов отчёта.",
            "evidence_gaps",
            "Это повысит плотность доказательств без лишней анкеты.",
        ),
    )
    proposals: list[FounderReportImprovementProposal] = []
    for area, title, recommendation, section_key, effect in definitions:
        section = by_key[section_key]
        proposals.append(
            FounderReportImprovementProposal(
                target_area=area,
                title_ru=title,
                recommendation_ru=recommendation,
                rationale_ru=(
                    f"Основание: раздел «{section.title_ru}» имеет статус "
                    f"«{section.status_label_ru.lower()}»."
                ),
                expected_effect_ru=effect,
            )
        )
    return tuple(proposals)


def _analytics(snapshot: ReportSnapshot) -> FounderReportAnalytics:
    return FounderReportAnalytics(
        metric_points=_metric_points(snapshot.sections),
        market_points=_market_points(snapshot.sections),
        readiness_dimensions=_readiness_dimensions(snapshot.sections),
    )


def _metric_points(sections: Mapping[str, object]) -> tuple[FounderReportDataPoint, ...]:
    points: list[FounderReportDataPoint] = []
    direct_groups: dict[tuple[str, str], list[_DirectMetricObservation]] = {}
    direct_group_order: list[tuple[str, str]] = []
    for row in _rows(_section(sections, "metrics")):
        if len(row) < 2:
            continue
        key = row[0].strip().casefold().replace("-", "_").replace(" ", "_")
        has_calculation_ref = any(cell.startswith("calculation_ref=") for cell in row)
        has_source_backed_direct_fact = any(cell.startswith("evidence_ref=") for cell in row)
        if not has_calculation_ref:
            if has_source_backed_direct_fact and key in _SOURCE_BACKED_DIRECT_METRIC_KEYS:
                observation = _direct_metric_observation(key, row)
                if observation is not None:
                    group_key = (key, observation.period_key)
                    if group_key not in direct_groups:
                        direct_group_order.append(group_key)
                    direct_groups.setdefault(group_key, []).append(observation)
            continue
        label = _ANALYTICS_METRIC_LABELS_RU.get(key)
        value = _non_negative_number(row[1])
        if label is None or value is None or _SAFE_ANALYTICS_KEY_PATTERN.fullmatch(key) is None:
            continue
        points.append(
            FounderReportDataPoint(
                key=key,
                label_ru=label,
                value=value,
                unit=_safe_analytics_unit(row[2] if len(row) > 2 else ""),
                period_ru=_analytics_period(row[3] if len(row) > 3 else ""),
                status="calculated",
            )
        )
        if len(points) >= 24:
            break
    for group_key in direct_group_order:
        selected = _select_direct_metric_observation(direct_groups[group_key])
        if selected is None:
            continue
        points.append(
            FounderReportDataPoint(
                key=selected.key,
                label_ru=selected.label_ru,
                value=selected.value,
                unit=selected.unit,
                period_ru=selected.period_ru,
                status=selected.status,
            )
        )
        if len(points) >= 24:
            break
    return tuple(points)


@dataclass(frozen=True)
class _DirectMetricObservation:
    key: str
    label_ru: str
    value: float
    unit: str | None
    period_key: str
    period_ru: str | None
    confidence: float
    status: Literal["confirmed", "contradiction"]


def _direct_metric_observation(
    key: str, row: tuple[str, ...]
) -> _DirectMetricObservation | None:
    label = _ANALYTICS_METRIC_LABELS_RU.get(key)
    value = _non_negative_number(row[1])
    if label is None or value is None or _SAFE_ANALYTICS_KEY_PATTERN.fullmatch(key) is None:
        return None
    raw_period = row[3] if len(row) > 3 else ""
    return _DirectMetricObservation(
        key=key,
        label_ru=label,
        value=value,
        unit=_safe_analytics_unit(row[2] if len(row) > 2 else ""),
        period_key=raw_period.strip().casefold() or "missing",
        period_ru=_analytics_period(raw_period),
        confidence=_row_confidence(row),
        status="contradiction" if _row_source_status(row) == "contradiction" else "confirmed",
    )


def _select_direct_metric_observation(
    observations: Sequence[_DirectMetricObservation],
) -> _DirectMetricObservation | None:
    if not observations:
        return None
    by_value: dict[float, _DirectMetricObservation] = {}
    for observation in observations:
        current = by_value.get(observation.value)
        if current is None or observation.confidence > current.confidence:
            by_value[observation.value] = observation
    highest = max(observation.confidence for observation in by_value.values())
    winners = tuple(
        observation for observation in by_value.values() if observation.confidence == highest
    )
    if len(winners) != 1:
        return None
    selected = winners[0]
    if any(observation.status == "contradiction" for observation in observations):
        return _DirectMetricObservation(
            key=selected.key,
            label_ru=selected.label_ru,
            value=selected.value,
            unit=selected.unit,
            period_key=selected.period_key,
            period_ru=selected.period_ru,
            confidence=selected.confidence,
            status="contradiction",
        )
    return selected


def _row_confidence(row: tuple[str, ...]) -> float:
    for cell in row:
        if cell.startswith("confidence="):
            value = _non_negative_number(cell.removeprefix("confidence="))
            if value is not None:
                return min(value, 1.0)
    return 0.0


def _row_source_status(row: tuple[str, ...]) -> str:
    for cell in row:
        if cell.startswith("status="):
            return cell.removeprefix("status=").strip().casefold()
    return "source_fact"


def _market_points(sections: Mapping[str, object]) -> tuple[FounderReportDataPoint, ...]:
    points: list[FounderReportDataPoint] = []
    for row in _rows(_section(sections, "market_size")):
        if len(row) < 3:
            continue
        key = row[0].strip().casefold()
        value = _non_negative_number(row[2])
        if key not in {"tam", "sam", "som"} or value is None:
            continue
        unit = _safe_analytics_text(row[4] if len(row) > 4 else "") or _safe_analytics_text(
            row[3] if len(row) > 3 else ""
        )
        period = _market_period(row)
        points.append(
            FounderReportDataPoint(
                key=key,
                label_ru=key.upper(),
                value=value,
                unit=unit,
                period_ru=period,
                status="confirmed" if row[1].casefold() == "source_fact" else "estimated",
            )
        )
    return tuple(points[:3])


def _readiness_dimensions(
    sections: Mapping[str, object],
) -> tuple[FounderReportReadinessDimension, ...]:
    dimensions: list[FounderReportReadinessDimension] = []
    for row in _rows(_section(sections, "metrics")):
        if len(row) < 4 or not row[3].startswith("dimension_ref="):
            continue
        key = row[0].strip().casefold()
        status = _readiness_status(row[1])
        label = _READINESS_LABELS_RU.get(key)
        if label is None or status is None:
            continue
        dimensions.append(
            FounderReportReadinessDimension(
                key=key,
                label_ru=label,
                status=status,
                status_label_ru={
                    "ready": "Готово",
                    "provisional": "Нужно подтвердить",
                    "blocked": "Нужны данные",
                }[status],
                explanation_ru=_readiness_explanation(key, row[2]),
            )
        )
        if len(dimensions) >= 32:
            break
    return tuple(dimensions)


def _readiness_explanation(key: str, reason: str) -> str:
    if reason.startswith("input.missing:"):
        missing_key = reason.removeprefix("input.missing:")
        return _MISSING_METRIC_GUIDANCE_RU.get(
            missing_key,
            f"Добавьте исходные данные для показателя «{_READINESS_LABELS_RU[key]}».",
        )
    if reason.startswith("method.profile_field:"):
        return "Проверка опирается на подтверждённое поле профиля проекта."
    if reason.startswith("method.metric_diagnostics:"):
        return "Проверка рассчитана по диагностике метрик и требует сверки исходного периода."
    if reason.startswith("metric.calculated:"):
        return "Показатель рассчитан из загруженных данных; проверьте период и единицы."
    if reason.startswith("assumption.missing:"):
        return "Добавьте проверяемое допущение или источник для этого расчёта."
    if reason.startswith("condition.inapplicable:"):
        return "Проверка пока не применима к текущей стадии или бизнес-модели проекта."
    return "Добавьте источник или уточнение, чтобы завершить эту проверку."


def _readiness_status(value: str) -> FounderReadinessStatus | None:
    normalized = value.strip().casefold()
    if normalized == "ready":
        return "ready"
    if normalized == "provisional":
        return "provisional"
    if normalized == "blocked":
        return "blocked"
    return None


def _market_period(row: tuple[str, ...]) -> str | None:
    for cell in row[3:]:
        if cell.startswith("as_of="):
            value = _safe_analytics_text(cell.removeprefix("as_of="))
            return f"На дату {value}" if value else None
    return None


def _analytics_period(value: str) -> str | None:
    safe = _safe_analytics_text(value)
    if safe is None or safe.casefold() == "unknown":
        return None
    return safe


def _safe_analytics_text(value: str) -> str | None:
    safe = _safe_founder_value(value)
    return safe if safe and len(safe) <= 80 else None


def _safe_analytics_unit(value: str) -> str | None:
    text = value.strip()
    if not text or len(text) > 40:
        return None
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in (
            "missing",
            "document_text_block",
            "sha256:",
            "evidence_ref",
            "calculation_ref",
            "finding_ref",
            "contradiction_ref",
            "prompt",
            "sk-",
        )
    ):
        return None
    if "\\" in text or "@" in text:
        return None
    if _UUID_PATTERN.search(text) or _BARE_HASH_PATTERN.search(text):
        return None
    return text if _SAFE_ANALYTICS_UNIT_PATTERN.fullmatch(text) else None


def _non_negative_number(value: str) -> float | None:
    normalized = value.strip()
    if _NON_NEGATIVE_NUMBER_PATTERN.fullmatch(normalized) is None:
        return None
    parsed = float(normalized)
    return parsed if parsed >= 0 else None


def _technical_appendix(
    snapshot: ReportSnapshot,
    sections: Sequence[FounderReportSection],
) -> FounderReportTechnicalAppendix:
    status_counts = {
        status: sum(section.status == status for section in sections)
        for status in ("confirmed", "partial", "needs_input", "contradiction")
    }
    source_count = len(_rows(_section(snapshot.sections, "source_appendix")))
    return FounderReportTechnicalAppendix(
        methodology_ru=(
            "Отчёт построен детерминированно из канонического снимка кейса.",
            f"Версия данных: {snapshot.data_revision}.",
            (
                "Покрытие разделов: подтверждено — "
                f"{status_counts['confirmed']}; частично — {status_counts['partial']}; "
                f"нужны данные — {status_counts['needs_input']}; "
                f"есть противоречия — {status_counts['contradiction']}."
            ),
            f"Каноническая схема: {STARTUP_REPORT_SCHEMA}.",
        ),
        sources_ru=(
            f"В каноническом приложении зарегистрировано источников: {source_count}.",
            (
                "Хэши, внутренние идентификаторы, трассировки, локаторы и сырой текст "
                "скрыты из версии для основателя."
            ),
        ),
    )


def _founder_status(value: str) -> FounderReportStatus:
    normalized = value.strip().upper()
    if normalized == "SUPPORTED":
        return "confirmed"
    if normalized == "PARTIAL":
        return "partial"
    if normalized == "CONTRADICTION":
        return "contradiction"
    return "needs_input"


def _status_label(status: FounderReportStatus) -> str:
    return {
        "confirmed": "Подтверждено",
        "partial": "Нужно уточнить",
        "needs_input": "Нужны данные",
        "contradiction": "Есть противоречие",
    }[status]


def _section(sections: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = sections.get(key)
    return value if isinstance(value, Mapping) else {}


def _rows(section: Mapping[str, object]) -> tuple[tuple[str, ...], ...]:
    value = section.get("rows", ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result: list[tuple[str, ...]] = []
    for row in value:
        if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            result.append(tuple(str(cell) for cell in row))
    return tuple(result)


def _items(section: Mapping[str, object]) -> tuple[str, ...]:
    value = section.get("items", ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


def _safe_founder_value(value: str) -> str | None:
    text = value.strip()
    lowered = text.casefold()
    if not text or len(text) > 160:
        return None
    if any(
        marker in lowered
        for marker in (
            "missing",
            "document_text_block",
            "sha256:",
            "evidence_ref",
            "calculation_ref",
            "finding_ref",
            "contradiction_ref",
            "prompt",
            "sk-",
            ".pdf",
            ".docx",
            ".xlsx",
            ".csv",
            ".pptx",
        )
    ):
        return None
    if "\\" in text or "/" in text or "@" in text:
        return None
    if _UUID_PATTERN.search(text) or _BARE_HASH_PATTERN.search(text):
        return None
    return text


__all__ = [
    "FounderReportAnalytics",
    "FounderReportDataPoint",
    "FounderReportImprovementProposal",
    "FounderReportReadinessDimension",
    "FounderReportSection",
    "FounderReportTechnicalAppendix",
    "FounderStartupReportPresentationService",
    "FounderStartupReportView",
]

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.domain.reports.models import ReportSnapshot


StartupReportSnapshot: TypeAlias = ReportSnapshot
FounderAdvisorCardStatus = Literal[
    "confirmed", "estimated", "needs_input", "contradiction"
]


class FounderAdvisorCard(BaseModel):
    """A deterministic Russian-language explanation of one founder-facing signal."""

    model_config = ConfigDict(frozen=True)

    title_ru: str
    summary_ru: str
    status: FounderAdvisorCardStatus
    why_it_matters_ru: str
    next_unlock_ru: str = Field(min_length=1)


class FounderAdvisorView(BaseModel):
    """Founder-facing cards keyed by their canonical snapshot signal identifier."""

    model_config = ConfigDict(frozen=True)

    metric_cards: Mapping[str, FounderAdvisorCard] = Field(default_factory=dict)


class FounderAdvisorPresentationService:
    """Maps canonical startup snapshot rows to deterministic Russian presentation cards."""

    def build(self, snapshot: StartupReportSnapshot) -> FounderAdvisorView:
        cards = {
            identifier: _card_from_metric_row(identifier, row)
            for identifier, row in _metric_rows(snapshot.sections)
        }
        cards.update(
            {
                identifier: _card_from_market_row(identifier, row)
                for identifier, row in _market_size_rows(snapshot.sections)
            }
        )
        return FounderAdvisorView(metric_cards=cards)


def _metric_rows(sections: Mapping[str, object]) -> Iterable[tuple[str, tuple[str, ...]]]:
    section = _section(sections, "metrics")
    rows_by_identifier: dict[str, list[tuple[str, ...]]] = {}
    for row in _rows(section):
        if not row:
            continue
        identifier = row[0]
        if _is_metric_row(row):
            rows_by_identifier.setdefault(identifier, []).append(row)
    for identifier, rows in rows_by_identifier.items():
        calculation_rows = tuple(
            row
            for row in rows
            if any(cell.startswith("calculation_ref=") for cell in row)
        )
        if calculation_rows:
            yield identifier, calculation_rows[0]
            continue
        direct_rows = tuple(
            row
            for row in rows
            if any(cell.startswith("evidence_ref=") for cell in row)
        )
        if direct_rows:
            yield identifier, _select_direct_metric_row(direct_rows)
            continue
        yield identifier, rows[0]


def _select_direct_metric_row(rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    best_by_value: dict[str, tuple[float, tuple[str, ...]]] = {}
    for row in rows:
        value = row[1] if len(row) > 1 else ""
        confidence = _row_confidence(row)
        current = best_by_value.get(value)
        if current is None or confidence > current[0]:
            best_by_value[value] = (confidence, row)
    highest = max(confidence for confidence, _row in best_by_value.values())
    winners = tuple(
        row
        for confidence, row in best_by_value.values()
        if confidence == highest
    )
    if len(winners) == 1:
        return winners[0]
    return (*winners[0], "status=contradiction")


def _row_confidence(row: tuple[str, ...]) -> float:
    for cell in row:
        if not cell.startswith("confidence="):
            continue
        try:
            return min(max(float(cell.removeprefix("confidence=")), 0.0), 1.0)
        except ValueError:
            return 0.0
    return 0.0


def _market_size_rows(sections: Mapping[str, object]) -> Iterable[tuple[str, tuple[str, ...]]]:
    section = _section(sections, "market_size")
    for row in _rows(section):
        if len(row) >= 3 and row[0] in {"tam", "sam", "som"}:
            yield row[0], row


def _section(sections: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = sections.get(name)
    return value if isinstance(value, Mapping) else {}


def _rows(section: Mapping[str, object]) -> Iterable[tuple[str, ...]]:
    raw_rows = section.get("rows", ())
    if not isinstance(raw_rows, tuple | list):
        return ()
    return tuple(
        tuple(str(cell) for cell in row)
        for row in raw_rows
        if isinstance(row, tuple | list)
    )


def _is_metric_row(row: tuple[str, ...]) -> bool:
    if any(cell.startswith("dimension_ref=") for cell in row):
        return False
    if any(cell.startswith(("calculation_ref=", "input.missing:")) for cell in row):
        return True
    if any(cell.startswith("evidence_ref=") for cell in row):
        identifier = row[0].strip().casefold().replace("-", "_").replace(" ", "_")
        return identifier in _SOURCE_BACKED_DIRECT_METRIC_KEYS
    return False


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


def _card_from_metric_row(identifier: str, row: tuple[str, ...]) -> FounderAdvisorCard:
    status = _metric_status(row)
    title = _title(identifier)
    if status == "needs_input":
        return FounderAdvisorCard(
            title_ru=title,
            summary_ru=f"{title} пока нельзя подтвердить по текущему срезу.",
            status=status,
            why_it_matters_ru=_why_it_matters(identifier),
            next_unlock_ru=_next_unlock(identifier),
        )
    if status == "contradiction":
        return FounderAdvisorCard(
            title_ru=title,
            summary_ru=f"По показателю «{title}» есть противоречивые сведения.",
            status=status,
            why_it_matters_ru=_why_it_matters(identifier),
            next_unlock_ru=f"Сверьте первичные данные по показателю «{title}» и подтвердите единый период.",
        )
    value = row[1] if len(row) > 1 else ""
    return FounderAdvisorCard(
        title_ru=title,
        summary_ru=f"Значение «{title}» подтверждено: {value}.",
        status=status,
        why_it_matters_ru=_why_it_matters(identifier),
        next_unlock_ru=_next_unlock_after_confirmed(identifier),
    )


def _card_from_market_row(identifier: str, row: tuple[str, ...]) -> FounderAdvisorCard:
    title = _title(identifier)
    source_status = row[1].casefold()
    value = row[2]
    if source_status == "contradiction":
        status: FounderAdvisorCardStatus = "contradiction"
        summary = f"По оценке «{title}» есть противоречивые источники."
        next_unlock = f"Сверьте источники для оценки «{title}» и зафиксируйте единый расчёт."
    elif source_status == "source_fact":
        status = "confirmed"
        summary = f"{title} подтверждён источником: {value}."
        next_unlock = _next_unlock_after_confirmed(identifier)
    elif value.casefold() == "missing" or source_status == "insufficient_data":
        status = "needs_input"
        summary = f"Оценку «{title}» пока нельзя подтвердить по текущему срезу."
        next_unlock = f"Добавьте источники и расчёт для оценки «{title}»."
    else:
        status = "estimated"
        summary = f"{title} — гипотеза: {value}."
        next_unlock = (
            f"Подтвердите оценку «{title}» независимым источником "
            "или проверяемым расчётом."
        )
    return FounderAdvisorCard(
        title_ru=title,
        summary_ru=summary,
        status=status,
        why_it_matters_ru=_why_it_matters(identifier),
        next_unlock_ru=next_unlock,
    )


def _metric_status(row: tuple[str, ...]) -> FounderAdvisorCardStatus:
    normalized = " ".join(row).casefold()
    if "contradiction" in normalized:
        return "contradiction"
    if "missing" in normalized or "blocked" in normalized or "input.missing:" in normalized:
        return "needs_input"
    return "confirmed"


def _title(identifier: str) -> str:
    return {
        "mrr": "MRR",
        "monthly_recurring_revenue": "MRR",
        "arr": "ARR",
        "runway": "Runway",
        "runway_months": "Runway",
        "burn": "Burn rate",
        "burn_rate": "Burn rate",
        "net_burn": "Net burn",
        "monthly_net_burn": "Net burn",
        "gross_margin": "Валовая маржа",
        "tam": "TAM",
        "sam": "SAM",
        "som": "SOM",
    }.get(identifier, identifier.replace("_", " ").upper())


def _why_it_matters(identifier: str) -> str:
    return {
        "mrr": "MRR показывает текущую повторяющуюся выручку и её динамику.",
        "monthly_recurring_revenue": "MRR показывает текущую повторяющуюся выручку и её динамику.",
        "gross_margin": "Валовая маржа показывает, какая часть выручки остаётся после прямых затрат.",
        "tam": "TAM задаёт верхнюю границу рынка для проверки масштаба возможности.",
        "sam": "SAM помогает сфокусировать достижимый целевой рынок.",
        "som": "SOM показывает реалистичную долю рынка для ближайшего плана.",
    }.get(identifier, "Показатель нужен, чтобы обосновать решение данными.")


def _next_unlock(identifier: str) -> str:
    if identifier == "mrr":
        return "добавьте MRR за текущий месяц, чтобы точнее оценить выручку."
    return f"Добавьте подтверждённые исходные данные для показателя «{_title(identifier)}»."


def _next_unlock_after_confirmed(identifier: str) -> str:
    title = _title(identifier)
    return f"Добавьте значение «{title}» за следующий период, чтобы увидеть динамику."

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Literal


FORMULA_SET_VERSION = "public_company_metrics@1"
QUANT = Decimal("0.000001")
MetricStatusLiteral = Literal["calculated", "insufficient_data"]
PeriodRole = Literal["single", "current", "prior", "market_as_of"]


@dataclass(frozen=True)
class MetricSlot:
    name: str
    fact_name: str
    period_role: PeriodRole = "single"
    unit_kind: Literal["currency", "shares"] = "currency"


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    slots: tuple[MetricSlot, ...]
    formula: Callable[[dict[str, Decimal]], Decimal]
    unit_policy: Literal["ratio", "currency"]
    display_places: int
    denominator_slots: tuple[str, ...] = ()
    allow_negative_slots: tuple[str, ...] = ()
    formula_version: str = ""

    def __post_init__(self) -> None:
        if not self.formula_version:
            object.__setattr__(self, "formula_version", f"{self.name}@1")


def _revenue_growth(v: dict[str, Decimal]) -> Decimal:
    return (v["current_revenue"] / v["prior_revenue"]) - Decimal("1")


def _gross_margin(v: dict[str, Decimal]) -> Decimal:
    return v["gross_profit"] / v["revenue"]


def _operating_margin(v: dict[str, Decimal]) -> Decimal:
    return v["operating_income"] / v["revenue"]


def _net_margin(v: dict[str, Decimal]) -> Decimal:
    return v["net_income"] / v["revenue"]


def _free_cash_flow(v: dict[str, Decimal]) -> Decimal:
    return v["operating_cash_flow"] - v["capital_expenditures"]


def _net_debt(v: dict[str, Decimal]) -> Decimal:
    return v["total_debt"] - v["cash_and_equivalents"]


def _current_ratio(v: dict[str, Decimal]) -> Decimal:
    return v["current_assets"] / v["current_liabilities"]


def _interest_coverage(v: dict[str, Decimal]) -> Decimal:
    return v["ebit"] / v["interest_expense"]


def _enterprise_value(v: dict[str, Decimal]) -> Decimal:
    return v["market_cap"] + v["total_debt"] - v["cash_and_equivalents"]


def _ev_sales(v: dict[str, Decimal]) -> Decimal:
    return _enterprise_value(v) / v["revenue"]


def _ev_ebitda(v: dict[str, Decimal]) -> Decimal:
    return _enterprise_value(v) / v["ebitda"]


def _pe_ratio(v: dict[str, Decimal]) -> Decimal:
    return v["market_cap"] / v["net_income"]


def _dilution(v: dict[str, Decimal]) -> Decimal:
    return (v["current_diluted_shares"] / v["prior_diluted_shares"]) - Decimal("1")


def _working_capital_trend(v: dict[str, Decimal]) -> Decimal:
    current = v["current_assets_current"] - v["current_liabilities_current"]
    prior = v["current_assets_prior"] - v["current_liabilities_prior"]
    return current - prior


PUBLIC_METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        name="revenue_growth",
        slots=(
            MetricSlot("current_revenue", "revenue", "current"),
            MetricSlot("prior_revenue", "revenue", "prior"),
        ),
        formula=_revenue_growth,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("prior_revenue",),
    ),
    MetricDefinition(
        name="gross_margin",
        slots=(MetricSlot("gross_profit", "gross_profit"), MetricSlot("revenue", "revenue")),
        formula=_gross_margin,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("revenue",),
        allow_negative_slots=("gross_profit",),
    ),
    MetricDefinition(
        name="operating_margin",
        slots=(MetricSlot("operating_income", "operating_income"), MetricSlot("revenue", "revenue")),
        formula=_operating_margin,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("revenue",),
        allow_negative_slots=("operating_income",),
    ),
    MetricDefinition(
        name="net_margin",
        slots=(MetricSlot("net_income", "net_income"), MetricSlot("revenue", "revenue")),
        formula=_net_margin,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("revenue",),
        allow_negative_slots=("net_income",),
    ),
    MetricDefinition(
        name="free_cash_flow",
        slots=(
            MetricSlot("operating_cash_flow", "operating_cash_flow"),
            MetricSlot("capital_expenditures", "capital_expenditures"),
        ),
        formula=_free_cash_flow,
        unit_policy="currency",
        display_places=2,
    ),
    MetricDefinition(
        name="net_debt",
        slots=(MetricSlot("total_debt", "total_debt"), MetricSlot("cash_and_equivalents", "cash_and_equivalents")),
        formula=_net_debt,
        unit_policy="currency",
        display_places=2,
    ),
    MetricDefinition(
        name="current_ratio",
        slots=(MetricSlot("current_assets", "current_assets"), MetricSlot("current_liabilities", "current_liabilities")),
        formula=_current_ratio,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("current_liabilities",),
    ),
    MetricDefinition(
        name="interest_coverage",
        slots=(MetricSlot("ebit", "ebit"), MetricSlot("interest_expense", "interest_expense")),
        formula=_interest_coverage,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("interest_expense",),
        allow_negative_slots=("ebit",),
    ),
    MetricDefinition(
        name="ev_sales",
        slots=(
            MetricSlot("market_cap", "market_cap", "market_as_of"),
            MetricSlot("total_debt", "total_debt", "current"),
            MetricSlot("cash_and_equivalents", "cash_and_equivalents", "current"),
            MetricSlot("revenue", "revenue", "current"),
        ),
        formula=_ev_sales,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("revenue",),
        allow_negative_slots=("market_cap",),
    ),
    MetricDefinition(
        name="ev_ebitda",
        slots=(
            MetricSlot("market_cap", "market_cap", "market_as_of"),
            MetricSlot("total_debt", "total_debt", "current"),
            MetricSlot("cash_and_equivalents", "cash_and_equivalents", "current"),
            MetricSlot("ebitda", "ebitda", "current"),
        ),
        formula=_ev_ebitda,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("ebitda",),
    ),
    MetricDefinition(
        name="pe_ratio",
        slots=(MetricSlot("market_cap", "market_cap", "market_as_of"), MetricSlot("net_income", "net_income", "current")),
        formula=_pe_ratio,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("net_income",),
    ),
    MetricDefinition(
        name="dilution",
        slots=(
            MetricSlot("current_diluted_shares", "weighted_average_diluted_shares", "current", "shares"),
            MetricSlot("prior_diluted_shares", "weighted_average_diluted_shares", "prior", "shares"),
        ),
        formula=_dilution,
        unit_policy="ratio",
        display_places=4,
        denominator_slots=("prior_diluted_shares",),
    ),
    MetricDefinition(
        name="working_capital_trend",
        slots=(
            MetricSlot("current_assets_current", "current_assets", "current"),
            MetricSlot("current_liabilities_current", "current_liabilities", "current"),
            MetricSlot("current_assets_prior", "current_assets", "prior"),
            MetricSlot("current_liabilities_prior", "current_liabilities", "prior"),
        ),
        formula=_working_capital_trend,
        unit_policy="currency",
        display_places=2,
    ),
)

PUBLIC_METRICS = {definition.name: definition for definition in PUBLIC_METRIC_DEFINITIONS}

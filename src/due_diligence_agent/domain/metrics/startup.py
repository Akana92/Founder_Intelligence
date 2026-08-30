from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


STARTUP_FORMULA_SET_VERSION = "startup_unit_economics_metrics@1"
STARTUP_QUANT = Decimal("0.000001")

StartupUnitPolicy = Literal["currency", "currency_per_month", "count", "ratio", "months"]
StartupAggregation = Literal["single", "sum"]
StartupPeriodRole = Literal["single", "current", "prior"]


@dataclass(frozen=True)
class StartupMetricInput:
    slot: str
    fact_name: str
    unit_policy: StartupUnitPolicy
    period_role: StartupPeriodRole = "single"
    aggregation: StartupAggregation = "single"


@dataclass(frozen=True)
class StartupMetricDefinition:
    name: str
    slots: tuple[StartupMetricInput, ...]
    formula: Callable[[dict[str, Decimal]], Decimal]
    unit: str
    display_places: int
    denominator_slots: tuple[str, ...] = ()
    allow_negative_slots: tuple[str, ...] = ()
    required_assumptions: tuple[str, ...] = ()
    formula_version: str = ""

    def __post_init__(self) -> None:
        if not self.formula_version:
            object.__setattr__(self, "formula_version", f"{self.name}@1")


def _mrr(v: dict[str, Decimal]) -> Decimal:
    return v["monthly_recurring_revenue"]


def _arr(v: dict[str, Decimal]) -> Decimal:
    return v["monthly_recurring_revenue"] * Decimal("12")


def _period_growth(v: dict[str, Decimal]) -> Decimal:
    return (v["current_value"] - v["prior_value"]) / v["prior_value"]


def _gross_margin(v: dict[str, Decimal]) -> Decimal:
    return (v["revenue"] - v["cogs"]) / v["revenue"]


def _net_burn(v: dict[str, Decimal]) -> Decimal:
    return v["cash_outflows"] - v["cash_inflows"]


def _runway(v: dict[str, Decimal]) -> Decimal:
    return v["cash"] / v["monthly_net_burn"]


def _cac(v: dict[str, Decimal]) -> Decimal:
    return v["sales_marketing_spend"] / v["new_customers"]


def _ltv(v: dict[str, Decimal]) -> Decimal:
    return (v["monthly_arpa"] * v["gross_margin_rate"]) / v["logo_churn_rate"]


def _ltv_cac(v: dict[str, Decimal]) -> Decimal:
    return v["ltv"] / v["cac"]


def _cac_payback(v: dict[str, Decimal]) -> Decimal:
    return v["cac"] / (v["monthly_arpa"] * v["gross_margin_rate"])


def _logo_churn(v: dict[str, Decimal]) -> Decimal:
    return v["lost_customers"] / v["opening_customers"]


def _revenue_churn(v: dict[str, Decimal]) -> Decimal:
    return v["churned_mrr"] / v["opening_mrr"]


def _nrr(v: dict[str, Decimal]) -> Decimal:
    return (
        v["opening_mrr"]
        + v["expansion_mrr"]
        - v["contraction_mrr"]
        - v["churned_mrr"]
    ) / v["opening_mrr"]


def _burn_multiple(v: dict[str, Decimal]) -> Decimal:
    return v["net_burn"] / v["net_new_arr"]


def _rule_of_40(v: dict[str, Decimal]) -> Decimal:
    return v["revenue_growth_rate"] + v["profit_margin"]


def _cohort_retention(v: dict[str, Decimal]) -> Decimal:
    return v["ending_cohort_customers"] / v["starting_cohort_customers"]


STARTUP_METRIC_DEFINITIONS: tuple[StartupMetricDefinition, ...] = (
    StartupMetricDefinition(
        name="mrr",
        slots=(
            StartupMetricInput(
                "monthly_recurring_revenue",
                "monthly_recurring_revenue",
                "currency_per_month",
                aggregation="sum",
            ),
        ),
        formula=_mrr,
        unit="currency_per_month",
        display_places=2,
    ),
    StartupMetricDefinition(
        name="arr",
        slots=(
            StartupMetricInput(
                "monthly_recurring_revenue",
                "monthly_recurring_revenue",
                "currency_per_month",
                aggregation="sum",
            ),
        ),
        formula=_arr,
        unit="currency",
        display_places=2,
    ),
    StartupMetricDefinition(
        name="period_growth",
        slots=(
            StartupMetricInput("current_value", "revenue", "currency", period_role="current"),
            StartupMetricInput("prior_value", "revenue", "currency", period_role="prior"),
        ),
        formula=_period_growth,
        unit="ratio",
        display_places=4,
        denominator_slots=("prior_value",),
    ),
    StartupMetricDefinition(
        name="gross_margin",
        slots=(
            StartupMetricInput("revenue", "revenue", "currency"),
            StartupMetricInput("cogs", "cogs", "currency"),
        ),
        formula=_gross_margin,
        unit="ratio",
        display_places=4,
        denominator_slots=("revenue",),
    ),
    StartupMetricDefinition(
        name="net_burn",
        slots=(
            StartupMetricInput("cash_outflows", "cash_outflows", "currency"),
            StartupMetricInput("cash_inflows", "cash_inflows", "currency"),
        ),
        formula=_net_burn,
        unit="currency",
        display_places=2,
    ),
    StartupMetricDefinition(
        name="runway_months",
        slots=(
            StartupMetricInput("cash", "cash", "currency"),
            StartupMetricInput("monthly_net_burn", "monthly_net_burn", "currency_per_month"),
        ),
        formula=_runway,
        unit="months",
        display_places=1,
        denominator_slots=("monthly_net_burn",),
    ),
    StartupMetricDefinition(
        name="cac",
        slots=(
            StartupMetricInput("sales_marketing_spend", "sales_marketing_spend", "currency"),
            StartupMetricInput("new_customers", "new_customers", "count"),
        ),
        formula=_cac,
        unit="currency",
        display_places=2,
        denominator_slots=("new_customers",),
    ),
    StartupMetricDefinition(
        name="ltv",
        slots=(
            StartupMetricInput("monthly_arpa", "monthly_arpa", "currency_per_month"),
            StartupMetricInput("gross_margin_rate", "gross_margin_rate", "ratio"),
            StartupMetricInput("logo_churn_rate", "logo_churn_rate", "ratio"),
        ),
        formula=_ltv,
        unit="currency",
        display_places=2,
        denominator_slots=("logo_churn_rate",),
        required_assumptions=("ltv_model",),
        formula_version="ltv@gross_margin_adjusted_arpa_churn@1",
    ),
    StartupMetricDefinition(
        name="ltv_cac",
        slots=(
            StartupMetricInput("ltv", "ltv", "currency"),
            StartupMetricInput("cac", "cac", "currency"),
        ),
        formula=_ltv_cac,
        unit="ratio",
        display_places=2,
        denominator_slots=("cac",),
    ),
    StartupMetricDefinition(
        name="cac_payback_months",
        slots=(
            StartupMetricInput("cac", "cac", "currency"),
            StartupMetricInput("monthly_arpa", "monthly_arpa", "currency_per_month"),
            StartupMetricInput("gross_margin_rate", "gross_margin_rate", "ratio"),
        ),
        formula=_cac_payback,
        unit="months",
        display_places=1,
        denominator_slots=("monthly_arpa", "gross_margin_rate"),
    ),
    StartupMetricDefinition(
        name="logo_churn",
        slots=(
            StartupMetricInput("lost_customers", "lost_customers", "count"),
            StartupMetricInput("opening_customers", "opening_customers", "count"),
        ),
        formula=_logo_churn,
        unit="ratio",
        display_places=4,
        denominator_slots=("opening_customers",),
    ),
    StartupMetricDefinition(
        name="revenue_churn",
        slots=(
            StartupMetricInput("churned_mrr", "churned_mrr", "currency_per_month"),
            StartupMetricInput("opening_mrr", "opening_mrr", "currency_per_month"),
        ),
        formula=_revenue_churn,
        unit="ratio",
        display_places=4,
        denominator_slots=("opening_mrr",),
    ),
    StartupMetricDefinition(
        name="nrr",
        slots=(
            StartupMetricInput("opening_mrr", "opening_mrr", "currency_per_month"),
            StartupMetricInput("expansion_mrr", "expansion_mrr", "currency_per_month"),
            StartupMetricInput("contraction_mrr", "contraction_mrr", "currency_per_month"),
            StartupMetricInput("churned_mrr", "churned_mrr", "currency_per_month"),
        ),
        formula=_nrr,
        unit="ratio",
        display_places=4,
        denominator_slots=("opening_mrr",),
    ),
    StartupMetricDefinition(
        name="burn_multiple",
        slots=(
            StartupMetricInput("net_burn", "net_burn", "currency"),
            StartupMetricInput("net_new_arr", "net_new_arr", "currency"),
        ),
        formula=_burn_multiple,
        unit="ratio",
        display_places=2,
        denominator_slots=("net_new_arr",),
    ),
    StartupMetricDefinition(
        name="rule_of_40",
        slots=(
            StartupMetricInput("revenue_growth_rate", "revenue_growth_rate", "ratio"),
            StartupMetricInput("profit_margin", "profit_margin", "ratio"),
        ),
        formula=_rule_of_40,
        unit="ratio",
        display_places=4,
    ),
    StartupMetricDefinition(
        name="cohort_retention",
        slots=(
            StartupMetricInput("starting_cohort_customers", "starting_cohort_customers", "count", "prior"),
            StartupMetricInput("ending_cohort_customers", "ending_cohort_customers", "count", "current"),
        ),
        formula=_cohort_retention,
        unit="ratio",
        display_places=4,
        denominator_slots=("starting_cohort_customers",),
    ),
)

STARTUP_METRICS = {definition.name: definition for definition in STARTUP_METRIC_DEFINITIONS}


def startup_metric_names() -> tuple[str, ...]:
    return tuple(STARTUP_METRICS)

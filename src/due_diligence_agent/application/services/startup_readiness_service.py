from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.domain.metrics import MetricCalculationResult, MetricStatus
from due_diligence_agent.domain.metrics.startup import STARTUP_METRICS
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.readiness import (
    StartupAdaptiveQuestion,
    StartupMetricPack,
    StartupReadinessDimension,
    StartupReadinessDimensionStatus,
    StartupReadinessSnapshot,
)
from due_diligence_agent.domain.startup.scenario import StartupScenarioVariant


_READINESS_NAMESPACE = NAMESPACE_URL
_ALLOWLISTED_METRIC_IDS = frozenset(STARTUP_METRICS)
_DEFAULT_PACK = ("gross_margin", "net_burn", "period_growth", "runway_months")
_PRE_REVENUE_PACK = ("cac", "gross_margin", "net_burn", "runway_months")
_MARKETPLACE_PACK = ("burn_multiple", "cac", "gross_margin", "net_burn", "period_growth", "runway_months")
_SAAS_PACK = (
    "arr",
    "burn_multiple",
    "cac",
    "cac_payback_months",
    "gross_margin",
    "logo_churn",
    "ltv",
    "ltv_cac",
    "mrr",
    "net_burn",
    "nrr",
    "period_growth",
    "revenue_churn",
    "runway_months",
)
_REQUIRED_READINESS_FIELDS: Mapping[str, tuple[StartupProfileFieldName, ...]] = {
    "business_model": (StartupProfileFieldName.BUSINESS_MODEL, StartupProfileFieldName.PRICING_REVENUE_MODEL),
    "traction": (StartupProfileFieldName.TRACTION,),
    "unit_economics": (StartupProfileFieldName.PRICING_REVENUE_MODEL, StartupProfileFieldName.METRIC_PACK_CANDIDATES),
    "market_evidence": (
        StartupProfileFieldName.ICP,
        StartupProfileFieldName.GEOGRAPHY,
        StartupProfileFieldName.COMPETITORS_MENTIONED,
    ),
    "gtm_evidence": (StartupProfileFieldName.CHANNELS_GTM,),
    "risk_disclosure": (StartupProfileFieldName.ASSUMPTIONS, StartupProfileFieldName.WEAKNESSES),
}
_QUESTION_PRIORITY = {
    "profile.contradiction:business_model": 1,
    "readiness.missing:business_model": 5,
    "readiness.missing:traction": 6,
    "readiness.missing:unit_economics": 7,
    "readiness.missing:market_evidence": 8,
    "readiness.missing:gtm_evidence": 9,
    "readiness.missing:risk_disclosure": 10,
    "input.missing:monthly_recurring_revenue": 10,
    "input.missing:cash": 20,
    "input.missing:revenue": 30,
    "input.missing:monthly_net_burn": 40,
    "input.missing:gross_margin_rate": 50,
}
_INPUT_LABELS = {
    "monthly_recurring_revenue": "monthly recurring revenue",
    "cash": "current cash balance",
    "revenue": "revenue for the target period",
    "monthly_net_burn": "monthly net burn",
    "gross_margin_rate": "gross margin rate",
    "monthly_arpa": "monthly ARPA",
}


class _PackKind(StrEnum):
    DEFAULT = "default"
    MARKETPLACE = "marketplace"
    PRE_REVENUE = "pre_revenue"
    SAAS = "saas"


class StartupScenarioCompleteness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    percent: int = Field(ge=0, le=100)
    executable_formula_keys: tuple[str, ...] = Field(default_factory=tuple)
    missing_input_keys: tuple[str, ...] = Field(default_factory=tuple)


class StartupReadinessService:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock

    def select_metric_pack(self, profile: StartupProfile) -> StartupMetricPack:
        kind = _select_pack_kind(profile)
        metric_ids = _metric_ids_for_kind(kind)
        dimensions = [_pack_dimension(profile, f"pack.selected:{kind.value}", status=_pack_status(kind))]
        dimensions.extend(_ignored_candidate_dimensions(profile))
        return StartupMetricPack.build(
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            profile_revision=profile.data_revision,
            metric_ids=metric_ids,
            dimensions=tuple(dimensions),
            adaptive_questions=(),
            built_at=self._now(),
        )

    def evaluate(
        self,
        profile: StartupProfile,
        metric_diagnostics: Sequence[MetricCalculationResult | Mapping[str, Any]],
        *,
        calculation_ids: Sequence[UUID],
    ) -> StartupReadinessSnapshot:
        pack = self.select_metric_pack(profile)
        diagnostics = {_diagnostic_metric_name(item): item for item in metric_diagnostics}
        evaluated_metric_ids = tuple(
            sorted(
                {
                    metric_id
                    for metric_id in (*pack.metric_ids, *diagnostics)
                    if metric_id in _ALLOWLISTED_METRIC_IDS
                }
            )
        )
        dimensions = (
            *_required_readiness_dimensions(profile, diagnostics),
            *(
                _metric_dimension(profile, metric_id, diagnostics.get(metric_id))
                for metric_id in evaluated_metric_ids
            ),
        )
        evaluated_pack = StartupMetricPack.build(
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            profile_revision=profile.data_revision,
            metric_ids=evaluated_metric_ids,
            dimensions=dimensions,
            adaptive_questions=(),
            built_at=self._now(),
        )
        return StartupReadinessSnapshot.build(
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            profile_revision=profile.data_revision,
            metric_pack=evaluated_pack,
            calculation_ids=tuple(calculation_ids),
            diagnostic_ids=(),
            built_at=self._now(),
        )

    def priority_questions(self, snapshot: StartupReadinessSnapshot) -> tuple[StartupAdaptiveQuestion, ...]:
        candidates = sorted(
            (
                (dimension.reason_code or f"input.missing:{dimension.metric_id}", dimension)
                for dimension in snapshot.metric_pack.dimensions
                if dimension.status is not StartupReadinessDimensionStatus.READY
            ),
            key=lambda item: (
                _QUESTION_PRIORITY.get(item[0], 500),
                item[0],
                item[1].metric_id,
                item[1].status.value,
            ),
        )
        questions: list[StartupAdaptiveQuestion] = []
        seen_codes: set[str] = set()
        for code, dimension in candidates:
            if code in seen_codes:
                continue
            if code.startswith("readiness.missing:"):
                continue
            seen_codes.add(code)
            questions.append(
                StartupAdaptiveQuestion(
                    question_id=_stable_uuid(f"question:{snapshot.snapshot_id}:{code}"),
                    question_code=code,
                    text=_question_text(code, dimension.metric_id),
                    dimension_id=dimension.dimension_id,
                    weight=_QUESTION_PRIORITY.get(code, 500),
                )
            )
            if len(questions) == 3:
                break
        return tuple(questions)

    def scenario_completeness(
        self,
        scenario: StartupScenarioVariant,
    ) -> StartupScenarioCompleteness:
        executable = tuple(
            sorted(
                metric.formula_key
                for metric in scenario.metrics.values()
                if metric.value_range is not None and not metric.gaps
            )
        )
        missing = tuple(
            sorted(
                {
                    gap.removeprefix("input.missing:")
                    for metric in scenario.metrics.values()
                    for gap in metric.gaps
                    if gap.startswith("input.missing:")
                }
            )
        )
        total = len(executable) + len(missing)
        percent = int((len(executable) / total) * 100) if total else 0
        return StartupScenarioCompleteness(
            percent=percent,
            executable_formula_keys=executable,
            missing_input_keys=missing,
        )

    def _now(self) -> datetime:
        value = self._clock() if self._clock is not None else datetime.now(UTC)
        if value.tzinfo != UTC:
            return value.astimezone(UTC)
        return value


def _select_pack_kind(profile: StartupProfile) -> _PackKind:
    stage = _field_text(profile, StartupProfileFieldName.STAGE)
    business_model = _field_text(profile, StartupProfileFieldName.BUSINESS_MODEL)
    pricing = _field_text(profile, StartupProfileFieldName.PRICING_REVENUE_MODEL)
    if _contains_any(stage, ("pre-revenue", "pre revenue", "idea", "prototype", "pilot")):
        return _PackKind.PRE_REVENUE
    if _contains_any(business_model + " " + pricing, ("marketplace", "transaction", "take rate")):
        return _PackKind.MARKETPLACE
    if _contains_any(business_model + " " + pricing, ("saas", "subscription", "recurring")):
        return _PackKind.SAAS
    return _PackKind.DEFAULT


def _metric_ids_for_kind(kind: _PackKind) -> tuple[str, ...]:
    values = {
        _PackKind.DEFAULT: _DEFAULT_PACK,
        _PackKind.MARKETPLACE: _MARKETPLACE_PACK,
        _PackKind.PRE_REVENUE: _PRE_REVENUE_PACK,
        _PackKind.SAAS: _SAAS_PACK,
    }[kind]
    return tuple(sorted(metric_id for metric_id in values if metric_id in _ALLOWLISTED_METRIC_IDS))


def _pack_status(kind: _PackKind) -> StartupReadinessDimensionStatus:
    if kind is _PackKind.DEFAULT:
        return StartupReadinessDimensionStatus.PROVISIONAL
    return StartupReadinessDimensionStatus.READY


def _pack_dimension(
    profile: StartupProfile,
    reason_code: str,
    *,
    status: StartupReadinessDimensionStatus,
) -> StartupReadinessDimension:
    return StartupReadinessDimension(
        dimension_id=_stable_uuid(f"pack:{profile.profile_id}:{reason_code}"),
        metric_id="gross_margin",
        status=status,
        reason_code=reason_code,
    )


def _ignored_candidate_dimensions(profile: StartupProfile) -> tuple[StartupReadinessDimension, ...]:
    field = profile.fields[StartupProfileFieldName.METRIC_PACK_CANDIDATES.value]
    dimensions: list[StartupReadinessDimension] = []
    emitted_unsupported = False
    for candidate in field.values:
        normalized = _normalize_candidate_for_allowlist(candidate)
        if normalized in _ALLOWLISTED_METRIC_IDS:
            continue
        if emitted_unsupported:
            continue
        emitted_unsupported = True
        dimensions.append(
            _pack_dimension(
                profile,
                "metric_candidate.ignored",
                status=StartupReadinessDimensionStatus.PROVISIONAL,
            )
        )
    return tuple(dimensions)


def _required_readiness_dimensions(
    profile: StartupProfile,
    diagnostics: Mapping[str, MetricCalculationResult | Mapping[str, Any]],
) -> tuple[StartupReadinessDimension, ...]:
    return tuple(
        _required_readiness_dimension(profile, dimension_code, field_names, diagnostics)
        for dimension_code, field_names in _REQUIRED_READINESS_FIELDS.items()
    )


def _required_readiness_dimension(
    profile: StartupProfile,
    dimension_code: str,
    field_names: tuple[StartupProfileFieldName, ...],
    diagnostics: Mapping[str, MetricCalculationResult | Mapping[str, Any]],
) -> StartupReadinessDimension:
    contradiction = _first_contradiction(profile, field_names)
    if contradiction is not None:
        return StartupReadinessDimension(
            dimension_id=_stable_uuid(f"readiness:{profile.profile_id}:{dimension_code}"),
            metric_id=dimension_code,
            status=StartupReadinessDimensionStatus.BLOCKED,
            reason_code=f"profile.contradiction:{contradiction.value}",
        )
    if dimension_code == "unit_economics":
        calculated = any(_diagnostic_status(item) is MetricStatus.CALCULATED for item in diagnostics.values())
        if calculated:
            return StartupReadinessDimension(
                dimension_id=_stable_uuid(f"readiness:{profile.profile_id}:{dimension_code}"),
                metric_id=dimension_code,
                status=StartupReadinessDimensionStatus.READY,
                reason_code="method.metric_diagnostics:unit_economics",
            )
        if any(_has_source_evidence(profile, field_name) for field_name in field_names):
            return StartupReadinessDimension(
                dimension_id=_stable_uuid(f"readiness:{profile.profile_id}:{dimension_code}"),
                metric_id=dimension_code,
                status=StartupReadinessDimensionStatus.PROVISIONAL,
                reason_code="method.metric_diagnostics:unit_economics",
            )
        return StartupReadinessDimension(
            dimension_id=_stable_uuid(f"readiness:{profile.profile_id}:{dimension_code}"),
            metric_id=dimension_code,
            status=StartupReadinessDimensionStatus.BLOCKED,
            reason_code="method.metric_diagnostics:unit_economics",
        )
    status = (
        StartupReadinessDimensionStatus.READY
        if any(_has_source_evidence(profile, field_name) for field_name in field_names)
        else StartupReadinessDimensionStatus.BLOCKED
    )
    return StartupReadinessDimension(
        dimension_id=_stable_uuid(f"readiness:{profile.profile_id}:{dimension_code}"),
        metric_id=dimension_code,
        status=status,
        reason_code=f"method.profile_field:{dimension_code}",
    )


def _metric_dimension(
    profile: StartupProfile,
    metric_id: str,
    diagnostic: MetricCalculationResult | Mapping[str, Any] | None,
) -> StartupReadinessDimension:
    contradiction = _blocking_contradiction(profile)
    if contradiction is not None:
        return StartupReadinessDimension(
            dimension_id=_stable_uuid(f"metric:{profile.profile_id}:{metric_id}"),
            metric_id=metric_id,
            status=StartupReadinessDimensionStatus.BLOCKED,
            reason_code=f"profile.contradiction:{contradiction.value}",
        )
    if diagnostic is None:
        return StartupReadinessDimension(
            dimension_id=_stable_uuid(f"metric:{profile.profile_id}:{metric_id}"),
            metric_id=metric_id,
            status=StartupReadinessDimensionStatus.BLOCKED,
            reason_code=f"input.missing:{metric_id}",
        )
    status = _diagnostic_status(diagnostic)
    if status == MetricStatus.CALCULATED:
        return StartupReadinessDimension(
            dimension_id=_stable_uuid(f"metric:{profile.profile_id}:{metric_id}"),
            metric_id=metric_id,
            status=StartupReadinessDimensionStatus.READY,
            reason_code=f"metric.calculated:{_diagnostic_formula_version(diagnostic)}",
        )
    return StartupReadinessDimension(
        dimension_id=_stable_uuid(f"metric:{profile.profile_id}:{metric_id}"),
        metric_id=metric_id,
        status=StartupReadinessDimensionStatus.BLOCKED,
        reason_code=_diagnostic_warning(diagnostic) or f"input.missing:{metric_id}",
    )


def _blocking_contradiction(profile: StartupProfile) -> StartupProfileFieldName | None:
    return _first_contradiction(
        profile,
        (
            StartupProfileFieldName.BUSINESS_MODEL,
            StartupProfileFieldName.STAGE,
            StartupProfileFieldName.PRICING_REVENUE_MODEL,
        ),
    )


def _first_contradiction(
    profile: StartupProfile,
    field_names: tuple[StartupProfileFieldName, ...],
) -> StartupProfileFieldName | None:
    for field_name in field_names:
        field = profile.fields[field_name.value]
        if field.status is StartupProfileFieldStatus.CONTRADICTION:
            return field_name
    return None


def _has_source_evidence(profile: StartupProfile, field_name: StartupProfileFieldName) -> bool:
    field = profile.fields[field_name.value]
    return field.status in {
        StartupProfileFieldStatus.SOURCE_FACT,
        StartupProfileFieldStatus.INFERENCE,
    } and bool(field.values)


def _field_text(profile: StartupProfile, field_name: StartupProfileFieldName) -> str:
    return " ".join(profile.fields[field_name.value].values).casefold()


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _normalize_candidate_for_allowlist(value: str) -> str:
    return re.sub(r"\s+", "_", value.strip().casefold())


def _diagnostic_metric_name(item: MetricCalculationResult | Mapping[str, Any]) -> str:
    if isinstance(item, MetricCalculationResult):
        return item.metric_name
    return str(item["metric_name"])


def _diagnostic_status(item: MetricCalculationResult | Mapping[str, Any]) -> MetricStatus:
    if isinstance(item, MetricCalculationResult):
        return item.status
    return MetricStatus(str(item["status"]))


def _diagnostic_formula_version(item: MetricCalculationResult | Mapping[str, Any]) -> str:
    if isinstance(item, MetricCalculationResult):
        return item.formula_version
    value = item.get("formula_version")
    if value is not None:
        return str(value)
    return f"{_diagnostic_metric_name(item)}@workflow"


def _diagnostic_warning(item: MetricCalculationResult | Mapping[str, Any]) -> str | None:
    warnings: tuple[str, ...]
    if isinstance(item, MetricCalculationResult):
        warnings = item.warnings
    else:
        raw = item.get("warnings", ())
        warnings = tuple(str(value) for value in raw)
    return warnings[0] if warnings else None


def _question_text(code: str, metric_id: str) -> str:
    if code.startswith("profile.contradiction:"):
        label = code.removeprefix("profile.contradiction:").replace("_", " ")
        return f"Clarify the {label} decision so the affected readiness checks can proceed."
    if code.startswith("input.missing:"):
        input_name = code.removeprefix("input.missing:")
        label = _INPUT_LABELS.get(input_name, input_name.replace("_", " "))
        return f"Provide {label} so the {metric_id} metric and readiness dimension can be assessed."
    if code.startswith("readiness.missing:"):
        label = code.removeprefix("readiness.missing:").replace("_", " ")
        return f"Provide source evidence for {label} so the readiness dimension can be assessed."
    return f"Provide the missing decision for {metric_id} so readiness can be assessed."


def _stable_uuid(seed: str) -> UUID:
    return uuid5(_READINESS_NAMESPACE, seed)

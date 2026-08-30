from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.domain.startup.market import (
    MarketSizingAssumption,
    MarketSizingEstimate,
    StartupMarketSizing,
    StartupResearchPlan,
    StartupResearchSentiment,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
    StartupSentimentSignal,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)

_MAX_QUERY_COUNT = 8
_MAX_LIVE_QUERY_COUNT = 3
_MAX_QUERY_LENGTH = 120
_MONEY_QUANT = Decimal("0.000001")
_SHARE_MIN = Decimal("0")
_SHARE_MAX = Decimal("1")
_RESEARCH_PLAN_FIELDS: tuple[StartupProfileFieldName, ...] = (
    StartupProfileFieldName.SOLUTION,
    StartupProfileFieldName.ICP,
    StartupProfileFieldName.USERS,
    StartupProfileFieldName.BUYERS,
    StartupProfileFieldName.GEOGRAPHY,
    StartupProfileFieldName.BUSINESS_MODEL,
    StartupProfileFieldName.PRICING_REVENUE_MODEL,
    StartupProfileFieldName.COMPETITORS_MENTIONED,
)
_GAP_FIELD_ORDER: tuple[StartupProfileFieldName, ...] = (
    StartupProfileFieldName.SOLUTION,
    StartupProfileFieldName.ICP,
    StartupProfileFieldName.GEOGRAPHY,
    StartupProfileFieldName.BUSINESS_MODEL,
)
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|authorization|bearer|password|passwd|private[_-]?key|secret)",
)
_PRIVATE_PATH_RE = re.compile(
    r"(?i)(?:file://|[a-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+|(?:^|[\\/])(?:tmp|var|home|etc|users)(?:[\\/]|$)|~[\\/])",
)
_QUERY_UNSAFE_RE = re.compile(r"(?i)(?:[?&](?:token|secret|api[_-]?key)=|authorization\s*:|bearer\s+)")
_LIVE_PRIVATE_TEXT_RE = re.compile(
    r"(?i)(?:%PDF|raw[_ -]?pdf|document[_ -]?text|filename|local[_ -]?path|"
    r"prompt|system\s+instructions|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])|"
    r"\.(?:pdf|docx|xlsx|csv|pptx)(?:\b|$)|"
    r"\b(?:mrr|arr|burn(?:[_ -]+rate)?|cash(?:[_ -]+balance)?|revenue|pricing|"
    r"contracts?|customers|clients|cap[_ -]+table|internal[_ -]+financial)\b|"
    r"\b(?:customer|client)[_ -]+(?:count|counts|number|list|names?)\b)"
)
_LIVE_QUERY_PROFILE_NOISE_RE = re.compile(
    r"(?iu)(?:\bbreak-even\b|\bgo/no-go\b|\bround\b|"
    r"\b(?:раунд|планов(?:ый|ая|ое|ые)|инвестиц|equity|ebitda|capex|opex)\b|"
    r"\b(?:финансир[а-яё]*|commercial\s+validation|staged\s+commercial)\b|"
    r"\d[\d\s,.]*(?:₸|kzt|usd|тенге|\$))"
)


@dataclass(frozen=True)
class StartupResearchPlanBuildResult:
    plan: StartupResearchPlan
    gap_codes: tuple[str, ...]
    omitted_values: tuple[str, ...]


@dataclass(frozen=True)
class StartupMarketSizingInputs:
    source_ids: tuple[UUID, ...]
    as_of: date
    currency: str = "USD"
    unit: str = "annual_revenue"
    tam_amount: Decimal | None = None
    sam_share: Decimal | None = None
    som_share: Decimal | None = None
    total_accounts: Decimal | None = None
    addressable_share: Decimal | None = None
    obtainable_share: Decimal | None = None
    annual_revenue_per_account: Decimal | None = None
    sam_currency: str | None = None
    narrative_market_size: str | None = None


@dataclass(frozen=True)
class StartupMarketSizingResult:
    sizing: StartupMarketSizing
    assumptions: tuple[MarketSizingAssumption, ...]


@dataclass(frozen=True)
class StartupSentimentAggregate:
    counts: Mapping[str, int]
    source_ids: tuple[UUID, ...]
    window_start: datetime | None
    window_end: datetime | None
    stale: bool
    supports_primary_financial_metrics: bool = False


class StartupMarketResearchService:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock

    def build_research_plan(
        self,
        profile: StartupProfile,
        *,
        source_mode: StartupResearchSourceMode = StartupResearchSourceMode.FROZEN,
        public_focus: str | None = None,
        public_topic: str | None = None,
    ) -> StartupResearchPlanBuildResult:
        if source_mode is StartupResearchSourceMode.LIVE:
            return _build_live_research_plan(
                profile,
                public_focus=public_focus,
                public_topic=public_topic,
            )

        safe_values: dict[StartupProfileFieldName, tuple[str, ...]] = {}
        unsafe_fields: set[StartupProfileFieldName] = set()
        gaps: list[str] = []

        for field_name in _RESEARCH_PLAN_FIELDS:
            field = profile.fields[field_name.value]
            if field.status is StartupProfileFieldStatus.CONTRADICTION:
                continue
            safe, unsafe = _safe_field_values(field)
            safe_values[field_name] = safe
            if unsafe:
                unsafe_fields.add(field_name)

        for field_name in _GAP_FIELD_ORDER:
            field = profile.fields[field_name.value]
            if field_name in unsafe_fields:
                gaps.append(f"research_plan.private_value:{field_name.value}")
                continue
            if field.status is StartupProfileFieldStatus.CONTRADICTION:
                gaps.append(f"research_plan.contradiction:{field_name.value}")
                continue
            if not safe_values.get(field_name):
                gaps.append(f"research_plan.missing:{field_name.value}")

        queries = _build_queries(safe_values)
        plan = StartupResearchPlan(
            case_id=profile.case_id,
            source_mode=StartupResearchSourceMode.FROZEN,
            queries=queries,
            max_queries=_MAX_QUERY_COUNT,
        )
        return StartupResearchPlanBuildResult(
            plan=plan,
            gap_codes=tuple(gaps),
            omitted_values=tuple(f"private_value:{field_name.value}" for field_name in sorted(unsafe_fields, key=lambda item: item.value)),
        )

    def calculate_market_sizing(self, inputs: StartupMarketSizingInputs) -> StartupMarketSizingResult:
        if inputs.narrative_market_size is not None:
            raise ValueError("narrative market size cannot be converted into numeric estimates")
        if inputs.sam_currency is not None and inputs.sam_currency.casefold() != inputs.currency.casefold():
            raise ValueError("currency mismatch")

        source_ids = tuple(sorted(inputs.source_ids))
        if inputs.tam_amount is not None:
            tam_value = _positive_money(inputs.tam_amount)
            tam = _source_estimate(
                "tam",
                tam_value,
                source_ids=source_ids,
                as_of=inputs.as_of,
                currency=inputs.currency,
                unit=inputs.unit,
                formula_version="market_sizing.top_down@1",
            )
            assumptions: list[MarketSizingAssumption] = []
            sam, sam_assumption = self._share_estimate(
                "sam",
                tam_value,
                inputs.sam_share,
                lineage=(),
                source_ids=source_ids,
                as_of=inputs.as_of,
                currency=inputs.currency,
                unit=inputs.unit,
                formula_version="market_sizing.top_down@1",
            )
            if sam_assumption is not None:
                assumptions.append(sam_assumption)
            som_base = sam.value
            som, som_assumption = self._share_estimate(
                "som",
                som_base,
                inputs.som_share,
                lineage=(sam_assumption.assumption_id,) if sam_assumption is not None else (),
                source_ids=source_ids,
                as_of=inputs.as_of,
                currency=inputs.currency,
                unit=inputs.unit,
                formula_version="market_sizing.top_down@1",
            )
            if som_assumption is not None:
                assumptions.append(som_assumption)
            return StartupMarketSizingResult(
                sizing=StartupMarketSizing(tam=tam, sam=sam, som=som),
                assumptions=tuple(sorted(assumptions, key=lambda item: str(item.assumption_id))),
            )

        if inputs.total_accounts is None or inputs.annual_revenue_per_account is None:
            return StartupMarketSizingResult(
                sizing=_insufficient_sizing(inputs, formula_version="market_sizing.insufficient@1"),
                assumptions=(),
            )

        assumptions = [
            _assumption(
                "bottom-up-total-accounts",
                f"Total reachable account universe: {_decimal_string(inputs.total_accounts)}",
                source_ids=source_ids,
                as_of=inputs.as_of,
            ),
            _assumption(
                "bottom-up-arpa",
                f"Annual revenue per account: {_decimal_string(inputs.annual_revenue_per_account)}",
                source_ids=source_ids,
                as_of=inputs.as_of,
            ),
        ]
        tam_value = _positive_money(inputs.total_accounts) * _positive_money(inputs.annual_revenue_per_account)
        tam = _inference_estimate(
            "tam",
            tam_value,
            assumption_refs=tuple(item.assumption_id for item in assumptions),
            source_ids=source_ids,
            as_of=inputs.as_of,
            currency=inputs.currency,
            unit=inputs.unit,
            formula_version="market_sizing.bottom_up@1",
        )
        sam, sam_assumption = self._share_estimate(
            "sam",
            tam_value,
            inputs.addressable_share,
            lineage=tuple(item.assumption_id for item in assumptions),
            source_ids=source_ids,
            as_of=inputs.as_of,
            currency=inputs.currency,
            unit=inputs.unit,
            formula_version="market_sizing.bottom_up@1",
        )
        if sam_assumption is not None:
            assumptions.append(sam_assumption)
        som, som_assumption = self._share_estimate(
            "som",
            sam.value,
            inputs.obtainable_share,
            lineage=(sam_assumption.assumption_id,) if sam_assumption is not None else (),
            source_ids=source_ids,
            as_of=inputs.as_of,
            currency=inputs.currency,
            unit=inputs.unit,
            formula_version="market_sizing.bottom_up@1",
        )
        if som_assumption is not None:
            assumptions.append(som_assumption)
        return StartupMarketSizingResult(
            sizing=StartupMarketSizing(tam=tam, sam=sam, som=som),
            assumptions=tuple(sorted(assumptions, key=lambda item: str(item.assumption_id))),
        )

    def aggregate_sentiment(
        self,
        signals: Sequence[StartupSentimentSignal],
        *,
        sources: Sequence[StartupResearchSource],
        max_age_days: int = 90,
    ) -> StartupSentimentAggregate:
        source_by_id = {source.source_id: source for source in sources}
        now = self._now()
        counter: Counter[str] = Counter()
        source_ids: set[UUID] = set()
        window_start: datetime | None = None
        window_end: datetime | None = None
        stale = False
        for signal in signals:
            if signal.supports_primary_financial_metrics:
                raise ValueError("sentiment cannot support primary financial metrics")
            source = source_by_id.get(signal.source_id)
            if source is None:
                raise ValueError("sentiment source is missing from source list")
            if signal.source_mode is not source.source_mode:
                raise ValueError("sentiment source mode mismatch")
            counter[signal.sentiment.value] += 1
            source_ids.add(signal.source_id)
            window_start = signal.as_of if window_start is None else min(window_start, signal.as_of)
            window_end = signal.as_of if window_end is None else max(window_end, signal.as_of)
            if source.stale or signal.as_of < now - timedelta(days=max_age_days):
                stale = True
        return StartupSentimentAggregate(
            counts={sentiment.value: counter[sentiment.value] for sentiment in StartupResearchSentiment},
            source_ids=tuple(sorted(source_ids)),
            window_start=window_start,
            window_end=window_end,
            stale=stale,
            supports_primary_financial_metrics=False,
        )

    def _share_estimate(
        self,
        level: str,
        base_value: Decimal | None,
        share: Decimal | None,
        *,
        lineage: tuple[UUID, ...],
        source_ids: tuple[UUID, ...],
        as_of: date,
        currency: str,
        unit: str,
        formula_version: str,
    ) -> tuple[MarketSizingEstimate, MarketSizingAssumption | None]:
        if base_value is None or share is None:
            return _insufficient_estimate(level, as_of=as_of, currency=currency, unit=unit, formula_version=formula_version), None
        checked_share = _share(share)
        assumption = _assumption(
            f"{level}-share",
            f"{level.upper()} share of parent market: {_decimal_string(checked_share)}",
            source_ids=source_ids,
            as_of=as_of,
            lineage=lineage,
        )
        return (
            _inference_estimate(
                level,
                base_value * checked_share,
                assumption_refs=(assumption.assumption_id,),
                source_ids=source_ids,
                as_of=as_of,
                currency=currency,
                unit=unit,
                formula_version=formula_version,
            ),
            assumption,
        )

    def _now(self) -> datetime:
        value = self._clock() if self._clock is not None else datetime.now(UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _safe_field_values(field: StartupProfileField) -> tuple[tuple[str, ...], tuple[str, ...]]:
    safe: list[str] = []
    unsafe: list[str] = []
    if field.status is StartupProfileFieldStatus.INSUFFICIENT_DATA:
        return (), ()
    for value in field.values:
        if _is_safe_query_text(value):
            safe.append(value)
        else:
            unsafe.append(value)
    return tuple(sorted(set(safe), key=str.casefold)), tuple(sorted(set(unsafe), key=str.casefold))


def _is_safe_query_text(value: str) -> bool:
    if _SENSITIVE_TEXT_RE.search(value) is not None:
        return False
    if _PRIVATE_PATH_RE.search(value) is not None:
        return False
    if _QUERY_UNSAFE_RE.search(value) is not None:
        return False
    return True


def _build_queries(values: Mapping[StartupProfileFieldName, tuple[str, ...]]) -> tuple[str, ...]:
    queries: list[str] = []
    solution = _first(values, StartupProfileFieldName.SOLUTION)
    icp = _first(values, StartupProfileFieldName.ICP)
    users = _first(values, StartupProfileFieldName.USERS)
    buyers = _first(values, StartupProfileFieldName.BUYERS)
    geography = _first(values, StartupProfileFieldName.GEOGRAPHY)
    business_model = _first(values, StartupProfileFieldName.BUSINESS_MODEL)
    pricing = _first(values, StartupProfileFieldName.PRICING_REVENUE_MODEL)
    competitors = values.get(StartupProfileFieldName.COMPETITORS_MENTIONED, ())

    if solution and icp and geography:
        queries.append(f"{solution} {icp} {geography} competitors")
    if business_model and pricing and icp and geography:
        queries.append(f"{business_model} {pricing} {icp} {geography} market size")
    if users and buyers and geography:
        queries.append(f"{users} {buyers} {geography} alternatives")
    queries.extend(f"{competitor} competitors" for competitor in competitors)

    bounded = (_normalize_query(query) for query in queries)
    return tuple(sorted(set(query for query in bounded if query)))[:_MAX_QUERY_COUNT]


def _build_live_research_plan(
    profile: StartupProfile,
    *,
    public_focus: str | None,
    public_topic: str | None,
) -> StartupResearchPlanBuildResult:
    allowed_fields = (
        StartupProfileFieldName.SOLUTION,
        StartupProfileFieldName.ICP,
        StartupProfileFieldName.GEOGRAPHY,
    )
    safe_values: dict[StartupProfileFieldName, tuple[str, ...]] = {}
    unsafe_fields: list[StartupProfileFieldName] = []
    for field_name in allowed_fields:
        field = profile.fields[field_name.value]
        safe = tuple(
            sorted(
                {
                    normalized
                    for value in field.values
                    if (normalized := _normalize_live_public_profile_text(field_name, value))
                },
                key=str.casefold,
            )
        )
        safe_values[field_name] = safe
        if field.values and not safe:
            unsafe_fields.append(field_name)

    topic = _normalize_live_public_text(public_topic or public_focus or "")
    solution = _first(safe_values, StartupProfileFieldName.SOLUTION)
    icp = _first(safe_values, StartupProfileFieldName.ICP)
    geography = _first(safe_values, StartupProfileFieldName.GEOGRAPHY)
    queries = (
        _normalize_query(" ".join(part for part in (solution, icp, geography, topic) if part)),
        _normalize_query(" ".join(part for part in (solution, geography, topic) if part)),
        _normalize_query(" ".join(part for part in (icp, geography, topic) if part)),
    )
    bounded_queries = tuple(
        dict.fromkeys(query for query in queries if query)
    )[:_MAX_LIVE_QUERY_COUNT]
    gaps = tuple(
        f"live_research.missing:{field_name.value}"
        for field_name in allowed_fields
        if not safe_values[field_name]
    )
    return StartupResearchPlanBuildResult(
        plan=StartupResearchPlan(
            case_id=profile.case_id,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=bounded_queries,
            max_queries=_MAX_LIVE_QUERY_COUNT,
        ),
        gap_codes=gaps,
        omitted_values=tuple(
            f"private_value:{field_name.value}" for field_name in unsafe_fields
        ),
    )


def _normalize_live_public_text(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized or len(normalized) > _MAX_QUERY_LENGTH:
        return ""
    if not _is_safe_query_text(normalized):
        return ""
    if _LIVE_PRIVATE_TEXT_RE.search(normalized) is not None:
        return ""
    if _LIVE_QUERY_PROFILE_NOISE_RE.search(normalized) is not None:
        return ""
    return normalized


def _normalize_live_public_profile_text(field_name: StartupProfileFieldName, value: str) -> str:
    normalized = _normalize_live_public_text(value)
    if not normalized:
        return ""
    if field_name is StartupProfileFieldName.GEOGRAPHY:
        normalized = _strip_deferred_vertical_from_geography(normalized)
    return normalized


def _strip_deferred_vertical_from_geography(value: str) -> str:
    segments = [segment.strip(" .;:-—") for segment in value.split(";")]
    if len(segments) < 2:
        return value
    deferred_vertical = re.compile(
        r"(?iu)\b(?:жиль[еёя]|аренд[ауы]?|недвижимост[ьи]|общежити[ея]|койко-?мест|housing|real\s+estate|rentals?)\b"
    )
    if any(deferred_vertical.search(segment) is not None for segment in segments[1:]):
        locations: list[str] = []
        for segment in segments[1:]:
            if deferred_vertical.search(segment) is None:
                continue
            location = deferred_vertical.sub("", segment)
            location = re.sub(r"\s+", " ", location).strip(" .;:-—")
            if location:
                locations.append(location)
        if locations:
            return ", ".join(dict.fromkeys((segments[0], *locations)))
        return segments[0]
    return value


def _first(values: Mapping[StartupProfileFieldName, tuple[str, ...]], field_name: StartupProfileFieldName) -> str | None:
    field_values = values.get(field_name, ())
    return field_values[0] if field_values else None


def _normalize_query(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized or not _is_safe_query_text(normalized):
        return ""
    return normalized[:_MAX_QUERY_LENGTH].rstrip()


def _source_estimate(
    level: str,
    value: Decimal,
    *,
    source_ids: tuple[UUID, ...],
    as_of: date,
    currency: str,
    unit: str,
    formula_version: str,
) -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=_stable_uuid(f"estimate:{level}:{value}:{as_of}:{formula_version}"),
        level=StartupResearchSourceStatus.SOURCE_FACT,
        value=_money(value),
        unit=unit,
        currency=currency,
        as_of=as_of,
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version=formula_version,
        source_refs=source_ids,
        confidence=Decimal("0.80"),
    )


def _inference_estimate(
    level: str,
    value: Decimal,
    *,
    assumption_refs: tuple[UUID, ...],
    source_ids: tuple[UUID, ...],
    as_of: date,
    currency: str,
    unit: str,
    formula_version: str,
) -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=_stable_uuid(f"estimate:{level}:{_money(value)}:{as_of}:{formula_version}:{assumption_refs}"),
        level=StartupResearchSourceStatus.INFERENCE,
        value=_money(value),
        unit=unit,
        currency=currency,
        as_of=as_of,
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version=formula_version,
        assumption_refs=assumption_refs,
        source_refs=source_ids,
        confidence=Decimal("0.65"),
    )


def _insufficient_estimate(
    level: str,
    *,
    as_of: date,
    currency: str,
    unit: str,
    formula_version: str,
) -> MarketSizingEstimate:
    return MarketSizingEstimate(
        estimate_id=_stable_uuid(f"estimate:{level}:insufficient:{as_of}:{formula_version}"),
        level=StartupResearchSourceStatus.INSUFFICIENT_DATA,
        value=None,
        unit=unit,
        currency=currency,
        as_of=as_of,
        source_mode=StartupResearchSourceMode.FROZEN,
        formula_version=formula_version,
        confidence=Decimal("0"),
    )


def _insufficient_sizing(inputs: StartupMarketSizingInputs, *, formula_version: str) -> StartupMarketSizing:
    return StartupMarketSizing(
        tam=_insufficient_estimate("tam", as_of=inputs.as_of, currency=inputs.currency, unit=inputs.unit, formula_version=formula_version),
        sam=_insufficient_estimate("sam", as_of=inputs.as_of, currency=inputs.currency, unit=inputs.unit, formula_version=formula_version),
        som=_insufficient_estimate("som", as_of=inputs.as_of, currency=inputs.currency, unit=inputs.unit, formula_version=formula_version),
    )


def _assumption(
    seed: str,
    text: str,
    *,
    source_ids: tuple[UUID, ...],
    as_of: date,
    lineage: tuple[UUID, ...] = (),
) -> MarketSizingAssumption:
    return MarketSizingAssumption(
        assumption_id=_stable_uuid(f"assumption:{seed}:{text}:{as_of}:{source_ids}:{lineage}"),
        text=text,
        status=StartupResearchSourceStatus.SOURCE_FACT,
        confidence=Decimal("0.65"),
        as_of=as_of,
        source_mode=StartupResearchSourceMode.FROZEN,
        source_ids=source_ids,
        lineage=lineage,
    )


def _positive_money(value: Decimal) -> Decimal:
    checked = _money(value)
    if checked <= Decimal("0"):
        raise ValueError("market size input must be positive")
    return checked


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_MONEY_QUANT)


def _share(value: Decimal) -> Decimal:
    checked = Decimal(value)
    if checked <= _SHARE_MIN or checked > _SHARE_MAX:
        raise ValueError("share must be between 0 and 1")
    return checked


def _decimal_string(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _stable_uuid(seed: str) -> UUID:
    return uuid5(NAMESPACE_URL, seed)

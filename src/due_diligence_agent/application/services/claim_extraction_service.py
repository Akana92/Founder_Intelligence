from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import re
from uuid import UUID, uuid4

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.evidence.startup_claims import (
    ClaimCategory,
    ClaimCriticality,
    ClaimExtractionItem,
    ClaimExtractionResult,
    StartupClaim,
)
from due_diligence_agent.ports.llm import LLMGatewayPort


_NUMERIC_CLAIM = re.compile(
    r"\b(?P<name>ARR|runway|gross margin|customer count)\b"
    r"[^\d\r\n]*(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>m|months?|мес\.?|месяц(?:а|ев)?|%|percent|customers|count|usd|kzt|₸)?",
    re.IGNORECASE,
)
_FINANCIAL_LINE_SPECS: tuple[tuple[re.Pattern[str], str, ClaimCategory, str], ...] = (
    (re.compile(r"\bmrr\b", re.IGNORECASE), "mrr", ClaimCategory.OTHER, "money"),
    (re.compile(r"\barr\b", re.IGNORECASE), "arr", ClaimCategory.ARR, "money"),
    (
        re.compile(r"\b(?:gross\s+margin|валовая\s+маржа)\b", re.IGNORECASE),
        "gross_margin",
        ClaimCategory.GROSS_MARGIN,
        "percent",
    ),
    (re.compile(r"\bcac\s+payback\b", re.IGNORECASE), "cac_payback", ClaimCategory.OTHER, "months"),
    (re.compile(r"\bnet\s+burn\b", re.IGNORECASE), "net_burn", ClaimCategory.OTHER, "money"),
    (re.compile(r"\brunway\b", re.IGNORECASE), "runway", ClaimCategory.RUNWAY, "months"),
    (
        re.compile(r"\bcustomer\s+count\b", re.IGNORECASE),
        "customer_count",
        ClaimCategory.CUSTOMER_COUNT,
        "count",
    ),
)
_FINANCIAL_CONTEXT_CHARS = 180
_LINE_NUMBER = re.compile(
    r"(?P<prefix>[$₸])?\s*"
    r"(?P<value>\d+(?:[.,]\d+)?)"
    r"(?P<suffix>\s*(?:млн|million|m)?\s*(?:₸|kzt|usd|\$|%|percent|months?|мес\.?|месяц(?:а|ев)?|customers|count)?)",
    re.IGNORECASE,
)
_BUSINESS_CLAIM_PATTERNS: tuple[tuple[re.Pattern[str], str, str | None], ...] = (
    (
        re.compile(
            r"(?:\bprocurement\s+cycles?\s+(?:cut|reduced|reduction)\b[^\d]{0,80}"
            r"(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\b|"
            r"(?P<value_prefix>\d+(?:\.\d+)?)\s*(?:%|percent)\s+"
            r"procurement\s+cycles?\s+(?:cut|reduced|reduction)\b)",
            re.IGNORECASE,
        ),
        "procurement_cycle_reduction",
        "percent",
    ),
    (
        re.compile(r"\bregulation[-\s]+driven\s+demand\b", re.IGNORECASE),
        "regulation_driven_demand",
        None,
    ),
    (
        re.compile(
            r"(?:\bchurn\s+reduction\b[^\d]{0,80}"
            r"(?P<value>\d+(?:\.\d+)?)\s*(?:%|percent)\b|"
            r"(?P<value_prefix>\d+(?:\.\d+)?)\s*(?:%|percent)\s+"
            r"churn\s+reduction\b)",
            re.IGNORECASE,
        ),
        "churn_reduction",
        "percent",
    ),
    (
        re.compile(r"\bconversion\s+benchmark\s+superiority\b", re.IGNORECASE),
        "conversion_benchmark_superiority",
        None,
    ),
)


class ClaimExtractionService:
    def __init__(self, *, llm_gateway: LLMGatewayPort | None = None) -> None:
        self._llm_gateway = llm_gateway

    def extract_fixture_claims(
        self,
        *,
        case_id: UUID,
        artifact_id: UUID,
        text: str,
        locator: SourceLocator,
        sensitivity: SensitivityClass,
        period: str | None = None,
    ) -> tuple[StartupClaim, ...]:
        claims: list[StartupClaim] = []
        handled_lines: set[int] = set()
        for line_number, line in enumerate(text.splitlines()):
            has_financial_marker = _financial_line_has_metric(line)
            extracted = _financial_line_claims(
                line,
                case_id=case_id,
                artifact_id=artifact_id,
                locator=locator,
                sensitivity=sensitivity,
                period=period or "unknown",
            )
            if extracted:
                claims.extend(extracted)
            if has_financial_marker:
                handled_lines.add(line_number)
        fallback_text = "\n".join(
            line for line_number, line in enumerate(text.splitlines()) if line_number not in handled_lines
        )
        for match in _NUMERIC_CLAIM.finditer(fallback_text):
            category = _category(match.group("name"))
            if category is ClaimCategory.RUNWAY and _is_forward_looking_metric_context(
                fallback_text,
                start=match.start(),
                end=match.end(),
            ):
                continue
            unit = _unit(match.group("unit"), category)
            value = _value(match.group("value"), match.group("unit"), unit)
            claims.append(
                StartupClaim(
                    id=uuid4(),
                    case_id=case_id,
                    text_ref=_text_ref(match.group(0)),
                    text_hash=_text_ref(match.group(0)),
                    category=category,
                    source_artifact_id=artifact_id,
                    locator=locator.model_copy(update={"artifact_id": artifact_id}),
                    criticality=ClaimCriticality.CRITICAL,
                    evidence_query=f"{category.value} {period or ''}".strip(),
                    normalized_name=category.value,
                    normalized_value=value,
                    unit=unit,
                    period=period or "unknown",
                    sensitivity=sensitivity,
                    confidence=Decimal("0.70"),
                    extracted_at=datetime.now(UTC),
                )
            )
        seen_business_claims: set[str] = set()
        for business_pattern, business_name, business_unit in _BUSINESS_CLAIM_PATTERNS:
            for match in business_pattern.finditer(text):
                business_value = _optional_value(match)
                claim_period = (period or "unknown") if business_value is not None else None
                claim_material = _business_claim_material(business_name, business_value, business_unit)
                if claim_material in seen_business_claims:
                    continue
                seen_business_claims.add(claim_material)
                claims.append(
                    StartupClaim(
                        id=uuid4(),
                        case_id=case_id,
                        text_ref=_text_ref(claim_material),
                        text_hash=_text_ref(claim_material),
                        category=ClaimCategory.OTHER,
                        source_artifact_id=artifact_id,
                        locator=locator.model_copy(update={"artifact_id": artifact_id}),
                        criticality=ClaimCriticality.CRITICAL,
                        evidence_query=f"other {claim_period}".strip() if claim_period else "other",
                        normalized_name=business_name,
                        normalized_value=business_value,
                        unit=business_unit,
                        period=claim_period,
                        sensitivity=sensitivity,
                        confidence=Decimal("0.65"),
                        extracted_at=datetime.now(UTC),
                    )
                )
        return tuple(claims)

    async def extract_with_external_model(self, *, gate2_approved: bool) -> ClaimExtractionResult:
        if not gate2_approved:
            raise PermissionError("gate2_required_for_external_claim_extraction")
        if self._llm_gateway is None:
            raise RuntimeError("llm_gateway_not_configured")
        raise NotImplementedError("external extraction is wired through the gateway in Task 9")

    def to_claims(
        self,
        *,
        case_id: UUID,
        items: tuple[ClaimExtractionItem, ...],
        extracted_at: datetime | None = None,
    ) -> tuple[StartupClaim, ...]:
        timestamp = extracted_at or datetime.now(UTC)
        return tuple(
            StartupClaim(
                id=uuid4(),
                case_id=case_id,
                text_ref=_text_ref(item.text),
                text_hash=_text_ref(item.text),
                category=item.category,
                source_artifact_id=item.source_artifact_id,
                locator=item.locator,
                criticality=item.criticality,
                evidence_query=f"{item.category.value} {item.period or ''}".strip(),
                normalized_name=item.normalized_name,
                normalized_value=item.normalized_value,
                unit=item.unit,
                period=item.period,
                sensitivity=item.sensitivity,
                confidence=item.confidence,
                extracted_at=timestamp,
            )
            for item in items
        )


def _category(raw: str) -> ClaimCategory:
    normalized = raw.strip().casefold().replace(" ", "_")
    return {
        "arr": ClaimCategory.ARR,
        "gross_margin": ClaimCategory.GROSS_MARGIN,
        "runway": ClaimCategory.RUNWAY,
        "customer_count": ClaimCategory.CUSTOMER_COUNT,
    }.get(normalized, ClaimCategory.OTHER)


def _financial_line_has_metric(line: str) -> bool:
    return any(pattern.search(line) is not None for pattern, _, _, _ in _FINANCIAL_LINE_SPECS)


def _financial_line_claims(
    line: str,
    *,
    case_id: UUID,
    artifact_id: UUID,
    locator: SourceLocator,
    sensitivity: SensitivityClass,
    period: str,
) -> tuple[StartupClaim, ...]:
    text = line.strip()
    if not text:
        return ()
    if _non_current_financial_line(text):
        return ()
    claims: list[StartupClaim] = []
    for pattern, raw_name, category, unit_kind in _FINANCIAL_LINE_SPECS:
        name_match = pattern.search(text)
        if name_match is None:
            continue
        normalized_name = _normalized_financial_name(raw_name)
        if normalized_name == "runway" and _is_forward_looking_metric_context(
            text,
            start=name_match.start(),
            end=name_match.end(),
        ):
            continue
        metric_text = _metric_value_segment(text, start=name_match.end(), current_pattern=pattern)
        for value, unit in _line_values(metric_text, unit_kind, normalized_name=normalized_name):
            claim_material = f"financial-claim:{normalized_name}:{value}:{unit}:{period}:{text}"
            claims.append(
                StartupClaim(
                    id=uuid4(),
                    case_id=case_id,
                    text_ref=_text_ref(claim_material),
                    text_hash=_text_ref(claim_material),
                    category=category,
                    source_artifact_id=artifact_id,
                    locator=locator.model_copy(update={"artifact_id": artifact_id}),
                    criticality=ClaimCriticality.CRITICAL,
                    evidence_query=f"{category.value} {period}".strip(),
                    normalized_name=normalized_name,
                    normalized_value=value,
                    unit=unit,
                    period=period,
                    sensitivity=sensitivity,
                    confidence=Decimal("0.70"),
                    extracted_at=datetime.now(UTC),
                )
            )
    return tuple(claims)


def _non_current_financial_line(text: str) -> bool:
    normalized = text.casefold()
    return any(
        marker in normalized
        for marker in (
            "целевой",
            "target",
            "requires plan",
            "требует выполнения",
        )
    )


def _metric_value_segment(text: str, *, start: int, current_pattern: re.Pattern[str]) -> str:
    end = len(text)
    for pattern, _, _, _ in _FINANCIAL_LINE_SPECS:
        if pattern is current_pattern:
            continue
        match = pattern.search(text, start)
        if match is not None:
            end = min(end, match.start())
    return text[start:end]


def _normalized_financial_name(raw_name: str) -> str:
    return {
        "mrr": "monthly_recurring_revenue",
        "net_burn": "monthly_net_burn",
    }.get(raw_name, raw_name)


def _line_values(
    line: str,
    unit_kind: str,
    *,
    normalized_name: str,
) -> tuple[tuple[Decimal, str], ...]:
    values: list[tuple[Decimal, str]] = []
    for match in _LINE_NUMBER.finditer(line):
        prefix = match.group("prefix") or ""
        suffix = match.group("suffix") or ""
        if unit_kind == "percent" and not _has_percent_suffix(suffix):
            continue
        if unit_kind == "months" and not _has_month_suffix(suffix):
            continue
        if unit_kind == "money" and not _has_money_suffix(prefix + suffix):
            continue
        if unit_kind == "count" and not _has_count_suffix(suffix):
            continue
        value = _decimal_value(match.group("value"))
        unit = _line_unit(prefix + suffix, unit_kind, normalized_name=normalized_name)
        if unit_kind == "money" and _has_million_suffix(suffix):
            value *= Decimal("1000000")
        values.append((value, unit))
    return tuple(values)


def _line_unit(suffix: str, unit_kind: str, *, normalized_name: str) -> str:
    normalized = suffix.casefold()
    if unit_kind == "percent" or "%" in suffix or "percent" in normalized:
        return "percent"
    if unit_kind == "months":
        return "months"
    if unit_kind == "count":
        return "count"
    if "₸" in suffix or "kzt" in normalized:
        return "KZT/month" if normalized_name == "monthly_net_burn" else "KZT"
    return "USD/month" if normalized_name == "monthly_net_burn" else "USD"


def _decimal_value(raw: str) -> Decimal:
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
        return Decimal(raw.replace(",", ""))
    return Decimal(raw.replace(",", "."))


def _is_forward_looking_metric_context(text: str, *, start: int, end: int) -> bool:
    context = text[max(0, start - _FINANCIAL_CONTEXT_CHARS): min(len(text), end + _FINANCIAL_CONTEXT_CHARS)]
    normalized = context.casefold()
    if any(
        marker in normalized
        for marker in (
            "current",
            "mechanical",
            "cash balance",
            "monthly net burn",
            "net burn",
            "текущ",
            "механичес",
        )
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "target",
            "forecast",
            "projected",
            "projection",
            "future",
            "after seed",
            "post-seed",
            "post seed",
            "цель",
            "целевой",
            "прогноз",
            "план",
            "после привлеч",
            "после раунд",
            "через",
        )
    )


def _has_percent_suffix(suffix: str) -> bool:
    return "%" in suffix or "percent" in suffix.casefold()


def _has_million_suffix(suffix: str) -> bool:
    normalized = suffix.casefold()
    return "млн" in normalized or "million" in normalized or re.search(r"\bm\b", normalized) is not None


def _has_money_suffix(suffix: str) -> bool:
    normalized = suffix.casefold()
    return (
        "₸" in suffix
        or "$" in suffix
        or "kzt" in normalized
        or "usd" in normalized
        or "млн" in normalized
        or "million" in normalized
        or re.search(r"\bm\b", normalized) is not None
    )


def _has_month_suffix(suffix: str) -> bool:
    normalized = suffix.casefold()
    return (
        "months" in normalized
        or "month" in normalized
        or "мес" in normalized
        or "месяц" in normalized
        or re.search(r"(?:^|\s)m(?:\s|$)", normalized) is not None
    )


def _has_count_suffix(suffix: str) -> bool:
    normalized = suffix.casefold()
    return "customers" in normalized or "count" in normalized


def _unit(raw: str | None, category: ClaimCategory) -> str:
    if category is ClaimCategory.GROSS_MARGIN:
        return "percent"
    if category is ClaimCategory.RUNWAY:
        return "months"
    if category is ClaimCategory.CUSTOMER_COUNT:
        return "count"
    if raw and raw.strip().casefold() == "m":
        return "USD"
    return raw or "count"


def _value(raw: str, raw_unit: str | None, normalized_unit: str) -> Decimal:
    value = _decimal_value(raw)
    if raw_unit and raw_unit.strip().casefold() == "m" and normalized_unit == "USD":
        return value * Decimal("1000000")
    return value


def _text_ref(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _optional_value(match: re.Match[str]) -> Decimal | None:
    for name in ("value", "value_prefix"):
        try:
            raw = match.group(name)
        except IndexError:
            continue
        if raw is not None:
            return Decimal(raw)
    return None


def _business_claim_material(normalized_name: str, value: Decimal | None, unit: str | None) -> str:
    return f"business-claim:{normalized_name}:{value or ''}:{unit or ''}"

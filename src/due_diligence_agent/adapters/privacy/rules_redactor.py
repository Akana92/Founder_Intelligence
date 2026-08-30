from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING
from typing import Final

from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.privacy.models import (
    PrivacyDetection,
    PrivacyScanResult,
    counts_for_detections,
    most_restrictive,
    redact_with_detections,
)

if TYPE_CHECKING:
    from due_diligence_agent.adapters.privacy.presidio_redactor import PresidioRedactor


POLICY_VERSION: Final[str] = "startup-redact-rules@1"


@dataclass(frozen=True)
class _Rule:
    category: str
    sensitivity: SensitivityClass
    pattern: re.Pattern[str]


_RULES: Final[tuple[_Rule, ...]] = (
    _Rule(
        "email",
        SensitivityClass.RESTRICTED,
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    ),
    _Rule(
        "secret",
        SensitivityClass.RESTRICTED,
        re.compile(
            r"(?i)\b(?:bearer\s+[A-Za-z0-9._=-]+|sk-proj-[A-Za-z0-9_-]+|"
            r"api[_ -]?key\s*[:=]\s*[A-Za-z0-9._=-]+|secret\s*[:=]\s*[A-Za-z0-9._=-]+|"
            r"password\s*[:=]\s*\S+)\b"
        ),
    ),
    _Rule(
        "banking",
        SensitivityClass.RESTRICTED,
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    ),
    _Rule(
        "phone",
        SensitivityClass.RESTRICTED,
        re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"),
    ),
    _Rule(
        "stable_id",
        SensitivityClass.CONFIDENTIAL,
        re.compile(r"(?i)\b(?:customer|user|account|tax|ssn|iin)[_-]?id\s*[:=]?\s*[A-Z0-9-]{4,}\b"),
    ),
)

_RESTRICTED_FIELD_MARKERS: Final[tuple[str, ...]] = (
    "email",
    "phone",
    "iban",
    "bank",
    "account_number",
    "authorization",
    "auth",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "ssn",
    "iin",
)
_CONFIDENTIAL_FIELD_MARKERS: Final[tuple[str, ...]] = (
    "customer_id",
    "user_id",
    "account_id",
    "tax_id",
    "cap_table",
)
_FINANCIAL_CONTEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?iu)(?:"
    r"\b(?:arr|mrr|arpa|cac|ebitda|kzt|usd|eur|mln|million|thousand|percent|margin|range|revenue)\b"
    r"|[₸$€%]"
    r"|млн|тыс|выруч|марж|диапазон|продаж"
    r")"
)
_PHONE_LABEL_CONTEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?iu)(?:\b(?:phone|tel|mobile|cell|contact)\b|телефон|тел\.)\s*[:#-]?\s*$"
)


class RulesRedactor:
    policy_version = POLICY_VERSION

    def __init__(self, *, presidio_redactor: PresidioRedactor | None = None) -> None:
        self._presidio_redactor = presidio_redactor

    def detect(
        self,
        text: str,
        *,
        field_name: str | None = None,
        base_sensitivity: SensitivityClass = SensitivityClass.PUBLIC,
    ) -> PrivacyScanResult:
        detections = self._detect_patterns(text, field_name=field_name)
        if field_name is not None:
            field_detection = self._detect_field_name(field_name, len(text))
            if field_detection is not None:
                detections.append(field_detection)
        detections = self._deduplicate(detections)
        sensitivity = most_restrictive([base_sensitivity, *(item.sensitivity for item in detections)])
        result = PrivacyScanResult(
            detections=tuple(detections),
            category_counts=counts_for_detections(detections),
            redacted_text=redact_with_detections(text, detections),
            sensitivity=sensitivity,
            policy_version=self.policy_version,
        )
        if self._presidio_redactor is None:
            return result
        enriched = self._presidio_redactor.detect(text, existing=result)
        merged = self._deduplicate(list(enriched.detections))
        merged_sensitivity = most_restrictive(
            [base_sensitivity, enriched.sensitivity, *(item.sensitivity for item in merged)]
        )
        return PrivacyScanResult(
            detections=tuple(merged),
            category_counts=counts_for_detections(merged),
            redacted_text=redact_with_detections(text, merged),
            sensitivity=merged_sensitivity,
            available=enriched.available,
            reason=enriched.reason,
            policy_version=self.policy_version,
        )

    def redact(self, text: str, detections: list[PrivacyDetection]) -> str:
        return redact_with_detections(text, detections)

    def _detect_patterns(self, text: str, *, field_name: str | None) -> list[PrivacyDetection]:
        detections: list[PrivacyDetection] = []
        for rule in _RULES:
            for match in rule.pattern.finditer(text):
                if rule.category == "phone" and not _is_phone_like(text, match):
                    continue
                detections.append(
                    PrivacyDetection(
                        category=rule.category,
                        sensitivity=rule.sensitivity,
                        start=match.start(),
                        end=match.end(),
                        field_name=_safe_field_name(field_name),
                        source="rules",
                    )
                )
        return detections

    @staticmethod
    def _detect_field_name(field_name: str, text_length: int) -> PrivacyDetection | None:
        normalized = field_name.strip().casefold().replace("-", "_").replace(" ", "_")
        if any(marker in normalized for marker in _RESTRICTED_FIELD_MARKERS):
            return PrivacyDetection(
                category=_field_category(normalized),
                sensitivity=SensitivityClass.RESTRICTED,
                start=0,
                end=max(text_length, 0),
                field_name=_safe_field_name(field_name),
                source="field_name",
            )
        if any(marker in normalized for marker in _CONFIDENTIAL_FIELD_MARKERS):
            return PrivacyDetection(
                category="stable_id",
                sensitivity=SensitivityClass.CONFIDENTIAL,
                start=0,
                end=max(text_length, 0),
                field_name=_safe_field_name(field_name),
                source="field_name",
            )
        return None

    @staticmethod
    def _deduplicate(detections: list[PrivacyDetection]) -> list[PrivacyDetection]:
        selected: list[PrivacyDetection] = []
        for detection in sorted(detections, key=lambda item: (item.start, -(item.end - item.start))):
            if any(_overlaps(detection, existing) for existing in selected):
                continue
            selected.append(detection)
        return selected


def _field_category(normalized_field_name: str) -> str:
    if "email" in normalized_field_name:
        return "email"
    if "phone" in normalized_field_name:
        return "phone"
    if "bank" in normalized_field_name or "iban" in normalized_field_name or "account" in normalized_field_name:
        return "banking"
    if any(marker in normalized_field_name for marker in ("auth", "token", "secret", "password", "api")):
        return "secret"
    return "stable_id"


def _safe_field_name(field_name: str | None) -> str | None:
    if field_name is None:
        return None
    normalized = field_name.strip().casefold().replace("-", "_").replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "_", normalized)[:64] or None


def _is_phone_like(text: str, match: re.Match[str]) -> bool:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        return False
    if raw.lstrip().startswith("+") or "(" in raw or ")" in raw:
        return True
    context_before = text[max(0, match.start() - 32) : match.start()]
    if _PHONE_LABEL_CONTEXT_RE.search(context_before):
        return True
    context = text[max(0, match.start() - 48) : min(len(text), match.end() + 48)]
    if _FINANCIAL_CONTEXT_RE.search(context):
        return False
    groups = re.findall(r"\d+", raw)
    return len(groups) >= 3 and len(groups[-1]) >= 2 and sum(len(group) >= 3 for group in groups) >= 2


def _overlaps(left: PrivacyDetection, right: PrivacyDetection) -> bool:
    return left.start < right.end and right.start < left.end

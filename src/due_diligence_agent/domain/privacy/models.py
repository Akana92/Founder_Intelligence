from __future__ import annotations

from uuid import UUID
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from due_diligence_agent.domain.common import SensitivityClass


_SENSITIVITY_RANK: dict[SensitivityClass, int] = {
    SensitivityClass.PUBLIC: 0,
    SensitivityClass.INTERNAL: 1,
    SensitivityClass.CONFIDENTIAL: 2,
    SensitivityClass.RESTRICTED: 3,
}
_SAFE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class PrivacyDetection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    sensitivity: SensitivityClass
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    field_name: str | None = None
    source: str

    @field_validator("category", "field_name", "source")
    @classmethod
    def validate_safe_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(char.isspace() for char in value) or any(char in value for char in "@:/\\"):
            raise ValueError("privacy label must be trace-safe")
        return value

    @field_validator("end")
    @classmethod
    def validate_span(cls, value: int, info: ValidationInfo) -> int:
        start = info.data.get("start")
        if isinstance(start, int) and value < start:
            raise ValueError("invalid detection span")
        return value


class PrivacyScanResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    detections: tuple[PrivacyDetection, ...] = ()
    category_counts: dict[str, int] = Field(default_factory=dict)
    redacted_text: str = Field(default="", repr=False)
    sensitivity: SensitivityClass = SensitivityClass.PUBLIC
    available: bool = True
    reason: str | None = None
    policy_version: str

    @field_validator("category_counts")
    @classmethod
    def validate_safe_dict_keys(cls, value: dict[str, object]) -> dict[str, object]:
        _validate_safe_dict_keys(value)
        return value

    @field_validator("redacted_text")
    @classmethod
    def reject_unredacted_sensitive_text(cls, value: str) -> str:
        lowered = value.casefold()
        forbidden_markers = ("bearer ", "sk-proj-", "api_key", "api-key")
        if "@" in value or any(marker in lowered for marker in forbidden_markers):
            raise ValueError("redacted_text contains sensitive marker")
        return value


class SensitivitySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_class: SensitivityClass
    field_classes: dict[str, SensitivityClass]
    category_counts: dict[str, int]
    policy_version: str

    @field_validator("field_classes", "category_counts")
    @classmethod
    def validate_safe_dict_keys(cls, value: dict[str, object]) -> dict[str, object]:
        _validate_safe_dict_keys(value)
        return value


class DisclosurePreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_class: SensitivityClass
    category_counts: dict[str, int]
    field_classes: dict[str, SensitivityClass] = Field(default_factory=dict)
    fragment_previews: tuple[str, ...] = Field(default_factory=tuple, repr=False)
    quasi_identifier_count: int = Field(default=0, ge=0)
    quasi_identifier_counts: dict[str, int] = Field(default_factory=dict)
    policy_version: str

    @field_validator("field_classes", "category_counts", "quasi_identifier_counts")
    @classmethod
    def validate_safe_dict_keys(cls, value: dict[str, object]) -> dict[str, object]:
        _validate_safe_dict_keys(value)
        return value

    @field_validator("fragment_previews")
    @classmethod
    def reject_raw_sensitive_preview(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        joined = " ".join(value).casefold()
        if "@" in joined or "bearer " in joined or "sk-proj-" in joined:
            raise ValueError("preview contains raw sensitive value")
        return value


class RedactedContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fragment_ids: list[UUID]
    local_text_refs: list[str]
    sensitivity: SensitivityClass
    redaction_counts: dict[str, int]
    content_hash: str

    @field_validator("local_text_refs")
    @classmethod
    def validate_text_refs(cls, value: list[str]) -> list[str]:
        for ref in value:
            _validate_sha256(ref)
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        return _validate_sha256(value)


def most_restrictive(classes: list[SensitivityClass] | tuple[SensitivityClass, ...]) -> SensitivityClass:
    if not classes:
        return SensitivityClass.PUBLIC
    return max(classes, key=lambda item: _SENSITIVITY_RANK[item])


def merge_category_counts(results: list[PrivacyScanResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        if result.category_counts:
            for category, count in result.category_counts.items():
                counts[category] = counts.get(category, 0) + count
            continue
        for detection in result.detections:
            counts[detection.category] = counts.get(detection.category, 0) + 1
    return counts


def counts_for_detections(detections: tuple[PrivacyDetection, ...] | list[PrivacyDetection]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for detection in _merge_overlapping_detections(detections):
        counts[detection.category] = counts.get(detection.category, 0) + 1
    return counts


def redact_with_detections(text: str, detections: tuple[PrivacyDetection, ...] | list[PrivacyDetection]) -> str:
    if not detections:
        return text
    result: list[str] = []
    cursor = 0
    category_counts: dict[str, int] = {}
    for detection in _merge_overlapping_detections(detections):
        if detection.start < cursor:
            continue
        result.append(text[cursor : detection.start])
        category_counts[detection.category] = category_counts.get(detection.category, 0) + 1
        result.append(f"[REDACTED:{detection.category}:{category_counts[detection.category]}]")
        cursor = detection.end
    result.append(text[cursor:])
    return "".join(result)


def safe_field_id(raw_label: str) -> str:
    from hashlib import sha256

    return f"field_{sha256(raw_label.encode('utf-8')).hexdigest()[:16]}"


def _merge_overlapping_detections(
    detections: tuple[PrivacyDetection, ...] | list[PrivacyDetection],
) -> tuple[PrivacyDetection, ...]:
    merged: list[PrivacyDetection] = []
    for detection in sorted(detections, key=lambda item: (item.start, item.end, item.category)):
        if not merged:
            merged.append(detection)
            continue
        prior = merged[-1]
        if detection.start <= prior.end:
            merged[-1] = prior.model_copy(
                update={
                    "end": max(prior.end, detection.end),
                    "sensitivity": most_restrictive([prior.sensitivity, detection.sensitivity]),
                }
            )
            continue
        merged.append(detection)
    return tuple(merged)


def _validate_safe_dict_keys(value: dict[str, object]) -> None:
    for key in value:
        if not _SAFE_KEY_RE.fullmatch(key):
            raise ValueError("privacy dict key is not trace-safe")


def _validate_sha256(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("invalid content reference")
    return value

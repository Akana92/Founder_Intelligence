from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
import re
from typing import Protocol, Literal, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.startup.profile import (
    StartupProfileFieldName as StartupProfileFieldName,
    StartupProfileFieldStatus as StartupProfileFieldStatus,
)

MAX_FRAGMENTS = 24
MAX_FRAGMENT_CHARS = 800
MAX_TOTAL_FRAGMENT_CHARS = 12_000
MAX_SPREADSHEET_FACTS = 64
MAX_OUTPUT_FIELDS = 18
MAX_VALUES_PER_FIELD = 8
MAX_VALUE_CHARS = 240
MAX_REASON_CODE_CHARS = 80
MAX_GAP_CODES = 32

__all__ = [
    "MAX_FRAGMENT_CHARS",
    "MAX_FRAGMENTS",
    "MAX_GAP_CODES",
    "MAX_OUTPUT_FIELDS",
    "MAX_REASON_CODE_CHARS",
    "MAX_SPREADSHEET_FACTS",
    "MAX_TOTAL_FRAGMENT_CHARS",
    "MAX_VALUES_PER_FIELD",
    "MAX_VALUE_CHARS",
    "StartupProfileBoundedFragment",
    "StartupProfileExtractedField",
    "StartupProfileExtractionPort",
    "StartupProfileExtractionRequest",
    "StartupProfileExtractionResponse",
    "StartupProfileExtractorInvalidOutputError",
    "StartupProfileFragmentInventoryPort",
    "StartupProfileFieldName",
    "StartupProfileFieldStatus",
    "StartupProfileSafeRef",
    "StartupProfileSpreadsheetFact",
    "max_sensitivity",
]


class StartupProfileExtractorInvalidOutputError(ValueError):
    stable_error_code = "STARTUP_PROFILE_EXTRACTOR_INVALID_OUTPUT"


class StartupProfileSafeRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    ref_type: Literal["fragment", "evidence_fact", "claim", "contradiction"]
    ref_id: UUID
    artifact_id: UUID | None = None
    artifact_hash: str | None = None
    locator_hash: str | None = None
    page: int | None = None
    table: str | None = None
    cell: str | None = None
    confidence: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("1"))

    @field_validator("artifact_hash", "locator_hash")
    @classmethod
    def validate_optional_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_hash_ref(value)

    @field_validator("table", "cell")
    @classmethod
    def validate_safe_coordinate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value, max_chars=64)
        if _contains_private_material(normalized):
            raise ValueError("unsafe coordinate")
        return normalized


class StartupProfileBoundedFragment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    fragment_id: UUID
    artifact_id: UUID
    text: str
    text_hash: str
    artifact_hash: str
    locator_hash: str
    page: int | None = None
    table: str | None = None
    cell: str | None = None
    sensitivity: SensitivityClass
    redacted: Literal[True]
    minimized: Literal[True]
    redaction_policy_version: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        normalized = _normalize_fragment_text(value, max_chars=MAX_FRAGMENT_CHARS)
        if len(value) > MAX_FRAGMENT_CHARS:
            raise ValueError("fragment text too long")
        if not normalized:
            raise ValueError("fragment text is required")
        if _contains_private_material(normalized):
            raise ValueError("unsafe fragment text")
        return normalized

    @field_validator("text_hash", "artifact_hash", "locator_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _validate_hash_ref(value)

    @field_validator("table", "cell")
    @classmethod
    def validate_safe_coordinate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value, max_chars=64)
        if _contains_private_material(normalized):
            raise ValueError("unsafe coordinate")
        return normalized

    @field_validator("redaction_policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        normalized = _normalize_text(value, max_chars=80)
        if not normalized:
            raise ValueError("redaction policy version is required")
        return normalized


class StartupProfileSpreadsheetFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    evidence_fact_id: UUID
    artifact_id: UUID
    name: str
    value_type: Literal["decimal", "integer", "text", "date", "boolean"]
    normalized_value: str
    unit: str | None = None
    period: str | None = None
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    sensitivity: SensitivityClass
    artifact_hash: str
    locator_hash: str
    table: str | None = None
    cell: str | None = None

    @field_validator("name", "normalized_value", "unit", "period", "table", "cell")
    @classmethod
    def validate_safe_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_bounded_text(value, max_chars=MAX_VALUE_CHARS, field_name="spreadsheet fact value")
        if _contains_private_material(normalized):
            raise ValueError("unsafe spreadsheet fact value")
        return normalized

    @field_validator("artifact_hash", "locator_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _validate_hash_ref(value)

    @model_validator(mode="after")
    def validate_numeric_context(self) -> StartupProfileSpreadsheetFact:
        if self.value_type in {"decimal", "integer"} and (not self.unit or not self.period):
            raise ValueError("numeric spreadsheet facts require unit and period")
        return self


class StartupProfileExtractionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal["startup_profile_extraction_request@1"] = (
        "startup_profile_extraction_request@1"
    )
    case_id: UUID
    data_revision: int = Field(ge=1)
    primary_profile_id: UUID | None = None
    allowed_field_names: tuple[StartupProfileFieldName, ...]
    fragments: tuple[StartupProfileBoundedFragment, ...]
    spreadsheet_facts: tuple[StartupProfileSpreadsheetFact, ...] = ()
    allowed_refs: tuple[StartupProfileSafeRef, ...] = ()
    source_hashes: tuple[str, ...]
    egress_policy_version: str
    redaction_policy_version: str

    @field_validator("allowed_field_names")
    @classmethod
    def validate_allowed_fields(
        cls,
        value: tuple[StartupProfileFieldName, ...],
    ) -> tuple[StartupProfileFieldName, ...]:
        if not value:
            raise ValueError("allowed field names are required")
        if len(set(value)) != len(value):
            raise ValueError("duplicate allowed field names")
        return value

    @field_validator("source_hashes")
    @classmethod
    def validate_source_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("source hashes are required")
        return tuple(sorted(_validate_hash_ref(item) for item in value))

    @field_validator("egress_policy_version", "redaction_policy_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        normalized = _normalize_text(value, max_chars=80)
        if not normalized:
            raise ValueError("policy version is required")
        return normalized

    @model_validator(mode="after")
    def validate_limits(self) -> StartupProfileExtractionRequest:
        if len(self.fragments) > MAX_FRAGMENTS:
            raise ValueError("too many fragments")
        if len(self.spreadsheet_facts) > MAX_SPREADSHEET_FACTS:
            raise ValueError("too many spreadsheet facts")
        if sum(len(fragment.text) for fragment in self.fragments) > MAX_TOTAL_FRAGMENT_CHARS:
            raise ValueError("total fragment text too long")
        if any(fragment.redaction_policy_version != self.redaction_policy_version for fragment in self.fragments):
            raise ValueError("fragment redaction policy mismatch")
        return self

    def known_ref_keys(self) -> frozenset[tuple[str, UUID, str | None, str | None]]:
        return frozenset(
            [
                *(
                    (
                        "fragment",
                        fragment.fragment_id,
                        fragment.artifact_hash,
                        fragment.locator_hash,
                    )
                    for fragment in self.fragments
                ),
                *(
                    (
                        "evidence_fact",
                        fact.evidence_fact_id,
                        fact.artifact_hash,
                        fact.locator_hash,
                    )
                    for fact in self.spreadsheet_facts
                ),
                *(_ref_key(ref) for ref in self.allowed_refs),
            ]
        )


class StartupProfileExtractedField(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    field_name: StartupProfileFieldName
    normalized_values: tuple[str, ...] = ()
    status: StartupProfileFieldStatus
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    refs: tuple[StartupProfileSafeRef, ...] = ()
    reason_code: str | None = None

    @field_validator("normalized_values")
    @classmethod
    def validate_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) > MAX_VALUES_PER_FIELD:
            raise ValueError("too many values for field")
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = _normalize_bounded_text(value, max_chars=MAX_VALUE_CHARS, field_name="extracted value")
            if not normalized:
                continue
            if _contains_private_material(normalized):
                raise ValueError("unsafe extracted value")
            key = normalized.casefold()
            if key not in seen:
                cleaned.append(normalized)
                seen.add(key)
        return tuple(cleaned)

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_bounded_text(
            value,
            max_chars=MAX_REASON_CODE_CHARS,
            field_name="reason code",
        )
        if not normalized:
            return None
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in normalized):
            raise ValueError("unsafe reason code")
        return normalized

    @model_validator(mode="after")
    def validate_status(self) -> StartupProfileExtractedField:
        if self.status is StartupProfileFieldStatus.SOURCE_FACT and not self.refs:
            raise ValueError("source_fact requires refs")
        if self.status is StartupProfileFieldStatus.INFERENCE and (
            not self.refs or not self.reason_code or not self.normalized_values
        ):
            raise ValueError("inference requires refs, values, and reason_code")
        if self.status is StartupProfileFieldStatus.INSUFFICIENT_DATA and self.normalized_values:
            raise ValueError("insufficient_data cannot carry values")
        if self.status is StartupProfileFieldStatus.CONTRADICTION and (
            len(self.refs) < 2 and not self.reason_code
        ):
            raise ValueError("contradiction requires competing refs")
        return self


class StartupProfileExtractionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal["startup_profile_extraction_response@1"] = (
        "startup_profile_extraction_response@1"
    )
    fields: tuple[StartupProfileExtractedField, ...]
    gap_codes: tuple[str, ...] = ()

    @field_validator("fields")
    @classmethod
    def validate_fields(
        cls,
        value: tuple[StartupProfileExtractedField, ...],
    ) -> tuple[StartupProfileExtractedField, ...]:
        if len(value) > MAX_OUTPUT_FIELDS:
            raise ValueError("too many output fields")
        return value

    @field_validator("gap_codes")
    @classmethod
    def validate_gap_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) > MAX_GAP_CODES:
            raise ValueError("too many gap codes")
        return tuple(_safe_code(value, field_name="gap code") for value in values)

    def validate_against_request(
        self,
        request: StartupProfileExtractionRequest,
    ) -> StartupProfileExtractionResponse:
        allowed_fields = set(request.allowed_field_names)
        unknown_fields = sorted(field.field_name.value for field in self.fields if field.field_name not in allowed_fields)
        if unknown_fields:
            raise ValueError(f"unknown extraction fields: {', '.join(unknown_fields)}")
        known_refs = request.known_ref_keys()
        unknown_refs = sorted(
            f"{ref.ref_type}:{ref.ref_id}"
            for field in self.fields
            for ref in field.refs
            if _ref_key(ref) not in known_refs
        )
        if unknown_refs:
            raise ValueError(f"unknown extraction refs: {', '.join(unknown_refs)}")
        return self


@runtime_checkable
class StartupProfileExtractionPort(Protocol):
    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfileExtractionResponse: ...


class StartupProfileFragmentInventoryPort(Protocol):
    def list_for_case_revision(
        self,
        case_id: UUID,
        data_revision: int,
    ) -> tuple[StartupProfileBoundedFragment, ...]: ...


def _validate_hash_ref(value: str) -> str:
    if value.startswith("sha256:"):
        digest = value.removeprefix("sha256:")
    else:
        digest = value
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("invalid sha256 reference")
    return f"sha256:{digest}"


def _ref_key(ref: StartupProfileSafeRef) -> tuple[str, UUID, str | None, str | None]:
    return (ref.ref_type, ref.ref_id, ref.artifact_hash, ref.locator_hash)


def _normalize_text(value: str, *, max_chars: int) -> str:
    normalized = " ".join(value.split())
    return normalized[:max_chars]


def _normalize_fragment_text(value: str, *, max_chars: int) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return normalized[:max_chars]


def _safe_code(value: str, *, field_name: str) -> str:
    normalized = _normalize_bounded_text(
        value,
        max_chars=MAX_REASON_CODE_CHARS,
        field_name=field_name,
    )
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in normalized):
        raise ValueError(f"unsafe {field_name}")
    return normalized


def _normalize_bounded_text(value: str, *, max_chars: int, field_name: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) > max_chars:
        raise ValueError(f"{field_name} too long")
    return normalized


def _contains_private_material(value: str) -> bool:
    lowered = _without_redaction_placeholders(value).casefold()
    if "sk-proj-" in lowered or "secret:" in lowered:
        return True
    if re.search(r"\bbearer\s+[a-z0-9._~+/=-]+", lowered):
        return True
    if "@" in value and "." in value.rsplit("@", 1)[-1]:
        return True
    if re.search(r"\b[a-z]:[\\/]", lowered) or lowered.startswith("\\\\"):
        return True
    if re.search(r"(^|\s)/(?:home|users?|var|tmp|etc|root|private|mnt|opt|usr)/\S+", lowered):
        return True
    return False


def _without_redaction_placeholders(value: str) -> str:
    return re.sub(r"\[REDACTED:[a-z0-9_-]+:\d+\]", "", value, flags=re.IGNORECASE)


def max_sensitivity(values: Iterable[SensitivityClass]) -> SensitivityClass:
    order = {
        SensitivityClass.PUBLIC: 0,
        SensitivityClass.INTERNAL: 1,
        SensitivityClass.CONFIDENTIAL: 2,
        SensitivityClass.RESTRICTED: 3,
    }
    selected = list(values)
    if not selected:
        return SensitivityClass.PUBLIC
    return max(selected, key=lambda item: order[item])

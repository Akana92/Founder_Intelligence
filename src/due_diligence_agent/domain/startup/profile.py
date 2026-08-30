from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from due_diligence_agent.domain.common import require_decimal, require_utc

_MAX_VALUE_LENGTH = 512
_MAX_REASON_CODE_LENGTH = 80
_MAX_VERSION_LENGTH = 120
_MAX_GAP_CODE_LENGTH = 80
_MAX_SAFE_REF_LENGTH = 120
_PROFILE_NAMESPACE = NAMESPACE_URL

_SAFE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$")
_SAFE_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.@:/-]{0,119}$")
_SHA256_PATTERN = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")


class StartupProfileFieldName(StrEnum):
    STARTUP_NAME = "startup_name"
    ONE_LINE_DESCRIPTION = "one_line_description"
    PROBLEM = "problem"
    SOLUTION = "solution"
    ICP = "icp"
    USERS = "users"
    BUYERS = "buyers"
    GEOGRAPHY = "geography"
    STAGE = "stage"
    BUSINESS_MODEL = "business_model"
    PRICING_REVENUE_MODEL = "pricing_revenue_model"
    TRACTION = "traction"
    CHANNELS_GTM = "channels_gtm"
    COMPETITORS_MENTIONED = "competitors_mentioned"
    ASSUMPTIONS = "assumptions"
    STRENGTHS = "strengths"
    WEAKNESSES = "weaknesses"
    METRIC_PACK_CANDIDATES = "metric_pack_candidates"


class StartupProfileFieldStatus(StrEnum):
    SOURCE_FACT = "source_fact"
    INFERENCE = "inference"
    INSUFFICIENT_DATA = "insufficient_data"
    CONTRADICTION = "contradiction"


class StartupProfileAnalysisStage(StrEnum):
    PRIMARY = "primary"
    ENRICHED = "enriched"


class StartupProfileEvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: UUID
    fragment_id: UUID | None = None
    artifact_id: UUID
    artifact_hash: str
    locator_hash: str
    page: int | None = Field(default=None, ge=1)
    table: str | None = None
    cell: str | None = None
    field_name: StartupProfileFieldName | None = None
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("artifact_hash", "locator_hash", mode="before")
    @classmethod
    def validate_sha256_ref(cls, value: Any) -> str:
        return _normalize_sha256_ref(value)

    @field_validator("table", "cell")
    @classmethod
    def normalize_safe_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_safe_code(value, max_length=_MAX_SAFE_REF_LENGTH, field_name="safe reference")


class StartupProfileField(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: StartupProfileFieldName
    status: StartupProfileFieldStatus
    values: tuple[str, ...] = Field(default_factory=tuple)
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    evidence_refs: tuple[StartupProfileEvidenceRef, ...] = Field(default_factory=tuple)
    dependency_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    reason_code: str | None = None
    contradiction_ids: tuple[UUID, ...] = Field(default_factory=tuple)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("values", mode="before")
    @classmethod
    def normalize_values(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            items: list[Any] = [value]
        else:
            items = list(value)
        normalized = tuple(_normalize_field_value(item) for item in items)
        if len(normalized) > 16:
            raise ValueError("values exceed the allowed bound")
        deduped: list[str] = []
        seen: set[str] = set()
        for item in normalized:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return tuple(deduped)

    @field_validator("reason_code")
    @classmethod
    def normalize_reason_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_safe_code(value, max_length=_MAX_REASON_CODE_LENGTH, field_name="reason code")

    @model_validator(mode="after")
    def enforce_invariants(self) -> "StartupProfileField":
        if self.status is StartupProfileFieldStatus.SOURCE_FACT:
            if not self.evidence_refs:
                raise ValueError("source_fact requires evidence refs")
            if not self.values:
                raise ValueError("source_fact requires normalized values")
        elif self.status is StartupProfileFieldStatus.INFERENCE:
            if not self.dependency_refs:
                raise ValueError("inference requires dependency refs")
            if not self.reason_code:
                raise ValueError("inference requires a safe reason code")
            if not self.values:
                raise ValueError("inference requires normalized values")
        elif self.status is StartupProfileFieldStatus.INSUFFICIENT_DATA:
            if self.values:
                raise ValueError("insufficient_data must not invent values")
        elif self.status is StartupProfileFieldStatus.CONTRADICTION:
            if len(self.values) < 2:
                raise ValueError("contradiction requires at least two normalized values")
            if len(self.evidence_refs) < 2 and not self.contradiction_ids:
                raise ValueError("contradiction requires competing refs or contradiction ids")
            if not self.reason_code:
                raise ValueError("contradiction requires a safe reason code")
        return self


class StartupProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: UUID
    profile_hash: str
    case_id: UUID
    schema_version: str
    profile_version: str
    extractor_version: str
    analysis_stage: StartupProfileAnalysisStage
    parent_profile_id: UUID | None = None
    data_revision: int = Field(ge=1)
    built_at: datetime
    source_hashes: Mapping[str, str]
    parse_outcomes: Mapping[str, str]
    fields: Mapping[str, StartupProfileField]
    gap_codes: tuple[str, ...] = Field(default_factory=tuple)
    contradiction_ids: tuple[UUID, ...] = Field(default_factory=tuple)

    @classmethod
    def build(
        cls,
        *,
        case_id: UUID,
        schema_version: str,
        profile_version: str,
        extractor_version: str,
        analysis_stage: StartupProfileAnalysisStage,
        parent_profile_id: UUID | None,
        data_revision: int,
        source_hashes: Mapping[str, str],
        parse_outcomes: Mapping[str, str],
        fields: Mapping[str, StartupProfileField],
        gap_codes: tuple[str, ...] = (),
        contradiction_ids: tuple[UUID, ...] = (),
        case_revision_at: datetime,
    ) -> "StartupProfile":
        built_at = require_utc(case_revision_at)
        if built_at is None:
            raise ValueError("timestamp is required")

        payload: dict[str, Any] = {
            "case_id": case_id,
            "schema_version": schema_version,
            "profile_version": profile_version,
            "extractor_version": extractor_version,
            "analysis_stage": analysis_stage,
            "parent_profile_id": parent_profile_id,
            "data_revision": data_revision,
            "built_at": built_at,
            "source_hashes": source_hashes,
            "parse_outcomes": parse_outcomes,
            "fields": fields,
            "gap_codes": gap_codes,
            "contradiction_ids": contradiction_ids,
        }
        profile_hash = cls.derive_profile_hash(payload)
        profile_id = cls.derive_profile_id(case_id=case_id, profile_hash=profile_hash)
        return cls(
            profile_id=profile_id,
            profile_hash=profile_hash,
            **payload,
        )

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python", exclude={"profile_id", "profile_hash"})
        return cast(dict[str, Any], _canonicalize(payload))

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_payload())

    def derived_profile_hash(self) -> str:
        return self.derive_profile_hash(self.model_dump(mode="python", exclude={"profile_id", "profile_hash"}))

    @classmethod
    def derive_profile_hash(cls, payload: Mapping[str, Any]) -> str:
        canonical_json = _canonical_json(_canonicalize(payload))
        return f"sha256:{sha256(canonical_json.encode('utf-8')).hexdigest()}"

    @classmethod
    def derive_profile_id(cls, *, case_id: UUID, profile_hash: str) -> UUID:
        return uuid5(_PROFILE_NAMESPACE, f"startup-profile:{case_id}:{profile_hash}")

    @field_validator("schema_version", "profile_version", "extractor_version", mode="before")
    @classmethod
    def normalize_version_tag(cls, value: Any) -> str:
        return _normalize_version_tag(value)

    @field_validator("built_at")
    @classmethod
    def validate_built_at(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

    @field_validator("profile_hash", mode="before")
    @classmethod
    def normalize_profile_hash(cls, value: Any) -> str:
        return _normalize_sha256_ref(value)

    @field_validator("source_hashes", mode="before")
    @classmethod
    def normalize_source_hashes(cls, value: Any) -> Mapping[str, str]:
        if not isinstance(value, Mapping):
            raise ValueError("source hashes must be a mapping")
        normalized = {
            _normalize_safe_key(key): _normalize_sha256_ref(item)
            for key, item in value.items()
        }
        return normalized

    @field_validator("parse_outcomes", mode="before")
    @classmethod
    def normalize_parse_outcomes(cls, value: Any) -> Mapping[str, str]:
        if not isinstance(value, Mapping):
            raise ValueError("parse outcomes must be a mapping")
        normalized = {
            _normalize_safe_key(key): _normalize_safe_code(item, max_length=_MAX_VERSION_LENGTH, field_name="parse outcome")
            for key, item in value.items()
        }
        return normalized

    @field_validator("fields", mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Mapping[str, StartupProfileField]:
        if not isinstance(value, Mapping):
            raise ValueError("fields must be a mapping")
        normalized: dict[str, StartupProfileField] = {}
        for key, item in value.items():
            field_name = key.value if isinstance(key, StartupProfileFieldName) else _normalize_safe_key(key)
            normalized[field_name] = item
        return normalized

    @field_validator("source_hashes", "parse_outcomes", "fields", mode="after")
    @classmethod
    def freeze_mappings(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return MappingProxyType(dict(value))

    @field_validator("gap_codes", mode="before")
    @classmethod
    def normalize_gap_codes(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        items = [value] if isinstance(value, str) else list(value)
        normalized = tuple(
            _normalize_safe_code(item, max_length=_MAX_GAP_CODE_LENGTH, field_name="gap code")
            for item in items
        )
        return normalized

    @model_validator(mode="after")
    def enforce_profile_contract(self) -> "StartupProfile":
        expected_fields = {field.value for field in StartupProfileFieldName}
        actual_fields = set(self.fields)
        if actual_fields != expected_fields:
            missing = sorted(expected_fields - actual_fields)
            extra = sorted(actual_fields - expected_fields)
            raise ValueError(
                f"startup profile must include the required fields; missing={missing}; extra={extra}"
            )
        for field_name, field in self.fields.items():
            if field.name.value != field_name:
                raise ValueError(f"field name mismatch for {field_name}")

        expected_hash = self.derived_profile_hash()
        if self.profile_hash != expected_hash:
            raise ValueError("invalid profile hash")

        expected_id = self.derive_profile_id(case_id=self.case_id, profile_hash=self.profile_hash)
        if self.profile_id != expected_id:
            raise ValueError("invalid profile id")

        if self.analysis_stage is StartupProfileAnalysisStage.PRIMARY and self.parent_profile_id is not None:
            raise ValueError("primary profiles must not reference a parent profile")
        if self.analysis_stage is StartupProfileAnalysisStage.ENRICHED and self.parent_profile_id is None:
            raise ValueError("enriched profiles require a parent profile")

        return self

    @field_serializer("source_hashes", "parse_outcomes", "fields")
    def serialize_mapping(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return dict(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, tuple | list):
        canonical_items = [_canonicalize(item) for item in value]
        return sorted(
            canonical_items,
            key=lambda item: json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        )
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    return value


def _normalize_field_value(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("field values must be strings")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("field values must not be blank")
    if len(normalized) > _MAX_VALUE_LENGTH:
        raise ValueError("field values exceed the allowed bound")
    return normalized


def _normalize_safe_code(value: Any, *, max_length: int, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = re.sub(r"\s+", "_", value.strip().casefold())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} exceeds the allowed bound")
    if not _SAFE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} contains unsupported characters")
    return normalized


def _normalize_version_tag(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("version tag must be a string")
    normalized = re.sub(r"\s+", "_", value.strip().casefold())
    if not normalized:
        raise ValueError("version tag must not be blank")
    if len(normalized) > _MAX_VERSION_LENGTH:
        raise ValueError("version tag exceeds the allowed bound")
    if not _SAFE_VERSION_PATTERN.fullmatch(normalized):
        raise ValueError("version tag contains unsupported characters")
    return normalized


def _normalize_sha256_ref(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid sha256 reference")
    normalized = value.strip().casefold()
    match = _SHA256_PATTERN.fullmatch(normalized)
    if not match:
        raise ValueError("invalid sha256 reference")
    return f"sha256:{match.group(1)}"


def _normalize_safe_key(value: Any) -> str:
    if isinstance(value, StrEnum):
        value = value.value
    if not isinstance(value, str):
        raise ValueError("mapping key must be a string")
    return _normalize_safe_code(value, max_length=_MAX_VERSION_LENGTH, field_name="mapping key")

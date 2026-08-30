from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from due_diligence_agent.domain.common import require_utc


_MAX_SAFE_CODE_LENGTH = 120
_MAX_VALUE_LENGTH = 512
_MAX_QUESTIONS = 3
_MAX_WEIGHT = 999
_MAX_NOTES_LENGTH = 256
_READINESS_NAMESPACE = NAMESPACE_URL
_SAFE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:@/-]{0,119}$")
_SAFE_NOTES_PATTERN = re.compile(r"^[a-z0-9 ,._-]{0,256}$")
_SHA256_PATTERN = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")


class StartupReadinessSchemaVersion(str):
    STARTUP_READINESS = "startup_readiness@1"


class StartupReadinessDimensionStatus(StrEnum):
    READY = "ready"
    PROVISIONAL = "provisional"
    BLOCKED = "blocked"


class StartupReadinessDimension(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension_id: UUID
    metric_id: str
    status: StartupReadinessDimensionStatus
    reason_code: str | None = None
    notes: str | None = None

    @field_validator("metric_id", "reason_code", mode="before")
    @classmethod
    def normalize_safe_code(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("safe code must be a string")
        normalized = re.sub(r"\s+", "_", value.strip().casefold())
        if not normalized:
            raise ValueError("safe code must not be blank")
        if len(normalized) > _MAX_SAFE_CODE_LENGTH:
            raise ValueError("safe code exceeds the allowed bound")
        if not _SAFE_CODE_PATTERN.fullmatch(normalized):
            raise ValueError("safe code contains unsupported characters")
        return normalized

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("notes must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("notes must not be blank")
        if len(normalized) > _MAX_NOTES_LENGTH:
            raise ValueError("notes exceeds the allowed bound")
        if re.search(r"[\\/]|\\.\\.|/\\w|http://|https://|file:|mailto:", normalized):
            raise ValueError("notes must not contain raw reference data")
        if not _SAFE_NOTES_PATTERN.fullmatch(normalized.lower()):
            raise ValueError("notes contains unsupported characters")
        return normalized


class StartupAdaptiveQuestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: UUID
    question_code: str
    text: str
    dimension_id: UUID
    weight: int = Field(ge=1, le=_MAX_WEIGHT)

    @field_validator("question_code", mode="before")
    @classmethod
    def normalize_question_code(cls, value: Any) -> str:
        return _normalize_safe_code(value, max_length=_MAX_SAFE_CODE_LENGTH, field_name="question code")

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("text must be a string")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("text must not be blank")
        if len(normalized) > _MAX_VALUE_LENGTH:
            raise ValueError("text exceeds allowed bound")
        return normalized


class StartupMetricPack(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: UUID
    profile_hash: str
    profile_revision: int = Field(ge=1)
    schema_version: str
    pack_id: UUID
    pack_hash: str
    metric_ids: tuple[str, ...] = Field(default_factory=tuple)
    dimensions: tuple[StartupReadinessDimension, ...] = Field(default_factory=tuple)
    adaptive_questions: tuple[StartupAdaptiveQuestion, ...] = Field(default_factory=tuple)
    built_at: datetime

    @classmethod
    def build(
        cls,
        *,
        profile_id: UUID,
        profile_hash: str,
        profile_revision: int,
        metric_ids: tuple[str, ...],
        dimensions: tuple[StartupReadinessDimension, ...] = (),
        adaptive_questions: tuple[StartupAdaptiveQuestion, ...] = (),
        built_at: datetime,
    ) -> "StartupMetricPack":
        normalized = cls._normalize_fields(
            profile_id=profile_id,
            profile_hash=profile_hash,
            profile_revision=profile_revision,
            schema_version=StartupReadinessSchemaVersion.STARTUP_READINESS,
            dimensions=dimensions,
            adaptive_questions=adaptive_questions,
            metric_ids=metric_ids,
            built_at=built_at,
        )
        pack_hash = cls.derive_pack_hash(
            {
                "profile_id": profile_id,
                "profile_hash": normalized["profile_hash"],
                "profile_revision": profile_revision,
                "schema_version": StartupReadinessSchemaVersion.STARTUP_READINESS,
                "metric_ids": normalized["metric_ids"],
                "dimensions": tuple(dimension.model_dump(mode="python") for dimension in normalized["dimensions"]),
                "adaptive_questions": tuple(
                    question.model_dump(mode="python") for question in normalized["adaptive_questions"]
                ),
                "built_at": built_at,
            }
        )
        pack_id = cls.derive_pack_id(profile_id=profile_id, pack_hash=pack_hash)
        return cls(
            profile_id=profile_id,
            profile_hash=normalized["profile_hash"],
            profile_revision=profile_revision,
            schema_version=StartupReadinessSchemaVersion.STARTUP_READINESS,
            pack_id=pack_id,
            pack_hash=pack_hash,
            metric_ids=normalized["metric_ids"],
            dimensions=normalized["dimensions"],
            adaptive_questions=normalized["adaptive_questions"],
            built_at=built_at,
        )

    @staticmethod
    def _normalize_fields(**payload: Any) -> dict[str, Any]:
        return {
            "schema_version": StartupReadinessSchemaVersion.STARTUP_READINESS,
            "metric_ids": _normalize_metric_ids(payload["metric_ids"]),
            "dimensions": tuple(_coerce_dimensions(payload["dimensions"])),
            "adaptive_questions": _normalize_adaptive_questions(payload["adaptive_questions"]),
            "built_at": require_utc(payload["built_at"]),
            "profile_id": payload["profile_id"],
            "profile_hash": _normalize_sha256_ref(payload["profile_hash"]),
        }

    @field_validator("metric_ids", mode="before")
    @classmethod
    def normalize_metric_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            raise ValueError("metric ids must be provided")
        ids = value if isinstance(value, (tuple, list, set)) else (value,)
        normalized = sorted({_normalize_metric_id(item) for item in ids})
        if len(normalized) == 0:
            return ()
        return tuple(normalized)

    @field_validator("profile_hash", mode="before")
    @classmethod
    def normalize_profile_hash(cls, value: Any) -> str:
        return _normalize_sha256_ref(value)


    @classmethod
    def derive_pack_hash(cls, payload: Mapping[str, Any]) -> str:
        canonical_json = _canonical_json(_canonicalize(payload))
        return f"sha256:{sha256(canonical_json.encode('utf-8')).hexdigest()}"

    @classmethod
    def derive_pack_id(cls, *, profile_id: UUID, pack_hash: str) -> UUID:
        return uuid5(_READINESS_NAMESPACE, f"startup-metric-pack:{profile_id}:{pack_hash}")

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python", exclude={"pack_id", "pack_hash"})
        return cast(dict[str, Any], _canonicalize(payload))

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_payload())

    def derived_pack_hash(self) -> str:
        return self.derive_pack_hash(self.model_dump(mode="python", exclude={"pack_id", "pack_hash"}))

    @field_validator("schema_version", mode="before")
    @classmethod
    def normalize_schema_version(cls, value: Any) -> str:
        return _normalize_version_tag(value)

    @field_validator("built_at")
    @classmethod
    def validate_built_at(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp must be timezone-aware UTC")
        return checked

    @field_validator("dimensions", "adaptive_questions", mode="after")
    @classmethod
    def freeze_tuple_fields(cls, value: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(value)

    @field_validator("adaptive_questions", mode="after")
    @classmethod
    def normalize_adaptive_questions(cls, value: tuple[StartupAdaptiveQuestion, ...]) -> tuple[StartupAdaptiveQuestion, ...]:
        return _normalize_adaptive_questions(value)

    @field_validator("adaptive_questions", mode="after")
    @classmethod
    def validate_question_limit(cls, value: tuple[StartupAdaptiveQuestion, ...]) -> tuple[StartupAdaptiveQuestion, ...]:
        if len(value) > _MAX_QUESTIONS:
            raise ValueError("adaptive questions must be at most 3")
        return value

    @model_validator(mode="after")
    def enforce_invariants(self) -> "StartupMetricPack":
        if self.schema_version != StartupReadinessSchemaVersion.STARTUP_READINESS:
            raise ValueError(f"schema_version must be {StartupReadinessSchemaVersion.STARTUP_READINESS}")
        expected_hash = self.derived_pack_hash()
        if self.pack_hash != expected_hash:
            raise ValueError("invalid pack hash")
        expected_id = self.derive_pack_id(profile_id=self.profile_id, pack_hash=self.pack_hash)
        if self.pack_id != expected_id:
            raise ValueError("invalid pack id")
        if len(self.adaptive_questions) > _MAX_QUESTIONS:
            raise ValueError("adaptive questions must be at most 3")
        if len({question.question_id for question in self.adaptive_questions}) != len(self.adaptive_questions):
            raise ValueError("adaptive question ids must be unique")
        if len({dimension.dimension_id for dimension in self.dimensions}) != len(self.dimensions):
            raise ValueError("dimension ids must be unique")
        return self

    @field_serializer("dimensions", "adaptive_questions")
    def serialize_tuples(self, value: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(value)


class StartupReadinessSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: UUID
    profile_hash: str
    profile_revision: int = Field(ge=1)
    schema_version: str
    snapshot_id: UUID
    snapshot_hash: str
    metric_pack: StartupMetricPack
    calculation_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    diagnostic_ids: tuple[UUID, ...] = Field(default_factory=tuple)
    built_at: datetime

    @classmethod
    def build(
        cls,
        *,
        profile_id: UUID,
        profile_hash: str,
        profile_revision: int,
        metric_pack: StartupMetricPack,
        calculation_ids: tuple[UUID, ...] = (),
        diagnostic_ids: tuple[UUID, ...] = (),
        built_at: datetime,
    ) -> "StartupReadinessSnapshot":
        normalized_profile_hash = _normalize_sha256_ref(profile_hash)
        payload = {
            "profile_id": profile_id,
            "profile_hash": normalized_profile_hash,
            "profile_revision": profile_revision,
            "schema_version": StartupReadinessSchemaVersion.STARTUP_READINESS,
            "metric_pack": metric_pack,
            "calculation_ids": tuple(_normalize_reference_ids(calculation_ids)),
            "diagnostic_ids": tuple(_normalize_reference_ids(diagnostic_ids)),
            "built_at": built_at,
        }
        snapshot_hash = cls.derive_snapshot_hash(payload)
        snapshot_id = cls.derive_snapshot_id(profile_id=profile_id, snapshot_hash=snapshot_hash)
        return cls(
            profile_id=profile_id,
            profile_hash=normalized_profile_hash,
            profile_revision=profile_revision,
            schema_version=StartupReadinessSchemaVersion.STARTUP_READINESS,
            snapshot_id=snapshot_id,
            snapshot_hash=snapshot_hash,
            metric_pack=metric_pack,
            calculation_ids=tuple(_normalize_reference_ids(calculation_ids)),
            diagnostic_ids=tuple(_normalize_reference_ids(diagnostic_ids)),
            built_at=built_at,
        )

    @field_validator("calculation_ids", mode="before")
    @classmethod
    def normalize_calculation_ids(cls, value: Any) -> tuple[UUID, ...]:
        return _normalize_reference_ids(value)

    @field_validator("diagnostic_ids", mode="before")
    @classmethod
    def normalize_diagnostic_ids(cls, value: Any) -> tuple[UUID, ...]:
        return _normalize_reference_ids(value)

    def derived_snapshot_hash(self) -> str:
        payload = self.model_dump(mode="python", exclude={"snapshot_id", "snapshot_hash"})
        return self.derive_snapshot_hash(payload)

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python", exclude={"snapshot_id", "snapshot_hash"})
        return cast(dict[str, Any], _canonicalize(payload))

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_payload())

    @classmethod
    def derive_snapshot_hash(cls, payload: Mapping[str, Any]) -> str:
        canonical_json = _canonical_json(_canonicalize(payload))
        return f"sha256:{sha256(canonical_json.encode('utf-8')).hexdigest()}"

    @classmethod
    def derive_snapshot_id(cls, *, profile_id: UUID, snapshot_hash: str) -> UUID:
        return uuid5(_READINESS_NAMESPACE, f"startup-readiness-snapshot:{profile_id}:{snapshot_hash}")

    @field_validator("schema_version", mode="before")
    @classmethod
    def normalize_schema_version(cls, value: Any) -> str:
        return _normalize_version_tag(value)

    @field_validator("profile_hash", mode="before")
    @classmethod
    def normalize_profile_hash(cls, value: Any) -> str:
        return _normalize_sha256_ref(value)

    @field_validator("built_at")
    @classmethod
    def validate_built_at(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp must be timezone-aware UTC")
        return checked

    @model_validator(mode="after")
    def enforce_invariants(self) -> "StartupReadinessSnapshot":
        if self.schema_version != StartupReadinessSchemaVersion.STARTUP_READINESS:
            raise ValueError(f"schema_version must be {StartupReadinessSchemaVersion.STARTUP_READINESS}")
        if self.metric_pack.profile_id != self.profile_id:
            raise ValueError("snapshot profile_id must match metric_pack profile_id")
        if self.metric_pack.profile_hash != self.profile_hash:
            raise ValueError("snapshot profile_hash must match metric_pack profile_hash")
        if self.metric_pack.profile_revision != self.profile_revision:
            raise ValueError("snapshot profile_revision must match metric_pack profile_revision")
        expected_hash = self.derived_snapshot_hash()
        if self.snapshot_hash != expected_hash:
            raise ValueError("invalid snapshot hash")
        expected_id = self.derive_snapshot_id(
            profile_id=self.profile_id,
            snapshot_hash=self.snapshot_hash,
        )
        if self.snapshot_id != expected_id:
            raise ValueError("invalid snapshot id")
        return self


def _normalize_metric_id(value: str) -> str:
    return _normalize_safe_code(value, max_length=_MAX_SAFE_CODE_LENGTH, field_name="metric id")


def _coerce_dimensions(value: tuple[StartupReadinessDimension, ...] | list[StartupReadinessDimension]) -> tuple[StartupReadinessDimension, ...]:
    dimensions: tuple[StartupReadinessDimension, ...] = tuple(value)
    return dimensions


def _coerce_questions(value: tuple[StartupAdaptiveQuestion, ...] | list[StartupAdaptiveQuestion]) -> tuple[StartupAdaptiveQuestion, ...]:
    return tuple(value)


def _normalize_adaptive_questions(value: tuple[StartupAdaptiveQuestion, ...] | list[StartupAdaptiveQuestion]) -> tuple[StartupAdaptiveQuestion, ...]:
    questions = tuple(value)
    return tuple(
        sorted(
            questions,
            key=lambda question: (question.weight, question.question_code, str(question.question_id)),
        ),
    )


def _normalize_metric_ids(value: Any) -> tuple[str, ...]:
    ids = value if isinstance(value, (tuple, list, set)) else (value,)
    return tuple(sorted({_normalize_metric_id(item) for item in ids}))


def _normalize_reference_ids(value: Any) -> tuple[UUID, ...]:
    if value is None:
        return ()
    ids = value if isinstance(value, (tuple, list, set)) else (value,)
    return tuple(sorted(set(ids)))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, tuple | list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {_canonicalize(k): _canonicalize(v) for k, v in value.items()}
    return value


def _normalize_sha256_ref(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid sha256 reference")
    normalized = value.strip().casefold()
    match = _SHA256_PATTERN.fullmatch(normalized)
    if not match:
        raise ValueError("invalid sha256 reference")
    return f"sha256:{match.group(1)}"


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
    return _normalize_safe_code(value, max_length=_MAX_SAFE_CODE_LENGTH, field_name="schema version")

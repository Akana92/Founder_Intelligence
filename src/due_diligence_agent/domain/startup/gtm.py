from __future__ import annotations

import json
import re
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.common import require_utc


_SCHEMA_VERSION = "startup_gtm@1"
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$")
_SAFE_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.:@-]{0,119}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_REFS = 512


class StartupGtmDimensionName(StrEnum):
    AUDIENCE = "audience"
    GEOGRAPHY = "geography"
    CHANNELS = "channels"
    OFFER = "offer"
    MARKET_CONTEXT = "market_context"
    PRODUCT_PROOF = "product_proof"
    ADOPTION_RISK = "adoption_risk"


class StartupGtmDimensionStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    MISSING = "missing"
    CONTRADICTED = "contradicted"


class StartupGtmStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    CONTRADICTED = "contradicted"


class StartupGtmHorizon(StrEnum):
    DAY_7 = "day_7"
    DAY_30 = "day_30"
    DAY_60 = "day_60"
    DAY_90 = "day_90"


class StartupGtmExperimentCode(StrEnum):
    RESOLVE_CONTRADICTIONS = "resolve_contradictions"
    CLARIFY_AUDIENCE = "clarify_audience"
    VALIDATE_GEOGRAPHY = "validate_geography"
    VALIDATE_CHANNEL = "validate_channel"
    VALIDATE_OFFER = "validate_offer"
    VALIDATE_PRODUCT_PROOF = "validate_product_proof"
    VALIDATE_MARKET_POSITIONING = "validate_market_positioning"
    VALIDATE_ADOPTION_RISK = "validate_adoption_risk"
    MEASURE_CHANNEL_SIGNAL = "measure_channel_signal"
    REVIEW_LAUNCH_EVIDENCE = "review_launch_evidence"


class StartupGtmDimension(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: StartupGtmDimensionName
    status: StartupGtmDimensionStatus
    evidence_fact_ids: tuple[str, ...] = ()
    market_source_ids: tuple[str, ...] = ()
    contradiction_ids: tuple[str, ...] = ()
    reason_code: str
    gap_code: str | None = None

    @field_validator(
        "evidence_fact_ids",
        "market_source_ids",
        "contradiction_ids",
        mode="before",
    )
    @classmethod
    def validate_safe_refs(cls, value: Any) -> tuple[str, ...]:
        return _safe_refs(value)

    @field_validator("reason_code", "gap_code", mode="before")
    @classmethod
    def validate_safe_code(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _safe_code(value)

    @model_validator(mode="after")
    def enforce_gap_semantics(self) -> "StartupGtmDimension":
        if self.status is StartupGtmDimensionStatus.MISSING and self.gap_code is None:
            raise ValueError("missing GTM dimension requires a gap code")
        if self.status is not StartupGtmDimensionStatus.MISSING and self.gap_code is not None:
            raise ValueError("only missing GTM dimensions may have a gap code")
        if self.status is StartupGtmDimensionStatus.SUPPORTED and not (
            self.evidence_fact_ids or self.market_source_ids
        ):
            raise ValueError("supported GTM dimension requires evidence references")
        if self.status is StartupGtmDimensionStatus.CONTRADICTED and not self.contradiction_ids:
            raise ValueError("contradicted GTM dimension requires contradiction references")
        return self


class StartupGtmLaunchPhase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    horizon: StartupGtmHorizon
    experiment_codes: tuple[StartupGtmExperimentCode, ...] = ()

    @field_validator("experiment_codes", mode="before")
    @classmethod
    def normalize_experiment_codes(cls, value: Any) -> tuple[StartupGtmExperimentCode, ...]:
        items = () if value is None else tuple(value)
        codes = {StartupGtmExperimentCode(item) for item in items}
        return tuple(code for code in StartupGtmExperimentCode if code in codes)


class StartupGtmSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    profile_id: UUID
    product_validation_snapshot_id: UUID
    market_research_snapshot_id: UUID
    data_revision: int = Field(ge=1)
    schema_version: str = _SCHEMA_VERSION
    snapshot_id: UUID
    snapshot_hash: str
    status: StartupGtmStatus
    dimensions: tuple[StartupGtmDimension, ...]
    launch_plan: tuple[StartupGtmLaunchPhase, ...]
    finding_ids: tuple[str, ...] = ()
    built_at: datetime

    @classmethod
    def build(cls, **values: Any) -> "StartupGtmSnapshot":
        normalized = cls._normalize(values)
        snapshot_hash = _hash_payload(normalized)
        return cls(
            **normalized,
            snapshot_hash=snapshot_hash,
            snapshot_id=uuid5(
                NAMESPACE_URL,
                f"startup-gtm:{normalized['case_id']}:{snapshot_hash}",
            ),
        )

    @staticmethod
    def _normalize(values: dict[str, Any]) -> dict[str, Any]:
        built_at = require_utc(values["built_at"])
        if built_at is None:
            raise ValueError("built_at is required")
        dimensions = tuple(
            StartupGtmDimension.model_validate(item) for item in values["dimensions"]
        )
        dimensions_by_name = {item.name: item for item in dimensions}
        phases = tuple(
            StartupGtmLaunchPhase.model_validate(item) for item in values["launch_plan"]
        )
        phases_by_horizon = {item.horizon: item for item in phases}
        if set(dimensions_by_name) != set(StartupGtmDimensionName):
            raise ValueError("GTM snapshot requires every dimension exactly once")
        if set(phases_by_horizon) != set(StartupGtmHorizon):
            raise ValueError("GTM launch plan requires every horizon exactly once")
        return {
            "case_id": UUID(str(values["case_id"])),
            "profile_id": UUID(str(values["profile_id"])),
            "product_validation_snapshot_id": UUID(
                str(values["product_validation_snapshot_id"])
            ),
            "market_research_snapshot_id": UUID(str(values["market_research_snapshot_id"])),
            "data_revision": int(values["data_revision"]),
            "schema_version": _SCHEMA_VERSION,
            "status": StartupGtmStatus(values["status"]),
            "dimensions": tuple(
                dimensions_by_name[name] for name in StartupGtmDimensionName
            ),
            "launch_plan": tuple(phases_by_horizon[horizon] for horizon in StartupGtmHorizon),
            "finding_ids": _safe_refs(values.get("finding_ids", ())),
            "built_at": built_at,
        }

    @field_validator("finding_ids", mode="before")
    @classmethod
    def validate_safe_refs(cls, value: Any) -> tuple[str, ...]:
        return _safe_refs(value)

    @field_validator("snapshot_hash")
    @classmethod
    def validate_snapshot_hash(cls, value: str) -> str:
        if _SHA256_RE.fullmatch(value) is None:
            raise ValueError("snapshot hash must be sha256")
        return value

    @field_validator("built_at")
    @classmethod
    def validate_built_at(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("built_at is required")
        return checked

    @model_validator(mode="after")
    def enforce_identity_and_shape(self) -> "StartupGtmSnapshot":
        if tuple(item.name for item in self.dimensions) != tuple(StartupGtmDimensionName):
            raise ValueError("GTM dimensions are not canonical")
        if tuple(item.horizon for item in self.launch_plan) != tuple(StartupGtmHorizon):
            raise ValueError("GTM launch plan is not canonical")
        payload = self.model_dump(mode="json", exclude={"snapshot_id", "snapshot_hash"})
        expected_hash = _hash_payload(payload)
        if self.snapshot_hash != expected_hash:
            raise ValueError("invalid GTM snapshot hash")
        expected_id = uuid5(
            NAMESPACE_URL,
            f"startup-gtm:{self.case_id}:{expected_hash}",
        )
        if self.snapshot_id != expected_id:
            raise ValueError("invalid GTM snapshot id")
        return self


def _safe_ref(value: Any) -> str:
    if isinstance(value, UUID):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("reference must be a string")
    normalized = value.strip()
    if _SAFE_REF_RE.fullmatch(normalized) is None:
        raise ValueError("unsafe reference")
    return normalized


def _safe_refs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    items = (value,) if isinstance(value, str | UUID) else tuple(value)
    normalized = tuple(sorted({_safe_ref(item) for item in items}))
    if len(normalized) > _MAX_REFS:
        raise ValueError("too many references")
    return normalized


def _safe_code(value: Any) -> str:
    if isinstance(value, StrEnum):
        value = value.value
    if not isinstance(value, str):
        raise ValueError("code must be a string")
    normalized = value.strip().casefold()
    if _SAFE_CODE_RE.fullmatch(normalized) is None:
        raise ValueError("unsafe code")
    return normalized


def _hash_payload(payload: Any) -> str:
    canonical = json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, StrEnum):
        return value.value
    return value

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


_SCHEMA_DOCUMENT_INTELLIGENCE = "startup_document_intelligence@1"
_SCHEMA_PRODUCT_VALIDATION = "startup_product_validation@1"
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$")
_SAFE_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.:@-]{0,119}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_REFS = 2048


class StartupDocumentIntelligenceStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class StartupProductValidationDimensionName(StrEnum):
    PROBLEM_CLARITY = "problem_clarity"
    ICP_PRECISION = "icp_precision"
    PAIN_INTENSITY = "pain_intensity"
    URGENCY = "urgency"
    WILLINGNESS_TO_PAY = "willingness_to_pay"
    EXISTING_CUSTOMER_BEHAVIOR = "existing_customer_behavior"
    ADOPTION_RISK = "adoption_risk"
    VALIDATION_EVIDENCE = "validation_evidence"


class StartupProductValidationDimensionStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    MISSING = "missing"
    CONTRADICTED = "contradicted"


class StartupProductValidationStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    CONTRADICTED = "contradicted"


class StartupDocumentIntelligenceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    data_revision: int = Field(ge=1)
    schema_version: str = _SCHEMA_DOCUMENT_INTELLIGENCE
    snapshot_id: UUID
    snapshot_hash: str
    inventory_id: str
    source_document_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    parsed_artifact_ids: tuple[str, ...] = ()
    evidence_fact_ids: tuple[str, ...] = ()
    startup_claim_ids: tuple[str, ...] = ()
    quarantine_reason_codes: tuple[str, ...] = ()
    accepted_artifact_count: int = Field(ge=0)
    parsed_artifact_count: int = Field(ge=0)
    evidence_fact_count: int = Field(ge=0)
    startup_claim_count: int = Field(ge=0)
    quarantined_artifact_count: int = Field(ge=0)
    status: StartupDocumentIntelligenceStatus
    gap_codes: tuple[str, ...] = ()

    @classmethod
    def build(cls, **values: Any) -> "StartupDocumentIntelligenceSnapshot":
        normalized = cls._normalize(values)
        snapshot_hash = _hash_payload(normalized)
        return cls(
            **normalized,
            snapshot_hash=snapshot_hash,
            snapshot_id=uuid5(
                NAMESPACE_URL,
                f"startup-document-intelligence:{normalized['case_id']}:{snapshot_hash}",
            ),
        )

    @staticmethod
    def _normalize(values: dict[str, Any]) -> dict[str, Any]:
        source_document_ids = _safe_refs(values.get("source_document_ids", ()))
        artifact_ids = _safe_refs(values.get("artifact_ids", ()))
        parsed_artifact_ids = _safe_refs(values.get("parsed_artifact_ids", ()))
        evidence_fact_ids = _safe_refs(values.get("evidence_fact_ids", ()))
        startup_claim_ids = _safe_refs(values.get("startup_claim_ids", ()))
        quarantine_reason_codes = _safe_codes(
            values.get("quarantine_reason_codes", ())
        )
        gap_codes = _safe_codes(values.get("gap_codes", ()))
        return {
            "case_id": UUID(str(values["case_id"])),
            "data_revision": int(values["data_revision"]),
            "schema_version": _SCHEMA_DOCUMENT_INTELLIGENCE,
            "inventory_id": _safe_ref(values["inventory_id"]),
            "source_document_ids": source_document_ids,
            "artifact_ids": artifact_ids,
            "parsed_artifact_ids": parsed_artifact_ids,
            "evidence_fact_ids": evidence_fact_ids,
            "startup_claim_ids": startup_claim_ids,
            "quarantine_reason_codes": quarantine_reason_codes,
            "accepted_artifact_count": len(artifact_ids),
            "parsed_artifact_count": len(parsed_artifact_ids),
            "evidence_fact_count": len(evidence_fact_ids),
            "startup_claim_count": len(startup_claim_ids),
            "quarantined_artifact_count": len(quarantine_reason_codes),
            "status": StartupDocumentIntelligenceStatus(values["status"]),
            "gap_codes": gap_codes,
        }

    @field_validator(
        "inventory_id",
        mode="before",
    )
    @classmethod
    def validate_safe_ref(cls, value: Any) -> str:
        return _safe_ref(value)

    @field_validator(
        "source_document_ids",
        "artifact_ids",
        "parsed_artifact_ids",
        "evidence_fact_ids",
        "startup_claim_ids",
        mode="before",
    )
    @classmethod
    def validate_safe_refs(cls, value: Any) -> tuple[str, ...]:
        return _safe_refs(value)

    @field_validator("quarantine_reason_codes", "gap_codes", mode="before")
    @classmethod
    def validate_safe_codes(cls, value: Any) -> tuple[str, ...]:
        return _safe_codes(value)

    @field_validator("snapshot_hash")
    @classmethod
    def validate_snapshot_hash(cls, value: str) -> str:
        if _SHA256_RE.fullmatch(value) is None:
            raise ValueError("snapshot hash must be sha256")
        return value

    @model_validator(mode="after")
    def enforce_identity_and_counts(self) -> "StartupDocumentIntelligenceSnapshot":
        expected_counts = (
            len(self.artifact_ids),
            len(self.parsed_artifact_ids),
            len(self.evidence_fact_ids),
            len(self.startup_claim_ids),
            len(self.quarantine_reason_codes),
        )
        actual_counts = (
            self.accepted_artifact_count,
            self.parsed_artifact_count,
            self.evidence_fact_count,
            self.startup_claim_count,
            self.quarantined_artifact_count,
        )
        if actual_counts != expected_counts:
            raise ValueError("document intelligence counts do not match references")
        payload = self.model_dump(
            mode="json",
            exclude={"snapshot_id", "snapshot_hash"},
        )
        expected_hash = _hash_payload(payload)
        if self.snapshot_hash != expected_hash:
            raise ValueError("invalid document intelligence snapshot hash")
        expected_id = uuid5(
            NAMESPACE_URL,
            f"startup-document-intelligence:{self.case_id}:{expected_hash}",
        )
        if self.snapshot_id != expected_id:
            raise ValueError("invalid document intelligence snapshot id")
        return self


class StartupProductValidationDimension(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: StartupProductValidationDimensionName
    status: StartupProductValidationDimensionStatus
    evidence_fact_ids: tuple[str, ...] = ()
    startup_claim_ids: tuple[str, ...] = ()
    contradiction_ids: tuple[str, ...] = ()
    reason_code: str
    gap_code: str | None = None

    @field_validator(
        "evidence_fact_ids",
        "startup_claim_ids",
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
    def enforce_gap_semantics(self) -> "StartupProductValidationDimension":
        if (
            self.status is StartupProductValidationDimensionStatus.MISSING
            and self.gap_code is None
        ):
            raise ValueError("missing product validation dimension requires gap code")
        if (
            self.status is not StartupProductValidationDimensionStatus.MISSING
            and self.gap_code is not None
        ):
            raise ValueError("only missing product validation dimensions may have gap code")
        return self


class StartupProductValidationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    profile_id: UUID
    profile_hash: str
    profile_revision: int = Field(ge=1)
    schema_version: str = _SCHEMA_PRODUCT_VALIDATION
    snapshot_id: UUID
    snapshot_hash: str
    status: StartupProductValidationStatus
    dimensions: tuple[StartupProductValidationDimension, ...]
    built_at: datetime

    @classmethod
    def build(cls, **values: Any) -> "StartupProductValidationSnapshot":
        normalized = cls._normalize(values)
        snapshot_hash = _hash_payload(normalized)
        return cls(
            **normalized,
            snapshot_hash=snapshot_hash,
            snapshot_id=uuid5(
                NAMESPACE_URL,
                f"startup-product-validation:{normalized['profile_id']}:{snapshot_hash}",
            ),
        )

    @staticmethod
    def _normalize(values: dict[str, Any]) -> dict[str, Any]:
        built_at = require_utc(values["built_at"])
        if built_at is None:
            raise ValueError("built_at must be UTC")
        dimensions = tuple(values["dimensions"])
        return {
            "case_id": UUID(str(values["case_id"])),
            "profile_id": UUID(str(values["profile_id"])),
            "profile_hash": _sha256_ref(values["profile_hash"]),
            "profile_revision": int(values["profile_revision"]),
            "schema_version": _SCHEMA_PRODUCT_VALIDATION,
            "status": StartupProductValidationStatus(values["status"]),
            "dimensions": dimensions,
            "built_at": built_at,
        }

    @field_validator("profile_hash", "snapshot_hash", mode="before")
    @classmethod
    def validate_hash(cls, value: Any) -> str:
        return _sha256_ref(value)

    @field_validator("built_at")
    @classmethod
    def validate_built_at(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("built_at must be UTC")
        return checked

    @model_validator(mode="after")
    def enforce_identity_and_dimensions(self) -> "StartupProductValidationSnapshot":
        expected_names = tuple(StartupProductValidationDimensionName)
        actual_names = tuple(item.name for item in self.dimensions)
        if actual_names != expected_names:
            raise ValueError("product validation dimensions must be exact and ordered")
        payload = self.model_dump(
            mode="json",
            exclude={"snapshot_id", "snapshot_hash"},
        )
        expected_hash = _hash_payload(payload)
        if self.snapshot_hash != expected_hash:
            raise ValueError("invalid product validation snapshot hash")
        expected_id = uuid5(
            NAMESPACE_URL,
            f"startup-product-validation:{self.profile_id}:{expected_hash}",
        )
        if self.snapshot_id != expected_id:
            raise ValueError("invalid product validation snapshot id")
        return self


def _safe_ref(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("safe reference must be a string")
    normalized = value.strip()
    if _SAFE_REF_RE.fullmatch(normalized) is None:
        raise ValueError("safe reference is invalid")
    return normalized


def _safe_refs(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    raw_values = (values,) if isinstance(values, str) else tuple(values)
    normalized = tuple(sorted({_safe_ref(value) for value in raw_values}))
    if len(normalized) > _MAX_REFS:
        raise ValueError("safe references exceed bound")
    return normalized


def _safe_code(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("safe code must be a string")
    normalized = re.sub(r"\s+", "_", value.strip().casefold())
    if _SAFE_CODE_RE.fullmatch(normalized) is None:
        raise ValueError("safe code is invalid")
    return normalized


def _safe_codes(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    raw_values = (values,) if isinstance(values, str) else tuple(values)
    return tuple(sorted({_safe_code(value) for value in raw_values}))


def _sha256_ref(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("hash must be a string")
    normalized = value.strip().casefold()
    if not normalized.startswith("sha256:"):
        normalized = f"sha256:{normalized}"
    if _SHA256_RE.fullmatch(normalized) is None:
        raise ValueError("hash must be sha256")
    return normalized


def _hash_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        _canonicalize(payload),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{sha256(serialized.encode('utf-8')).hexdigest()}"


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")

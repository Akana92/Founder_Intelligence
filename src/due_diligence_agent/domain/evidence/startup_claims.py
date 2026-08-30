from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass, require_decimal, require_utc
from due_diligence_agent.domain.findings.models import Contradiction


class ClaimCategory(StrEnum):
    ARR = "arr"
    GROSS_MARGIN = "gross_margin"
    RUNWAY = "runway"
    CUSTOMER_COUNT = "customer_count"
    VALUATION = "valuation"
    GROWTH = "growth"
    MARKET_SIZE = "market_size"
    OTHER = "other"


class ClaimCriticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClaimStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_DATA = "insufficient_data"


class StartupClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    text_ref: str
    text_hash: str
    category: ClaimCategory
    source_artifact_id: UUID
    locator: SourceLocator
    criticality: ClaimCriticality
    evidence_query: str
    normalized_name: str
    normalized_value: Decimal | None = Field(default=None, repr=False, exclude=True)
    unit: str | None = None
    period: str | None = None
    sensitivity: SensitivityClass
    confidence: Decimal = Field(ge=0, le=1)
    extracted_at: datetime
    version: int = 1

    @classmethod
    def from_raw_text(
        cls,
        *,
        raw_text: str,
        raw_evidence_query: str | None = None,
        **values: Any,
    ) -> "StartupClaim":
        text_hash = sha256(raw_text.encode("utf-8")).hexdigest()
        values["text_ref"] = text_hash
        values["text_hash"] = text_hash
        values["evidence_query"] = _canonical_query(
            category=values["category"],
            normalized_name=values["normalized_name"],
            period=values.get("period"),
        )
        return cls(**values)

    @field_validator("confidence", "normalized_value", mode="before")
    @classmethod
    def validate_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("extracted_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

    @model_validator(mode="after")
    def require_numeric_context(self) -> "StartupClaim":
        if self.normalized_value is not None and (not self.unit or not self.period):
            raise ValueError("numeric claim requires period and unit")
        return self

    @model_validator(mode="after")
    def require_canonical_evidence_query(self) -> "StartupClaim":
        expected = _canonical_query(
            category=self.category,
            normalized_name=self.normalized_name,
            period=self.period,
        )
        if self.evidence_query != expected:
            raise ValueError("invalid canonical evidence query")
        return self

    @field_validator("text_ref", "text_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("evidence_query")
    @classmethod
    def validate_safe_query(cls, value: str) -> str:
        safe = value.strip().casefold()
        if len(safe) > 80 or not safe:
            raise ValueError("invalid canonical evidence query")
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_ -qfy." for char in safe):
            raise ValueError("invalid canonical evidence query")
        return safe


class ClaimEvidenceLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: UUID
    evidence_fact_id: UUID | None
    calculation_id: UUID | None
    relation: Literal["supports", "partially_supports", "contradicts", "missing"]
    confidence: Decimal = Field(ge=0, le=1)
    reason: str

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)


class ClaimEvidenceMatrixRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim: StartupClaim
    status: ClaimStatus
    links: tuple[ClaimEvidenceLink, ...]
    contradictions: tuple[Contradiction, ...] = ()
    contradiction_ids: tuple[UUID, ...] = ()
    executive_summary_eligible: bool


class ClaimEvidenceMatrix(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    rows: tuple[ClaimEvidenceMatrixRow, ...]


class ClaimExtractionItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(repr=False, exclude=True)
    category: ClaimCategory
    source_artifact_id: UUID
    locator: SourceLocator
    criticality: ClaimCriticality
    evidence_query: str = Field(repr=False, exclude=True)
    normalized_name: str
    normalized_value: Decimal | None = Field(default=None, repr=False, exclude=True)
    unit: str | None = None
    period: str | None = None
    sensitivity: SensitivityClass
    confidence: Decimal = Field(ge=0, le=1)

    @field_validator("confidence", "normalized_value", mode="before")
    @classmethod
    def validate_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)


class ClaimExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[ClaimExtractionItem, ...] = ()
    schema_version: str = "startup-claim-extraction@1"


def _canonical_query(
    *,
    category: ClaimCategory | str,
    normalized_name: str,
    period: str | None,
) -> str:
    del normalized_name
    try:
        claim_category = category if isinstance(category, ClaimCategory) else ClaimCategory(category)
    except ValueError:
        claim_category = ClaimCategory.OTHER
    safe_metric = claim_category.value
    return f"{safe_metric} {period.strip().casefold() if period else ''}".strip()


def _validate_sha256(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("invalid sha256")
    return value

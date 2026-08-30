from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from due_diligence_agent.domain.common import (
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
    require_decimal,
    require_utc,
)


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    category: str
    severity: FindingSeverity
    claim: str
    evidence_fact_ids: tuple[UUID, ...] = ()
    calculation_ids: tuple[UUID, ...] = ()
    confidence: Decimal
    status: FindingStatus
    counter_evidence_fact_ids: tuple[UUID, ...] = ()
    author_node: str
    author_model: str | None = None
    sensitivity: SensitivityClass
    created_at: datetime
    version: int = 1

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked


class Contradiction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    conflict_type: str
    fact_ids: tuple[UUID, ...] = ()
    finding_ids: tuple[UUID, ...] = ()
    explanation: str
    severity: FindingSeverity
    status: ContradictionStatus
    recommended_resolution: str | None = None
    resolved_by_approval_id: UUID | None = None
    sensitivity: SensitivityClass
    detected_at: datetime
    version: int = 1

    @field_validator("detected_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

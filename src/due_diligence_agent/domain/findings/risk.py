from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.common import (
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
    require_decimal,
    require_utc,
)
from due_diligence_agent.domain.findings.models import Finding


class RiskFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    category: str
    probability: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    impact: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    severity: FindingSeverity
    claim: str
    evidence_fact_ids: tuple[UUID, ...] = ()
    calculation_ids: tuple[UUID, ...] = ()
    counter_evidence_fact_ids: tuple[UUID, ...] = ()
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    status: FindingStatus
    author_node: str = "risk_analysis"
    author_model: str | None = None
    sensitivity: SensitivityClass
    created_at: datetime
    version: int = 1

    @field_validator("probability", "impact", "confidence", mode="before")
    @classmethod
    def validate_decimal(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

    @model_validator(mode="after")
    def require_support(self) -> "RiskFinding":
        if not self.evidence_fact_ids and not self.calculation_ids:
            raise ValueError("risk finding requires evidence or calculation references")
        return self

    def to_finding(self, *, finding_id: UUID) -> Finding:
        category = self.category if self.category.startswith("risk:") else f"risk:{self.category}"
        return Finding(
            id=finding_id,
            case_id=self.case_id,
            category=category,
            severity=self.severity,
            claim=self.claim,
            evidence_fact_ids=self.evidence_fact_ids,
            calculation_ids=self.calculation_ids,
            confidence=self.confidence,
            status=self.status,
            counter_evidence_fact_ids=self.counter_evidence_fact_ids,
            author_node=self.author_node,
            author_model=self.author_model,
            sensitivity=self.sensitivity,
            created_at=self.created_at,
            version=self.version,
        )

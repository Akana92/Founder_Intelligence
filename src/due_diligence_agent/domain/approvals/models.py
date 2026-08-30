from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from due_diligence_agent.domain.common import ContradictionStatus, FindingSeverity, require_utc


class Approval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    gate: str
    action: str
    actor: str
    comment: str | None = None
    decided_at: datetime
    data_revision: int
    subject_id: UUID | None = None
    subject_hash: str | None = None
    subject_version: int | None = None

    @field_validator("decided_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked


class ContradictionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    contradiction_id: UUID
    approval_id: UUID
    action: str
    status: ContradictionStatus
    data_revision: int
    invalidated_artifact_ids: tuple[UUID, ...] = ()
    invalidated_fact_ids: tuple[UUID, ...] = ()
    invalidated_calculation_ids: tuple[UUID, ...] = ()
    invalidated_finding_ids: tuple[UUID, ...] = ()
    invalidated_contradiction_ids: tuple[UUID, ...] = ()
    affected_report_snapshot_ids: tuple[UUID, ...] = ()
    report_snapshot_invalidated: bool = False
    forced_executive_summary_contradiction_ids: tuple[UUID, ...] = ()
    target_severity: FindingSeverity | None = None
    decided_at: datetime
    version: int = 1

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

    @model_validator(mode="after")
    def require_reclassify_severity(self) -> "ContradictionDecision":
        if self.action == "reclassify" and self.target_severity is None:
            raise ValueError("reclassify decision requires target severity")
        return self

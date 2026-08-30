from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    SensitivityClass,
    require_utc,
)


class DueDiligenceCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: UUID
    mode: AnalysisMode
    entity_name: str
    entity_identifier: str
    jurisdiction: str
    scope: tuple[str, ...]
    period_start: str | None = None
    period_end: str | None = None
    as_of: datetime
    base_currency: str
    privacy_policy: str
    budget_policy: str
    status: CaseStatus
    sensitivity: SensitivityClass = SensitivityClass.PUBLIC
    created_at: datetime
    updated_at: datetime
    workflow_version: str
    data_revision: int = 1

    @property
    def id(self) -> UUID:
        return self.case_id

    @field_validator("as_of", "created_at", "updated_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

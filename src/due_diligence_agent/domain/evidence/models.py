from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass, require_decimal, require_utc


class EvidenceFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    artifact_id: UUID
    name: str
    value: Any
    value_type: Literal["decimal", "integer", "text", "date", "boolean"]
    unit: str | None
    period: str | None
    locator: SourceLocator
    sensitivity: SensitivityClass
    confidence: Decimal
    source_priority: int | None = None
    extraction_method: str | None = None
    supporting_text_hash: str | None = None
    source_freshness_at: datetime | None = None
    retrieved_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    version: int = 1

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("retrieved_at", "source_freshness_at")
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc(value)

    @model_validator(mode="after")
    def require_numeric_context(self) -> "EvidenceFact":
        if self.value_type in {"decimal", "integer"} and (not self.unit or not self.period):
            raise ValueError("numeric evidence requires period and unit")
        if self.value_type == "decimal":
            object.__setattr__(self, "value", require_decimal(self.value))
        if self.value_type == "integer" and (
            not isinstance(self.value, int) or isinstance(self.value, bool)
        ):
            raise ValueError("integer evidence requires an int value")
        return self


class Calculation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    metric_name: str
    formula_version: str
    input_fact_ids: tuple[UUID, ...]
    value: Decimal
    unit: str
    period: str
    warnings: tuple[str, ...] = ()
    calculated_at: datetime
    sensitivity: SensitivityClass
    version: int = 1

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("calculated_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

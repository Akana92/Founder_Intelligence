from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.common import require_decimal


class CaseValueKind(StrEnum):
    SOURCE_FACT = "source_fact"
    FOUNDER_STATEMENT = "founder_statement"
    PUBLIC_BENCHMARK = "public_benchmark"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    AI_SCENARIO = "ai_scenario"
    CONTRADICTION = "contradiction"


class CaseStage(StrEnum):
    IDEA = "idea"
    FIRST_SALES = "first_sales"
    GROWTH = "growth"


class CaseFactRequirement(BaseModel):
    """One explicit missing fact needed before an input can be trusted as evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    field_key: str
    required_kind: CaseValueKind
    prompt: str
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    dependency_refs: tuple[UUID, ...] = Field(default_factory=tuple)

    @field_validator("field_key", "prompt", mode="before")
    @classmethod
    def validate_required_text(cls, value: Any) -> str:
        return _normalize_required_text(value)

    @model_validator(mode="after")
    def enforce_requirement_refs(self) -> "CaseFactRequirement":
        if self.required_kind in {
            CaseValueKind.SOURCE_FACT,
            CaseValueKind.PUBLIC_BENCHMARK,
        } and not self.source_refs:
            raise ValueError("source refs are required for source_fact and public_benchmark")
        if self.required_kind is CaseValueKind.DETERMINISTIC_CALCULATION and not self.dependency_refs:
            raise ValueError("dependency refs are required for deterministic_calculation")
        return self


class FounderStatement(BaseModel):
    """A founder-provided claim, kept separate from verified source evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    field_key: str
    value: str
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    provenance: CaseValueKind = CaseValueKind.FOUNDER_STATEMENT
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    period: str | None = None
    declared_source: str | None = None
    rationale: str
    validation_plan: str = "Replace with eligible source evidence before treating this as source_fact."

    @field_validator("field_key", "value", "rationale", "validation_plan", mode="before")
    @classmethod
    def validate_required_text(cls, value: Any) -> str:
        return _normalize_required_text(value)

    @field_validator("period", "declared_source", mode="before")
    @classmethod
    def validate_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @model_validator(mode="after")
    def enforce_founder_provenance(self) -> "FounderStatement":
        if self.provenance is CaseValueKind.SOURCE_FACT:
            raise ValueError("founder statements cannot be source_fact")
        if self.provenance is not CaseValueKind.FOUNDER_STATEMENT:
            raise ValueError("founder statements must use founder_statement provenance")
        return self


def _normalize_required_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("text value must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("text value must not be blank")
    return normalized


__all__ = [
    "CaseFactRequirement",
    "CaseStage",
    "CaseValueKind",
    "FounderStatement",
]

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from due_diligence_agent.domain.startup.scenario import ScenarioKey


class CaseAssetDraft(BaseModel):
    """A scenario-bound founder asset draft; it is never evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    scenario_set_id: UUID
    selected_scenario_key: ScenarioKey = "base"
    draft_version: int = Field(ge=1)
    asset_key: str
    status: Literal["draft"] = "draft"
    body_markdown: str
    metadata: dict[str, str] = Field(default_factory=dict)
    source_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    dependency_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    is_evidence: bool = False

    @field_validator("asset_key", mode="before")
    @classmethod
    def validate_text(cls, value: Any) -> str:
        return _normalize_required_text(value)

    @field_validator("body_markdown", mode="before")
    @classmethod
    def validate_markdown(cls, value: Any) -> str:
        return _normalize_required_markdown(value)

    @field_validator("metadata", mode="after")
    @classmethod
    def validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        return {
            _normalize_required_text(key): _normalize_required_text(item)
            for key, item in value.items()
        }

    @model_validator(mode="after")
    def enforce_non_evidence_contract(self) -> "CaseAssetDraft":
        if self.is_evidence:
            raise ValueError("case asset drafts are never evidence")
        return self


def _normalize_required_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("text value must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("text value must not be blank")
    return normalized


def _normalize_required_markdown(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("markdown value must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("markdown value must not be blank")
    return normalized


__all__ = ["CaseAssetDraft"]

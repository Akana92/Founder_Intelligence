from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CopilotActionKey = Literal[
    "open_fact_input",
    "open_document_upload",
    "prepare_public_research",
    "explain_metric",
    "navigate",
    "prepare_asset",
    "review_improvements",
]
CopilotActionStatus = Literal["available", "requires_input", "requires_consent", "blocked"]
CopilotMessageRole = Literal["system", "system_event", "user", "assistant", "tool"]
CopilotPayloadValue: TypeAlias = str | int | bool | tuple[str, ...]


class CopilotQuestion(BaseModel):
    """One case-local question that may block analysis until answered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    question_key: str
    prompt: str
    blocks_analysis: bool = False

    @field_validator("question_key", "prompt", mode="before")
    @classmethod
    def validate_text(cls, value: Any) -> str:
        return _normalize_required_text(value)


class CopilotAction(BaseModel):
    """A typed copilot action envelope for later handler and blocker enforcement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    action_key: CopilotActionKey
    status: CopilotActionStatus
    effect_preview: str
    payload: Mapping[str, CopilotPayloadValue]

    @field_validator("effect_preview", mode="before")
    @classmethod
    def validate_effect_preview(cls, value: Any) -> str:
        return _normalize_required_text(value, field_name="effect preview")

    @field_validator("payload", mode="before")
    @classmethod
    def validate_payload(cls, value: Any) -> Mapping[str, CopilotPayloadValue]:
        if not isinstance(value, Mapping):
            raise ValueError("payload must be a mapping")
        return dict(value)


class CopilotMessage(BaseModel):
    """One immutable message in a case/revision scoped copilot thread."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    role: CopilotMessageRole
    content: str
    page_context: str | None = None
    current_section: str | None = None
    idempotency_fingerprint: str | None = None
    related_evidence_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    question_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    action_refs: tuple[UUID, ...] = Field(default_factory=tuple)
    action_snapshots: tuple[Mapping[str, Any], ...] = Field(default_factory=tuple)
    action_result: Mapping[str, CopilotPayloadValue] | None = None

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value: Any) -> str:
        return _normalize_required_text(value)

    @field_validator("page_context", "current_section", mode="before")
    @classmethod
    def validate_optional_context(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value)


class CopilotThread(BaseModel):
    """Immutable message history for one case and data revision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: UUID
    case_id: UUID
    data_revision: int = Field(ge=1)
    messages: tuple[CopilotMessage, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def enforce_history_scope(self) -> "CopilotThread":
        for message in self.messages:
            if message.case_id != self.case_id:
                raise ValueError("copilot messages must share the same case_id")
            if message.data_revision > self.data_revision:
                raise ValueError("copilot messages cannot reference future revisions")
        return self


def _normalize_required_text(value: Any, *, field_name: str = "text value") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


__all__ = [
    "CopilotAction",
    "CopilotMessage",
    "CopilotQuestion",
    "CopilotThread",
]

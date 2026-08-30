from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from due_diligence_agent.domain.artifacts.models import SourceLocator

VerificationStatus = Literal["candidate", "needs_review", "verified"]
ParserStatus = Literal["parsed", "partial", "parser_unavailable", "damaged", "unsupported"]


class TextBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text_ref: str
    content_hash: str
    char_count: int = Field(ge=0)
    locator: SourceLocator
    confidence: Decimal = Field(ge=0, le=1)
    verification_status: VerificationStatus

    @field_validator("text_ref", "content_hash")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("invalid content reference")
        return value


class ParsedPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(ge=1)
    locator: SourceLocator
    text_blocks: list[TextBlock] = Field(default_factory=list)
    width: Decimal | None = Field(default=None, ge=0)
    height: Decimal | None = Field(default=None, ge=0)


class ParsedTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    locator: SourceLocator
    text_ref: str
    content_hash: str
    char_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    text_blocks: list[TextBlock] = Field(default_factory=list)
    confidence: Decimal = Field(ge=0, le=1)

    @field_validator("text_ref", "content_hash")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        return TextBlock.validate_sha256(value)


class ParsedDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    detected_mime_type: str | None = None
    pages: list[ParsedPage] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    text_blocks: list[TextBlock] = Field(default_factory=list)
    parser_name: str
    parser_version: str
    confidence: Decimal = Field(ge=0, le=1)
    status: ParserStatus
    error_code: str | None = None

    @classmethod
    def outcome(
        cls,
        *,
        artifact_id: UUID,
        detected_mime_type: str | None,
        parser_name: str,
        parser_version: str,
        status: ParserStatus,
        error_code: str,
    ) -> ParsedDocument:
        return cls(
            artifact_id=artifact_id,
            detected_mime_type=detected_mime_type,
            parser_name=parser_name,
            parser_version=parser_version,
            confidence=Decimal("0"),
            status=status,
            error_code=error_code,
        )

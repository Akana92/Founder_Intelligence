from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from due_diligence_agent.domain.documents.models import ParsedDocument
from due_diligence_agent.domain.documents.tabular import SpreadsheetParseResult

StartupArtifactKind = Literal["document", "spreadsheet", "unsupported"]
StartupArtifactStatus = Literal[
    "parsed",
    "partial",
    "parser_unavailable",
    "damaged",
    "unsupported",
    "rejected",
    "quota_exceeded",
]


class ParsedStartupArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    case_id: UUID
    kind: StartupArtifactKind
    status: StartupArtifactStatus
    parser_name: str
    parser_version: str
    detected_mime_type: str | None = None
    error_code: str | None = None
    document: ParsedDocument | None = Field(default=None, repr=False)
    spreadsheet: SpreadsheetParseResult | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_payload_matches_kind(self) -> ParsedStartupArtifact:
        payload_count = int(self.document is not None) + int(self.spreadsheet is not None)
        if payload_count > 1:
            raise ValueError("startup artifacts accept at most one parsed payload")
        if self.document is not None:
            if self.kind != "document":
                raise ValueError("document payload requires document kind")
            if self.document.artifact_id != self.artifact_id:
                raise ValueError("document payload artifact_id mismatch")
        if self.spreadsheet is not None:
            if self.kind != "spreadsheet":
                raise ValueError("spreadsheet payload requires spreadsheet kind")
            if self.spreadsheet.artifact_id != self.artifact_id:
                raise ValueError("spreadsheet payload artifact_id mismatch")
        if self.kind == "unsupported" and payload_count:
            raise ValueError("unsupported artifacts cannot carry parsed payloads")
        if self.status in {"parsed", "partial"} and payload_count != 1:
            raise ValueError("parsed startup artifacts require exactly one parsed payload")
        return self

    @classmethod
    def from_document(cls, document: ParsedDocument, *, case_id: UUID) -> ParsedStartupArtifact:
        return cls(
            artifact_id=document.artifact_id,
            case_id=case_id,
            kind="document",
            status=document.status,
            parser_name=document.parser_name,
            parser_version=document.parser_version,
            detected_mime_type=document.detected_mime_type,
            error_code=document.error_code,
            document=document,
        )

    @classmethod
    def from_spreadsheet(
        cls,
        result: SpreadsheetParseResult,
        *,
        case_id: UUID,
        detected_mime_type: str | None,
        parser_name: str,
        parser_version: str,
    ) -> ParsedStartupArtifact:
        return cls(
            artifact_id=result.artifact_id,
            case_id=case_id,
            kind="spreadsheet",
            status=_spreadsheet_status(result.status),
            parser_name=parser_name,
            parser_version=parser_version,
            detected_mime_type=detected_mime_type,
            error_code=result.error_code,
            spreadsheet=result,
        )

    @classmethod
    def outcome(
        cls,
        *,
        artifact_id: UUID,
        case_id: UUID,
        kind: StartupArtifactKind,
        detected_mime_type: str | None,
        parser_name: str,
        parser_version: str,
        status: StartupArtifactStatus,
        error_code: str,
    ) -> ParsedStartupArtifact:
        return cls(
            artifact_id=artifact_id,
            case_id=case_id,
            kind=kind,
            status=status,
            parser_name=parser_name,
            parser_version=parser_version,
            detected_mime_type=detected_mime_type,
            error_code=error_code,
        )

    def __getattr__(self, name: str) -> Any:
        document = self.document
        if document is not None and hasattr(document, name):
            return getattr(document, name)
        spreadsheet = self.spreadsheet
        if spreadsheet is not None and hasattr(spreadsheet, name):
            return getattr(spreadsheet, name)
        raise AttributeError(name)


def _spreadsheet_status(value: str) -> StartupArtifactStatus:
    if value == "malformed":
        return "damaged"
    if value in {
        "parsed",
        "partial",
        "rejected",
        "quota_exceeded",
        "unsupported",
    }:
        return value  # type: ignore[return-value]
    return "parser_unavailable"

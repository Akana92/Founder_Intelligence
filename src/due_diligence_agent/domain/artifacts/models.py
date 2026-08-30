from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from due_diligence_agent.domain.common import (
    ArtifactParsingStatus,
    SensitivityClass,
    require_utc,
)


class SourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    value: str
    artifact_id: UUID | None = None
    page: int | None = None
    table: str | None = None
    cell: str | None = None
    byte_range_start: int | None = None
    byte_range_end: int | None = None


class Artifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    content_hash: str
    mime_type: str
    source: str
    source_url: str | None = None
    normalized_query: tuple[tuple[str, str], ...] = ()
    retrieved_at: datetime
    published_at: datetime | None = None
    filing_acceptance_at: datetime | None = None
    effective_at: datetime | None = None
    source_snapshot_hash: str
    storage_ref: str | None = None
    parsing_status: ArtifactParsingStatus = ArtifactParsingStatus.PENDING
    sensitivity: SensitivityClass
    parent_artifact_id: UUID | None = None
    version: int = 1

    @field_validator("retrieved_at", "published_at", "filing_acceptance_at", "effective_at")
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc(value)


class StoredArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    content_hash: str
    source_snapshot_hash: str
    storage_ref: str
    media_type: str
    byte_size: int
    stored_at: datetime
    sensitivity: SensitivityClass
    version: int = 1

    @field_validator("stored_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        checked = require_utc(value)
        if checked is None:
            raise ValueError("timestamp is required")
        return checked

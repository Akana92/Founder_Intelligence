from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator


class QuarantinedArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceLocator
    content_hash: str
    reason: str
    byte_size: int = Field(ge=0)
    quarantine_ref: str | None = None


class DataRoomInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    accepted: list[Artifact] = Field(default_factory=list)
    quarantined: list[QuarantinedArtifact] = Field(default_factory=list)
    scanned_files: int = Field(default=0, ge=0)
    unpacked_bytes: int = Field(default=0, ge=0)

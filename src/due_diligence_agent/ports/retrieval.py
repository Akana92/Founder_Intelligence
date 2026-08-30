from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol
from uuid import UUID

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, field_validator

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass


INDEX_VERSION = "faiss-flat-ip@1"
CHUNK_CONFIG_VERSION = "filing-html-chunker@1"


class EvidenceChunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: UUID
    case_id: UUID
    artifact_id: UUID
    locator: SourceLocator
    content_hash: str
    sensitivity: SensitivityClass
    text_ref: str
    chunk_config_hash: str
    chunk_config_version: str = CHUNK_CONFIG_VERSION

    @field_validator("content_hash", "text_ref", "chunk_config_hash")
    @classmethod
    def validate_sha256_fields(cls, value: str) -> str:
        return _validate_sha256(value)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: UUID
    case_id: UUID
    artifact_id: UUID
    locator: SourceLocator
    content_hash: str
    sensitivity: SensitivityClass
    text_ref: str
    chunk_config_hash: str
    chunk_config_version: str
    model_id: str
    model_revision: str
    index_version: str
    score: float

    @field_validator("content_hash", "text_ref", "chunk_config_hash")
    @classmethod
    def validate_sha256_fields(cls, value: str) -> str:
        return _validate_sha256(value)


class RetrievalAuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: Literal["index", "search"]
    case_id: UUID
    artifact_id: UUID | None = None
    chunk_ids: tuple[UUID, ...] = ()
    content_hashes: tuple[str, ...] = ()
    count: int = Field(ge=0)
    k: int | None = Field(default=None, ge=1)
    status: Literal["success", "failed"]
    index_version: str = INDEX_VERSION


class EmbeddingPort(Protocol):
    dimension: int
    model_id: str
    model_revision: str

    def embed_passages(self, texts: Sequence[str]) -> npt.NDArray[np.float32]: ...
    def embed_query(self, text: str) -> npt.NDArray[np.float32]: ...


class EvidenceIndexPort(Protocol):
    def index(self, chunks: Sequence[EvidenceChunk]) -> None: ...
    def search(self, query: str, *, k: int, case_id: UUID) -> list[RetrievalHit]: ...


def _validate_sha256(value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("invalid sha256")
    return value

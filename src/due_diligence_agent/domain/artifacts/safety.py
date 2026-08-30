from __future__ import annotations

from pathlib import Path
from shutil import rmtree
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from due_diligence_agent.domain.artifacts.models import SourceLocator


class SafetyLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_files: int = Field(default=100, ge=1)
    max_file_bytes: int = Field(default=250 * 1024 * 1024, ge=1)
    max_unpacked_bytes: int = Field(default=1024 * 1024 * 1024, ge=1)
    max_archive_depth: int = Field(default=2, ge=0, le=2)
    max_decompression_ratio: float = Field(default=100.0, gt=0, le=100.0)
    allowed_media_types: frozenset[str] = frozenset(
        {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/csv",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/png",
            "image/jpeg",
            "application/zip",
        }
    )


class ScannedArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceLocator
    media_type: str
    content_hash: str
    byte_size: int = Field(ge=0)
    staged_path: Path = Field(repr=False)


class SafetyScanResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceLocator
    source_content_hash: str
    source_payload: bytes | None = Field(default=None, repr=False)
    accepted: tuple[ScannedArtifact, ...] = ()
    reason: str | None = None
    file_count: int = Field(default=0, ge=0)
    accounted_unpacked_bytes: int = Field(default=0, ge=0)
    unpacked_bytes: int = Field(default=0, ge=0)
    _transaction_root: Path | None = PrivateAttr(default=None)

    def attach_transaction(self, transaction_root: Path) -> Self:
        self._transaction_root = transaction_root
        return self

    def close(self) -> None:
        if self._transaction_root is not None:
            rmtree(self._transaction_root, ignore_errors=True)
            self._transaction_root = None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> SafetyScanResult:
        if self.reason is None and not self.accepted:
            raise ValueError("a safe scan must contain accepted artifacts")
        if self.reason is not None and self.accepted:
            raise ValueError("an unsafe scan cannot contain accepted artifacts")
        if self.reason is not None and (self.unpacked_bytes or self.accounted_unpacked_bytes):
            raise ValueError("an unsafe scan cannot report unpacked bytes")
        return self

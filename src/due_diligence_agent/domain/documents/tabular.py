from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.evidence.models import EvidenceFact


CellStatus = Literal["candidate", "insufficient_data", "verified"]
SheetVisibility = Literal["visible", "hidden", "veryHidden"]
SpreadsheetStatus = Literal[
    "parsed",
    "partial",
    "rejected",
    "malformed",
    "quota_exceeded",
    "unsupported",
]

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class NormalizedCell(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    row: int = Field(ge=1)
    column: int = Field(ge=1)
    label: str | None = Field(default=None, repr=False)
    period: str | None = None
    value: bool | date | Decimal | str | None = Field(default=None, repr=False)
    unit: str | None = None
    locator: SourceLocator
    status: CellStatus
    formula_cached: bool | None = None


class NormalizedTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    name: str = Field(repr=False)
    cells: list[NormalizedCell] = Field(default_factory=list, repr=False)
    snapshot_hash: str
    snapshot_ref: str
    visibility: SheetVisibility = "visible"
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)

    @field_validator("snapshot_hash", "snapshot_ref")
    @classmethod
    def validate_content_reference(cls, value: str) -> str:
        if not _SHA256_HEX.fullmatch(value):
            raise ValueError("invalid snapshot reference")
        return value

    def find(self, *, label: str, period: str | None = None) -> NormalizedCell | None:
        normalized_label = label.strip().casefold()
        normalized_period = period.strip().casefold() if period is not None else None
        for cell in self.cells:
            if cell.label is None or cell.label.strip().casefold() != normalized_label:
                continue
            if normalized_period is not None and (
                cell.period is None or cell.period.strip().casefold() != normalized_period
            ):
                continue
            return cell
        return None


class SpreadsheetParseResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    tables: list[NormalizedTable] = Field(default_factory=list, repr=False)
    evidence_facts: list[EvidenceFact] = Field(default_factory=list, repr=False)
    status: SpreadsheetStatus
    error_code: str | None = None
    encoding: str | None = None

    @classmethod
    def outcome(
        cls,
        *,
        artifact_id: UUID,
        status: Literal["rejected", "malformed", "quota_exceeded", "unsupported"],
        error_code: str,
    ) -> SpreadsheetParseResult:
        return cls(artifact_id=artifact_id, status=status, error_code=error_code)

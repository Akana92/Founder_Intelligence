from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class AnalysisMode(StrEnum):
    PUBLIC_COMPANY = "public_company"
    STARTUP = "startup"


class SensitivityClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CaseStatus(StrEnum):
    CREATED = "created"
    AWAITING_SCOPE_APPROVAL = "awaiting_scope_approval"
    RUNNING = "running"
    AWAITING_EVIDENCE = "awaiting_evidence"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    UNSUPPORTED_JURISDICTION = "unsupported_jurisdiction"


class ArtifactParsingStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    PARTIAL = "partial"
    FAILED = "failed"


class FindingStatus(StrEnum):
    DRAFT = "draft"
    VERIFIED = "verified"
    INSUFFICIENT_DATA = "insufficient_data"
    CONTRADICTED = "contradicted"
    REQUIRES_REVIEW = "requires_review"


class ContradictionStatus(StrEnum):
    OPEN = "open"
    ACCEPTED_SOURCE = "accepted_source"
    EXCLUDED_ARTIFACT = "excluded_artifact"
    AWAITING_EVIDENCE = "awaiting_evidence"
    RECLASSIFIED = "reclassified"
    UNRESOLVED = "unresolved"


def require_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value


def require_decimal(value: Any) -> Decimal:
    if isinstance(value, float):
        raise ValueError("canonical financial values must be Decimal, not float")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError("canonical financial values must be Decimal-compatible")

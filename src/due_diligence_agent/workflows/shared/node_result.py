from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class NodeStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    RETRYABLE_ERROR = "retryable_error"
    BLOCKED = "blocked"
    FAILED = "failed"


class NodeResult(BaseModel, Generic[T]):
    status: NodeStatus
    data: T | None = None
    data_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    fallback_used: str | None = None
    retry_after_seconds: float | None = None
    trace_id: str | None = None

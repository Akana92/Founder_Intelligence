from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class TraceContext:
    request_id: str
    run_id: str
    case_id: str
    correlation_id: str
    workflow_type: Literal["public_company", "startup"]
    app_version: str
    graph_version: str
    redaction_policy_version: str


@dataclass(frozen=True)
class AuditEvent:
    schema_version: str
    event_id: str
    timestamp_utc: str
    run_id: str
    correlation_id: str
    span_name: str
    event_type: str
    attributes: Mapping[str, str | int | float | bool | None]


class AuditSpool(Protocol):
    def append(self, event: AuditEvent) -> str: ...
    def read_batch(self, limit: int = 100) -> list[AuditEvent]: ...
    def mark_flushed(self, event_ids: Sequence[str]) -> None: ...


@runtime_checkable
class TraceSanitizer(Protocol):
    def sanitize_attributes(
        self,
        attributes: Mapping[str, object | None],
        *,
        drop_disallowed: bool = False,
    ) -> dict[str, str | int | float | bool | None]: ...

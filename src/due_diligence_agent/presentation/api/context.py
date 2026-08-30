from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from starlette.datastructures import Headers


REQUEST_ID_HEADER = "X-Request-ID"


@dataclass(frozen=True)
class RequestContext:
    """Per-request metadata with C-ready identity seams.

    Delivery profile B is anonymous/single-operator, so actor/workspace are
    intentionally nullable and are not resolved from arbitrary request headers.
    """

    request_id: UUID
    actor_id: str | None = None
    workspace_id: str | None = None


def resolve_request_context(headers: Headers | dict[str, str] | None = None) -> RequestContext:
    request_headers = Headers(headers or {})
    return RequestContext(request_id=_canonical_request_id(request_headers.get(REQUEST_ID_HEADER)))


def _canonical_request_id(raw_value: str | None) -> UUID:
    if raw_value is None:
        return uuid4()
    try:
        candidate = UUID(raw_value)
    except ValueError:
        return uuid4()
    if str(candidate) != raw_value:
        return uuid4()
    return candidate

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from due_diligence_agent.presentation.api.context import (
    REQUEST_ID_HEADER,
    RequestContext,
    resolve_request_context,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach canonical request context and safe scalar trace metadata."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        context = resolve_request_context(request.headers)
        request.state.request_context = context
        span = trace.get_current_span()
        _set_span_name(span, "http.request")
        _set_span_attribute(span, "http.request.method", request.method)
        try:
            response = await call_next(request)
        except Exception:
            _record_trace_result(span, request, context, status_code=500)
            raise
        response.headers[REQUEST_ID_HEADER] = str(context.request_id)
        _record_trace_result(span, request, context, status_code=response.status_code)
        return response


async def unhandled_exception_response(request: Request, _exc: Exception) -> Response:
    """Return a generic 500 response while preserving the safe request identifier."""

    context = getattr(request.state, "request_context", None)
    if not isinstance(context, RequestContext):
        context = resolve_request_context()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers={REQUEST_ID_HEADER: str(context.request_id)},
    )


def _record_trace_result(
    span: Any,
    request: Request,
    context: RequestContext,
    *,
    status_code: int,
) -> None:
    route = _route_path(request)
    _set_span_attribute(span, "http.route", route)
    _set_span_attribute(span, "http.response.status_code", status_code)
    _set_span_attribute(span, "api.version", _api_version(route))
    _set_span_attribute(span, "request_id", str(context.request_id))


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str):
        return route_path
    return "unmatched"


def _api_version(route: str) -> str:
    parts = route.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "api":
        return parts[1]
    return "none"


def _set_span_name(span: Any, name: str) -> None:
    update_name = getattr(span, "update_name", None)
    if callable(update_name):
        update_name(name)


def _set_span_attribute(span: Any, key: str, value: str | int) -> None:
    set_attribute = getattr(span, "set_attribute", None)
    if callable(set_attribute):
        set_attribute(key, value)

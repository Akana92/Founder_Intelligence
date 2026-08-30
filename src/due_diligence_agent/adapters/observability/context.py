from __future__ import annotations

from contextvars import ContextVar

from due_diligence_agent.ports.tracing import TraceContext


_CURRENT_TRACE_CONTEXT: ContextVar[TraceContext | None] = ContextVar(
    "due_diligence_trace_context",
    default=None,
)


def set_trace_context(context: TraceContext) -> object:
    return _CURRENT_TRACE_CONTEXT.set(context)


def reset_trace_context(token: object) -> None:
    _CURRENT_TRACE_CONTEXT.reset(token)  # type: ignore[arg-type]


def current_trace_context() -> TraceContext | None:
    return _CURRENT_TRACE_CONTEXT.get()

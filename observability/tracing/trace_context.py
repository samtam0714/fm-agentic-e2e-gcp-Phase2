"""Trace ID generation and request-scoped context."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field


def new_trace_id() -> str:
    return f"tr_{uuid.uuid4().hex[:12]}"


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=new_trace_id)
    session_id: str = ""
    app_name: str = ""
    user_query: str = ""


_current_context: ContextVar[TraceContext | None] = ContextVar(
    "trace_context", default=None
)


def set_trace_context(ctx: TraceContext) -> None:
    _current_context.set(ctx)


def get_trace_context() -> TraceContext | None:
    return _current_context.get()


def clear_trace_context() -> None:
    _current_context.set(None)

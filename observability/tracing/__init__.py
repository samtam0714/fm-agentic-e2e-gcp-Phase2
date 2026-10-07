"""JSONL tracing for agent runs.

Note: cloud_trace_exporter is intentionally NOT imported here - it pulls in
structured logging, and structured_logger imports trace_context, which would
create a circular import via this package __init__.
Import exporter from observability.tracing.cloud_trace_exporter when needed
(span_recorder already does this lazily).
"""

from observability.tracing.models import TraceSpan
from observability.tracing.span_recorder import SpanRecorder, record_trace_from_events
from observability.tracing.trace_context import TraceContext, new_trace_id

__all__ = [
    "TraceContext",
    "TraceSpan",
    "SpanRecorder",
    "new_trace_id",
    "record_trace_from_events",
]

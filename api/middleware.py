"""HTTP middleware for trace context propagation."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from observability.tracing import TraceContext, new_trace_id
from observability.tracing.trace_context import clear_trace_context, set_trace_context


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Attach a trace_id to each request and echo it in the response header."""

    header_name = "X-Trace-Id"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        trace_id = request.headers.get(self.header_name) or new_trace_id()
        request.state.trace_id = trace_id
        set_trace_context(TraceContext(trace_id=trace_id, app_name="fm-agentops-api"))
        try:
            response = await call_next(request)
            response.headers[self.header_name] = trace_id
            return response
        finally:
            clear_trace_context()

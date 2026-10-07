"""Export local TraceSpan records to Google Cloud Trace (Sprint 4 / 2.4.1).

Design:
- Disabled by default when ENABLE_CLOUD_TRACE is unset; writes local JSONL only.
- When enabled, converts existing spans to Cloud Trace v2 BatchWriteSpans.
- Failures are logged without blocking the investigation.

Environment variables:
  ENABLE_CLOUD_TRACE=1|true|yes
  GOOGLE_CLOUD_PROJECT (required when enabled)
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from observability.logging.structured_logger import get_logger
from observability.tracing.models import TraceSpan

_log = get_logger(__name__)


class _TraceClient(Protocol):
    def batch_write_spans(self, *, name: str, spans: list[Any]) -> None: ...


def cloud_trace_enabled() -> bool:
    return os.getenv("ENABLE_CLOUD_TRACE", "").strip().lower() in {"1", "true", "yes"}


def to_cloud_trace_id(local_trace_id: str) -> str:
    """Map a local trace ID to the 32-character hex ID required by Cloud Trace."""
    return hashlib.sha256(local_trace_id.encode("utf-8")).hexdigest()[:32]


def to_cloud_span_id(local_trace_id: str, index: int) -> str:
    """Return the 16-character hex span ID required by Cloud Trace."""
    return hashlib.sha256(f"{local_trace_id}:{index}".encode("utf-8")).hexdigest()[:16]


def _attr_map(attrs: dict[str, str]) -> Any:
    from google.cloud.trace_v2.types import AttributeValue, Span

    attribute_map = {
        key: AttributeValue(string_value={"value": value[:256]})
        for key, value in attrs.items()
        if value is not None
    }
    return Span.Attributes(attribute_map=attribute_map)


def build_cloud_spans(
    spans: list[TraceSpan],
    *,
    project_id: str,
    local_trace_id: str,
) -> list[Any]:
    """Convert local TraceSpan list into Cloud Trace v2 Span messages."""
    from google.cloud.trace_v2.types import Span
    from google.protobuf.timestamp_pb2 import Timestamp

    if not spans:
        return []

    cloud_trace_id = to_cloud_trace_id(local_trace_id)
    # Anchor on the first timestamped span, or use the current time.
    anchor = next((s.timestamp for s in spans if s.timestamp is not None), None)
    cursor = (
        datetime.fromtimestamp(anchor, tz=timezone.utc)
        if anchor is not None
        else datetime.now(timezone.utc)
    )

    cloud_spans: list[Any] = []
    parent_id: str | None = None

    for index, span in enumerate(spans):
        span_id = to_cloud_span_id(local_trace_id, index)
        duration = max(span.latency_ms, 1.0) / 1000.0
        if span.timestamp is not None:
            start = datetime.fromtimestamp(span.timestamp, tz=timezone.utc)
        else:
            start = cursor
        end = start + timedelta(seconds=duration)
        cursor = end

        start_pb = Timestamp()
        start_pb.FromDatetime(start)
        end_pb = Timestamp()
        end_pb.FromDatetime(end)

        display = f"{span.agent}/{span.step}"[:128]
        attrs = {
            "fm/agent": span.agent,
            "fm/step": span.step,
            "fm/span_type": span.span_type,
            "fm/status": span.status,
            "fm/local_trace_id": local_trace_id,
        }
        if span.tool_calls:
            attrs["fm/tools"] = ",".join(span.tool_calls)[:256]
        if span.input_summary:
            attrs["fm/input"] = span.input_summary[:256]
        if span.output_summary:
            attrs["fm/output"] = span.output_summary[:256]

        cloud_span = Span(
            name=f"projects/{project_id}/traces/{cloud_trace_id}/spans/{span_id}",
            span_id=span_id,
            parent_span_id=parent_id or "",
            display_name={"value": display},
            start_time=start_pb,
            end_time=end_pb,
            attributes=_attr_map(attrs),
            span_kind=Span.SpanKind.INTERNAL,
        )
        # Use the first span as root and attach later spans as direct children.
        if parent_id is None:
            parent_id = span_id
        cloud_spans.append(cloud_span)

    return cloud_spans


def export_spans_to_cloud_trace(
    spans: list[TraceSpan],
    *,
    local_trace_id: str,
    project_id: str | None = None,
    client: _TraceClient | None = None,
) -> bool:
    """Export spans when ENABLE_CLOUD_TRACE is on. Returns True if exported."""
    if not cloud_trace_enabled():
        return False
    if not spans:
        return False

    project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        _log.warning("cloud_trace.skipped", reason="GOOGLE_CLOUD_PROJECT missing")
        return False

    try:
        from google.cloud import trace_v2

        trace_client: _TraceClient = client or trace_v2.TraceServiceClient()
        cloud_spans = build_cloud_spans(
            spans, project_id=project, local_trace_id=local_trace_id
        )
        trace_client.batch_write_spans(
            name=f"projects/{project}",
            spans=cloud_spans,
        )
        _log.info(
            "cloud_trace.exported",
            local_trace_id=local_trace_id,
            cloud_trace_id=to_cloud_trace_id(local_trace_id),
            span_count=len(cloud_spans),
            project=project,
        )
        return True
    except Exception as exc:
        _log.warning(
            "cloud_trace.export_failed",
            local_trace_id=local_trace_id,
            error=str(exc),
        )
        return False

"""Build spans from ADK events and write JSONL trace files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from observability.tracing.models import TraceSpan
from observability.tracing.trace_context import TraceContext, new_trace_id

DEFAULT_TRACES_DIR = (
    Path(__file__).resolve().parents[2] / "eval_harness" / "reports" / "traces"
)
_SUMMARY_MAX_LEN = 300


def _truncate(value: Any, max_len: int = _SUMMARY_MAX_LEN) -> str:
    text = str(value).replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


LOAD_SKILL_TOOL = "load_skill"


def _requested_skill_name(tool_name: str, args: Any) -> str | None:
    if tool_name != LOAD_SKILL_TOOL or not isinstance(args, dict):
        return None
    skill_name = args.get("skill_name")
    return str(skill_name) if skill_name else None


def _skill_load_fields(tool_name: str, response: Any) -> dict[str, Any]:
    """Extract key fields because summaries truncate load_skill responses."""
    if tool_name != LOAD_SKILL_TOOL or not isinstance(response, dict):
        return {}

    frontmatter = response.get("frontmatter")
    metadata = frontmatter.get("metadata") if isinstance(frontmatter, dict) else None
    version = metadata.get("version") if isinstance(metadata, dict) else None
    return {
        "skill_name": response.get("skill_name"),
        "skill_version": str(version) if version else None,
        "skill_load_result": "error" if response.get("error") else "loaded",
    }


def _usage_tokens(event: Any) -> tuple[int | None, int | None]:
    usage = getattr(event, "usage_metadata", None)
    if not usage:
        return None, None
    tokens_in = getattr(usage, "prompt_token_count", None)
    tokens_out = getattr(usage, "candidates_token_count", None)
    return tokens_in, tokens_out


def events_to_spans(
    events: list[Any],
    *,
    trace_id: str,
    user_query: str = "",
) -> list[TraceSpan]:
    """Convert ADK runner events into ordered trace spans."""
    spans: list[TraceSpan] = []
    prev_ts: float | None = None

    if user_query:
        spans.append(
            TraceSpan(
                trace_id=trace_id,
                agent="user",
                step="user_query",
                input_summary=_truncate(user_query),
                output_summary="",
                span_type="request",
                status="success",
            )
        )

    for event in events:
        author = getattr(event, "author", None) or "unknown"
        timestamp = getattr(event, "timestamp", None)
        latency_ms = 0.0
        if timestamp is not None and prev_ts is not None:
            latency_ms = max(0.0, (timestamp - prev_ts) * 1000)
        if timestamp is not None:
            prev_ts = timestamp

        tokens_in, tokens_out = _usage_tokens(event)
        content = getattr(event, "content", None)
        if not content or not getattr(content, "parts", None):
            continue

        for part in content.parts:
            if part.text:
                spans.append(
                    TraceSpan(
                        trace_id=trace_id,
                        agent=author,
                        step="agent_response",
                        output_summary=_truncate(part.text),
                        latency_ms=latency_ms,
                        tokens_input=tokens_in,
                        tokens_output=tokens_out,
                        span_type="agent_turn",
                        timestamp=timestamp,
                        status="success",
                    )
                )
            if part.function_call and part.function_call.name:
                tool_name = part.function_call.name
                args = part.function_call.args
                spans.append(
                    TraceSpan(
                        trace_id=trace_id,
                        agent=author,
                        step=tool_name,
                        input_summary=_truncate(args),
                        latency_ms=latency_ms,
                        tool_calls=[tool_name],
                        span_type="tool_call",
                        timestamp=timestamp,
                        status="success",
                        skill_name=_requested_skill_name(tool_name, args),
                    )
                )
            if part.function_response and part.function_response.name:
                tool_name = part.function_response.name
                response = part.function_response.response
                skill_fields = _skill_load_fields(tool_name, response)
                spans.append(
                    TraceSpan(
                        trace_id=trace_id,
                        agent=author,
                        step=tool_name,
                        output_summary=_truncate(response),
                        latency_ms=latency_ms,
                        tool_calls=[tool_name],
                        span_type="tool_result",
                        timestamp=timestamp,
                        status="success",
                        **skill_fields,
                    )
                )

    return spans


class SpanRecorder:
    """Append trace spans to a JSONL file."""

    def __init__(self, trace_id: str, output_dir: Path | None = None) -> None:
        self.trace_id = trace_id
        self.output_dir = output_dir or DEFAULT_TRACES_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.output_dir / f"{trace_id}.jsonl"

    def write_spans(self, spans: list[TraceSpan]) -> Path:
        with open(self.path, "w", encoding="utf-8") as f:
            for span in spans:
                f.write(span.model_dump_json() + "\n")
        return self.path

    def append_span(self, span: TraceSpan) -> Path:
        """Append one span (used by remote A2A services sharing Root's trace_id)."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(span.model_dump_json() + "\n")
        return self.path

    def read_spans(self) -> list[TraceSpan]:
        if not self.path.exists():
            return []
        spans: list[TraceSpan] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    spans.append(TraceSpan.model_validate_json(line))
        return spans


def record_trace_from_events(
    events: list[Any],
    *,
    context: TraceContext | None = None,
    user_query: str = "",
    latency_seconds: float = 0.0,
    output_dir: Path | None = None,
) -> tuple[str, Path]:
    """Build spans from events, write JSONL, return (trace_id, path)."""
    ctx = context or TraceContext(user_query=user_query)
    trace_id = ctx.trace_id or new_trace_id()
    query = user_query or ctx.user_query

    spans = events_to_spans(events, trace_id=trace_id, user_query=query)
    if latency_seconds > 0 and spans:
        spans.append(
            TraceSpan(
                trace_id=trace_id,
                agent="system",
                step="run_complete",
                output_summary=f"total_latency_s={latency_seconds:.3f}",
                latency_ms=latency_seconds * 1000,
                span_type="agent_turn",
                status="success",
            )
        )

    recorder = SpanRecorder(trace_id, output_dir=output_dir)
    path = recorder.write_spans(spans)

    # Sprint 4: Optional Cloud Trace/BigQuery export; failures do not block the run.
    from observability.tracing.cloud_trace_exporter import export_spans_to_cloud_trace
    from observability.analytics.bigquery_exporter import export_spans_to_bigquery

    export_spans_to_cloud_trace(spans, local_trace_id=trace_id)
    export_spans_to_bigquery(spans, local_trace_id=trace_id)

    return trace_id, path

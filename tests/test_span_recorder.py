"""Unit tests for JSONL tracing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from observability.tracing.models import TraceSpan
from observability.tracing.span_recorder import (
    SpanRecorder,
    events_to_spans,
    record_trace_from_events,
)
from observability.tracing.trace_context import TraceContext, new_trace_id


@dataclass
class FakePart:
    text: str | None = None
    function_call: object | None = None
    function_response: object | None = None


@dataclass
class FakeFunctionCall:
    name: str
    args: dict


@dataclass
class FakeFunctionResponse:
    name: str
    response: dict


@dataclass
class FakeContent:
    parts: list[FakePart] = field(default_factory=list)


@dataclass
class FakeEvent:
    author: str
    content: FakeContent | None = None
    timestamp: float = 0.0


def test_new_trace_id_format():
    trace_id = new_trace_id()
    assert trace_id.startswith("tr_")
    assert len(trace_id) == 15


def test_events_to_spans_builds_call_chain():
    events = [
        FakeEvent(
            author="alarm_agent",
            timestamp=1.0,
            content=FakeContent(
                parts=[
                    FakePart(
                        function_call=FakeFunctionCall(
                            name="search_alarm_history", args={"floor": 3}
                        )
                    )
                ]
            ),
        ),
        FakeEvent(
            author="alarm_agent",
            timestamp=1.5,
            content=FakeContent(
                parts=[
                    FakePart(
                        function_response=FakeFunctionResponse(
                            name="search_alarm_history",
                            response={"asset_id": "AHU-3F-01", "event_count": 7},
                        )
                    )
                ]
            ),
        ),
        FakeEvent(
            author="alarm_agent",
            timestamp=2.0,
            content=FakeContent(
                parts=[FakePart(text="Recurring P1 alarm for AHU-3F-01.")]
            ),
        ),
    ]

    spans = events_to_spans(
        events,
        trace_id="tr_test123",
        user_query="Check Floor 3 HVAC alarm",
    )

    assert spans[0].step == "user_query"
    assert spans[0].span_type == "request"
    assert spans[1].step == "search_alarm_history"
    assert spans[1].span_type == "tool_call"
    assert "floor" in spans[1].input_summary
    assert spans[2].span_type == "tool_result"
    assert "AHU-3F-01" in spans[2].output_summary
    assert spans[3].span_type == "agent_turn"
    assert spans[3].latency_ms == 500.0


def test_span_recorder_writes_and_reads_jsonl(tmp_path: Path):
    trace_id = "tr_unit_test"
    recorder = SpanRecorder(trace_id, output_dir=tmp_path)
    spans = [
        TraceSpan(
            trace_id=trace_id,
            agent="alarm_agent",
            step="search_alarm_history",
            input_summary='{"floor": 3}',
            tool_calls=["search_alarm_history"],
            span_type="tool_call",
        ),
        TraceSpan(
            trace_id=trace_id,
            agent="alarm_agent",
            step="agent_response",
            output_summary="7 recurring events",
            span_type="agent_turn",
        ),
    ]

    path = recorder.write_spans(spans)
    assert path.exists()
    assert path.name == f"{trace_id}.jsonl"

    loaded = recorder.read_spans()
    assert len(loaded) == 2
    assert loaded[0].agent == "alarm_agent"
    assert loaded[1].output_summary == "7 recurring events"


def test_record_trace_from_events_adds_run_complete_span(tmp_path: Path):
    events = [
        FakeEvent(
            author="kb_agent",
            timestamp=1.0,
            content=FakeContent(parts=[FakePart(text="Policy HVAC-MNT-003 applies.")]),
        )
    ]
    ctx = TraceContext(trace_id="tr_record_test", user_query="investigate alarm")

    trace_id, path = record_trace_from_events(
        events,
        context=ctx,
        latency_seconds=1.234,
        output_dir=tmp_path,
    )

    assert trace_id == "tr_record_test"
    assert path.exists()

    recorder = SpanRecorder(trace_id, output_dir=tmp_path)
    spans = recorder.read_spans()
    assert spans[0].step == "user_query"
    assert spans[-1].step == "run_complete"
    assert spans[-1].agent == "system"
    assert "1.234" in spans[-1].output_summary

"""Tests for Cloud Trace exporter (Sprint 4 / 2.4.1)."""

from __future__ import annotations

from observability.tracing.cloud_trace_exporter import (
    build_cloud_spans,
    cloud_trace_enabled,
    export_spans_to_cloud_trace,
    to_cloud_span_id,
    to_cloud_trace_id,
)
from observability.tracing.models import TraceSpan


class _FakeTraceClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def batch_write_spans(self, *, name: str, spans: list) -> None:
        self.calls.append({"name": name, "spans": spans})


def _sample_spans() -> list[TraceSpan]:
    return [
        TraceSpan(
            trace_id="tr_abc",
            agent="user",
            step="user_query",
            input_summary="check AHU",
            span_type="request",
            latency_ms=0,
            timestamp=1_700_000_000.0,
        ),
        TraceSpan(
            trace_id="tr_abc",
            agent="alarm_agent",
            step="search_alarm_history",
            tool_calls=["search_alarm_history"],
            span_type="tool_call",
            latency_ms=120.0,
            timestamp=1_700_000_001.0,
        ),
    ]


def test_cloud_trace_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_CLOUD_TRACE", raising=False)
    assert cloud_trace_enabled() is False
    assert export_spans_to_cloud_trace(_sample_spans(), local_trace_id="tr_abc") is False


def test_cloud_trace_id_is_32_hex():
    tid = to_cloud_trace_id("tr_abc")
    assert len(tid) == 32
    assert all(c in "0123456789abcdef" for c in tid)


def test_cloud_span_id_is_16_hex():
    sid = to_cloud_span_id("tr_abc", 0)
    assert len(sid) == 16


def test_build_cloud_spans_shapes():
    cloud = build_cloud_spans(
        _sample_spans(), project_id="demo-project", local_trace_id="tr_abc"
    )
    assert len(cloud) == 2
    assert cloud[0].name.startswith("projects/demo-project/traces/")
    assert "alarm_agent/search_alarm_history" in cloud[1].display_name.value


def test_export_calls_batch_write_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_CLOUD_TRACE", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    client = _FakeTraceClient()
    ok = export_spans_to_cloud_trace(
        _sample_spans(),
        local_trace_id="tr_abc",
        client=client,
    )
    assert ok is True
    assert len(client.calls) == 1
    assert client.calls[0]["name"] == "projects/demo-project"
    assert len(client.calls[0]["spans"]) == 2


def test_export_skips_without_project(monkeypatch):
    monkeypatch.setenv("ENABLE_CLOUD_TRACE", "1")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    client = _FakeTraceClient()
    ok = export_spans_to_cloud_trace(
        _sample_spans(), local_trace_id="tr_abc", client=client
    )
    assert ok is False
    assert client.calls == []

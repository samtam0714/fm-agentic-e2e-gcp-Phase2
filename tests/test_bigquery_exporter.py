"""Tests for BigQuery exporter (Sprint 4 / 2.4.2)."""

from __future__ import annotations

from typing import Any

from observability.analytics.bigquery_exporter import (
    bigquery_enabled,
    eval_report_to_rows,
    export_eval_report_to_bigquery,
    export_gate_result_to_bigquery,
    export_spans_to_bigquery,
    gate_result_to_rows,
    spans_to_rows,
)
from observability.tracing.models import TraceSpan


class _FakeBQClient:
    def __init__(self) -> None:
        self.ready: list[tuple[str, str]] = []
        self.inserts: list[dict[str, Any]] = []

    def ensure_ready(self, *, project_id: str, dataset_id: str) -> None:
        self.ready.append((project_id, dataset_id))

    def insert_rows(
        self, *, project_id: str, dataset_id: str, table_id: str, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        self.inserts.append(
            {
                "project_id": project_id,
                "dataset_id": dataset_id,
                "table_id": table_id,
                "rows": rows,
            }
        )
        return []


def _sample_spans() -> list[TraceSpan]:
    return [
        TraceSpan(
            trace_id="tr_abc",
            agent="alarm_agent",
            step="search_alarm_history",
            tool_calls=["search_alarm_history"],
            span_type="tool_call",
            latency_ms=120.0,
            tokens_input=10,
            tokens_output=20,
            timestamp=1_700_000_001.0,
        )
    ]


def _sample_report() -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "case_count": 1,
        "pass_count": 1,
        "fail_count": 0,
        "pass_rate": 1.0,
        "avg_tool_call_accuracy": 1.0,
        "avg_tool_arg_accuracy": None,
        "avg_task_success": 1.0,
        "avg_groundedness": 0.9,
        "avg_failure_recovery": None,
        "p50_latency_seconds": 5.0,
        "p95_latency_seconds": 5.0,
        "critical_failures": 0,
        "cases": [
            {
                "case_id": "rag_001",
                "case_category": "rag",
                "pass": True,
                "tool_call_accuracy": 1.0,
                "latency_seconds": 5.0,
                "trace_id": "tr_abc",
            }
        ],
    }


def test_bigquery_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_BIGQUERY", raising=False)
    assert bigquery_enabled() is False
    assert export_spans_to_bigquery(_sample_spans(), local_trace_id="tr_abc") is False


def test_spans_to_rows_shape():
    rows = spans_to_rows(_sample_spans(), inserted_at="2026-01-01T00:00:00+00:00")
    assert len(rows) == 1
    assert rows[0]["trace_id"] == "tr_abc"
    assert rows[0]["tool_calls"] == "search_alarm_history"
    assert rows[0]["tokens_input"] == 10


def test_eval_report_to_rows():
    run_rows, case_rows, run_id = eval_report_to_rows(
        _sample_report(), run_id="eval_test", inserted_at="2026-01-01T00:00:00+00:00"
    )
    assert run_id == "eval_test"
    assert len(run_rows) == 1
    assert run_rows[0]["pass_rate"] == 1.0
    report_payload = __import__("json").loads(run_rows[0]["report_json"])
    assert "cases" not in report_payload
    assert report_payload["case_count"] == 1
    assert len(case_rows) == 1
    assert case_rows[0]["case_id"] == "rag_001"


def test_gate_result_to_rows():
    rows = gate_result_to_rows(
        {
            "pass": True,
            "absolute": {"pass": True, "checks": {}},
            "regression": {"pass": False, "checks": {}},
        },
        gate_id="gate_1",
        inserted_at="2026-01-01T00:00:00+00:00",
    )
    assert rows[0]["overall_pass"] is True
    assert rows[0]["absolute_pass"] is True
    assert rows[0]["regression_pass"] is False


def test_export_spans_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_BIGQUERY", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    monkeypatch.setenv("BIGQUERY_DATASET", "fm_agentops_test")
    client = _FakeBQClient()
    ok = export_spans_to_bigquery(
        _sample_spans(), local_trace_id="tr_abc", client=client
    )
    assert ok is True
    assert client.ready == [("demo-project", "fm_agentops_test")]
    assert len(client.inserts) == 1
    assert client.inserts[0]["table_id"] == "agent_spans"
    assert client.inserts[0]["rows"][0]["trace_id"] == "tr_abc"


def test_export_eval_and_gate(monkeypatch):
    monkeypatch.setenv("ENABLE_BIGQUERY", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    client = _FakeBQClient()
    assert export_eval_report_to_bigquery(_sample_report(), run_id="r1", client=client)
    assert export_gate_result_to_bigquery(
        {"pass": True, "absolute": {"pass": True}, "regression": None},
        gate_id="g1",
        client=client,
    )
    tables = {item["table_id"] for item in client.inserts}
    assert tables == {"eval_runs", "eval_cases", "gate_results"}


def test_export_skips_without_project(monkeypatch):
    monkeypatch.setenv("ENABLE_BIGQUERY", "1")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    client = _FakeBQClient()
    ok = export_spans_to_bigquery(_sample_spans(), local_trace_id="tr_abc", client=client)
    assert ok is False
    assert client.inserts == []

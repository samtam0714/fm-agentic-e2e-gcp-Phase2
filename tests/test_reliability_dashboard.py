"""Tests for reliability dashboard metrics (Sprint 4 / 2.4.4)."""

from __future__ import annotations

import json
from pathlib import Path

from observability.dashboard.metrics import (
    build_reliability_metrics,
    estimate_cost_usd,
)
from observability.dashboard.render import render_reliability_html
from observability.tracing.models import TraceSpan


def test_estimate_cost_usd():
    cost = estimate_cost_usd(1_000_000, 1_000_000)
    assert cost == round(0.15 + 0.60, 6)


def test_build_reliability_metrics_from_local_files(tmp_path: Path):
    report = {
        "schema_version": "2.0",
        "case_count": 3,
        "pass_count": 2,
        "fail_count": 1,
        "pass_rate": 0.667,
        "avg_task_success": 0.9,
        "avg_groundedness": 0.8,
        "avg_failure_recovery": 0.5,
        "p50_latency_seconds": 4.0,
        "p95_latency_seconds": 9.0,
        "case_category_breakdown": {
            "normal": {"case_count": 2, "pass_count": 2, "fail_count": 0, "pass_rate": 1.0},
            "fallback": {"case_count": 1, "pass_count": 0, "fail_count": 1, "pass_rate": 0.0},
        },
        "cases": [
            {"case_id": "n1", "case_category": "normal", "pass": True},
            {"case_id": "n2", "case_category": "normal", "pass": True},
            {
                "case_id": "fb1",
                "case_category": "fallback",
                "pass": False,
                "missing_tools": ["search_policy_doc"],
                "llm_reason": "fallback failed",
            },
        ],
    }
    gate = {
        "pass": False,
        "absolute": {"pass": True, "checks": {}},
        "regression": {"pass": False, "checks": {}},
    }
    (tmp_path / "eval_report.json").write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "gate_result.json").write_text(json.dumps(gate), encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    spans = [
        TraceSpan(
            trace_id="tr_1",
            agent="alarm_agent",
            step="search_alarm_history",
            span_type="tool_call",
            status="success",
            tokens_input=1000,
            tokens_output=500,
            tool_calls=["search_alarm_history"],
        ),
        TraceSpan(
            trace_id="tr_1",
            agent="kb_agent",
            step="search_policy_doc",
            span_type="tool_result",
            status="error",
            tokens_input=200,
            tokens_output=50,
            tool_calls=["search_policy_doc"],
        ),
    ]
    with open(traces / "tr_1.jsonl", "w", encoding="utf-8") as f:
        for span in spans:
            f.write(span.model_dump_json() + "\n")

    metrics = build_reliability_metrics(reports_dir=tmp_path)
    assert metrics["latency"]["p50_seconds"] == 4.0
    assert metrics["latency"]["p95_seconds"] == 9.0
    assert metrics["judge_pass_rate"] == 0.667
    assert metrics["tool_error_rate"] == 0.5
    assert metrics["fallback_rate"] == round(1 / 3, 4)
    assert metrics["failure_recovery_rate"] == 0.5
    assert metrics["release_gate"]["overall_pass"] is False
    assert metrics["release_gate"]["absolute_pass"] is True
    assert metrics["top_failing_cases"][0]["case_id"] == "fb1"
    assert metrics["cost_estimate"]["request_count"] == 1
    assert metrics["cost_estimate"]["avg_cost_usd"] is not None

    page = render_reliability_html(metrics)
    assert "FM AgentOps Reliability" in page
    assert "fb1" in page
    assert "FAIL" in page

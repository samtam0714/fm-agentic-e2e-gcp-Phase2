"""Reliability dashboard - aggregate local eval/gate/traces (Sprint 4 / 2.4.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from observability.tracing.models import TraceSpan

DEFAULT_REPORTS_DIR = (
    Path(__file__).resolve().parents[2] / "eval_harness" / "reports"
)

# Rough Gemini 2.5 Flash-ish list prices (USD / 1M tokens) for estimates only.
_INPUT_USD_PER_1M = 0.15
_OUTPUT_USD_PER_1M = 0.60


def estimate_cost_usd(
    tokens_input: int | None,
    tokens_output: int | None,
    *,
    input_usd_per_1m: float = _INPUT_USD_PER_1M,
    output_usd_per_1m: float = _OUTPUT_USD_PER_1M,
) -> float:
    tin = tokens_input or 0
    tout = tokens_output or 0
    return round((tin / 1_000_000) * input_usd_per_1m + (tout / 1_000_000) * output_usd_per_1m, 6)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else None


def _load_trace_spans(traces_dir: Path, limit_files: int = 50) -> list[TraceSpan]:
    if not traces_dir.exists():
        return []
    paths = sorted(traces_dir.glob("tr_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    spans: list[TraceSpan] = []
    for path in paths[:limit_files]:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    spans.append(TraceSpan.model_validate_json(line))
                except Exception:
                    continue
    return spans


def _tool_error_rate(spans: list[TraceSpan]) -> float | None:
    tool_spans = [s for s in spans if s.span_type in {"tool_call", "tool_result"}]
    if not tool_spans:
        return None
    errors = sum(1 for s in tool_spans if s.status == "error")
    return round(errors / len(tool_spans), 4)


def _cost_from_spans(spans: list[TraceSpan]) -> dict[str, Any]:
    by_trace: dict[str, dict[str, int]] = {}
    for span in spans:
        bucket = by_trace.setdefault(span.trace_id, {"tokens_input": 0, "tokens_output": 0})
        bucket["tokens_input"] += span.tokens_input or 0
        bucket["tokens_output"] += span.tokens_output or 0

    if not by_trace:
        return {
            "request_count": 0,
            "avg_cost_usd": None,
            "total_cost_usd": None,
            "total_tokens_input": 0,
            "total_tokens_output": 0,
        }

    costs = [
        estimate_cost_usd(v["tokens_input"], v["tokens_output"]) for v in by_trace.values()
    ]
    total_in = sum(v["tokens_input"] for v in by_trace.values())
    total_out = sum(v["tokens_output"] for v in by_trace.values())
    return {
        "request_count": len(by_trace),
        "avg_cost_usd": round(sum(costs) / len(costs), 6),
        "total_cost_usd": round(sum(costs), 6),
        "total_tokens_input": total_in,
        "total_tokens_output": total_out,
    }


def _fallback_rate(report: dict[str, Any] | None) -> float | None:
    if not report:
        return None
    breakdown = report.get("case_category_breakdown") or {}
    fallback = breakdown.get("fallback")
    if not fallback:
        # Derive from cases if breakdown missing
        cases = report.get("cases") or []
        fallback_cases = [c for c in cases if c.get("case_category") == "fallback"]
        if not fallback_cases:
            return 0.0 if cases else None
        return round(len(fallback_cases) / len(cases), 4)
    total = report.get("case_count") or 0
    if total <= 0:
        return None
    return round((fallback.get("case_count") or 0) / total, 4)


def _top_failing_cases(report: dict[str, Any] | None, *, limit: int = 10) -> list[dict[str, Any]]:
    if not report:
        return []
    failing = [c for c in (report.get("cases") or []) if not c.get("pass")]
    failing.sort(key=lambda c: (c.get("case_category") or "", c.get("case_id") or ""))
    out: list[dict[str, Any]] = []
    for case in failing[:limit]:
        out.append(
            {
                "case_id": case.get("case_id"),
                "case_category": case.get("case_category"),
                "missing_tools": case.get("missing_tools") or [],
                "missing_agents": case.get("missing_agents") or [],
                "llm_reason": (case.get("llm_reason") or "")[:200],
            }
        )
    return out


def build_reliability_metrics(
    *,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Aggregate dashboard metrics from local eval_report / gate_result / traces."""
    root = reports_dir or DEFAULT_REPORTS_DIR
    report = _load_json(root / "eval_report.json")
    gate = _load_json(root / "gate_result.json")
    spans = _load_trace_spans(root / "traces")
    cost = _cost_from_spans(spans)

    return {
        "source": {
            "reports_dir": str(root),
            "has_eval_report": report is not None,
            "has_gate_result": gate is not None,
            "trace_span_count": len(spans),
        },
        "latency": {
            "p50_seconds": None if report is None else report.get("p50_latency_seconds"),
            "p95_seconds": None if report is None else report.get("p95_latency_seconds"),
        },
        "tool_error_rate": _tool_error_rate(spans),
        "judge_pass_rate": None if report is None else report.get("pass_rate"),
        "release_gate": {
            "overall_pass": None if gate is None else gate.get("pass"),
            "absolute_pass": None
            if gate is None
            else (gate.get("absolute") or {}).get("pass"),
            "regression_pass": None
            if gate is None or gate.get("regression") is None
            else (gate.get("regression") or {}).get("pass"),
        },
        "top_failing_cases": _top_failing_cases(report),
        "cost_estimate": cost,
        "fallback_rate": _fallback_rate(report),
        "failure_recovery_rate": None
        if report is None
        else report.get("avg_failure_recovery"),
        "eval_summary": None
        if report is None
        else {
            "case_count": report.get("case_count"),
            "pass_count": report.get("pass_count"),
            "fail_count": report.get("fail_count"),
            "avg_task_success": report.get("avg_task_success"),
            "avg_groundedness": report.get("avg_groundedness"),
            "case_category_breakdown": report.get("case_category_breakdown") or {},
        },
    }

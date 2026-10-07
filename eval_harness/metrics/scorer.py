"""Aggregate per-case eval results into a report."""

from __future__ import annotations

from typing import Any

from eval_harness.metrics.schema import DEFAULT_CASE_CATEGORY, SCHEMA_VERSION


def _avg_metric(case_results: list[dict[str, Any]], key: str) -> float | None:
    values = [r[key] for r in case_results if key in r and r[key] is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return round(sorted_values[lower], 3)
    weight = position - lower
    interpolated = sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
    return round(interpolated, 3)


def _category_breakdown(case_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for result in case_results:
        category = result.get("case_category", DEFAULT_CASE_CATEGORY)
        buckets.setdefault(category, []).append(result)

    breakdown: dict[str, dict[str, Any]] = {}
    for category, results in sorted(buckets.items()):
        pass_count = sum(1 for r in results if r.get("pass"))
        breakdown[category] = {
            "case_count": len(results),
            "pass_count": pass_count,
            "fail_count": len(results) - pass_count,
            "pass_rate": round(pass_count / len(results), 3) if results else 0.0,
        }
    return breakdown


def _empty_report() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_count": 0,
        "pass_count": 0,
        "fail_count": 0,
        "pass_rate": 0.0,
        "avg_tool_call_accuracy": 0.0,
        "avg_tool_arg_accuracy": None,
        "avg_agent_coverage": 0.0,
        "avg_answer_keyword_score": 0.0,
        "avg_task_success": 0.0,
        "avg_groundedness": 0.0,
        "avg_failure_recovery": None,
        "p50_latency_seconds": None,
        "p95_latency_seconds": None,
        "llm_judged_cases": 0,
        "critical_failures": 0,
        "case_category_breakdown": {},
        "cases": [],
    }


def build_report(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not case_results:
        return _empty_report()

    pass_count = sum(1 for r in case_results if r.get("pass"))
    fail_count = len(case_results) - pass_count
    llm_judged_cases = sum(1 for r in case_results if not r.get("llm_judge_skipped"))
    latencies = [
        r["latency_seconds"]
        for r in case_results
        if "latency_seconds" in r and r["latency_seconds"] is not None
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "case_count": len(case_results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate": round(pass_count / len(case_results), 3),
        "avg_tool_call_accuracy": _avg_metric(case_results, "tool_call_accuracy") or 0.0,
        "avg_tool_arg_accuracy": _avg_metric(case_results, "tool_arg_accuracy"),
        "avg_agent_coverage": _avg_metric(case_results, "agent_coverage") or 0.0,
        "avg_answer_keyword_score": _avg_metric(case_results, "answer_keyword_score") or 0.0,
        "avg_task_success": _avg_metric(case_results, "task_success") or 0.0,
        "avg_groundedness": _avg_metric(case_results, "groundedness") or 0.0,
        "avg_failure_recovery": _avg_metric(case_results, "failure_recovery"),
        "p50_latency_seconds": _percentile(latencies, 0.50),
        "p95_latency_seconds": _percentile(latencies, 0.95),
        "llm_judged_cases": llm_judged_cases,
        "critical_failures": fail_count,
        "case_category_breakdown": _category_breakdown(case_results),
        "cases": case_results,
    }

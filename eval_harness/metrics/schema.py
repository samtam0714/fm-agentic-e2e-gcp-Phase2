"""Phase 2 eval metrics schema - contract for reports and golden cases."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "2.0"

CASE_CATEGORIES = frozenset({"normal", "safety", "rag", "failure", "fallback"})
DEFAULT_CASE_CATEGORY = "normal"

REPORT_AGGREGATE_METRICS = (
    "case_count",
    "pass_count",
    "fail_count",
    "pass_rate",
    "avg_tool_call_accuracy",
    "avg_tool_arg_accuracy",
    "avg_agent_coverage",
    "avg_answer_keyword_score",
    "avg_task_success",
    "avg_groundedness",
    "avg_failure_recovery",
    "p50_latency_seconds",
    "p95_latency_seconds",
    "llm_judged_cases",
    "critical_failures",
)

PER_CASE_METRICS = (
    "case_id",
    "case_category",
    "pass",
    "tool_call_accuracy",
    "tool_arg_accuracy",
    "agent_coverage",
    "answer_keyword_score",
    "task_success",
    "groundedness",
    "failure_recovery",
    "latency_seconds",
)


def validate_report(report: dict[str, Any]) -> list[str]:
    """Return validation errors for an eval report against the Phase 2 schema."""
    errors: list[str] = []

    for key in REPORT_AGGREGATE_METRICS:
        if key not in report:
            errors.append(f"missing aggregate metric: {key}")

    if "cases" not in report:
        errors.append("missing cases list")
        return errors

    if not isinstance(report["cases"], list):
        errors.append("cases must be a list")
        return errors

    for index, case in enumerate(report["cases"]):
        prefix = f"cases[{index}]"
        if "case_id" not in case:
            errors.append(f"{prefix}: missing case_id")
        category = case.get("case_category", DEFAULT_CASE_CATEGORY)
        if category not in CASE_CATEGORIES:
            errors.append(f"{prefix}: invalid case_category: {category}")

    return errors

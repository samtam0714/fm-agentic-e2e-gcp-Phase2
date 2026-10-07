"""Validate the JSON structure of every golden-dataset case."""

from __future__ import annotations

from typing import Any

from eval_harness.metrics.schema import CASE_CATEGORIES, DEFAULT_CASE_CATEGORY

# Required fields for every case
REQUIRED_FIELDS = ("case_id", "input", "expected_tools", "expected_agents")

# Optional fields, including Phase 2 Sprint 1 failure metadata
OPTIONAL_FIELDS = (
    "case_category",           # normal / safety / rag / failure / fallback
    "expected_answer_contains",  # Required answer keywords
    "must_not_contains",       # Prohibited answer phrases
    "must_not_do",             # Prohibited business behavior
    "expected_behavior",       # Human-readable steps; documentation only
    "optional_tools",          # Helpful but not required tools
    "expected_tool_args",      # Expected key arguments for tool_arg_accuracy
    "keyword_alternatives",    # Keyword synonyms used by the rule-based judge
    "failure_scenario",        # invalid_arg / tool_fail / timeout / safety / fallback
    "expected_recovery_contains",  # Recovery/degradation terms for scoring
    "fault_injection",         # Make a tool fail its first N calls
)


def validate_case(case: dict[str, Any]) -> list[str]:
    """Validate one case and return errors; an empty list means valid."""
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in case:
            errors.append(f"missing required field: {field}")

    case_id = case.get("case_id")
    if case_id is not None and not str(case_id).strip():
        errors.append("case_id must be non-empty")

    if "input" in case and not str(case.get("input", "")).strip():
        errors.append("input must be non-empty")

    for list_field in ("expected_tools", "expected_agents", "expected_answer_contains"):
        value = case.get(list_field)
        if list_field in REQUIRED_FIELDS and not isinstance(value, list):
            errors.append(f"{list_field} must be a list")
        elif isinstance(value, list) and not value:
            errors.append(f"{list_field} must not be empty")

    category = case.get("case_category", DEFAULT_CASE_CATEGORY)
    if category not in CASE_CATEGORIES:
        errors.append(f"case_category must be one of {sorted(CASE_CATEGORIES)}")

    tool_args = case.get("expected_tool_args")
    if tool_args is not None:
        if not isinstance(tool_args, dict):
            errors.append("expected_tool_args must be a dict of tool_name -> args dict")
        else:
            expected_tools = set(case.get("expected_tools", []))
            optional_tools = set(case.get("optional_tools") or [])
            known_tools = expected_tools | optional_tools
            for tool_name, args in tool_args.items():
                if not isinstance(args, dict):
                    errors.append(
                        f"expected_tool_args[{tool_name}] must be a dict of arg -> value"
                    )
                if known_tools and tool_name not in known_tools:
                    errors.append(
                        f"expected_tool_args references unknown tool: {tool_name}"
                    )

    return errors


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    """Validate a full dataset and ensure case IDs are unique."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    if not cases:
        errors.append("dataset must contain at least one case")
        return errors

    for index, case in enumerate(cases):
        prefix = f"case[{index}]"
        case_errors = validate_case(case)
        errors.extend(f"{prefix}: {msg}" for msg in case_errors)

        case_id = case.get("case_id")
        if case_id:
            if case_id in seen_ids:
                errors.append(f"{prefix}: duplicate case_id {case_id}")
            seen_ids.add(case_id)

    return errors

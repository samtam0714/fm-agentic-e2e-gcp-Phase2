"""Rule-based evaluation against golden dataset cases."""

from __future__ import annotations

from typing import Any

from eval_harness.trace_collector import AgentTrace

_AGENT_OUTPUT_NAMES = (
    "alarm_agent",
    "kb_agent",
    "workorder_agent",
    "auditor_agent",
)
_WORK_ORDER_CREATION_PHRASES = frozenset(
    {"create a new work order", "create new work order"}
)
# Default synonyms match common equivalent phrasing without per-case alternatives.
_DEFAULT_KEYWORD_ALTERNATIVES: dict[str, list[str]] = {
    "not recurring": [
        "single event",
        "one event",
        "one occurrence",
        "isolated",
        "transient",
        "does not recur",
        "non-recurring",
        "not meet recurrence",
        "no recurrence",
        "only one",
    ],
    "history": [
        "alarm history",
        "historical",
        "events",
        "occurrence",
        "investigated",
    ],
    "monitor": [
        "monitoring",
        "continue monitoring",
        "no work order",
        "no_action",
        "no action",
        "not warranted",
    ],
    "investigate": [
        "investigation",
        "identify",
        "asset_id",
        "asset id",
    ],
    "asset": [
        "asset_id",
        "asset id",
        "without an asset",
        "without asset",
        "identify the asset",
        "which asset",
        "cannot create",
        "unable to create",
        "refuse",
        "decline",
    ],
}


def _required_tools(case: dict[str, Any]) -> list[str]:
    """Return required tools after excluding optional tools."""
    expected = case.get("expected_tools", [])
    optional = set(case.get("optional_tools") or [])
    return [tool for tool in expected if tool not in optional]


def _keyword_alternatives(case: dict[str, Any], keyword: str) -> list[str]:
    custom = (case.get("keyword_alternatives") or {}).get(keyword, [])
    defaults = _DEFAULT_KEYWORD_ALTERNATIVES.get(keyword, [])
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in [keyword, *custom, *defaults]:
        lowered = candidate.lower()
        if lowered not in seen:
            seen.add(lowered)
            ordered.append(candidate)
    return ordered


def _matches_keyword(case: dict[str, Any], keyword: str, text: str) -> bool:
    lowered = text.lower()
    return any(alt.lower() in lowered for alt in _keyword_alternatives(case, keyword))


def _agent_output_text(trace: AgentTrace) -> str:
    return "\n".join(trace.final_agent_text(agent) for agent in _AGENT_OUTPUT_NAMES).lower()


def _normalize_arg(value: Any) -> str:
    """Normalize values for loose comparison using lowercase and separator folding."""
    return str(value).lower().replace("_", " ").replace("-", " ").strip()


def _arg_value_matches(expected: Any, actual: Any) -> bool:
    """Return whether one argument value matches.

    Strings use normalized bidirectional substring matching. Other values use
    relaxed equality after string conversion.
    """
    if isinstance(expected, str) and isinstance(actual, str):
        exp = _normalize_arg(expected)
        act = _normalize_arg(actual)
        if not exp:
            return True
        return exp in act or act in exp
    return _normalize_arg(expected) == _normalize_arg(actual)


def _arg_matches_any_call(calls: list[dict[str, Any]], key: str, expected: Any) -> bool:
    """Return whether any call to a tool has the expected value for a key."""
    for call in calls:
        if key in call and _arg_value_matches(expected, call[key]):
            return True
    return False


def _score_tool_args(case: dict[str, Any], trace: AgentTrace) -> float | None:
    """Score argument accuracy for key tools.

    Score only cases with expected_tool_args; otherwise return None.
    The score is matched (tool, argument) pairs divided by expected pairs.
    """
    expected_tool_args = case.get("expected_tool_args")
    if not expected_tool_args:
        return None

    total = 0
    hits = 0
    for tool_name, expected_args in expected_tool_args.items():
        calls = trace.tool_args.get(tool_name, [])
        for key, expected_value in expected_args.items():
            total += 1
            if _arg_matches_any_call(calls, key, expected_value):
                hits += 1

    if total == 0:
        return None
    return round(hits / total, 3)


def _score_failure_recovery(case: dict[str, Any], trace: AgentTrace) -> float | None:
    """Score safe recovery for failure and fallback cases.

    Score only cases with failure_scenario and expected_recovery_contains.
    Normal alarm, safety, and RAG cases return None.

    1.0 means all expected recovery terms matched; 0.0 means none matched.
    """
    scenario = case.get("failure_scenario")
    if not scenario:
        return None

    signals = case.get("expected_recovery_contains") or []
    if not signals:
        return None

    answer_text = _agent_output_text(trace)
    tool_text = " ".join(
        str(value).lower() for value in trace.tool_results.values()
    )
    combined = f"{answer_text}\n{tool_text}"

    hits = sum(1 for signal in signals if _matches_keyword(case, signal, combined))
    if hits == len(signals):
        return 1.0
    if hits == 0:
        return 0.0
    return round(hits / len(signals), 3)


def judge_case(case: dict[str, Any], trace: AgentTrace) -> dict[str, Any]:
    """Score a single golden case against an agent run trace."""
    expected_tools = _required_tools(case)
    expected_agents = case.get("expected_agents", [])
    expected_answer_contains = case.get("expected_answer_contains", [])
    must_not_contains = case.get("must_not_contains", [])

    missing_tools = [t for t in expected_tools if t not in trace.tools]
    missing_agents = [a for a in expected_agents if a not in trace.agents]
    answer_text = _agent_output_text(trace)
    missing_keywords = [
        kw
        for kw in expected_answer_contains
        if not _matches_keyword(case, kw, answer_text)
    ]

    must_not_violations = _check_must_not(case, trace, must_not_contains)

    tool_call_accuracy = (
        1.0 if not expected_tools else (len(expected_tools) - len(missing_tools)) / len(expected_tools)
    )
    agent_coverage = (
        1.0 if not expected_agents else (len(expected_agents) - len(missing_agents)) / len(expected_agents)
    )
    answer_keyword_score = (
        1.0
        if not expected_answer_contains
        else (len(expected_answer_contains) - len(missing_keywords)) / len(expected_answer_contains)
    )

    passed = (
        not missing_tools
        and not missing_agents
        and not missing_keywords
        and not must_not_violations
    )

    failure_recovery = _score_failure_recovery(case, trace)
    tool_arg_accuracy = _score_tool_args(case, trace)

    return {
        "case_id": case.get("case_id"),
        "pass": passed,
        "tool_call_accuracy": round(tool_call_accuracy, 3),
        "tool_arg_accuracy": tool_arg_accuracy,  # Scored only with expected_tool_args
        "agent_coverage": round(agent_coverage, 3),
        "answer_keyword_score": round(answer_keyword_score, 3),
        "failure_recovery": failure_recovery,  # Failure cases only
        "actual_tools": trace.tools,
        "actual_agents": trace.agents,
        "missing_tools": missing_tools,
        "missing_agents": missing_agents,
        "missing_keywords": missing_keywords,
        "must_not_violations": must_not_violations,
        "latency_seconds": round(trace.latency_seconds, 3),
    }


def _check_must_not(
    case: dict[str, Any],
    trace: AgentTrace,
    must_not_contains: list[str],
) -> list[str]:
    violations: list[str] = []
    agent_text = _agent_output_text(trace)
    workorder_text = trace.final_agent_text("workorder_agent").lower()

    wo_result = trace.tool_results.get("recommend_work_order", {})
    recommendation = wo_result.get("recommendation", {}) if isinstance(wo_result, dict) else {}
    action = recommendation.get("action", "")
    should_create = recommendation.get("should_create", False)

    for phrase in must_not_contains:
        phrase_lower = phrase.lower()
        if phrase_lower in _WORK_ORDER_CREATION_PHRASES:
            # Trust tool action: no_action may cite policy language about when to create.
            if action == "create_new" and should_create:
                violations.append(f"Answer contains forbidden phrase: {phrase}")
            continue
        if phrase_lower in agent_text:
            violations.append(f"Answer contains forbidden phrase: {phrase}")

    if action == "create_new" and should_create:
        if "wo-2026-0142" in case.get("expected_answer_contains", []):
            violations.append(
                "recommend_work_order returned create_new but existing WO-2026-0142 expected"
            )

    if "create new work order" in workorder_text and "escalate" not in workorder_text:
        if "escalate" in [k.lower() for k in case.get("expected_answer_contains", [])]:
            violations.append(
                "WorkOrder agent recommended create without escalate for recurring demo case"
            )

    for rule in case.get("must_not_do", []):
        if "without checking existing" in rule.lower():
            if action == "create_new" and "wo-2026-0142" in agent_text:
                violations.append(rule)

    return violations

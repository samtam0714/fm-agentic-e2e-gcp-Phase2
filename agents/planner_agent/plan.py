"""Dynamic 3-step plan generation (Sprint 5 / 2.5.2).

Canonical steps: investigate -> policy -> recommend.
Auditor is always appended by the execution pipeline as a quality gate
(outside the 3-step plan, matching the current planner architecture).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agents.router_agent.classify import INTENT_ALARM, INTENT_POLICY, INTENT_WORKORDER

STEP_INVESTIGATE = "investigate"
STEP_POLICY = "policy"
STEP_RECOMMEND = "recommend"

AGENT_FOR_STEP = {
    STEP_INVESTIGATE: "alarm_agent",
    STEP_POLICY: "kb_agent",
    STEP_RECOMMEND: "workorder_agent",
}


@dataclass(frozen=True)
class PlanStep:
    step: str
    agent: str
    goal: str
    primary: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_plan(intent: str, *, error_hint: str | None = None) -> list[PlanStep]:
    """Build a 3-step plan for the given intent.

    All intents keep the full investigate -> policy -> recommend spine so V1
    eval cases still exercise every specialist. Intent only shifts which
    step is marked primary (emphasis for downstream agents).
    """
    intent = (intent or INTENT_ALARM).strip().lower() or INTENT_ALARM

    goals = {
        STEP_INVESTIGATE: "Gather alarm history and similar resolved cases.",
        STEP_POLICY: "Retrieve and cite governing maintenance policy.",
        STEP_RECOMMEND: "Recommend create / escalate / monitor work-order action.",
    }
    if intent == INTENT_POLICY:
        goals[STEP_POLICY] = "Primary: cite governing policy rules verbatim."
    elif intent == INTENT_WORKORDER:
        goals[STEP_RECOMMEND] = "Primary: decide create vs escalate vs no_action."
    else:
        goals[STEP_INVESTIGATE] = "Primary: investigate recurring alarms and asset facts."

    if error_hint:
        for key in goals:
            goals[key] = f"{goals[key]} On prior tool error ({error_hint}): retry once, then degrade safely."

    primary_step = {
        INTENT_POLICY: STEP_POLICY,
        INTENT_WORKORDER: STEP_RECOMMEND,
        INTENT_ALARM: STEP_INVESTIGATE,
    }.get(intent, STEP_INVESTIGATE)

    steps: list[PlanStep] = []
    for step_name in (STEP_INVESTIGATE, STEP_POLICY, STEP_RECOMMEND):
        steps.append(
            PlanStep(
                step=step_name,
                agent=AGENT_FOR_STEP[step_name],
                goal=goals[step_name],
                primary=(step_name == primary_step),
            )
        )
    return steps


def replan_after_tool_error(
    intent: str,
    *,
    failed_tool: str | None = None,
    error: str | None = None,
) -> list[PlanStep]:
    """Rebuild plan after a retryable tool failure (Sprint 5 / 2.5.4)."""
    hint_parts = [p for p in (failed_tool, error) if p]
    hint = ": ".join(hint_parts) if hint_parts else "retryable tool error"
    return build_plan(intent, error_hint=hint)


def plan_to_jsonable(steps: list[PlanStep]) -> list[dict[str, Any]]:
    return [step.to_dict() for step in steps]

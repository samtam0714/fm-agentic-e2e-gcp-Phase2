"""PlannerAgent - emit a dynamic 3-step execution plan (Sprint 5)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from typing_extensions import override

from agents.common.events import make_agent_text_event
from agents.planner_agent.plan import build_plan, plan_to_jsonable
from agents.router_agent.agent import ROUTE_INTENT_KEY
from agents.router_agent.classify import INTENT_ALARM

EXECUTION_PLAN_KEY = "execution_plan"
PLAN_SUMMARY_KEY = "plan_summary"


class PlannerAgent(BaseAgent):
    """Read route_intent from session state and write a 3-step plan."""

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = getattr(ctx.session, "state", {}) or {}
        intent = str(state.get(ROUTE_INTENT_KEY) or INTENT_ALARM)
        steps = build_plan(intent)
        plan_dicts = plan_to_jsonable(steps)
        summary = " -> ".join(step.step for step in steps)
        text = (
            f"Plan for intent={intent}: {summary}.\n"
            f"plan_json={json.dumps(plan_dicts, ensure_ascii=False)}"
        )
        yield make_agent_text_event(
            ctx,
            author=self.name,
            text=text,
            state_delta={
                EXECUTION_PLAN_KEY: plan_dicts,
                PLAN_SUMMARY_KEY: summary,
            },
        )


def create_planner_agent() -> PlannerAgent:
    return PlannerAgent(
        name="planner_agent",
        description="Builds a 3-step plan (investigate -> policy -> recommend) from route intent.",
    )


root_agent = create_planner_agent()

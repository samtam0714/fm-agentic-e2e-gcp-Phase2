"""RouterAgent - select a Skill then expose its intent (Sprint 5 / 5.5)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from typing_extensions import override

from agents.common.events import make_agent_text_event, user_query_text
from agents.router_agent.classify import VALID_INTENTS
from skills.loader import match_skill

ROUTE_INTENT_KEY = "route_intent"
ROUTE_REASON_KEY = "route_reason"
ROUTE_SKILL_KEY = "route_skill"
ROUTE_SKILL_NAME_KEY = "route_skill_name"


class RouterAgent(BaseAgent):
    """Match query -> Skill Registry, write skill + intent into session state.

    Deterministic (no LLM) so routing is fast, testable, and does not add
    flaky latency to the V1 eval path.
    """

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        query = user_query_text(ctx)
        skill = match_skill(query)
        intent = skill.intent if skill.intent in VALID_INTENTS else "alarm"

        reason = (
            f"Matched skill={skill.id} ({skill.name}). "
            f"{skill.description.strip().splitlines()[0][:120]}"
        )
        payload = {
            "skill": skill.id,
            "skill_name": skill.name,
            "intent": intent,
            "allowed_tools": list(skill.allowed_tools),
            "reason": reason,
            "query_preview": query[:160],
        }
        text = (
            f"Routed skill={skill.id} intent={intent}. {reason}\n"
            f"route_json={json.dumps(payload, ensure_ascii=False)}"
        )
        yield make_agent_text_event(
            ctx,
            author=self.name,
            text=text,
            state_delta={
                ROUTE_INTENT_KEY: intent,
                ROUTE_REASON_KEY: reason,
                ROUTE_SKILL_KEY: skill.id,
                ROUTE_SKILL_NAME_KEY: skill.name,
            },
        )


def create_router_agent() -> RouterAgent:
    return RouterAgent(
        name="router_agent",
        description=(
            "Selects a FM AgentOps skill (alarm_investigation / policy_lookup / "
            "workorder_recommendation) and exposes its intent for the planner."
        ),
    )


root_agent = create_router_agent()

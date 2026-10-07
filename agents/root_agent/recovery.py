"""Recovery gate - exit LoopAgent or trigger one replan pass (Sprint 5 / 2.5.4)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from typing_extensions import override

from agents.common.events import make_agent_text_event
from agents.planner_agent.plan import plan_to_jsonable, replan_after_tool_error
from agents.planner_agent.agent import EXECUTION_PLAN_KEY, PLAN_SUMMARY_KEY
from agents.router_agent.agent import ROUTE_INTENT_KEY
from agents.router_agent.classify import INTENT_ALARM

RECOVERY_ATTEMPTED_KEY = "recovery_attempted"
LAST_TOOL_ERROR_KEY = "last_tool_error"


def _tool_error_from_response(response: Any) -> dict[str, Any] | None:
    if not isinstance(response, dict):
        return None
    if response.get("retryable") is True or response.get("error"):
        return {
            "error": response.get("error") or "error",
            "retryable": bool(response.get("retryable", False)),
            "message": response.get("message"),
        }
    return None


def find_latest_retryable_tool_error(ctx: InvocationContext) -> dict[str, Any] | None:
    """Scan session events newest-first for a retryable tool failure."""
    session = getattr(ctx, "session", None)
    events = list(getattr(session, "events", None) or [])
    for event in reversed(events):
        content = getattr(event, "content", None)
        if not content or not getattr(content, "parts", None):
            continue
        for part in content.parts:
            fn = getattr(part, "function_response", None)
            if not fn:
                continue
            err = _tool_error_from_response(getattr(fn, "response", None))
            if err and err.get("retryable"):
                return {
                    "tool": getattr(fn, "name", None),
                    **err,
                }
    return None


class RecoveryGateAgent(BaseAgent):
    """After specialists run: escalate to leave the loop, or replan once.

    Happy path -> escalate immediately (single pipeline pass).
    First retryable tool error -> rewrite execution_plan and allow one more loop.
    """

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = getattr(ctx.session, "state", {}) or {}
        already = bool(state.get(RECOVERY_ATTEMPTED_KEY))
        err = find_latest_retryable_tool_error(ctx)

        if err and not already:
            intent = str(state.get(ROUTE_INTENT_KEY) or INTENT_ALARM)
            steps = replan_after_tool_error(
                intent,
                failed_tool=err.get("tool"),
                error=str(err.get("error") or "retryable"),
            )
            plan_dicts = plan_to_jsonable(steps)
            summary = " -> ".join(step.step for step in steps)
            text = (
                "Recovery: detected retryable tool error; replanning once.\n"
                f"error_json={json.dumps(err, ensure_ascii=False)}\n"
                f"plan_json={json.dumps(plan_dicts, ensure_ascii=False)}"
            )
            yield make_agent_text_event(
                ctx,
                author=self.name,
                text=text,
                state_delta={
                    RECOVERY_ATTEMPTED_KEY: True,
                    LAST_TOOL_ERROR_KEY: err,
                    EXECUTION_PLAN_KEY: plan_dicts,
                    PLAN_SUMMARY_KEY: f"replan:{summary}",
                },
                escalate=False,
            )
            return

        status = "ok" if not err else "degraded_after_recovery"
        text = f"Recovery gate: {status}. Exiting execution loop."
        yield make_agent_text_event(
            ctx,
            author=self.name,
            text=text,
            state_delta={LAST_TOOL_ERROR_KEY: err},
            escalate=True,
        )


def create_recovery_gate_agent() -> RecoveryGateAgent:
    return RecoveryGateAgent(
        name="recovery_gate",
        description="Exits the execution loop or triggers one replan after retryable tool errors.",
    )

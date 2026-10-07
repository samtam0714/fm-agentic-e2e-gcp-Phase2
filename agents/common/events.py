"""Helpers for custom BaseAgent event emission."""

from __future__ import annotations

from typing import Any

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types


def user_query_text(ctx: InvocationContext) -> str:
    """Extract the latest user query text from the invocation context."""
    content = getattr(ctx, "user_content", None)
    if content is None or not getattr(content, "parts", None):
        return ""
    return "".join(part.text or "" for part in content.parts).strip()


def make_agent_text_event(
    ctx: InvocationContext,
    *,
    author: str,
    text: str,
    state_delta: dict[str, Any] | None = None,
    escalate: bool | None = None,
) -> Event:
    """Build a model text event, optionally writing session state / escalate."""
    actions_kwargs: dict[str, Any] = {}
    if state_delta:
        actions_kwargs["state_delta"] = state_delta
    if escalate is not None:
        actions_kwargs["escalate"] = escalate
    return Event(
        invocation_id=ctx.invocation_id,
        author=author,
        content=types.Content(
            role="model",
            parts=[types.Part(text=text)],
        ),
        actions=EventActions(**actions_kwargs),
        turn_complete=True,
    )

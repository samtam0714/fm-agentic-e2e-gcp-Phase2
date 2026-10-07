"""Remote WorkOrder agent over Mini A2A with local fallback (Sprint 7)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from typing_extensions import override

from agents.common.events import make_agent_text_event, user_query_text
from agents.workorder_agent.a2a_client import WorkOrderA2AClient
from agents.workorder_agent.a2a_protocol import (
    A2AClientError,
    extract_asset_id,
    parse_recommendation_payload,
    recommendation_text_from_tool,
)
from observability.tracing.trace_context import get_trace_context
from tools.registry import get_tool

OUTPUT_KEY = "work_order_recommendation"
A2A_META_KEY = "a2a_workorder_meta"


def a2a_workorder_enabled() -> bool:
    return os.getenv("USE_A2A_WORKORDER", "").strip().lower() in {"1", "true", "yes"}


def _state_metadata(state: dict[str, Any], query: str) -> dict[str, Any]:
    alarm = str(state.get("alarm_summary") or "")
    policy = str(state.get("policy_context") or "")
    asset_id = extract_asset_id(alarm, policy, query) or ""
    event_count = 0
    m = re.search(r"event_count\s*[=:]\s*(\d+)", alarm, re.IGNORECASE)
    if m:
        event_count = int(m.group(1))
    is_recurring = "recurring" in alarm.lower() or event_count >= 3
    alarm_priority = None
    if re.search(r"\bP1\b", alarm):
        alarm_priority = "P1"
    elif re.search(r"\bP2\b", alarm):
        alarm_priority = "P2"
    policy_ids = re.findall(r"HVAC-MNT-\d+", policy)
    return {
        "asset_id": asset_id,
        "event_count": event_count,
        "is_recurring": is_recurring,
        "alarm_priority": alarm_priority,
        "policy_ids": policy_ids or None,
        "alarm_summary": alarm,
        "policy_context": policy,
    }


def local_workorder_fallback(
    *,
    text: str,
    metadata: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Deterministic local fallback using the same recommend_work_order tool."""
    kwargs = parse_recommendation_payload(text, metadata)
    if not kwargs.get("asset_id"):
        text_out = (
            "A2A fallback: missing asset_id. Recommend monitoring / no_action."
        )
        return text_out, {"error": "missing_asset_id", "fallback": "local"}
    tool = get_tool("recommend_work_order")
    result = tool(**{k: v for k, v in kwargs.items() if v is not None})
    return recommendation_text_from_tool(result), {
        "fallback": "local",
        "tool_result": result,
    }


class RemoteWorkOrderA2AAgent(BaseAgent):
    """Call remote WorkOrder via A2A; retry once on timeout; fallback locally."""

    # Declared so ADK's pydantic BaseAgent allows the attribute.
    output_key: str = OUTPUT_KEY

    def __init__(
        self,
        *,
        client: WorkOrderA2AClient | None = None,
        name: str = "workorder_agent",
        max_attempts: int = 2,
    ) -> None:
        super().__init__(
            name=name,
            description=(
                "Remote WorkOrder agent over Mini A2A with timeout retry and "
                "local tool fallback."
            ),
        )
        object.__setattr__(self, "_client", client or WorkOrderA2AClient())
        object.__setattr__(self, "_max_attempts", max_attempts)

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = dict(getattr(ctx.session, "state", {}) or {})
        query = user_query_text(ctx)
        metadata = _state_metadata(state, query)
        trace_ctx = get_trace_context()
        trace_id = (
            str(state.get("trace_id") or "")
            or (trace_ctx.trace_id if trace_ctx else "")
            or ctx.invocation_id
        )
        text = (
            f"{query}\n"
            f"alarm_summary={metadata.get('alarm_summary')}\n"
            f"policy_context={metadata.get('policy_context')}"
        ).strip()

        last_error: dict[str, Any] | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.send_message(
                    text=text,
                    trace_id=trace_id,
                    metadata=metadata,
                )
                parts = response.task.artifacts[0].parts
                recommendation = " ".join(p.text for p in parts if p.text).strip()
                meta = {
                    "mode": "a2a_remote",
                    "attempt": attempt,
                    "remote_trace_id": response.trace_id,
                    "task_id": response.task.id,
                    "fallback": None,
                }
                yield make_agent_text_event(
                    ctx,
                    author=self.name,
                    text=recommendation,
                    state_delta={
                        OUTPUT_KEY: recommendation,
                        A2A_META_KEY: meta,
                        "trace_id": response.trace_id or trace_id,
                    },
                )
                return
            except A2AClientError as exc:
                last_error = {
                    "error": exc.error,
                    "retryable": exc.retryable,
                    "message": exc.message,
                    "attempt": attempt,
                }
                # Retry only timeout/unavailable once; invalid_response -> fallback now
                if exc.error == "invalid_response":
                    break
                if not exc.retryable or attempt >= self._max_attempts:
                    break
                continue

        fallback_text, fallback_meta = local_workorder_fallback(
            text=text, metadata=metadata
        )
        note = (
            f"[a2a_degraded fallback=local last_error="
            f"{json.dumps(last_error, ensure_ascii=False)}] "
            f"{fallback_text}"
        )
        yield make_agent_text_event(
            ctx,
            author=self.name,
            text=note,
            state_delta={
                OUTPUT_KEY: note,
                A2A_META_KEY: {
                    "mode": "a2a_fallback_local",
                    "last_error": last_error,
                    **fallback_meta,
                },
                "trace_id": trace_id,
            },
        )


def create_remote_workorder_agent(
    client: WorkOrderA2AClient | None = None,
) -> RemoteWorkOrderA2AAgent:
    return RemoteWorkOrderA2AAgent(client=client)

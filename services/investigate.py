"""Shared investigate pipeline for API, CLI, and eval harness."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.root_agent.agent import create_root_agent
from eval_harness.trace_collector import AgentTrace, collect_trace_from_events
from memory.session_store import capture_session_memory
from observability.logging import get_logger
from observability.tracing import TraceContext, new_trace_id, record_trace_from_events
from observability.tracing.trace_context import clear_trace_context, set_trace_context

_log = get_logger(__name__)


@dataclass
class InvestigationResult:
    query: str
    trace_id: str = ""
    session_id: str = ""
    latency_seconds: float = 0.0
    agents: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    tool_args: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    combined_text: str = ""
    texts_by_agent: dict[str, list[str]] = field(default_factory=dict)
    tool_results: dict[str, Any] = field(default_factory=dict)
    session_snapshot: dict[str, Any] = field(default_factory=dict)
    trace_path: str = ""
    session_path: str = ""

    def to_agent_trace(self) -> AgentTrace:
        trace = AgentTrace()
        trace.agents = list(self.agents)
        trace.tools = list(self.tools)
        trace.tool_args = {k: list(v) for k, v in self.tool_args.items()}
        trace.combined_text = self.combined_text
        trace.texts_by_agent = dict(self.texts_by_agent)
        trace.tool_results = dict(self.tool_results)
        trace.latency_seconds = self.latency_seconds
        trace.trace_id = self.trace_id
        trace.trace_path = self.trace_path
        trace.session_snapshot = dict(self.session_snapshot)
        trace.session_path = self.session_path
        return trace


async def run_investigation(
    query: str,
    *,
    app_name: str = "fm-investigate",
    user_id: str = "api-user",
    trace_id: str | None = None,
    persist_session: bool = True,
) -> InvestigationResult:
    """Run the root agent pipeline and collect trace + session memory."""
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=app_name,
        agent=create_root_agent(),
        session_service=session_service,
        auto_create_session=True,
    )

    session = await session_service.create_session(app_name=app_name, user_id=user_id)
    content = types.Content(role="user", parts=[types.Part(text=query)])

    ctx = TraceContext(
        trace_id=trace_id or new_trace_id(),
        session_id=session.id,
        app_name=app_name,
        user_query=query,
    )
    set_trace_context(ctx)
    _log.info(
        "investigation.started",
        query=query[:120],
        user_id=user_id,
    )

    events: list[Any] = []
    start = time.perf_counter()
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
        ):
            events.append(event)

        latency = time.perf_counter() - start
        agent_trace = collect_trace_from_events(events)

        written_trace_id, trace_path = record_trace_from_events(
            events,
            context=ctx,
            user_query=query,
            latency_seconds=latency,
        )

        snapshot, session_path = await capture_session_memory(
            session_service,
            app_name=app_name,
            user_id=user_id,
            session_id=session.id,
            trace_id=written_trace_id,
            persist=persist_session,
        )

        _log.info(
            "investigation.completed",
            latency_seconds=round(latency, 3),
            agents=agent_trace.agents,
            tools=agent_trace.tools,
            trace_path=str(trace_path),
        )

        return InvestigationResult(
            query=query,
            trace_id=written_trace_id,
            session_id=session.id,
            latency_seconds=latency,
            agents=agent_trace.agents,
            tools=agent_trace.tools,
            tool_args=agent_trace.tool_args,
            combined_text=agent_trace.combined_text,
            texts_by_agent=dict(agent_trace.texts_by_agent),
            tool_results=agent_trace.tool_results,
            session_snapshot=snapshot,
            trace_path=str(trace_path),
            session_path=str(session_path) if session_path else "",
        )
    except Exception:
        _log.error("investigation.failed", exc_info=True)
        raise
    finally:
        clear_trace_context()

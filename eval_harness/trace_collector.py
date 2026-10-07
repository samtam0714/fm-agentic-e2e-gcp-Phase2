"""Extract structured trace data from ADK runner events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentTrace:
    agents: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    # tool_name -> list of arg dicts (one entry per call; a tool may be called >1 time)
    tool_args: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    texts_by_agent: dict[str, list[str]] = field(default_factory=dict)
    tool_results: dict[str, Any] = field(default_factory=dict)
    combined_text: str = ""
    latency_seconds: float = 0.0
    trace_id: str = ""
    trace_path: str = ""
    session_snapshot: dict = field(default_factory=dict)
    session_path: str = ""

    def record_event(self, event: Any) -> None:
        author = getattr(event, "author", None) or "unknown"
        if author not in self.agents:
            self.agents.append(author)

        content = getattr(event, "content", None)
        if not content or not getattr(content, "parts", None):
            return

        for part in content.parts:
            if part.text:
                self.texts_by_agent.setdefault(author, []).append(part.text)
            if part.function_call and part.function_call.name:
                name = part.function_call.name
                if name not in self.tools:
                    self.tools.append(name)
                args = part.function_call.args
                self.tool_args.setdefault(name, []).append(
                    dict(args) if args else {}
                )
            if part.function_response and part.function_response.name:
                name = part.function_response.name
                response = part.function_response.response
                if isinstance(response, dict):
                    self.tool_results[name] = response
                else:
                    self.tool_results[name] = {"raw": response}

        self.combined_text = "\n".join(
            text for texts in self.texts_by_agent.values() for text in texts
        )

    def final_agent_text(self, agent_name: str) -> str:
        return "\n".join(self.texts_by_agent.get(agent_name, []))


def collect_trace_from_events(events: list[Any]) -> AgentTrace:
    trace = AgentTrace()
    for event in events:
        trace.record_event(event)
    return trace

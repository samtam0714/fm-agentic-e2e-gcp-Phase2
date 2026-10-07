"""Trace span schema for JSONL export."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TraceSpan(BaseModel):
    trace_id: str
    agent: str
    step: str
    input_summary: str = ""
    output_summary: str = ""
    latency_ms: float = 0.0
    tokens_input: int | None = None
    tokens_output: int | None = None
    tool_calls: list[str] = Field(default_factory=list)
    status: Literal["success", "error"] = "success"
    timestamp: float | None = None
    span_type: Literal["request", "agent_turn", "tool_call", "tool_result"] = "agent_turn"
    # Preserve fields separately because summaries truncate the load_skill payload.
    skill_name: str | None = None
    skill_version: str | None = None
    skill_load_result: Literal["loaded", "error"] | None = None

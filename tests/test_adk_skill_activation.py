"""ADK Agent Skills activation tests (Sprint 5.5 / 2.5.9).

Verify real activation: load_skill -> activated state -> business tools.
Covers all three specialist skills without calling Vertex.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from observability.tracing.span_recorder import events_to_spans
from tools.registry import get_tools_for_agent

SKILL_META_TOOLS = {
    "list_skills",
    "load_skill",
    "load_skill_resource",
    "run_skill_script",
}

# agent -> (skill name, business tools that appear after activation)
AGENT_SKILLS: dict[str, tuple[str, set[str]]] = {
    "alarm_agent": ("alarm-investigation", {"search_alarm_history", "search_similar_cases"}),
    "kb_agent": ("policy-lookup", {"search_policy_doc"}),
    "workorder_agent": ("workorder-recommendation", {"recommend_work_order"}),
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("USE_ADK_SKILLS", raising=False)
    monkeypatch.delenv("USE_MCP_TOOLS", raising=False)


class FakeToolContext:
    def __init__(self, agent_name: str = "alarm_agent") -> None:
        self.agent_name = agent_name
        self.invocation_id = "inv_test"
        self.state: dict = {}


class FakeReadonlyContext:
    def __init__(self, ctx: FakeToolContext) -> None:
        self.agent_name = ctx.agent_name
        self.invocation_id = ctx.invocation_id
        self.state = ctx.state


def _skill_toolset(agent_name: str):
    tools = get_tools_for_agent(agent_name)
    assert len(tools) == 1, f"{agent_name}: only SkillToolset should be top-level"
    assert type(tools[0]).__name__ == "SkillToolset"
    return tools[0]


def _tool_names(toolset: Any, ctx: FakeToolContext | None) -> set[str]:
    readonly = FakeReadonlyContext(ctx) if ctx else None
    return {t.name for t in asyncio.run(toolset.get_tools(readonly))}


def _load_skill_tool(toolset: Any) -> Any:
    return next(t for t in asyncio.run(toolset.get_tools(None)) if t.name == "load_skill")


def _run_load_skill(toolset: Any, ctx: FakeToolContext, skill_name: str) -> dict:
    return asyncio.run(
        _load_skill_tool(toolset).run_async(
            args={"skill_name": skill_name}, tool_context=ctx
        )
    )


def test_flag_off_returns_legacy_direct_tools():
    assert [getattr(t, "__name__", type(t).__name__) for t in get_tools_for_agent("alarm_agent")] == [
        "search_alarm_history",
        "search_similar_cases",
    ]
    assert [t.__name__ for t in get_tools_for_agent("kb_agent")] == ["search_policy_doc"]
    assert [t.__name__ for t in get_tools_for_agent("workorder_agent")] == [
        "recommend_work_order"
    ]
    assert [t.__name__ for t in get_tools_for_agent("auditor_agent")] == [
        "audit_recommendation"
    ]


def test_flag_on_leaves_auditor_without_skill(monkeypatch):
    monkeypatch.setenv("USE_ADK_SKILLS", "1")
    tools = get_tools_for_agent("auditor_agent")
    assert [t.__name__ for t in tools] == ["audit_recommendation"]
    assert "SkillToolset" not in [type(t).__name__ for t in tools]


@pytest.mark.parametrize("agent_name", list(AGENT_SKILLS))
def test_flag_on_exposes_only_skill_toolset(agent_name: str, monkeypatch):
    monkeypatch.setenv("USE_ADK_SKILLS", "1")
    _skill_toolset(agent_name)


@pytest.mark.parametrize("agent_name,skill_and_tools", list(AGENT_SKILLS.items()))
def test_business_tools_hidden_before_activation(
    agent_name: str, skill_and_tools: tuple[str, set[str]], monkeypatch
):
    skill_name, business = skill_and_tools
    monkeypatch.setenv("USE_ADK_SKILLS", "1")
    toolset = _skill_toolset(agent_name)
    ctx = FakeToolContext(agent_name)

    names = _tool_names(toolset, ctx)
    assert names == SKILL_META_TOOLS
    assert not (names & business), f"{skill_name}: business tools exposed before activation"


@pytest.mark.parametrize("agent_name,skill_and_tools", list(AGENT_SKILLS.items()))
def test_load_skill_returns_skill_md_instructions(
    agent_name: str, skill_and_tools: tuple[str, set[str]], monkeypatch
):
    skill_name, _ = skill_and_tools
    monkeypatch.setenv("USE_ADK_SKILLS", "1")
    toolset = _skill_toolset(agent_name)
    ctx = FakeToolContext(agent_name)

    result = _run_load_skill(toolset, ctx, skill_name)

    on_disk = (
        Path(__file__).resolve().parents[1] / "skills" / skill_name / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert result["skill_name"] == skill_name
    assert result["instructions"].strip()
    assert result["instructions"].strip() in on_disk
    assert result["frontmatter"]["metadata"]["version"] == "1.0.0"


@pytest.mark.parametrize("agent_name,skill_and_tools", list(AGENT_SKILLS.items()))
def test_load_skill_records_activation_state(
    agent_name: str, skill_and_tools: tuple[str, set[str]], monkeypatch
):
    skill_name, _ = skill_and_tools
    monkeypatch.setenv("USE_ADK_SKILLS", "1")
    toolset = _skill_toolset(agent_name)
    ctx = FakeToolContext(agent_name)

    _run_load_skill(toolset, ctx, skill_name)

    assert ctx.state[f"_adk_activated_skill_{agent_name}"] == [skill_name]


@pytest.mark.parametrize("agent_name,skill_and_tools", list(AGENT_SKILLS.items()))
def test_business_tools_appear_only_after_activation(
    agent_name: str, skill_and_tools: tuple[str, set[str]], monkeypatch
):
    skill_name, business = skill_and_tools
    monkeypatch.setenv("USE_ADK_SKILLS", "1")
    toolset = _skill_toolset(agent_name)
    ctx = FakeToolContext(agent_name)

    before = _tool_names(toolset, ctx)
    _run_load_skill(toolset, ctx, skill_name)
    after = _tool_names(toolset, ctx)

    assert not (before & business)
    assert business <= after
    # Activation must not expose tools from other skills.
    all_business = set().union(*(t for _, t in AGENT_SKILLS.values()))
    assert not (after & (all_business - business))


def test_activation_respects_mcp_switch(monkeypatch):
    monkeypatch.setenv("USE_ADK_SKILLS", "1")
    monkeypatch.setenv("USE_MCP_TOOLS", "1")
    toolset = _skill_toolset("alarm_agent")
    ctx = FakeToolContext("alarm_agent")

    _run_load_skill(toolset, ctx, "alarm-investigation")
    assert {"search_alarm_history", "search_similar_cases"} <= _tool_names(toolset, ctx)


@dataclass
class FakeFunctionCall:
    name: str
    args: dict


@dataclass
class FakeFunctionResponse:
    name: str
    response: dict


@dataclass
class FakePart:
    text: str | None = None
    function_call: object | None = None
    function_response: object | None = None


@dataclass
class FakeContent:
    parts: list = field(default_factory=list)


@dataclass
class FakeEvent:
    author: str
    content: FakeContent | None = None
    timestamp: float = 0.0


def test_trace_captures_skill_name_version_and_result():
    skill_name = "policy-lookup"
    events = [
        FakeEvent(
            author="kb_agent",
            timestamp=1.0,
            content=FakeContent(
                parts=[
                    FakePart(
                        function_call=FakeFunctionCall(
                            name="load_skill", args={"skill_name": skill_name}
                        )
                    )
                ]
            ),
        ),
        FakeEvent(
            author="kb_agent",
            timestamp=1.2,
            content=FakeContent(
                parts=[
                    FakePart(
                        function_response=FakeFunctionResponse(
                            name="load_skill",
                            response={
                                "skill_name": skill_name,
                                "instructions": "# Policy Lookup\n" + "x" * 5000,
                                "frontmatter": {"metadata": {"version": "1.0.0"}},
                            },
                        )
                    )
                ]
            ),
        ),
    ]

    spans = events_to_spans(events, trace_id="tr_skill", user_query="what policy?")
    call_span = next(s for s in spans if s.span_type == "tool_call")
    result_span = next(s for s in spans if s.span_type == "tool_result")

    assert call_span.skill_name == skill_name
    assert result_span.skill_name == skill_name
    assert result_span.skill_version == "1.0.0"
    assert result_span.skill_load_result == "loaded"


def test_trace_marks_failed_skill_load():
    events = [
        FakeEvent(
            author="alarm_agent",
            timestamp=1.0,
            content=FakeContent(
                parts=[
                    FakePart(
                        function_response=FakeFunctionResponse(
                            name="load_skill",
                            response={
                                "error": "Skill 'nope' not found.",
                                "error_code": "SKILL_NOT_FOUND",
                            },
                        )
                    )
                ]
            ),
        )
    ]

    span = next(
        s for s in events_to_spans(events, trace_id="tr_skill_err") if s.span_type == "tool_result"
    )
    assert span.skill_load_result == "error"


import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agents.alarm_agent.tools import search_alarm_history
from agents.auditor_agent.tools import audit_recommendation
from agents.kb_agent.tools import search_policy_doc
from agents.workorder_agent.tools import recommend_work_order
from memory.tools import search_similar_cases
from tools.retryable import with_retryable_retry

ToolFn = Callable[..., dict]

# Bare in-process tools. Retry wrapping is applied in get_tool() so fault_injection
# can patch the bare entry and still be absorbed by one transparent retry.
_REGISTRY: dict[str, ToolFn] = {
    "search_alarm_history": search_alarm_history,
    "search_similar_cases": search_similar_cases,
    "search_policy_doc": search_policy_doc,
    "recommend_work_order": recommend_work_order,
    "audit_recommendation": audit_recommendation,
}

_AGENT_TOOL_NAMES: dict[str, list[str]] = {
    "alarm_agent": ["search_alarm_history", "search_similar_cases"],
    "kb_agent": ["search_policy_doc"],
    "workorder_agent": ["recommend_work_order"],
    "auditor_agent": ["audit_recommendation"],
}

# Phase 2 Sprint 5.5: agent -> ADK skill directory (kebab-case SKILL.md name).
# Used only with USE_ADK_SKILLS; the auditor exposes tools directly.
_AGENT_SKILLS: dict[str, str] = {
    "alarm_agent": "alarm-investigation",
    "kb_agent": "policy-lookup",
    "workorder_agent": "workorder-recommendation",
}

# Phase 2 Sprint 3: tools migrated to standalone MCP server processes.
# Used only with USE_MCP_TOOLS; remaining tools stay in-process.
_MCP_SERVERS: dict[str, dict[str, Any]] = {
    "alarm_agent": {
        "module": "mcp_servers.alarm.server",
        "tools": ["search_alarm_history"],
        # search_similar_cases remains in-process because it uses local memory.
    },
    "kb_agent": {
        "module": "mcp_servers.policy.server",
        "tools": ["search_policy_doc"],
    },
    "workorder_agent": {
        "module": "mcp_servers.ticket.server",
        "tools": ["recommend_work_order"],
    },
}


def _mcp_enabled() -> bool:
    """Use MCP when USE_MCP_TOOLS is 1/true/yes; otherwise use in-process tools."""
    return os.getenv("USE_MCP_TOOLS", "").strip().lower() in {"1", "true", "yes"}


def _adk_skills_enabled() -> bool:
    """Provide business tools through SkillToolset when USE_ADK_SKILLS is enabled."""
    return os.getenv("USE_ADK_SKILLS", "").strip().lower() in {"1", "true", "yes"}


def _build_mcp_toolset(module: str, tool_names: list[str]) -> Any:
    """Wrap an MCP server module as an ADK McpToolset stdio subprocess.

    ADK launches `sys.executable -m <module>` and communicates over stdin/stdout.
    tool_filter limits exposure to declared tools. Imports are deferred so the
    default path does not load heavy ADK/MCP dependencies.
    """
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
    from mcp import StdioServerParameters

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", module],
            ),
        ),
        tool_filter=list(tool_names),
    )


def _build_skill_toolset(skill_id: str, business_tools: list[Any]) -> Any:
    """Wrap an ADK skill as a SkillToolset.

    Business tools are supplied only through the additional_tools pool. The model
    must load the skill before ADK resolves metadata.adk_additional_tools. This
    prevents duplicate top-level tools. Imports are deferred on the default path.
    """
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools.skill_toolset import SkillToolset

    skill_dir = Path(__file__).resolve().parent.parent / "skills" / skill_id
    return SkillToolset(
        skills=[load_skill_from_dir(skill_dir)],
        additional_tools=business_tools,
    )


def get_tool(name: str) -> ToolFn:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown tool: {name}")
    # Sprint 5: Always apply retryable automatic retries.
    return with_retryable_retry(_REGISTRY[name])


def get_tools(names: list[str]) -> list[ToolFn]:
    return [get_tool(name) for name in names]


def _business_tools_for_agent(agent_name: str) -> list[Any]:
    """Return business tools for an agent, respecting USE_MCP_TOOLS."""
    tool_names = _AGENT_TOOL_NAMES[agent_name]
    if _mcp_enabled() and agent_name in _MCP_SERVERS:
        spec = _MCP_SERVERS[agent_name]
        mcp_tool_names = set(spec["tools"])
        remaining = [n for n in tool_names if n not in mcp_tool_names]
        tools: list[Any] = get_tools(remaining)
        tools.append(_build_mcp_toolset(spec["module"], spec["tools"]))
        return tools

    return get_tools(tool_names)


def get_tools_for_agent(agent_name: str) -> list[Any]:
    """Return tools for an agent.

    With both switches off, all tools are in-process. USE_MCP_TOOLS replaces
    migrated tools with McpToolset while retaining unmigrated functions.
    USE_ADK_SKILLS exposes only SkillToolset at the top level and activates
    business tools dynamically after load_skill, avoiding duplicate names.
    """
    if agent_name not in _AGENT_TOOL_NAMES:
        raise KeyError(f"Unknown agent: {agent_name}")

    business_tools = _business_tools_for_agent(agent_name)
    if _adk_skills_enabled() and agent_name in _AGENT_SKILLS:
        return [_build_skill_toolset(_AGENT_SKILLS[agent_name], business_tools)]

    return business_tools


def list_tools() -> list[str]:
    return list(_REGISTRY.keys())
"""Registry behavior controlled by the USE_MCP_TOOLS switch."""

from __future__ import annotations

import pytest

from tools.registry import get_tools_for_agent


@pytest.fixture(autouse=True)
def _clear_mcp_env(monkeypatch):
    """Clear switches before each test to prevent environment leakage."""
    monkeypatch.delenv("USE_MCP_TOOLS", raising=False)


def test_registry_default_returns_inprocess_function():
    tools = get_tools_for_agent("kb_agent")
    assert len(tools) == 1
    assert tools[0].__name__ == "search_policy_doc"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_registry_mcp_enabled_returns_mcp_toolset(monkeypatch, value):
    monkeypatch.setenv("USE_MCP_TOOLS", value)
    tools = get_tools_for_agent("kb_agent")
    assert len(tools) == 1
    assert type(tools[0]).__name__ == "McpToolset"


def test_registry_alarm_mixes_mcp_and_inprocess(monkeypatch):
    """Alarm history uses MCP while similar-case search remains in-process."""
    monkeypatch.setenv("USE_MCP_TOOLS", "1")
    tools = get_tools_for_agent("alarm_agent")
    types = [type(t).__name__ for t in tools]
    names = [getattr(t, "__name__", type(t).__name__) for t in tools]
    assert "McpToolset" in types
    assert "search_similar_cases" in names
    assert len(tools) == 2


def test_registry_workorder_uses_mcp_toolset(monkeypatch):
    monkeypatch.setenv("USE_MCP_TOOLS", "1")
    tools = get_tools_for_agent("workorder_agent")
    assert len(tools) == 1
    assert type(tools[0]).__name__ == "McpToolset"


def test_registry_auditor_stays_inprocess_even_with_mcp(monkeypatch):
    """The unmigrated auditor remains in-process when MCP is enabled."""
    monkeypatch.setenv("USE_MCP_TOOLS", "1")
    tools = get_tools_for_agent("auditor_agent")
    assert len(tools) == 1
    assert tools[0].__name__ == "audit_recommendation"

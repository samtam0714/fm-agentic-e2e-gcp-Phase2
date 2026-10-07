"""Alarm MCP server contract tests (Sprint 3 / 2.3.1 + 2.3.5)."""

from __future__ import annotations

from mcp import ClientSession

from tests.mcp_contract.helpers import (
    parse_tool_json,
    run_async,
    with_alarm_session,
)


def test_alarm_tools_list_schema():
    """The server exposes search_alarm_history with optional query arguments."""

    async def _check(session: ClientSession) -> None:
        listed = await session.list_tools()
        tools = {t.name: t for t in listed.tools}
        assert "search_alarm_history" in tools

        schema = tools["search_alarm_history"].inputSchema or {}
        props = schema.get("properties", {})
        required = schema.get("required") or []

        for key in ("floor", "asset_id", "building", "time_range_days"):
            assert key in props
        # The schema must not require any optional argument.
        assert "asset_id" not in required

    run_async(with_alarm_session(_check))


def test_alarm_valid_asset_id_returns_issues():
    """A valid asset_id returns structured issues."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "search_alarm_history",
            {"asset_id": "AHU-3F-01"},
        )
        assert result.isError is False
        data = parse_tool_json(result)
        assert "match_count" in data or "issues" in data
        issues = data.get("issues", [])
        assert isinstance(issues, list)
        assert len(issues) >= 1
        assert any(i.get("asset_id") == "AHU-3F-01" for i in issues)

    run_async(with_alarm_session(_check))


def test_alarm_invalid_asset_id_returns_structured_empty():
    """An invalid asset_id returns a structured empty result without crashing."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "search_alarm_history",
            {"asset_id": "AHU-DOES-NOT-EXIST"},
        )
        assert result.isError is False
        data = parse_tool_json(result)
        issues = data.get("issues", [])
        assert issues == [] or data.get("match_count", 0) == 0

    run_async(with_alarm_session(_check))

"""Policy MCP server contract tests (Sprint 3 / 2.3.5).

Covers the contract required by plan_phase2.md:
- tools/list schema: query required, asset_type optional
- valid request -> structured response (match_count / policies)
- empty query -> structured empty result without crashing
- missing required argument -> clean isError response without process failure
"""

from __future__ import annotations

from mcp import ClientSession

from tests.mcp_contract.helpers import (
    parse_tool_json,
    run_async,
    tool_error_text,
    with_policy_session,
)


def test_policy_tools_list_schema():
    """The server exposes search_policy_doc with required query and optional asset_type."""

    async def _check(session: ClientSession) -> None:
        listed = await session.list_tools()
        tools = {t.name: t for t in listed.tools}
        assert "search_policy_doc" in tools

        schema = tools["search_policy_doc"].inputSchema or {}
        props = schema.get("properties", {})
        required = schema.get("required", [])

        assert "query" in props
        assert "asset_type" in props
        assert "query" in required
        assert "asset_type" not in required

    run_async(with_policy_session(_check))


def test_policy_valid_request_returns_structured_policies():
    """A valid request returns structured JSON with match_count and policies."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "search_policy_doc",
            {"query": "recurring filter", "asset_type": "AHU"},
        )
        assert result.isError is False
        data = parse_tool_json(result)

        assert "match_count" in data
        assert "policies" in data
        assert "query" in data
        assert data["match_count"] >= 1
        assert isinstance(data["policies"], list)
        assert all("policy_id" in p for p in data["policies"])

    run_async(with_policy_session(_check))


def test_policy_empty_query_returns_structured_empty():
    """An empty query returns no matches without crashing."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool("search_policy_doc", {"query": ""})
        assert result.isError is False
        data = parse_tool_json(result)
        assert data["match_count"] == 0
        assert data["policies"] == []

    run_async(with_policy_session(_check))


def test_policy_missing_required_query_returns_clean_error():
    """A missing query returns isError and leaves the process available."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool("search_policy_doc", {})
        assert result.isError is True
        text = tool_error_text(result).lower()
        assert "query" in text
        assert "required" in text or "missing" in text or "field required" in text

        # The process still accepts valid requests after the error.
        ok = await session.call_tool(
            "search_policy_doc",
            {"query": "HVAC-MNT-003", "asset_type": "AHU"},
        )
        assert ok.isError is False
        data = parse_tool_json(ok)
        assert data["match_count"] >= 1

    run_async(with_policy_session(_check))

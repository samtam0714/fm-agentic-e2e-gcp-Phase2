"""Ticket MCP server contract tests (Sprint 3 / 2.3.3 + 2.3.5)."""

from __future__ import annotations

from mcp import ClientSession

from tests.mcp_contract.helpers import (
    parse_tool_json,
    run_async,
    tool_error_text,
    with_ticket_session,
)


def test_ticket_tools_list_schema():
    """The server exposes recommend_work_order with required asset_id."""

    async def _check(session: ClientSession) -> None:
        listed = await session.list_tools()
        tools = {t.name: t for t in listed.tools}
        assert "recommend_work_order" in tools

        schema = tools["recommend_work_order"].inputSchema or {}
        props = schema.get("properties", {})
        required = schema.get("required", [])

        assert "asset_id" in props
        assert "asset_id" in required
        assert "event_count" in props

    run_async(with_ticket_session(_check))


def test_ticket_valid_request_returns_recommendation():
    """A valid AHU-3F-01 request returns a recommendation with an action."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "recommend_work_order",
            {
                "asset_id": "AHU-3F-01",
                "event_count": 7,
                "is_recurring": True,
                "policy_ids": ["HVAC-MNT-003"],
                "likely_cause": "clogged filter",
            },
        )
        assert result.isError is False
        data = parse_tool_json(result)
        rec = data.get("recommendation")
        assert isinstance(rec, dict)
        assert "action" in rec
        assert rec["action"] in {
            "escalate_existing",
            "use_existing",
            "create_new",
            "no_action",
        }

    run_async(with_ticket_session(_check))


def test_ticket_empty_asset_id_returns_structured_error():
    """An empty asset_id returns a structured error without crashing."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "recommend_work_order",
            {"asset_id": ""},
        )
        assert result.isError is False
        data = parse_tool_json(result)
        assert data.get("error")
        assert data.get("recommendation") is None

    run_async(with_ticket_session(_check))


def test_ticket_missing_required_asset_id_returns_clean_error():
    """A missing asset_id sets isError and leaves the process available."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool("recommend_work_order", {})
        assert result.isError is True
        text = tool_error_text(result).lower()
        assert "asset_id" in text
        assert "required" in text or "missing" in text or "field required" in text

        ok = await session.call_tool(
            "recommend_work_order",
            {"asset_id": "AHU-3F-01", "event_count": 7, "is_recurring": True},
        )
        assert ok.isError is False
        data = parse_tool_json(ok)
        assert data.get("recommendation") is not None

    run_async(with_ticket_session(_check))

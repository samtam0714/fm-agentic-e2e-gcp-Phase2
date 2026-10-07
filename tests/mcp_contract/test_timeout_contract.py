"""MCP timeout -> retryable error contract (plan_phase2.md Sprint 3)."""

from __future__ import annotations

import time

from mcp import ClientSession

from mcp_servers.common.timeout import run_with_timeout, timeout_error_payload
from tests.mcp_contract.helpers import (
    parse_tool_json,
    run_async,
    with_alarm_session,
    with_policy_session,
    with_ticket_session,
)


def test_timeout_error_payload_is_retryable():
    payload = timeout_error_payload(timeout_seconds=0.1, tool="search_policy_doc")
    assert payload["error"] == "timeout"
    assert payload["retryable"] is True
    assert payload["tool"] == "search_policy_doc"


def test_run_with_timeout_returns_retryable_on_slow_fn():
    def _slow() -> dict:
        time.sleep(0.5)
        return {"ok": True}

    result = run_with_timeout(_slow, tool_name="demo", timeout_seconds=0.05)
    assert isinstance(result, dict)
    assert result["error"] == "timeout"
    assert result["retryable"] is True
    assert result["tool"] == "demo"


def test_policy_timeout_via_force_env_returns_retryable():
    """MCP_FORCE_TIMEOUT produces a structured retryable response without crashing."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "search_policy_doc",
            {"query": "recurring filter", "asset_type": "AHU"},
        )
        assert result.isError is False
        data = parse_tool_json(result)
        assert data.get("error") == "timeout"
        assert data.get("retryable") is True
        assert data.get("tool") == "search_policy_doc"

        # The process remains alive and can still list tools.
        listed = await session.list_tools()
        assert any(t.name == "search_policy_doc" for t in listed.tools)

    run_async(
        with_policy_session(
            _check,
            extra_env={"MCP_FORCE_TIMEOUT": "1"},
        )
    )


def test_alarm_timeout_via_slow_simulate_returns_retryable():
    """A slow tool with a short timeout produces a retryable wall-clock timeout."""

    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "search_alarm_history",
            {"asset_id": "AHU-3F-01"},
        )
        assert result.isError is False
        data = parse_tool_json(result)
        assert data.get("error") == "timeout"
        assert data.get("retryable") is True
        assert data.get("tool") == "search_alarm_history"

    run_async(
        with_alarm_session(
            _check,
            extra_env={
                "MCP_SIMULATE_SLOW_SECONDS": "1",
                "MCP_TOOL_TIMEOUT_SECONDS": "0.1",
                "MCP_FORCE_TIMEOUT": "0",
            },
        )
    )


def test_ticket_timeout_via_force_env_returns_retryable():
    async def _check(session: ClientSession) -> None:
        result = await session.call_tool(
            "recommend_work_order",
            {"asset_id": "AHU-3F-01", "event_count": 7, "is_recurring": True},
        )
        assert result.isError is False
        data = parse_tool_json(result)
        assert data.get("error") == "timeout"
        assert data.get("retryable") is True

    run_async(
        with_ticket_session(
            _check,
            extra_env={"MCP_FORCE_TIMEOUT": "1"},
        )
    )

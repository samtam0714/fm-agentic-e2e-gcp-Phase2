"""Shared helpers for MCP contract tests (stdio client ↔ server)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

T = TypeVar("T")

POLICY_MODULE = "mcp_servers.policy.server"
ALARM_MODULE = "mcp_servers.alarm.server"
TICKET_MODULE = "mcp_servers.ticket.server"


def run_async(coro: Awaitable[T]) -> T:
    """Run an async coroutine from a sync pytest test."""
    return asyncio.run(coro)


async def with_mcp_session(
    module: str,
    fn: Callable[[ClientSession], Awaitable[T]],
    *,
    extra_env: dict[str, str] | None = None,
) -> T:
    """Start an MCP server module as stdio subprocess, run fn(session), then tear down.

    Starts a temporary server process, sends requests, and shuts it down.
    extra_env is injected into the subprocess, for example MCP_FORCE_TIMEOUT=1.
    """
    env = {**os.environ, **(extra_env or {})}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


async def with_policy_session(
    fn: Callable[[ClientSession], Awaitable[T]],
    *,
    extra_env: dict[str, str] | None = None,
) -> T:
    return await with_mcp_session(POLICY_MODULE, fn, extra_env=extra_env)


async def with_alarm_session(
    fn: Callable[[ClientSession], Awaitable[T]],
    *,
    extra_env: dict[str, str] | None = None,
) -> T:
    return await with_mcp_session(ALARM_MODULE, fn, extra_env=extra_env)


async def with_ticket_session(
    fn: Callable[[ClientSession], Awaitable[T]],
    *,
    extra_env: dict[str, str] | None = None,
) -> T:
    return await with_mcp_session(TICKET_MODULE, fn, extra_env=extra_env)


def parse_tool_json(result: Any) -> dict[str, Any]:
    """Parse the first text content block of a CallToolResult as JSON."""
    assert result.content, "tool result has no content"
    text = result.content[0].text
    return json.loads(text)


def tool_error_text(result: Any) -> str:
    """Extract human-readable error text from a failed CallToolResult."""
    assert result.isError, "expected isError=True"
    assert result.content, "error result has no content"
    return result.content[0].text

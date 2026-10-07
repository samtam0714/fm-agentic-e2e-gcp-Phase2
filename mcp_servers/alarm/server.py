"""Alarm MCP server exposing search_alarm_history as a standalone stdio process.

It reuses agents/alarm_agent/tools.py, including freshness rebasing.
ADK and contract tests launch it with `python -m mcp_servers.alarm.server`.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agents.alarm_agent.tools import search_alarm_history as _search_alarm_history
from mcp_servers.common.timeout import run_with_timeout

mcp = FastMCP("fm-alarm")


@mcp.tool()
def search_alarm_history(
    floor: int | None = None,
    asset_id: str | None = None,
    building: str | None = None,
    time_range_days: int = 30,
) -> dict:
    """Search aggregated alarm issues and related events.

    Use this to investigate recurring building alarms. Query by floor,
    asset_id, or building/site name. Returns issues with event details.

    Args:
        floor: Optional floor number filter (e.g. 3).
        asset_id: Optional exact asset id (e.g. "AHU-3F-01", "VAV-3F-12").
        building: Optional building/site/customer text (e.g. "Toronto").
        time_range_days: Lookback window in days (default 30).

    Returns:
        dict with query echo, match_count, and issues list.
    """
    return run_with_timeout(
        _search_alarm_history,
        floor=floor,
        asset_id=asset_id,
        building=building,
        time_range_days=time_range_days,
        tool_name="search_alarm_history",
    )


def main() -> None:
    """Run the alarm MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

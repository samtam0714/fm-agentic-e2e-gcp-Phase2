"""Ticket MCP server exposing recommend_work_order as a standalone stdio process.

It reuses agents/workorder_agent/tools.py without duplicating business logic.
ADK and contract tests launch it with `python -m mcp_servers.ticket.server`.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agents.workorder_agent.tools import recommend_work_order as _recommend_work_order
from mcp_servers.common.timeout import run_with_timeout

mcp = FastMCP("fm-ticket")


@mcp.tool()
def recommend_work_order(
    asset_id: str,
    event_count: int = 0,
    is_recurring: bool = False,
    alarm_priority: str | None = None,
    policy_ids: list[str] | None = None,
    likely_cause: str | None = None,
) -> dict:
    """Recommend whether to create or update a work order for an asset.

    Checks existing tickets and applies recurring-alarm policy thresholds.
    Use after alarm investigation and policy search.

    Args:
        asset_id: Exact asset id (required, e.g. "AHU-3F-01"). Must be non-empty.
        event_count: Alarm event count from investigation (0 = load from issue record).
        is_recurring: Whether the alarm pattern is recurring.
        alarm_priority: Optional alarm priority (e.g. "P1", "medium").
        policy_ids: Optional list of policy ids already cited (e.g. ["HVAC-MNT-003"]).
        likely_cause: Optional likely cause string from alarm investigation.

    Returns:
        dict with query, active_work_orders, and recommendation action/priority.
    """
    return run_with_timeout(
        _recommend_work_order,
        asset_id=asset_id,
        event_count=event_count,
        is_recurring=is_recurring,
        alarm_priority=alarm_priority,
        policy_ids=policy_ids,
        likely_cause=likely_cause,
        tool_name="recommend_work_order",
    )


def main() -> None:
    """Run the ticket MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

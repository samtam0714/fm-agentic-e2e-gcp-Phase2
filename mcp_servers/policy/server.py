"""Policy MCP server exposing search_policy_doc as a standalone stdio process.

Design:
- Reuse search_policy_doc from agents/kb_agent/tools.py.
- Let @mcp.tool() derive the schema from the signature and docstring.
- ADK launches this module as a subprocess and communicates over stdin/stdout.

Manual verification (waits for requests; press Ctrl+C to exit):
    uv run python -m mcp_servers.policy.server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agents.kb_agent.tools import search_policy_doc as _search_policy_doc
from mcp_servers.common.timeout import run_with_timeout

mcp = FastMCP("fm-policy")


@mcp.tool()
def search_policy_doc(query: str, asset_type: str | None = None) -> dict:
    """Search maintenance policy documents by keywords and optional asset type.

    Args:
        query: Free-text keywords (e.g. "recurring filter", alarm_type like
            "high_supply_air_temp"). Required and must be non-empty to match.
        asset_type: Optional asset type filter (e.g. "AHU", "VAV"). When given,
            only policies whose applies_to contains it are returned.

    Returns:
        dict with keys: query (echo of inputs), match_count (int), policies (list).
    """
    return run_with_timeout(
        _search_policy_doc,
        query=query,
        asset_type=asset_type,
        tool_name="search_policy_doc",
    )


def main() -> None:
    """Run the policy MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

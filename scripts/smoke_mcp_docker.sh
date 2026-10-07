#!/usr/bin/env bash
# Local smoke: Docker image includes MCP servers and registry can enable them.
# Does not call Vertex - only verifies packaging + USE_MCP_TOOLS wiring.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-fm-mcp-smoke:local}"

echo "[smoke-mcp] Checking Dockerfile copies mcp_servers..."
grep -q 'COPY mcp_servers/' "${ROOT_DIR}/deployment/Dockerfile"

echo "[smoke-mcp] Building image ${IMAGE_NAME}..."
docker build -f "${ROOT_DIR}/deployment/Dockerfile" -t "${IMAGE_NAME}" "${ROOT_DIR}"

echo "[smoke-mcp] Verifying MCP modules + registry switch inside container..."
docker run --rm \
  -e USE_MCP_TOOLS=1 \
  -e MCP_TOOL_TIMEOUT_SECONDS=30 \
  "${IMAGE_NAME}" \
  python -c "
import os
assert os.environ.get('USE_MCP_TOOLS') == '1'
from tools.registry import get_tools_for_agent, _mcp_enabled
assert _mcp_enabled() is True
tools = get_tools_for_agent('kb_agent')
assert any('McpToolset' in type(t).__name__ for t in tools), tools
import mcp_servers.alarm.server  # noqa: F401
import mcp_servers.policy.server  # noqa: F401
import mcp_servers.ticket.server  # noqa: F401
print('[smoke-mcp] OK: mcp_servers present, USE_MCP_TOOLS registry returns McpToolset')
"

echo "[smoke-mcp] Done."

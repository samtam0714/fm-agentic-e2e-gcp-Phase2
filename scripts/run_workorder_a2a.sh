#!/usr/bin/env bash
# Start the remote WorkOrder Mini A2A server (Sprint 7).
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
export WORKORDER_A2A_PORT="${WORKORDER_A2A_PORT:-8091}"
exec uv run workorder-a2a

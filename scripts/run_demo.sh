#!/usr/bin/env bash
# FM AgentOps Phase 2 demo - Floor 3 recurring HVAC alarm (full investigate pipeline).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DEFAULT_QUERY="The HVAC alarm on Floor 3 keeps recurring. Check the issue, search policy, decide if we should create a work order, and recommend priority."

QUERY="${DEFAULT_QUERY}"
ALARM_ONLY=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Run the FM AgentOps demo story locally (mock data: issue_demo_001 / AHU-3F-01).

Options:
  --query TEXT     Custom investigation query (default: Floor 3 HVAC demo)
  --alarm-only     Run AlarmAgent only via run_agent_cli.py
  -h, --help       Show this help

Examples:
  $(basename "$0")
  $(basename "$0") --query "The HVAC alarm on Floor 3 keeps recurring..."
  $(basename "$0") --alarm-only
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --query)
      QUERY="${2:?--query requires a value}"
      shift 2
      ;;
    --alarm-only)
      ALARM_ONLY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

echo ""
echo "========== FM AgentOps Demo: Floor 3 HVAC recurring alarm =========="
echo "[query] ${QUERY}"
echo ""

if [[ "${ALARM_ONLY}" == true ]]; then
  uv run python scripts/run_agent_cli.py --query "${QUERY}"
else
  uv run python scripts/run_investigate_cli.py --query "${QUERY}"
fi

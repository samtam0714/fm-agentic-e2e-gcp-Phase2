#!/usr/bin/env bash
# Run eval harness and release gate.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[run_eval] Running golden dataset eval..."
uv run python eval_harness/runners/run_agent_eval.py "$@"
EVAL_EXIT=$?

echo "[run_eval] Running release gate (absolute + regression)..."
set +e
uv run python eval_harness/release_gate/gate.py eval_harness/reports/eval_report.json
GATE_EXIT=$?
set -e

if [[ ${EVAL_EXIT} -ne 0 || ${GATE_EXIT} -ne 0 ]]; then
  echo "[run_eval] BLOCKED: eval_exit=${EVAL_EXIT} gate_exit=${GATE_EXIT}"
  exit 1
fi

echo "[run_eval] PASS: eval, absolute gate, and regression gate succeeded"
exit 0

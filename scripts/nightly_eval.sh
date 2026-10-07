#!/usr/bin/env bash
# Sprint 2.2.5 -- Nightly full golden evaluation and regression gate.
#
# Unlike ci_release.sh:
#   - This is a monitoring job, not a release job; it does not build or deploy.
#   - It runs the full evaluation and archives timestamped results for trend analysis.
#   - Gate failures return a nonzero exit code for Cloud Scheduler and alerting.
#
# Environment variables:
#   EVAL_DATASET             Defaults to all (30 cases)
#   EVAL_CASE_DELAY_SECONDS  Delay between cases (default: 60s, mitigates Vertex 429s)
#   NIGHTLY_ALERT_WEBHOOK    Optional URL for regression alert JSON
#   GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION  Required for Vertex evaluation
set -euo pipefail

export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

if [[ -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
  echo "[nightly] BLOCK: GOOGLE_CLOUD_PROJECT is not set"
  exit 1
fi

export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
export GOOGLE_GENAI_USE_VERTEXAI="${GOOGLE_GENAI_USE_VERTEXAI:-true}"
export EVAL_CASE_DELAY_SECONDS="${EVAL_CASE_DELAY_SECONDS:-60}"
export EVAL_CASE_MAX_RETRIES="${EVAL_CASE_MAX_RETRIES:-12}"
export EVAL_CASE_RETRY_MAX_WAIT="${EVAL_CASE_RETRY_MAX_WAIT:-600}"
export EVAL_RATE_LIMIT_COOLDOWN="${EVAL_RATE_LIMIT_COOLDOWN:-180}"
EVAL_DATASET="${EVAL_DATASET:-all}"

REPORT="${ROOT_DIR}/eval_harness/reports/eval_report.json"
HISTORY_DIR="${ROOT_DIR}/eval_harness/reports/history"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVED="${HISTORY_DIR}/eval_report_${TIMESTAMP}.json"
mkdir -p "${HISTORY_DIR}"

echo ""
echo "========== [nightly] Step 1/3: Full evaluation (dataset=${EVAL_DATASET}) =========="
# Continue after evaluation failure so the report is archived, gated, and alerted.
set +e
uv run python eval_harness/runners/run_agent_eval.py --dataset "${EVAL_DATASET}" --quiet
EVAL_EXIT=$?
set -e

echo ""
echo "========== [nightly] Step 2/3: Archive report to history =========="
if [[ -f "${REPORT}" ]]; then
  cp "${REPORT}" "${ARCHIVED}"
  echo "[nightly] Archived: ${ARCHIVED}"
else
  echo "[nightly] WARN: ${REPORT} not found; skipping archive"
fi

echo ""
echo "========== [nightly] Step 3/3: Regression gate (vs baseline) =========="
set +e
uv run python eval_harness/release_gate/gate.py "${REPORT}"
GATE_EXIT=$?
set -e

if [[ ${EVAL_EXIT} -ne 0 || ${GATE_EXIT} -ne 0 ]]; then
  echo "[nightly] REGRESSION DETECTED: eval_exit=${EVAL_EXIT} gate_exit=${GATE_EXIT}"
  if [[ -n "${NIGHTLY_ALERT_WEBHOOK:-}" ]]; then
    PASS_RATE="$(uv run python -c "import json;print(json.load(open('${REPORT}')).get('pass_rate','?'))" 2>/dev/null || echo '?')"
    curl -sf -X POST -H 'Content-Type: application/json' \
      -d "{\"text\":\"[FM AgentOps nightly] regression detected at ${TIMESTAMP} (pass_rate=${PASS_RATE}, eval_exit=${EVAL_EXIT}, gate_exit=${GATE_EXIT})\"}" \
      "${NIGHTLY_ALERT_WEBHOOK}" >/dev/null 2>&1 \
      && echo "[nightly] Alert sent to NIGHTLY_ALERT_WEBHOOK" \
      || echo "[nightly] WARN: Failed to send alert"
  fi
  exit 1
fi

echo ""
echo "========== [nightly] PASS: Full evaluation and regression gate passed =========="

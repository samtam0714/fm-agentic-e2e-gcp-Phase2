#!/usr/bin/env bash
# Phase 2 CI pipeline: unit tests -> agent evaluation -> absolute and regression gates
#
# Verifies before deployment that code is healthy and agent quality meets the baseline.
#
# Environment variables:
#   SKIP_AGENT_EVAL=1  Skip evaluation; run unit tests and gates using an existing report
#   EVAL_DATASET       Defaults to all (30 cases); use alarm_cases (10 cases) if rate-limited
#   EVAL_CASE_DELAY_SECONDS   Delay between cases and backoff base (default: 60s)
#   EVAL_CASE_MAX_RETRIES     Maximum retries per case (default: 12)
#   EVAL_CASE_RETRY_MAX_WAIT  Maximum rate-limit backoff (default: 600s)
#   EVAL_RATE_LIMIT_COOLDOWN  Additional cooldown after a 429 (default: 180s)
#   EVAL_SKIP_LLM_JUDGE=1     Skip the LLM judge to reduce API calls
#   GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION  Required for Vertex evaluation
set -euo pipefail

# Make uv available in Cloud Build and locally.
export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Load the project-root .env, as deploy.sh does.
if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

echo ""
echo "========== [ci] Step 1/3: Unit tests (pytest) =========="
uv sync --frozen --extra dev
uv run pytest tests/ -q

echo ""
echo "========== [ci] Step 2/3: Agent eval (golden dataset) =========="
if [[ "${SKIP_AGENT_EVAL:-0}" == "1" ]]; then
  echo "[ci] SKIP_AGENT_EVAL=1; skipping evaluation and using the existing eval_report.json"
  if [[ ! -f eval_harness/reports/eval_report.json ]]; then
    echo "[ci] BLOCK: eval_report.json is required when evaluation is skipped"
    exit 1
  fi
else
  if [[ -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
    echo "[ci] BLOCK: GOOGLE_CLOUD_PROJECT is not set"
    echo "[ci] Configure it in .env or export GOOGLE_CLOUD_PROJECT=<project-id>"
    echo "[ci] To test gates without evaluation: SKIP_AGENT_EVAL=1 ./scripts/ci_release.sh"
    exit 1
  fi
  export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
  export GOOGLE_GENAI_USE_VERTEXAI="${GOOGLE_GENAI_USE_VERTEXAI:-true}"
  export EVAL_CASE_DELAY_SECONDS="${EVAL_CASE_DELAY_SECONDS:-60}"
  export EVAL_CASE_MAX_RETRIES="${EVAL_CASE_MAX_RETRIES:-12}"
  export EVAL_CASE_RETRY_MAX_WAIT="${EVAL_CASE_RETRY_MAX_WAIT:-600}"
  export EVAL_RATE_LIMIT_COOLDOWN="${EVAL_RATE_LIMIT_COOLDOWN:-180}"
  EVAL_DATASET="${EVAL_DATASET:-all}"
  EVAL_ARGS=(--dataset "${EVAL_DATASET}" --quiet)
  if [[ "${EVAL_SKIP_LLM_JUDGE:-0}" == "1" ]]; then
    EVAL_ARGS+=(--skip-llm-judge)
    echo "[ci] EVAL_SKIP_LLM_JUDGE=1; running rule-based evaluation only"
  fi
  echo "[ci] dataset=${EVAL_DATASET} project=${GOOGLE_CLOUD_PROJECT} delay=${EVAL_CASE_DELAY_SECONDS}s"
  uv run python eval_harness/runners/run_agent_eval.py "${EVAL_ARGS[@]}"
fi

echo ""
echo "========== [ci] Step 3/3: Release gates (absolute + baseline regression) =========="
uv run python eval_harness/release_gate/gate.py eval_harness/reports/eval_report.json

echo ""
echo "========== [ci] PASS: Tests, evaluation, and gates passed; ready to build/deploy =========="

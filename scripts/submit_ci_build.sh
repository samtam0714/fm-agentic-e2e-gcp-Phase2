#!/usr/bin/env bash
# Submit the Phase 2 CI pipeline to Cloud Build: test -> gate -> build -> deploy.
#
# By default, Cloud Build reuses the local eval_report.json and runs pytest plus gates.
# Before submission this script verifies the report exists, checks that it is not stale,
# and runs the gate locally.
#
# To run evaluation in Cloud Build: SKIP_AGENT_EVAL=0 ./scripts/submit_ci_build.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"

REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-fm-agentops}"
REPO_NAME="${REPO_NAME:-fm-agentops}"
DEPLOY="${DEPLOY:-true}"
EVAL_DATASET="${EVAL_DATASET:-all}"
SKIP_AGENT_EVAL="${SKIP_AGENT_EVAL:-1}"

# Normalize SKIP_AGENT_EVAL from 1/0 or true/false for Cloud Build.
if [[ "${SKIP_AGENT_EVAL}" == "1" || "${SKIP_AGENT_EVAL}" == "true" ]]; then
  SKIP_FLAG="true"
else
  SKIP_FLAG="false"
fi

REPORT="${ROOT_DIR}/eval_harness/reports/eval_report.json"

if [[ "${SKIP_FLAG}" == "true" ]]; then
  echo "[submit_ci] Reusing local evaluation; validating eval_report.json"

  if [[ ! -f "${REPORT}" ]]; then
    echo "[submit_ci] BLOCK: Missing ${REPORT}"
    echo "[submit_ci] Run ./scripts/ci_release.sh locally first"
    exit 1
  fi

  # The report may be stale if agent, data, or golden source files are newer.
  STALE=$(find agents data/mock eval_harness/golden_dataset eval_harness/judges services \
    -type f -newer "${REPORT}" 2>/dev/null | head -n 5 || true)
  if [[ -n "${STALE}" ]]; then
    echo "[submit_ci] WARN: These source files are newer than eval_report.json:"
    echo "${STALE}" | sed 's/^/  - /'
    if [[ "${ALLOW_STALE_EVAL:-0}" != "1" ]]; then
      echo "[submit_ci] BLOCK: Rerun ./scripts/ci_release.sh or set ALLOW_STALE_EVAL=1"
      exit 1
    fi
    echo "[submit_ci] ALLOW_STALE_EVAL=1; continuing"
  fi

  echo "[submit_ci] Running the local gate before Cloud Build..."
  uv run python eval_harness/release_gate/gate.py "${REPORT}"
  echo "[submit_ci] Local gate passed."
fi

echo "[submit_ci] Project=${GOOGLE_CLOUD_PROJECT} region=${REGION} deploy=${DEPLOY} skip_agent_eval=${SKIP_FLAG}"
echo "[submit_ci] Ensuring Artifact Registry repo exists..."
gcloud artifacts repositories describe "${REPO_NAME}" \
  --location="${REGION}" \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --description="Facility Management AgentOps images"

gcloud builds submit "${ROOT_DIR}" \
  --config="${ROOT_DIR}/deployment/cloudbuild-ci.yaml" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --substitutions="_REGION=${REGION},_SERVICE_NAME=${SERVICE_NAME},_REPO_NAME=${REPO_NAME},_DEPLOY=${DEPLOY},_EVAL_DATASET=${EVAL_DATASET},_SKIP_AGENT_EVAL=${SKIP_FLAG}"

echo "[submit_ci] Cloud Build CI submitted. Track in Cloud Console -> Cloud Build -> History"

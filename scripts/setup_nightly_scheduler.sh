#!/usr/bin/env bash
# Sprint 2.2.5 -- Configure Cloud Scheduler to trigger nightly evaluation.
#
# Cloud Scheduler invokes Cloud Build to run deployment/cloudbuild-nightly.yaml.
# Requires authenticated gcloud access and build/scheduler creation permissions.
#
# Usage:
#   GOOGLE_CLOUD_PROJECT=<project-id> ./scripts/setup_nightly_scheduler.sh
#
# Optional environment variables:
#   NIGHTLY_CRON     Default: "0 8 * * *" (08:00 UTC daily)
#   SCHEDULER_REGION Default: us-central1
#   JOB_NAME         Default: fm-nightly-eval
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
REGION="${SCHEDULER_REGION:-us-central1}"
JOB_NAME="${JOB_NAME:-fm-nightly-eval}"
CRON="${NIGHTLY_CRON:-0 8 * * *}"
CONFIG_PATH="deployment/cloudbuild-nightly.yaml"

echo "[scheduler] project=${GOOGLE_CLOUD_PROJECT} region=${REGION} job=${JOB_NAME} cron='${CRON}'"

# Cloud Build's run-trigger mode requires an existing trigger. Submitting source
# directly from Scheduler is more complex, so create a GitHub-backed manual trigger
# first and let Scheduler invoke it.
#
# The following commands schedule that manual build trigger.

TRIGGER_NAME="${JOB_NAME}-trigger"

echo "[scheduler] Checking Cloud Build trigger: ${TRIGGER_NAME}"
if ! gcloud builds triggers describe "${TRIGGER_NAME}" \
  --region="${REGION}" --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1; then
  echo "[scheduler] Trigger not found. Open Cloud Console -> Cloud Build -> Triggers"
  echo "[scheduler] Connect the GitHub repository and create a manual trigger for ${CONFIG_PATH}"
  echo "[scheduler] Name it ${TRIGGER_NAME}, then rerun this script."
  echo "[scheduler] GitHub connection is interactive and cannot be automated here."
  exit 1
fi

echo "[scheduler] Checking Cloud Scheduler job: ${JOB_NAME}"
RUN_URI="https://cloudbuild.googleapis.com/v1/projects/${GOOGLE_CLOUD_PROJECT}/locations/${REGION}/triggers/${TRIGGER_NAME}:run"

if gcloud scheduler jobs describe "${JOB_NAME}" \
  --location="${REGION}" --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${JOB_NAME}" \
    --location="${REGION}" --project="${GOOGLE_CLOUD_PROJECT}" \
    --schedule="${CRON}" --time-zone="Etc/UTC" \
    --uri="${RUN_URI}" --http-method=POST \
    --oauth-service-account-email="$(gcloud config get-value account 2>/dev/null)"
  echo "[scheduler] Updated job ${JOB_NAME}"
else
  gcloud scheduler jobs create http "${JOB_NAME}" \
    --location="${REGION}" --project="${GOOGLE_CLOUD_PROJECT}" \
    --schedule="${CRON}" --time-zone="Etc/UTC" \
    --uri="${RUN_URI}" --http-method=POST \
    --oauth-service-account-email="$(gcloud config get-value account 2>/dev/null)"
  echo "[scheduler] Created job ${JOB_NAME}"
fi

echo "[scheduler] Done. Nightly evaluation will run at '${CRON}' UTC."

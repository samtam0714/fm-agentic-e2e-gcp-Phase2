#!/usr/bin/env bash
# Build, push, and deploy FM AgentOps API to Cloud Run.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-fm-agentops}"
IMAGE_TAG="${IMAGE_TAG:-v1}"
REPO_NAME="${REPO_NAME:-fm-agentops}"
# Sprint 3: Enable MCP for Cloud Run integration; set USE_MCP_TOOLS=0 to override locally.
USE_MCP_TOOLS="${USE_MCP_TOOLS:-1}"
MCP_TOOL_TIMEOUT_SECONDS="${MCP_TOOL_TIMEOUT_SECONDS:-30}"
# Sprint 4: Observability exports are off by default to avoid unexpected GCP writes or costs.
ENABLE_CLOUD_TRACE="${ENABLE_CLOUD_TRACE:-0}"
ENABLE_BIGQUERY="${ENABLE_BIGQUERY:-0}"
BIGQUERY_DATASET="${BIGQUERY_DATASET:-fm_agentops_observability}"

IMAGE_URI="${REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${REPO_NAME}/${SERVICE_NAME}:${IMAGE_TAG}"

echo "[deploy] Ensuring Artifact Registry repo exists..."
gcloud artifacts repositories describe "${REPO_NAME}" \
  --location="${REGION}" \
  --project="${GOOGLE_CLOUD_PROJECT}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${GOOGLE_CLOUD_PROJECT}" \
    --description="Facility Management AgentOps images"

echo "[deploy] Building and pushing ${IMAGE_URI}..."
gcloud builds submit "${ROOT_DIR}" \
  --config="${ROOT_DIR}/deployment/cloudbuild.yaml" \
  --substitutions=_IMAGE_URI="${IMAGE_URI}" \
  --project="${GOOGLE_CLOUD_PROJECT}"

echo "[deploy] Deploying Cloud Run service ${SERVICE_NAME}..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE_URI}" \
  --region "${REGION}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --allow-unauthenticated \
  --timeout=300 \
  --memory=2Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},GOOGLE_CLOUD_LOCATION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-flash},USE_MCP_TOOLS=${USE_MCP_TOOLS},MCP_TOOL_TIMEOUT_SECONDS=${MCP_TOOL_TIMEOUT_SECONDS},ENABLE_CLOUD_TRACE=${ENABLE_CLOUD_TRACE},ENABLE_BIGQUERY=${ENABLE_BIGQUERY},BIGQUERY_DATASET=${BIGQUERY_DATASET}"

echo "[deploy] Done. Fetch service URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --format='value(status.url)'

#!/usr/bin/env bash
# Build and run the FM AgentOps API container locally.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-fm-agentops:local}"
CONTAINER_NAME="${CONTAINER_NAME:-fm-agentops-local}"
HOST_PORT="${HOST_PORT:-8080}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env or environment}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"

ADC_PATH="${HOME}/.config/gcloud/application_default_credentials.json"
ADC_MOUNT=()
if [[ -f "${ADC_PATH}" ]]; then
  ADC_MOUNT=(
    -v "${ADC_PATH}:/tmp/adc.json:ro"
    -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json
  )
else
  echo "Warning: ${ADC_PATH} not found. Run: gcloud auth application-default login"
fi

echo "[docker] Building ${IMAGE_NAME}..."
docker build -f "${ROOT_DIR}/deployment/Dockerfile" -t "${IMAGE_NAME}" "${ROOT_DIR}"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

echo "[docker] Starting ${CONTAINER_NAME} on port ${HOST_PORT}..."
docker run --name "${CONTAINER_NAME}" -p "${HOST_PORT}:8080" \
  -e GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
  -e GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION}" \
  -e GOOGLE_GENAI_USE_VERTEXAI=true \
  -e GEMINI_MODEL="${GEMINI_MODEL}" \
  "${ADC_MOUNT[@]}" \
  "${IMAGE_NAME}"

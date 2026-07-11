#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-morita-bot-tick}"
SCHEDULER_JOB="${SCHEDULER_JOB:-morita-bot-every-5m}"
ARTIFACT_REPO="${ARTIFACT_REPO:-morita-bot}"
DRY_RUN="${DRY_RUN:-true}"
ALLOW_TEST_OVERRIDES="${ALLOW_TEST_OVERRIDES:-true}"

if [[ -z "${PROJECT_ID}" ]]; then
  read -r -p "Google Cloud project ID: " PROJECT_ID
fi
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-morita-bot-state}"

: "${PUSHOVER_APP_TOKEN:?Set PUSHOVER_APP_TOKEN before running this script.}"
: "${PUSHOVER_USER_KEY:?Set PUSHOVER_USER_KEY before running this script.}"

gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q . || {
  echo "No active gcloud account. Run: gcloud auth login" >&2
  exit 1
}

gcloud config set project "${PROJECT_ID}"
gcloud projects describe "${PROJECT_ID}" >/dev/null

BILLING_ENABLED="$(gcloud billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)' 2>/dev/null || true)"
if [[ "${BILLING_ENABLED}" != "True" && "${BILLING_ENABLED}" != "true" ]]; then
  echo "Billing is not enabled for ${PROJECT_ID}. Enable billing, then rerun." >&2
  exit 1
fi

echo "Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com

RUNTIME_SA_NAME="morita-bot-runtime"
SCHEDULER_SA_NAME="morita-bot-scheduler"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${RUNTIME_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${RUNTIME_SA_NAME}" \
    --display-name="Morita Bot Cloud Run runtime"
fi
if ! gcloud iam service-accounts describe "${SCHEDULER_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SCHEDULER_SA_NAME}" \
    --display-name="Morita Bot Cloud Scheduler invoker"
fi

if ! gcloud artifacts repositories describe "${ARTIFACT_REPO}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Morita Bot container images"
fi

if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --location="${REGION}" \
    --uniform-bucket-level-access
fi

TMP_LIFECYCLE="$(mktemp)"
cat > "${TMP_LIFECYCLE}" <<'JSON'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 45}
    }
  ]
}
JSON
gcloud storage buckets update "gs://${BUCKET_NAME}" --lifecycle-file="${TMP_LIFECYCLE}"
rm -f "${TMP_LIFECYCLE}"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/storage.objectAdmin" >/dev/null

ensure_secret() {
  local name="$1"
  local value="$2"
  if ! gcloud secrets describe "${name}" >/dev/null 2>&1; then
    gcloud secrets create "${name}" --replication-policy=automatic
  fi
  printf '%s' "${value}" | gcloud secrets versions add "${name}" --data-file=- >/dev/null
  gcloud secrets add-iam-policy-binding "${name}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
}

ensure_secret "morita-pushover-app-token" "${PUSHOVER_APP_TOKEN}"
ensure_secret "morita-pushover-user-key" "${PUSHOVER_USER_KEY}"

SECRET_BINDINGS="PUSHOVER_APP_TOKEN=morita-pushover-app-token:latest,PUSHOVER_USER_KEY=morita-pushover-user-key:latest"
if [[ -n "${STOCK:-}" ]]; then
  ensure_secret "morita-discord-webhook" "${STOCK}"
  SECRET_BINDINGS="${SECRET_BINDINGS},STOCK=morita-discord-webhook:latest"
fi

IMAGE_TAG="$(date -u +%Y%m%d-%H%M%S)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE_NAME}:${IMAGE_TAG}"

echo "Building ${IMAGE}..."
gcloud builds submit --tag "${IMAGE}" .

echo "Deploying Cloud Run service..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --cpu=1 \
  --memory=2Gi \
  --timeout=1800 \
  --concurrency=1 \
  --min-instances=0 \
  --max-instances=1 \
  --set-env-vars="GCS_BUCKET=${BUCKET_NAME},DRY_RUN=${DRY_RUN},ALLOW_TEST_OVERRIDES=${ALLOW_TEST_OVERRIDES},MIN_INTRADAY_COVERAGE=0.50,PRECOMPUTE_PERIOD=18mo" \
  --set-secrets="${SECRET_BINDINGS}"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --format='value(status.url)')"

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --member="serviceAccount:${SCHEDULER_SA}" \
  --role="roles/run.invoker" >/dev/null

SCHEDULE="*/5 12-21 * * 1-5"
COMMON_SCHEDULER_ARGS=(
  --location="${REGION}"
  --schedule="${SCHEDULE}"
  --time-zone="Etc/UTC"
  --uri="${SERVICE_URL}/tick"
  --http-method=POST
  --oidc-service-account-email="${SCHEDULER_SA}"
  --oidc-token-audience="${SERVICE_URL}"
  --headers="Content-Type=application/json"
  --message-body='{}'
  --attempt-deadline=1800s
  --max-retry-attempts=1
)

if gcloud scheduler jobs describe "${SCHEDULER_JOB}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER_JOB}" "${COMMON_SCHEDULER_ARGS[@]}"
else
  gcloud scheduler jobs create http "${SCHEDULER_JOB}" "${COMMON_SCHEDULER_ARGS[@]}"
fi

cat <<EOF

Deployment complete.
Service URL: ${SERVICE_URL}
State bucket: gs://${BUCKET_NAME}
Scheduler: ${SCHEDULER_JOB} (${SCHEDULE} UTC)
DRY_RUN: ${DRY_RUN}

Manual shadow test:
  TOKEN=\$(gcloud auth print-identity-token)
  curl -X POST -H "Authorization: Bearer \${TOKEN}" -H "Content-Type: application/json" \\
    "${SERVICE_URL}/tick" \\
    -d '{"force_action":"12:00","mock_time_et":"2026-07-10T12:05:00-04:00"}'

After shadow validation, enable live notifications:
  gcloud run services update ${SERVICE_NAME} --region=${REGION} \\
    --update-env-vars=DRY_RUN=false,ALLOW_TEST_OVERRIDES=false
EOF

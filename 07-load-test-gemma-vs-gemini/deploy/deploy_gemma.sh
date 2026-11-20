#!/usr/bin/env bash
# Deploy Gemma 4 with vLLM on Cloud Run with one GPU. NOT run by the tests or by CI.
# Running this rents a GPU. It bills for every second the instance lives (instance-based billing).
# Usage: PROJECT=my-project bash deploy/deploy_gemma.sh
# Defaults (region, service, model, instance cap) come from config.py, the one source.
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to your project id}"
# shellcheck disable=SC1090
eval "$(python3 "$(dirname "$0")/../config.py" --shell)"

if ! [[ "$MAX_INSTANCES" =~ ^[0-9]+$ ]] || [ "$MAX_INSTANCES" -lt 1 ] || [ "$MAX_INSTANCES" -gt "$MAX_INSTANCES_LIMIT" ]; then
  echo "MAX_INSTANCES must be a whole number from 1 to $MAX_INSTANCES_LIMIT (your default GPU quota)." >&2
  exit 1
fi

RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

# The container runs a public image, so give it an identity with NO project roles.
# Without --service-account it would run as the Compute Engine default account, which
# can hold the Editor role. Your account needs roles/iam.serviceAccountUser on this one.
# The account is created only if absent. A marker file records that THIS script created it,
# so delete_gemma.sh removes only an account it made. Use a dedicated project for this test.
MARKER="$(dirname "$0")/.created_service_account"
# The marker holds "email uniqueId". The uniqueId changes if the account is deleted and
# recreated with the same email, so an account someone else made later never matches.
CURRENT_ID="$(gcloud iam service-accounts describe "$RUNTIME_SA" --project "$PROJECT" --format='value(uniqueId)' 2>/dev/null || true)"
if [ -n "$CURRENT_ID" ]; then
  if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$RUNTIME_SA $CURRENT_ID" ]; then
    echo "$RUNTIME_SA already exists and this script did not create it, or its uniqueId changed. Not attaching it." >&2
    echo "Delete it, or use a dedicated project, then run this script again." >&2
    exit 1
  fi
  echo "Reusing $RUNTIME_SA created by an earlier run of this script."
else
  gcloud iam service-accounts create "$RUNTIME_SA_NAME" --project "$PROJECT" \
    --display-name "Coral Gemma load test (no roles)"
  NEW_ID="$(gcloud iam service-accounts describe "$RUNTIME_SA" --project "$PROJECT" --format='value(uniqueId)')"
  echo "$RUNTIME_SA $NEW_ID" > "$MARKER"
fi

if [ "$MAX_INSTANCES" -gt 1 ]; then
  echo "MAX_INSTANCES above 1: report.py needs a one-instance run (MAX_INSTANCES=1) to get per-instance numbers." >&2
fi

# The prebuilt vLLM image comes from the Cloud Run Gemma 4 guide.
# RTX PRO 6000 needs at least 20 CPU and 80Gi memory. --no-cpu-throttling and instance
# billing are required for GPU. --max-instances caps one revision and --max caps the whole
# service; Cloud Run can briefly go over a cap while it scales, so delete the service when done.
# --invoker-iam-check makes the private setting explicit if you rerun this on an old service.
# "^@^" makes @ the separator for --args, so the values can contain commas.
gcloud beta run deploy "$SERVICE" \
  --image us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:gemma4 \
  --project "$PROJECT" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --execution-environment gen2 \
  --no-allow-unauthenticated \
  --invoker-iam-check \
  --cpu 20 \
  --memory 80Gi \
  --gpu 1 \
  --gpu-type nvidia-rtx-pro-6000 \
  --no-gpu-zonal-redundancy \
  --no-cpu-throttling \
  --max-instances "$MAX_INSTANCES" \
  --max "$MAX_INSTANCES" \
  --concurrency 64 \
  --timeout 600 \
  --startup-probe tcpSocket.port=8080,initialDelaySeconds=240,failureThreshold=1,timeoutSeconds=240,periodSeconds=240 \
  --command vllm \
  --args="^@^serve@${MODEL}@--enable-chunked-prefill@--enable-prefix-caching@--generation-config=auto@--dtype=bfloat16@--max-num-seqs=64@--gpu-memory-utilization=0.95@--tensor-parallel-size=1@--port=8080@--host=0.0.0.0"

echo "Deployed ${SERVICE} in ${REGION}. Next: gcloud run services proxy ${SERVICE} --project ${PROJECT} --region ${REGION} --port=9090"

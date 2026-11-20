#!/usr/bin/env bash
# Delete the GPU service, then the runtime service account if deploy_gemma.sh created it.
# Run it the moment the Gemma run ends, and again after an interrupted run: an idle GPU
# instance still bills. Same defaults as deploy_gemma.sh (config.py).
set -uo pipefail

PROJECT="${PROJECT:?set PROJECT to your project id}"
# shellcheck disable=SC1090
eval "$(python3 "$(dirname "$0")/../config.py" --shell)"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
MARKER="$(dirname "$0")/.created_service_account"

echo "Deleting service ${SERVICE} in ${REGION} of project ${PROJECT}"
gcloud run services delete "$SERVICE" --project "$PROJECT" --region "$REGION" --quiet
status=$?

# Delete the account only after the service delete succeeded AND the service is confirmed gone;
# a still-running service would lose its identity. If either check fails, run this script again.
# Only a "not found" answer proves the service is gone; a permission or API error does not.
DESCRIBE_OUT="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" 2>&1)"
describe_status=$?
if [ "$status" -ne 0 ] || [ "$describe_status" -eq 0 ] || ! grep -qiE "not found|NOT_FOUND|cannot find service" <<<"$DESCRIBE_OUT"; then
  echo "Service ${SERVICE} is not confirmed deleted. Keeping the service account. Run this script again." >&2
  exit 1
fi

CURRENT_ID="$(gcloud iam service-accounts describe "$RUNTIME_SA" --project "$PROJECT" --format='value(uniqueId)' 2>/dev/null || true)"
if [ -n "$CURRENT_ID" ] && [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$RUNTIME_SA $CURRENT_ID" ]; then
  if gcloud iam service-accounts delete "$RUNTIME_SA" --project "$PROJECT" --quiet; then
    rm -f "$MARKER"
  else
    status=1
  fi
else
  echo "Not deleting $RUNTIME_SA: deploy_gemma.sh did not create this account (missing, or its uniqueId differs from the marker)."
fi
exit "$status"

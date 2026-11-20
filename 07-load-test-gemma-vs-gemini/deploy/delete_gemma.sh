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

# The service account goes even if the service delete failed, so an interrupted run leaves nothing.
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

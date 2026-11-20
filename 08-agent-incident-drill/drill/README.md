# Incident drill runbook: wrong currency

Pebble Post's agent has a built-in fault so you can practise before a real incident. Run this in a test project, with test traffic only. Only trusted drill operators should be able to call the service: the raw ADK API takes any `user_id` and `session_id` the caller sends.

Fault: with `DRILL_FAULT=wrong_currency` the `lookup_order` tool reports the wrong currency (USD for a GBP order). The prompt below does not say a currency, so the agent takes it from the lookup and asks `refund_order` to refund in USD. The refund tool checks the true order currency, so it refuses. No wrong money moves. Customers just cannot get refunds. You will see it as a run of refusals.

You need `gcloud` and `jq`, and a shell with `pipefail` so a failed `curl` is not hidden by `jq`. Set these once (use your own values):

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export REGION=europe-west1
export SERVICE=pebble-agent
export URL=$(gcloud run services describe $SERVICE --region $REGION --format='value(status.url)')
set -o pipefail
```

The helper stops on HTTP errors (a 403 means you lack Cloud Run Invoker on the service, a 504 means the request timed out) and prints only the tool calls and tool results, so you check what the agent did, not what it said:

```bash
ask() {
  curl -sS --fail-with-body -X POST "$URL/run" \
    -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    -H "Content-Type: application/json" \
    -d "{\"app_name\":\"pebble_support\",\"user_id\":\"drill\",\"session_id\":\"$1\",\"new_message\":{\"role\":\"user\",\"parts\":[{\"text\":\"$2\"}]}}" \
  | jq -c '.[] | .content.parts[]? | (.functionCall // .functionResponse // empty) | {name, args, response}'
}
```

## 0. Baseline

```bash
ask s-baseline-1 "Refund 1500 minor units on order PP-1003. Look up the order first and use the order's own currency."
```

Expected output: a `lookup_order` call, its response with `"currency":"GBP"`, a `refund_order` call with `"currency":"GBP"`, and a response with `"status":"refunded"`. If you do not see that, stop and fix it before you inject anything.

## 1. Inject the fault

This deploys a new revision. Cloud Run makes a new revision for any configuration change.

```bash
gcloud run services update $SERVICE --region $REGION --update-env-vars=DRILL_FAULT=wrong_currency
export FAULT_REV=$(gcloud run services describe $SERVICE --region $REGION --format='value(status.latestReadyRevisionName)')
echo $FAULT_REV
ask s-fault-1 "Refund 1000 minor units on order PP-1001. Look up the order first and use the order's own currency."
```

Expected output: the lookup response shows `"currency":"USD"`, the refund call uses `USD`, and the refund response is `"status":"refused"` with `"reason":"currency_mismatch"`. Run the `ask` line two or three times with new session ids (`s-fault-2`, `s-fault-3`).

## 2. Observe in Logs Explorer

Refusals caused by the fault, on the fault revision only:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="pebble-agent"
resource.labels.revision_name="PASTE_FAULT_REV_HERE"
jsonPayload.tool="refund_order"
jsonPayload.decision="refused"
jsonPayload.reason="currency_mismatch"
```

Everything the refund tool decided, any outcome, any revision:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="pebble-agent"
jsonPayload.tool="refund_order"
```

Each tool call writes exactly one line with `tool`, `decision`, `reason` and `order_id`. A run of `currency_mismatch` with no change in traffic is the signal.

Optional alert: in Logging, open Logs-based metrics and create a counter named `pebble-refund-refusals` from the first query, then create an alerting policy on it in Monitoring. Remember to delete both at the end (see the main README, Clean up).

## 3. Observe in Trace Explorer

1. Open Trace Explorer in the Google Cloud console.
2. In the filter bar choose **Span name**, then enter `execute_tool refund_order`. ADK names every tool span `execute_tool <tool name>`. The span attribute `gen_ai.tool.name` has the same value.
3. Open one trace. The waterfall shows the agent run, the model calls and the two tool calls. The `lookup_order` span comes before `refund_order`.
4. In the trace details, use "Show logs" next to the waterfall, or the Log "View" link in Details. This opens Logs Explorer filtered to that trace.

Go the other way too. Copy a trace ID from the trace, then in Logs Explorer:

```text
trace:"PASTE_TRACE_ID_HERE"
```

The log lines carry `logging.googleapis.com/trace`, which Cloud Logging stores as the entry's `trace` field. That is the link.

Message text: the deployment sets `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`. ADK's default for that switch is on (it applies to the older span schema), so we set it explicitly. A unit test checks that a prompt and a tool result stay out of span attributes. For local debugging only, set it to `true`.

## 4. Find who changed the revision

Admin Activity audit logs are always on. Query them:

```text
protoPayload.serviceName="run.googleapis.com"
protoPayload.methodName=("google.cloud.run.v2.Services.UpdateService" OR "google.cloud.run.v1.Services.ReplaceService")
resource.labels.service_name="pebble-agent"
```

Open an entry and read `protoPayload.authenticationInfo.principalEmail` (who) and the entry timestamp (when). To list the callers in one view, add `protoPayload.authenticationInfo.principalEmail` as a summary field in Logs Explorer.

Which of the two method names appears depends on the API the client used. Search for both.

Gemini calls: Data Access logs for `aiplatform.googleapis.com` are off by default. Terraform in this folder turns on DATA_READ, which covers `generateContent`. To read Data Access logs you need `roles/logging.privateLogViewer`; the project Owner role has it, a plain Logs Viewer does not. Query:

```text
logName="projects/YOUR_PROJECT_ID/logs/cloudaudit.googleapis.com%2Fdata_access"
protoPayload.serviceName="aiplatform.googleapis.com"
```

Data Access logs can be large and cost money. Remove them when the drill is over (see the main README, Clean up).

## 5. Roll back

Remove the flag. This creates another revision, with the fault gone:

```bash
gcloud run services update $SERVICE --region $REGION --remove-env-vars=DRILL_FAULT
export GOOD_REV=$(gcloud run services describe $SERVICE --region $REGION --format='value(status.latestReadyRevisionName)')
test "$GOOD_REV" != "$FAULT_REV" && echo "new revision: $GOOD_REV"
ask s-after-1 "Refund 1000 minor units on order PP-1001. Look up the order first and use the order's own currency."
```

Expected output: the lookup shows `"currency":"GBP"` and the refund response is `"status":"refunded"`. PP-1001 was never refunded during the fault, because every attempt was refused. (The sample keeps refunds in memory, per instance. The service runs with `--max-instances 1` for that reason, so a second try on the same instance gives `already_refunded`. After a restart or a new revision the ledger is empty again.)

Now check the logs. Run this on the new revision. It should show one `refunded` line and no `currency_mismatch`:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="pebble-agent"
resource.labels.revision_name="PASTE_GOOD_REV_HERE"
jsonPayload.tool="refund_order"
```

Then confirm the audit entry for the rollback exists with the query from step 4.

## 6. Write the postmortem

Copy `postmortem_template.md`, fill it in from the logs and traces above, and give every action item an owner. Do it the same day, while memory is fresh.

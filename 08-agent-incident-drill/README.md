# 08 Agent incident drill

Pebble Post is a parcel shop. Its customer-service agent, built with Google's Agent Development Kit (ADK), answers order questions and issues small refunds. This folder shows how to run it so that when something breaks you can see it, trace it, undo it and learn from it. It also has a drill you can practise in a test project.

```text
customer message
  -> Cloud Run (ADK FastAPI app, runs as its own service account)
  -> agent "pebble_support" (Gemini)
       -> lookup_order(order_id)
       -> refund_order(order_id, amount_minor, currency)
            cap 5000 minor units, never above the order total, currency must equal the order currency
  -> one JSON log line per tool call (decision + reason + trace id)
  -> spans to Cloud Trace (ADK trace_to_cloud), no message text in spans
  -> audit logs: who changed the service, who called Gemini
```

Production touches that a codelab skips:

- Money rules are in code (`agents/pebble_support/tools.py`), not in the prompt. The model cannot talk past them.
- Refusals return a clear message, so the agent can say no politely.
- The sample refund ledger is simulated and lives in memory (one process). It blocks a repeat refund on the same order inside that process only. It resets on restart or on a new revision, and other instances cannot see it. A real shop needs a database and a stable refund key.
- Model calls have a 30 second timeout, at most 2 attempts on transient errors, and one request makes at most 4 model calls (`max_llm_calls`). Best-effort worst case for a request: 4 x (2 x 30 s + 4 s backoff) = 256 s. HTTP timeouts apply to each network operation, not to the whole request, so the 300 s Cloud Run timeout is the outer bound. Only the model request is retried; tools never replay a refund.
- The runtime service account has `roles/aiplatform.user` (Agent Platform User) and `roles/cloudtrace.agent`. No keys.
- Calls need an IAM identity token (Cloud Run Invoker). The service still has a public `*.run.app` address, which IAM protects.
- Logs and traces share a trace id, so you can jump from one to the other.

## Steps

Use a disposable project. These steps create resources and IAM grants, and Clean up ends with deleting the project. You need billing on that project, `gcloud`, `terraform`, `jq`, and an account that can administer the project (Owner is simplest in a throwaway project).

1. Sign in, and also create Application Default Credentials, because Terraform reads those, not your `gcloud` login:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project YOUR_PROJECT_ID
   ```
2. Enable the APIs first:
   ```bash
   gcloud services enable \
     aiplatform.googleapis.com \
     artifactregistry.googleapis.com \
     cloudbuild.googleapis.com \
     cloudresourcemanager.googleapis.com \
     cloudtrace.googleapis.com \
     iam.googleapis.com \
     logging.googleapis.com \
     run.googleapis.com \
     serviceusage.googleapis.com
   ```
   The same list is `REQUIRED_APIS` in `config.py` and in `terraform/main.tf`. A test keeps all three equal.
3. Create the service account, its roles, and the Data Access audit config for Gemini calls:
   ```bash
   cd terraform
   terraform init
   terraform plan -var project_id=YOUR_PROJECT_ID
   terraform apply -var project_id=YOUR_PROJECT_ID
   cd ..
   ```
   If you are not Owner, you also need permission to grant project roles and set the project's audit config.
4. Let the source build work. Source deploys are built by the default Cloud Build service account, which needs `roles/run.builder`. If you are not Owner, you also need `roles/run.sourceDeveloper`, `roles/serviceusage.serviceUsageConsumer` on the project and `roles/iam.serviceAccountUser` on the runtime service account.
   Find the account first. Run `gcloud builds get-default-service-account`, copy the email it shows, and use it below:
   ```bash
   BUILD_SA=THE_EMAIL_FROM_THE_COMMAND
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:${BUILD_SA}" \
     --role="roles/run.builder"
   ```
   Which account builds depends on your project's defaults, so do not guess it. If the first deploy still fails with a build permission error, the message names the account. Grant it the same role.
5. Deploy from this folder. Cloud Build builds the `Dockerfile`, which installs exactly what `uv.lock` pins:
   ```bash
   gcloud run deploy pebble-agent \
     --source . \
     --region europe-west1 \
     --service-account $(terraform -chdir=terraform output -raw runtime_service_account) \
     --no-allow-unauthenticated \
     --invoker-iam-check \
     --timeout 300 \
     --max-instances 1 \
     --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false
   ```
   `global` is the location the model page lists for `gemini-3.8-flash`. `--max-instances 1` keeps the drill on one instance almost always, because the sample refund ledger is in memory and a second instance would not see it. Cloud Run can briefly exceed the limit, so the in-memory ledger is a drill shortcut. Production needs a shared store such as Firestore. It is a scale limit, not a spending cap. Set a budget alert in Billing for that. `--invoker-iam-check` keeps the IAM check on for repeat deploys. The Google Gen AI SDK reads either `GOOGLE_GENAI_USE_VERTEXAI` or the newer `GOOGLE_GENAI_USE_ENTERPRISE`; the ADK Cloud Run guide uses the second.
6. Allow yourself to call it, if you are not Owner:
   ```bash
   gcloud run services add-iam-policy-binding pebble-agent --region europe-west1 \
     --member="user:YOU@example.com" --role="roles/run.invoker"
   ```
   Then call it:
   ```bash
   URL=$(gcloud run services describe pebble-agent --region europe-west1 --format='value(status.url)')
   curl -sS --fail-with-body -X POST "$URL/run" \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" \
     -d '{"app_name":"pebble_support","user_id":"me","session_id":"s1","new_message":{"role":"user","parts":[{"text":"Refund 1500 minor units on order PP-1003"}]}}'
   ```
   Only give the invoker role to trusted drill operators. The raw ADK API accepts any user and session id the caller sends.
7. Open Logs Explorer and Trace Explorer and find that request. Then do the drill in [`drill/README.md`](drill/README.md). It injects `DRILL_FAULT=wrong_currency`, shows you the signal, and rolls back.

A narrower custom role is possible (the Agent Platform access-control page lists `aiplatform.endpoints.predict` for prompt requests), but it must be tested against a live call before you rely on it. This tutorial uses the predefined role.

## Run the tests on your machine

```bash
uv run pytest tests -q
uvx ruff check .
```

The tests do not call Google. They use fake orders, a scripted fake model and in-process OpenTelemetry spans.

## Audit logs

| Log | Service | State | What it tells you |
|---|---|---|---|
| Admin Activity | `run.googleapis.com` | Always on | Who updated the Cloud Run service (a new revision) and when |
| Admin Activity | `aiplatform.googleapis.com` | Always on | Who changed Agent Platform resources |
| Data Access (DATA_READ) | `aiplatform.googleapis.com` | Off by default. Terraform here turns it on | Calls such as `generateContent`. Reading them needs `roles/logging.privateLogViewer` |

Queries are in [`drill/README.md`](drill/README.md), step 4.

## Clean up

Easiest and complete: delete the disposable project. `gcloud projects delete YOUR_PROJECT_ID` removes every resource, IAM grant, log metric, alert and enabled API in it (it can be restored for 30 days, then it is gone).

If you used a project you want to keep, remove only what this tutorial made. Order matters.

```bash
# 1. The service and the grants made by hand
gcloud run services delete pebble-agent --region europe-west1
gcloud projects remove-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:${BUILD_SA}" \
  --role="roles/run.builder"
# 2. The optional drill metric, then the alerting policy you created on it (Monitoring, Alerting)
gcloud logging metrics delete pebble-refund-refusals
# 3. Terraform: service account, both role bindings, Data Access audit config
cd terraform
terraform destroy -var project_id=YOUR_PROJECT_ID
cd ..
```

Only remove the `roles/run.builder` grant if the project did not have it before you started. The `roles/run.invoker` grant from step 6 is attached to the service, so deleting the service removes it.

Source deploys also leave an Artifact Registry repository named `cloud-run-source-deploy` and a source bucket named like `run-sources-YOUR_PROJECT_ID-europe-west1`. In a shared project other services use them, so delete only this tutorial's own pieces. First look:

```bash
gcloud artifacts docker images list europe-west1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy
gcloud storage ls "gs://run-sources-YOUR_PROJECT_ID-europe-west1/**" | grep pebble-agent
```

Delete the `pebble-agent` image (all its tags) and the uploaded source objects the second command listed, one `rm` per line:

```bash
gcloud artifacts docker images delete europe-west1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/pebble-agent --delete-tags
gcloud storage rm gs://run-sources-YOUR_PROJECT_ID-europe-west1/PATH_FROM_THE_LIST
```

Leave the repository and the bucket alone if anything else is in them. If they hold nothing else, you may delete them too (`gcloud artifacts repositories delete cloud-run-source-deploy --location europe-west1`, `gcloud storage rm -r gs://run-sources-YOUR_PROJECT_ID-europe-west1`).

Terraform leaves the APIs enabled (`disable_on_destroy = false`). Disable the ones only this drill needed, if you want:

```bash
gcloud services disable cloudtrace.googleapis.com cloudbuild.googleapis.com --project YOUR_PROJECT_ID
```

Other APIs (Run, Logging, IAM, Artifact Registry, Agent Platform, Resource Manager, Service Usage) are commonly used by other things; disable them only if you know nothing else needs them. Logs and traces expire by the retention settings of your project.

## What this costs

No totals here, because they depend on traffic. Each item has a price page:

- Gemini tokens: https://cloud.google.com/vertex-ai/generative-ai/pricing
- Cloud Run: https://cloud.google.com/run/pricing
- Cloud Build and Artifact Registry: https://cloud.google.com/build/pricing and https://cloud.google.com/artifact-registry/pricing
- Cloud Trace, Cloud Logging (including Data Access audit logs) and Monitoring: https://cloud.google.com/products/observability/pricing

Data Access logs on Gemini calls grow with traffic. Switch them off outside drills if you do not need them.

## How this was checked

- Unit tests with mocks: orders, refund cap and order total, currency check, strict integer amounts, duplicate refunds, the fault flag, the log line shape, the API list. One offline test runs a real ADK agent with a scripted fake model and an in-memory span exporter. It checks that the tool log line has the same trace and span id as the exported `execute_tool` span, and that a prompt and a tool result stay out of span attributes when `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`. No Google client is called.
- `ruff check` and `terraform fmt` and `terraform validate` (CI runs validate).
- ADK and Google Cloud names were read from the current docs and from the installed package on 2026-11-20. See `FACTS.md`.
- Not run on a live Google Cloud project. The queries, the link between logs and traces, the build permissions and the Trace Explorer steps are written from the documentation and not yet seen working. Try them in a test project first.

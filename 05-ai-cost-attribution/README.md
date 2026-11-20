# 05 AI cost attribution

Tidewell is a B2B SaaS with three AI features (`ticket_summary`, `invoice_extract`, `smart_reply`) and 40 customer accounts. The question: what does each customer cost, and what does each feature cost?

This folder does not stop spend. It only measures it.

```text
Cloud Run service (runtime identity, ADC)
  -> Gemini call with request labels (feature, customer hash)  -> Cloud Billing detailed export -> cost
  -> one JSON log line (tokens) on stdout -> Cloud Logging -> log sink -> BigQuery -> tokens
BigQuery views join cost and tokens -> Data Studio
```

The customer id is hashed with a keyed hash (HMAC-SHA256) before it goes anywhere. Labels are not for personal data. The log field `customer_id` holds the hash, never the raw id.

## Steps

You need a project you can bill, `gcloud`, `terraform`, and a billing account you can administer. Use a dedicated tutorial project so clean up is simple. These steps change your project. Run them yourself.

1. Pick the project: `gcloud config set project YOUR_PROJECT_ID`.
2. Enable the APIs:
   ```bash
   gcloud services enable aiplatform.googleapis.com artifactregistry.googleapis.com bigquery.googleapis.com cloudbuild.googleapis.com cloudresourcemanager.googleapis.com iam.googleapis.com logging.googleapis.com run.googleapis.com secretmanager.googleapis.com serviceusage.googleapis.com
   ```
3. Create the sink, datasets, runtime service account and the empty salt secret:
   ```bash
   terraform -chdir=terraform init
   terraform -chdir=terraform apply -var project_id=YOUR_PROJECT_ID -var region=BILLING_EXPORT_LOCATION
   ```
   `region` is the BigQuery location of both datasets. It must be the same location as your billing export dataset (step 5): views cannot join datasets in different locations. If you reuse an existing export, read its location with `bq show --format=prettyjson PROJECT:DATASET` and pass it here (for example `EU` or `US`).
4. Generate the salt with a random generator and store it. It never enters Terraform state, your shell history or the screen. Only a random value from this generator is safe. The service checks the length (32 characters) but cannot detect a guessable value, and a predictable key lets anyone who knows your customer ids recompute every hash.
   ```bash
   openssl rand -base64 32 | gcloud secrets versions add customer-hash-salt --data-file=-
   ```
5. Turn on the detailed usage cost export in the console: Billing, Billing export, BigQuery export, Detailed usage cost, Edit settings. If your billing account already has this export, reuse it as it is and change nothing. Otherwise pick a project and a dataset (for example `billing_export`). The table is `gcp_billing_export_resource_v1_BILLING_ACCOUNT_ID`. Terraform does not cover this step. The export fills forward from the day you enable it; check the setup page for back-fill rules for your export type. Cost rows can take more than 24 hours to appear.
6. Allow source deploys. Cloud Build uses the Compute Engine default service account, which needs `roles/run.builder` ([source deploy docs](https://docs.cloud.google.com/run/docs/deploying-source-code)). Wait a couple of minutes for it to apply:
   ```bash
   PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format 'value(projectNumber)')
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member "serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
     --role roles/run.builder
   ```
   Then deploy the demo service from this folder. It runs as the runtime service account (Gemini access plus read access to the one secret), uses Application Default Credentials, and is private:
   ```bash
   gcloud run deploy tidewell-ai --source . --region europe-west1 \
     --service-account "$(terraform -chdir=terraform output -raw runtime_service_account)" \
     --set-env-vars GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
     --set-secrets CUSTOMER_HASH_SALT=customer-hash-salt:latest \
     --no-allow-unauthenticated
   ```
   The service refuses to start if the salt is missing or shorter than 32 characters. Gemini is called in location `global`, as the model page lists for `gemini-3.8-flash`.
7. Make a call, as a few customers and features:
   ```bash
   URL=$(gcloud run services describe tidewell-ai --region europe-west1 --format 'value(status.url)')
   curl -X POST "$URL/generate" \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" \
     -d '{"feature": "smart_reply", "customer_id": "acme-corp", "text": "Reply to: when is my invoice due?"}'
   ```
   Your own account needs `roles/run.invoker` on the service. The call is pay-as-you-go: labels are ignored for Provisioned Throughput.
8. Wait until both sources exist: the table `run_googleapis_com_stdout` in dataset `ai_usage_logs` (minutes), and rows in the billing export (more than 24 hours). Check the table name in BigQuery.
9. Find the Gemini service and SKU ids. Run `sql/00_discover_skus.sql` (replace the placeholders). It lists the ids on rows of your project that carry the `feature` label. You can also look them up in the [Cloud Billing Catalog API](https://docs.cloud.google.com/billing/v1/how-tos/catalog-api). Put them into `SERVICE_ID` and `SKU_ID_1`, `SKU_ID_2` in `sql/02_cost_from_billing.sql`. Use `BILLING_EXPORT_PROJECT` for the project that holds the export and `WORKLOAD_PROJECT` for the project that runs the service. They can differ.
10. In BigQuery, in dataset `ai_cost`, save `01` as view `tokens_daily` and `02` as view `cost_daily`. Create a table `ai_cost.customers (customer_hash STRING, customer_name STRING)` from your own customer list, hashed with the same salt. Terraform already made dataset `ai_dashboard`. Run `03`, then `04` (the dashboard view goes into `ai_dashboard`). Then authorize the views, so viewers never need access to the source data:
    ```bash
    terraform -chdir=terraform apply -var project_id=YOUR_PROJECT_ID -var region=BILLING_EXPORT_LOCATION \
      -var authorize_views=true -var billing_export_project=EXPORT_PROJECT -var billing_export_dataset=EXPORT_DATASET
    ```
    This adds the four views to the access lists of the log, billing export and cost datasets. It edits the billing export dataset's access list; the grants are removed again on `terraform destroy`.
11. Reconcile once with `sql/05_reconcile.sql`. It compares the spend your SKU filter keeps against all spend of the Gemini service in your project for the last 30 usage days, cost plus credits. The usage-day view will not match the console Cost table exactly: that table groups by invoice month and includes late usage. `cost_missing_from_filter` must be near zero; if not, add the missing SKU ids to `02`. Rows shown as `unlabelled` in `cost_daily` are spend that did not carry both labels.
12. Data Studio dashboard:
    1. Open [Data Studio](https://datastudio.google.com), Create, Report, BigQuery connector. Pick your project, dataset `ai_dashboard`, view `dashboard`.
    2. Data credentials: the BigQuery connector defaults to the owner's credentials, so anyone with report access would see customer-level cost. Open the data source, switch Data credentials to viewer's credentials, and give each viewer `roles/bigquery.dataViewer` on dataset `ai_dashboard` only, plus `roles/bigquery.jobUser` on the project that runs the query. The authorized view lets them read the dashboard without access to the logs, billing export or `ai_cost` datasets. Share the report with named people only.
    3. Add a time series (dimension `usage_date`, metric `cost`), a table (dimension `customer`, metrics `cost`, `calls`, `total_tokens`), and a bar chart (dimension `feature`, metric `cost`).
    4. Add a date range control and a customer filter.

Reading the numbers: `cost` is `NULL` for a day when billing has not arrived yet, not zero. `cost_per_call` is a daily average from two sources (billing and logs), not the price of one call.

Label limits to remember: 64 labels per call, 63 characters per key or value, lowercase letters, digits, underscore, dash. A key can hold at most 1,000 unique values over the account lifetime, so do not put a request id in a label. Forty customer hashes are fine.

### Timeouts and retries

The SDK timeout is 30 s per attempt, with up to 3 attempts on 429 and 503, so one request can wait about 90 s plus back-off. Set the Cloud Run request timeout above that and give your callers their own deadline. A retry replays the whole generation, so a retried call can be billed twice. The usage line is written once per `generate()` call, after the last response, so it records the final attempt's tokens. When all attempts fail the service answers `503 model unavailable` and logs only the status code, never the prompt or the customer id.

## Clean up

Do these in order.

1. Stop the workload: `gcloud run services delete tidewell-ai --region europe-west1`. Delete only this tutorial's images. The repository `cloud-run-source-deploy` is shared by every source-deployed service in the project and region, so never delete it. List it with `gcloud artifacts docker images list europe-west1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy` and delete the `tidewell-ai` entries with `gcloud artifacts docker images delete IMAGE_PATH --delete-tags`.
2. Delete the tutorial-owned Data Studio report and data source in Data Studio.
3. Destroy the Terraform resources. Both datasets are set to delete their contents, so the log tables, your saved views and the customers table go with them. The secret and the service account go too:
   ```bash
   terraform -chdir=terraform destroy -var project_id=YOUR_PROJECT_ID
   ```
4. In the console, turn off the detailed usage cost export and delete the billing export dataset, but only if you created them for this tutorial. If you reused an existing export, leave it in place.
5. Terraform leaves the APIs enabled (`disable_on_destroy = false`), because other things in a project may use them. In a dedicated tutorial project, disable them with `gcloud services disable API_NAME --force`, or delete the project.

## What this costs

Prices change, so read the pages: [BigQuery pricing](https://cloud.google.com/bigquery/pricing), [Cloud Logging pricing](https://cloud.google.com/logging/pricing), [Cloud Run pricing](https://cloud.google.com/run/pricing), [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing), [Gemini pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing). The sink stores one small row per Gemini call; the billing export grows with all your usage. Data Studio is free.

## How this was checked

Unit tests with mocked Google clients (log line fields, hash vector, label rules including the 63 and 64 character edge and a trailing newline, weak salt, clean 503), `sqlglot` parsing of the SQL in the BigQuery dialect, and the final join run on fixture rows (matched, billing-only, log-only) with the sqlglot Python engine. The service answers 503 for SDK transport errors and Google auth transport or refresh errors (tested with a fake httpx2-style error). Also ruff and `terraform fmt`. `terraform validate` runs in CI. Not run on a live project: the log table name, the Gemini service and SKU ids, and the billing queries need a look against your own tables (see `FACTS.md`, "Not verified"). The cost query itself (02) is checked by text only, not on fixture rows.

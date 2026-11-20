# Facts and sources

Format: claim | URL | date checked.

- Current Gemini Flash model id is `gemini-3.8-flash` | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models | 2026-11-20
- Request labels: up to 64 per call; key 1 to 63 chars, value 0 to 63 chars; lowercase letters, digits, underscore, dash; key must start with a lowercase letter; max 1,000 unique values per key over the billing account lifetime; supported on generateContent and streamGenerateContent; ignored for Provisioned Throughput; no PII | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/add-labels-to-api-calls | 2026-11-20
- `google-genai` 3.6.1: `GenerateContentConfig.labels: dict[str, str]`; `usage_metadata` fields `prompt_token_count`, `candidates_token_count`, `cached_content_token_count`, `thoughts_token_count`, `total_token_count`; `HttpOptions(timeout, retry_options)`; `HttpRetryOptions(attempts, http_status_codes, ...)`; checked by introspecting the installed package | https://googleapis.github.io/python-genai/ | 2026-11-20
- Detailed usage export table `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>`; columns `labels` (key, value), `service.description`, `sku.description`, `cost`, `credits` (amount), `usage_start_time`, `project.id` | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage | 2026-11-20
- Label grouping uses `JOIN UNNEST(labels) ... ON labels.key = ...`; cost plus credits uses `SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0))` | https://docs.cloud.google.com/billing/docs/how-to/bq-examples | 2026-11-20
- Log sink to BigQuery: partitioned tables are named after the log id only; jsonPayload fields become columns (names lowercased) | https://docs.cloud.google.com/logging/docs/export/bigquery | 2026-11-20
- `google_logging_project_sink` arguments `name`, `destination`, `filter`, `unique_writer_identity`, `bigquery_options.use_partitioned_tables`; attribute `writer_identity` | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/logging_project_sink.html.markdown | 2026-11-20

- Sink writer needs `roles/bigquery.dataEditor` on the destination dataset | https://docs.cloud.google.com/logging/docs/export/configure_export_v2 | 2026-11-20
- Cloud Run stdout log id is `run.googleapis.com/stdout`; JSON lines become jsonPayload | https://docs.cloud.google.com/run/docs/logging | 2026-11-20
- Agent Platform role `roles/aiplatform.user` includes `aiplatform.endpoints.predict` | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/access-control | 2026-11-20
- `gemini-3.8-flash` is available in location `global` | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash | 2026-11-20
- Terraform resources used: `google_project_service`, `google_bigquery_dataset` (`delete_contents_on_destroy`), `google_logging_project_sink`, `google_bigquery_dataset_iam_member`, `google_service_account`, `google_project_iam_member`, `google_secret_manager_secret` (`replication { auto {} }`), `google_secret_manager_secret_iam_member` | https://registry.terraform.io/providers/hashicorp/google/latest/docs | 2026-11-20
- Commands: `gcloud services enable`, `gcloud run deploy --source --service-account --set-secrets --set-env-vars --no-allow-unauthenticated`, `gcloud secrets versions add --data-file=-`, `gcloud artifacts repositories delete` | https://docs.cloud.google.com/sdk/gcloud/reference | 2026-11-20
- SDK: `HttpOptions.timeout` is per request attempt (milliseconds); `HttpRetryOptions` retries replay the request | https://github.com/googleapis/python-genai/blob/v3.6.1/google/genai/types.py | 2026-11-20
- The product is now called Data Studio (was Looker Studio) | https://docs.cloud.google.com/data-studio/welcome | 2026-11-20
- Cloud Build deploys from source as the Compute Engine default service account (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`), which needs `roles/run.builder` | https://docs.cloud.google.com/run/docs/deploying-source-code | 2026-11-20
- google-genai 3.6.1 uses httpx, httpx2 or aiohttp; httpx2 errors are not httpx errors | installed package source `google/genai/_api_client.py` | 2026-11-20

## Not verified

- The billing export page did not state whether `labels` is repeated; the example queries use `UNNEST(labels)`, so the SQL does too.
- Sink table name `run_googleapis_com_stdout` is derived from the Cloud Run log id `run.googleapis.com/stdout` by the documented naming rule; the docs have no stdout example. Check the table name in BigQuery after the first rows arrive.
- The Gemini `service.id` and `sku.id` values are not known; the SQL uses placeholders and `00_discover_skus.sql` finds them in your own export.
- The new Terraform resources (secret, service account, dataset `delete_contents_on_destroy`) passed `terraform fmt` only; `terraform validate` needs the registry and runs in CI.
- Billing export setup (console only, no Terraform resource found for the detailed export) not re-checked against a Terraform reference page.

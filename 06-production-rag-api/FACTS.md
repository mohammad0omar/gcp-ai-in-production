# Facts and sources

Format: claim | URL | date checked.

- Embedding model `gemini-embedding-001`, default 3072 dimensions, `output_dimensionality` shrinks it; page also lists `gemini-embedding-2` for long and mixed media | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings | 2026-11-20
- google-genai call `client.models.embed_content(model, contents, config=EmbedContentConfig(task_type, output_dimensionality))`; response `.embeddings[i].values` | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings | 2026-11-20
- Task types include `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY`; supported by `gemini-embedding-001` | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/task-types | 2026-11-20
- Embedding request limits: 250 texts and 20000 tokens per request, 2048 tokens per text. The one-text limit is for the documented REST `:predict` route; google-genai 3.6.1 uses `:batchEmbedContents` for many inputs and `:embedContent` for one (code read), so batching 16 is used; hosted behaviour at `global` not exercised | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings | 2026-11-20
- Gemini answer model `gemini-3.8-flash`, location `global` (checked earlier today for folder 01) | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash | 2026-11-20
- Cloud SQL supports pgvector 0.8.5 on PostgreSQL 13 and later | https://docs.cloud.google.com/sql/docs/postgres/extensions | 2026-11-20
- Cloud SQL latest PostgreSQL major is 18 (default); Terraform `database_version = "POSTGRES_18"` | https://docs.cloud.google.com/sql/docs/db-versions | 2026-11-20
- pgvector: HNSW indexes on `vector` support at most 2000 dimensions; `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`; cosine distance operator `<=>` | https://github.com/pgvector/pgvector | 2026-11-20
- `google_sql_database_instance`: `edition` must be `ENTERPRISE` for custom tiers on PostgreSQL 16+; `ip_configuration.ipv4_enabled`, `private_network`; needs `depends_on` the service networking connection; `deletion_protection` | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/sql_database_instance.html.markdown | 2026-11-20
- Database flag `cloudsql.iam_authentication = on` enables IAM database authentication | https://docs.cloud.google.com/sql/docs/postgres/create-edit-iam-instances | 2026-11-20
- `google_sql_user` type `CLOUD_IAM_SERVICE_ACCOUNT`, Postgres name is the email without `.gserviceaccount.com`, no password | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/sql_user.html.markdown | 2026-11-20
- `roles/cloudsql.instanceUser` allows login (`cloudsql.instances.login`); `roles/cloudsql.client` gives `cloudsql.instances.connect` | https://docs.cloud.google.com/sql/docs/postgres/iam-logins | 2026-11-20
- `cloud-sql-python-connector[pg8000]`: `Connector(ip_type="private", enable_iam_auth=True, timeout=30, refresh_strategy="lazy")`, `connect(instance, "pg8000", user, db, enable_iam_auth=True)`; "lazy" recommended on Cloud Run | https://github.com/GoogleCloudPlatform/cloud-sql-python-connector | 2026-11-20
- `google_cloud_run_v2_service` and job template `vpc_access { egress, network_interfaces { network, subnetwork } }` (direct VPC egress); `timeout`; `deletion_protection` defaults true | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/cloud_run_v2_service.html.markdown | 2026-11-20
- Cloud Trace via OTLP: packages `opentelemetry-exporter-otlp-proto-grpc`, `google-auth`, `grpcio`; endpoint `telemetry.googleapis.com`; the older `CloudTraceSpanExporter` repo is deprecated with a migration to OTLP | https://github.com/GoogleCloudPlatform/opentelemetry-operations-python/blob/main/MIGRATION.md | 2026-11-20
- Cloud Trace API must stay enabled: with `cloudtrace.googleapis.com` disabled, OTLP trace data is discarded | https://docs.cloud.google.com/trace/docs/setup | 2026-11-20
- Role for writing traces is `roles/telemetry.tracesWriter` (Cloud Telemetry Traces Writer) | https://docs.cloud.google.com/trace/docs/setup/python-ot | 2026-11-20
- Vertex AI role `roles/aiplatform.user` is "Agent Platform User" | https://docs.cloud.google.com/vertex-ai/docs/general/access-control | 2026-11-20
- Google provider `~> 8.0` (latest release 8.12.0 per folder 01 check) | https://github.com/hashicorp/terraform-provider-google/releases | 2026-11-20

- `google_sql_user.database_roles` (Postgres and MySQL 8+) e.g. `["cloudsqlsuperuser"]`; IAM users otherwise start with no privileges; CREATE EXTENSION needs cloudsqlsuperuser | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/sql_user.html.markdown | 2026-11-20
- `google_service_networking_connection.deletion_policy`: default and `DELETE` delete the connection; `ABANDON` leaves the peering and blocks network deletion; `REMOVE_PEERING` is the teardown escape hatch | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/service_networking_connection.html.markdown | 2026-11-20
- Delete a private services connection: `gcloud services vpc-peerings delete --service=servicenetworking.googleapis.com --network=NETWORK`; Cloud SQL producer resources are kept for 4 days after instance deletion | https://docs.cloud.google.com/vpc/docs/configure-private-services-access | 2026-11-20
- `gcloud builds submit --tag --service-account --gcs-source-staging-dir --gcs-log-dir`; a `.gcloudignore` overrides `.gitignore`; upload list checked locally with `gcloud meta list-files-for-upload` | https://docs.cloud.google.com/sdk/gcloud/reference/builds/submit | 2026-11-20
- Terraform resources used: `google_compute_network`, `google_compute_subnetwork`, `google_compute_global_address`, `google_service_networking_connection`, `google_sql_database_instance`, `google_sql_database`, `google_sql_user`, `google_cloud_run_v2_service`, `google_cloud_run_v2_job`, `google_cloud_run_v2_service_iam_member`, `google_storage_bucket`, `google_*_iam_member`, `google_artifact_registry_repository`, `google_project_service` | https://registry.terraform.io/providers/hashicorp/google/latest/docs | 2026-11-20 (field names from the provider docs fetched above; `terraform validate` runs in CI only)
- `uv export --no-dev --no-hashes --no-emit-project` writes pinned requirements from `uv.lock` | https://docs.astral.sh/uv/reference/cli/#uv-export | 2026-11-20

## Not verified

- The exact OTLP gRPC endpoint form: the page shows `telemetry.googleapis.com`; the code uses `telemetry.googleapis.com:443`. Check on a live project.
- That the Telemetry API is the API name to enable for `roles/telemetry.tracesWriter` (`telemetry.googleapis.com`); the Trace page does not name an API.
- That `rag-admin` (created with `database_roles = ["cloudsqlsuperuser"]`) can `CREATE EXTENSION vector` and `GRANT` on `chunks` on a live instance; and that the `public` schema grants `USAGE`/`CREATE` as the ingest and API users expect on PostgreSQL 18.
- pg8000 handling of an array parameter (`doc_id <> ALL(%s)` with a Python list); not run against a database. The grant SQL uses `quote_ident` (no `%` tokens), checked through pg8000 `convert_paramstyle` in a test.
- That pg8000 accepts `CAST(%s AS vector)` with a string parameter. This is the standard cast; not run against a database.
- `google_cloud_run_v2_job` nested `template.template.vpc_access`, the `dynamic "env"` blocks and the `merge([...]...)` local: written from provider knowledge; CI `terraform validate` will catch schema errors.
- Cloud Run direct VPC egress subnet size (a /24 is used) and Cloud SQL tier `db-custom-1-3840` for pgvector workloads.
- `MAX_DISTANCE = 0.45` is a starting value, not measured.
- Whether Gemini embeddings at 768 dimensions give the quality the eval needs; truncated outputs are not normalised, which does not matter for cosine distance.

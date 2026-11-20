# Facts and sources

Format: claim | URL | date checked.

- Model id `gemini-3.8-flash`; Standard PayGo lists only `global` and multi-regions `us`, `eu`; the broader tables add `northamerica-northeast1` and `asia-northeast1` (data residency, Provisioned Throughput); europe-west1 is not listed, so Gemini location defaults to `global` | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash | 2026-11-20
- `roles/aiplatform.user` is "Agent Platform User" | https://docs.cloud.google.com/vertex-ai/docs/general/access-control | 2026-11-20
- `google-genai`: `GenerateContentConfig` has `response_mime_type`, `response_schema`, `system_instruction`, `http_options`; `HttpOptions.timeout` | https://googleapis.github.io/python-genai/ (also introspected, google-genai 3.6.1) | 2026-11-20
- DLP `deidentify_content(request={parent, inspect_config, deidentify_config, item})`, parent `projects/P/locations/L`, listing info types avoids default ALL_BASIC scan | https://docs.cloud.google.com/sensitive-data-protection/docs/deidentify-sensitive-data | 2026-11-20
- `PrimitiveTransformation.replace_with_info_type_config` exists (the doc page shows `replace_config` only) | https://docs.cloud.google.com/python/docs/reference/dlp/latest/google.cloud.dlp_v2.types.PrimitiveTransformation (also introspected, google-cloud-dlp 3.40.0) | 2026-11-20
- `roles/dlp.user` is "Inspect, Redact, and De-identify Content" | https://docs.cloud.google.com/sensitive-data-protection/docs/iam-roles | 2026-11-20
- `roles/datastore.user` gives read/write to Firestore data, includes `datastore.entities.*` | https://docs.cloud.google.com/firestore/docs/security/iam | 2026-11-20
- Push body has `message.data` (base64), `message.messageId`, `subscription`; 102, 200, 201, 202, 204 ack, anything else nacks | https://docs.cloud.google.com/pubsub/docs/push | 2026-11-20
- Push OIDC claims `aud`, `email`, `email_verified`; verify with `id_token.verify_oauth2_token(token, requests.Request(), audience=...)`, which checks signature, aud, exp; email checks are ours; Pub/Sub service agent needs `roles/iam.serviceAccountTokenCreator` on the push SA; push SA needs `roles/run.invoker` | https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions | 2026-11-20
- Dead letter: service agent needs `roles/pubsub.publisher` on the dead letter topic and `roles/pubsub.subscriber` on the subscription; max delivery attempts 5 to 100 | https://docs.cloud.google.com/pubsub/docs/dead-letter-topics | 2026-11-20
- `google_pubsub_subscription` (resource page is the same for the next four rows): `push_config.oidc_token.{service_account_email,audience}`, `dead_letter_policy.{dead_letter_topic,max_delivery_attempts}`, `retry_policy`, `ack_deadline_seconds` | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/pubsub_subscription.html.markdown | 2026-11-20
- `google_cloud_run_v2_service` (own page): `custom_audiences`, `deletion_protection`, `ingress`, `template.{service_account,timeout,scaling.max_instance_count,containers.{image,env}}` | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/cloud_run_v2_service.html.markdown | 2026-11-20
- `google_firestore_database` (own page): `name, `location_id`, `type`, `deletion_policy = "DELETE"` | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/firestore_database.html.markdown | 2026-11-20
- gcloud `pubsub topics publish --message` | https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/topics/publish | 2026-11-20
- gcloud `pubsub subscriptions pull --limit` (and `--auto-ack`, not used) | https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions/pull | 2026-11-20
- gcloud `auth configure-docker HOST` | https://docs.cloud.google.com/sdk/gcloud/reference/auth/configure-docker | 2026-11-20
- gcloud `services enable` and `services disable` take a list of service names | https://docs.cloud.google.com/sdk/gcloud/reference/services/disable | 2026-11-20
- `genai.Client(enterprise=True, project, location)` is the current spelling; `vertexai=True` is a legacy alias | https://googleapis.github.io/python-genai/ (parameter present in google-genai 3.6.1) | 2026-11-20
- Firestore `WriteBatch.create(reference, data)` and `commit(timeout=)`, `DocumentReference.get(timeout=)`: batch commit is atomic; create fails if the document exists | https://docs.cloud.google.com/python/docs/reference/firestore/latest/google.cloud.firestore_v1.batch.WriteBatch | 2026-11-20
- `google.auth.transport.requests.Request.__call__` has `timeout=120` default; `verify_oauth2_token` can raise `ValueError` and `GoogleAuthError`; cert fetch failures are `TransportError` | https://google-auth.readthedocs.io/en/latest/_modules/google/oauth2/id_token.html | 2026-11-20
- `google_pubsub_subscription` `expiration_policy.ttl`: default 31 days, `""` never expires, `message_retention_duration` | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/pubsub_subscription.html.markdown | 2026-11-20
- Pub/Sub dead letter max delivery attempts is a best-effort count | https://docs.cloud.google.com/pubsub/docs/dead-letter-topics | 2026-11-20
- DLP detectors are probabilistic; see the infoType reference | https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-infotypes | 2026-11-20
- Google provider `~> 8.0` | https://github.com/hashicorp/terraform-provider-google/releases | 2026-11-20

- IAM member resources `google_cloud_run_v2_service_iam_member` (name, location, role, member), `google_pubsub_subscription_iam_member` (subscription), `google_pubsub_topic_iam_member` (topic), `google_service_account_iam_member` (service_account_id) | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/pubsub_topic_iam.html.markdown | 2026-11-20

- google-api-core default retry for gapic calls has a long window (DLP and Firestore reads 300 s, commit 60 s), so the app passes `retry=None` with `timeout=` | https://googleapis.dev/python/google-api-core/latest/retry.html | 2026-11-20
- Gen AI SDK retryable HTTP codes include 408, 429, 500, 502, 503, 504, and it may use `httpx` or `httpx2` | https://github.com/googleapis/python-genai/blob/main/google/genai/_api_client.py | 2026-11-20

## Not verified

- That the Gen AI SDK `HttpOptions.timeout` unit is milliseconds: read from the SDK source description, not tested against the service.
- That a real `WriteBatch.commit` surfaces an existing document as `AlreadyExists` (the tests use a fake that raises it).
- That Firestore `timeout` bounds the whole call including retries; treat the 65 s worst case as an estimate.
- The leftover regex (email, 13 to 19 digit runs) is a heuristic and can send harmless emails with long order numbers to needs_review.

- That every one of the four info types is available in the DLP location you choose. `DLP_LOCATION` defaults to `global`; check the regional support list before setting a region.
- That the Cloud Run custom audience matches the OIDC `aud` for a push endpoint exactly as configured; verify with a live publish.
- The `google_firestore_database` for a project that already has a `(default)` database: terraform would fail to create it.
- DLP pricing unit: the pricing page body could not be read here; the README only links it.

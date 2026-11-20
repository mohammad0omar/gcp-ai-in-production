# Facts and sources

Format: claim | URL | date checked.

- Primary model id `gemini-3.8-flash`, GA; locations global, multi-regions us and eu, plus Provisioned Throughput on global | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash | 2026-11-20
- Fallback model id `gemini-3.5-flash-lite`, GA, listed for global, retirement July 21 2027 or later | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite | 2026-11-20
- `gemini-3.7-flash` is GA but retires 2027-01-28, so it was not chosen as the fallback | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-7-flash | 2026-11-20
- Vertex AI is now named Gemini Enterprise Agent Platform in the docs | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/quotas | 2026-11-20
- `genai.Client(vertexai=True, project, location="global", http_options=HttpOptions(timeout=<ms>))` is the documented pattern; the SDK also accepts `enterprise=True` (the locations page uses it); checked by introspecting google-genai 3.6.1 | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/retry-strategy | 2026-11-20
- `HttpOptions.timeout` is in milliseconds; `GenerateContentConfig.http_options` sets it per request (introspected in google-genai 3.6.1) | https://googleapis.github.io/python-genai/ | 2026-11-20
- With no `retry_options` the SDK makes one attempt and does not retry (`retry_args(None)` stops after 1), so the client adds no hidden retries under ours | https://googleapis.github.io/python-genai/ | 2026-11-20
- `errors.APIError` has `.code`, `.status`, `.message`, `.response` (httpx response, headers available); subclasses `ClientError`, `ServerError` | https://googleapis.github.io/python-genai/ | 2026-11-20
- `usage_metadata.cached_content_token_count` holds cached input tokens | https://googleapis.github.io/python-genai/ | 2026-11-20
- Docs list 408, 429 and 5xx as transient and say 400 and 401 should not be retried; the SDK built-in option defaults are initial_delay 1.0, attempts 5, exp_base 2, max_delay 60, jitter 1 | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/retry-strategy | 2026-11-20
- Global endpoints cover the entire world, give higher availability than a single region, and do not guarantee data residency or in-region ML processing | https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations | 2026-11-20
- Quotas: Cloud console, "Quotas & System Limits" page, filter by quota name and request an adjustment for adjustable quotas | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/quotas | 2026-11-20
- Provisioned Throughput is a fixed-cost, fixed-term subscription that reserves throughput for a model in chosen locations | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/provisioned-throughput | 2026-11-20
- 429 troubleshooting page | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/deploy/error-code-429 | 2026-11-20

- gcloud commands used: `projects create`, `billing projects link --billing-account`, `services enable --project`, `auth application-default login|set-quota-project|revoke`, `projects delete`, `projects remove-iam-policy-binding` | https://docs.cloud.google.com/sdk/gcloud/reference | 2026-11-20
- Inference permission is `aiplatform.endpoints.predict`; `roles/aiplatform.user` is the predefined role | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/access-control | 2026-11-20
- Pricing: charged only for 200 responses; 4xx and 5xx are not charged for input or output | https://cloud.google.com/model-garden/pricing | 2026-11-20
- Standard PayGo runs on shared capacity with usage tiers over a rolling 30 days | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/standard-paygo | 2026-11-20
- google-genai 3.6.1 `generate_content` follows continuation tokens by default; `GenerateContentConfig.automatic_continuation=False` turns it off. Per-request `HttpOptions.retry_options=HttpRetryOptions(attempts=1)` overrides client-level retries (confirmed with a mock transport test) | https://github.com/googleapis/python-genai/blob/v3.6.1/google/genai/models.py | 2026-11-20
- `Retry-After` may be delta-seconds or an HTTP-date | https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3 | 2026-11-20
- `genai.Client.close()` closes the sync client | https://googleapis.github.io/python-genai/ | 2026-11-20
- FastAPI lifespan for startup and shutdown | https://fastapi.tiangolo.com/advanced/events/ | 2026-11-20
- Data residency controls page | https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/data-residency | 2026-11-20
- Terraform validation: not applicable, no Terraform in this folder

## Not verified

- Whether Gemini error responses on the global endpoint ever carry a `Retry-After` header. The code reads it when present and falls back to jitter when absent.
- Pricing numbers: no totals are given in the README on purpose.
- The exact gcloud flags were not run (no live project); they follow the gcloud reference.
- Behaviour against a live project: nothing here was run against Google Cloud.

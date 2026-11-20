# Facts and sources

Format: claim | URL | date checked.

- Current Gemini Flash model id is `gemini-3.8-flash`, listed as generally available | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models | 2026-11-20
- Model page for `gemini-3.8-flash`: id string; locations global, multi-regions us and eu; europe-west1 not listed, so Gemini location defaults to `global` | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash | 2026-11-20
- Vertex AI is now named Gemini Enterprise Agent Platform in the IAM docs; role `roles/aiplatform.user` is "Agent Platform User" | https://docs.cloud.google.com/vertex-ai/docs/general/access-control | 2026-11-20
- `google-genai` Client(vertexai=True, project, location), `models.generate_content(model, contents, config)`, `GenerateContentConfig.system_instruction`, `errors.APIError(code, response_json)` with `ClientError`/`ServerError` subclasses; checked by introspecting google-genai 3.6.1 | https://googleapis.github.io/python-genai/ | 2026-11-20
- GitHub OIDC issuer `https://token.actions.githubusercontent.com`, attribute condition and principalSet format, `roles/iam.workloadIdentityUser` | https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines | 2026-11-20
- `google_iam_workload_identity_pool_provider` arguments (attribute_mapping, attribute_condition, oidc.issuer_uri) | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/iam_workload_identity_pool_provider.html.markdown | 2026-11-20
- `google_org_policy_policy` arguments (name, parent, spec.rules.enforce = "TRUE") | https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/org_policy_policy.html.markdown | 2026-11-20
- Google provider latest release is 8.12.0, so `~> 8.0` | https://github.com/hashicorp/terraform-provider-google/releases | 2026-11-20
- Constraint to block key creation: managed `iam.managed.disableServiceAccountKeyCreation` (recommended), legacy `iam.disableServiceAccountKeyCreation`; not retroactive | https://docs.cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts | 2026-11-20
- `google-github-actions/auth` v3.0.0 = 7c6bc770dae815cd3e89ee6cdf493a5fab2cc093: inputs `workload_identity_provider`, `service_account`; job needs `id-token: write` | https://github.com/google-github-actions/auth/releases/tag/v3.0.0 | 2026-11-20
- `google-github-actions/setup-gcloud` v3.0.1 = aa5489c8933f4cc7a4f7d45035b3b1440c9c10db | https://github.com/google-github-actions/setup-gcloud/releases/tag/v3.0.1 | 2026-11-20
- `actions/checkout` v7.0.1 = 3d3c42e5aac5ba805825da76410c181273ba90b1 | https://github.com/actions/checkout/releases/tag/v7.0.1 | 2026-11-20
- `hashicorp/setup-terraform` v4.0.1 = dfe3c3f87815947d99a8997f908cb6525fc44e9e | https://github.com/hashicorp/setup-terraform/releases/tag/v4.0.1 | 2026-11-20
- `astral-sh/setup-uv` v10.3.3 = 68559e99cc807c1eb7e9238fd43a15bba460eec2 (there is no `v10` tag as a release; `python-version` input) | https://github.com/astral-sh/setup-uv/releases/tag/v10.3.3 | 2026-11-20

- Runtime uses predefined `roles/aiplatform.user` (Agent Platform User); the generateContent reference names `aiplatform.endpoints.predict` as the permission, but a custom role with only that permission was not tested | https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.endpoints/generateContent | 2026-11-20
- Disabling or re-enabling the Invoker IAM check needs run.services.create, update and setIamPolicy (in roles/run.admin); the check is on by default; `gcloud run ... --invoker-iam-check` enables it | https://docs.cloud.google.com/run/docs/authenticating/public | 2026-11-20
- `gcloud run deploy` flags `--[no-]allow-unauthenticated`, `--[no-]invoker-iam-check`, `--service-account`, `--set-env-vars` | https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy | 2026-11-20
- Google recommends numeric repository_id (and owner id) over names in WIF conditions | https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines | 2026-11-20
- google_project_service needs Service Usage API; org policy API is orgpolicy.googleapis.com | https://docs.cloud.google.com/organization-policy/reference/rest/v2/projects.policies/create | 2026-11-20
- Deleted workload identity pools are kept 30 days | https://docs.cloud.google.com/iam/docs/manage-workload-identity-pools-providers | 2026-11-20
- `genai.types.HttpOptions(timeout=...)` is in milliseconds | https://googleapis.github.io/python-genai/ | 2026-11-20
- Gemini location: `global` and multi-regions us/eu for Standard PayGo; other regions listed on the model page apply to ML processing or Provisioned Throughput only | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-8-flash | 2026-11-20

- google-genai 3.6.1 (pinned in app/requirements.txt) depends on httpx2, not httpx; checked by `uv pip show google-genai` and by reading its _api_client imports | https://github.com/googleapis/python-genai/releases/tag/v3.0.0 | 2026-11-20

## Not verified

- The managed org policy now uses the project number in name and parent (canonical form); not applied live.
- Whether run.admin can be narrowed with an IAM condition on the service name; not tested, so it stays project-wide (README says so).
- SHAs were resolved with the GitHub API on 2026-11-20 but not code-reviewed.

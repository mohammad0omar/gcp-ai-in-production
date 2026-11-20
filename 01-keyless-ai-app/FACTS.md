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
- `google-github-actions/auth@v3`: inputs `workload_identity_provider`, `service_account`; job needs `id-token: write` | https://github.com/google-github-actions/auth | 2026-11-20
- `google-github-actions/setup-gcloud@v3` | https://github.com/google-github-actions/setup-gcloud | 2026-11-20
- `actions/checkout@v7` | https://github.com/actions/checkout | 2026-11-20
- `hashicorp/setup-terraform@v4` | https://github.com/hashicorp/setup-terraform | 2026-11-20
- `astral-sh/setup-uv@v10` with `python-version` input | https://github.com/astral-sh/setup-uv | 2026-11-20

## Not verified

- Whether the managed constraint accepts a project-level policy name with the project id (Terraform `name` doc says project number; id is used here). Verify with `terraform plan` before you rely on it.
- That `roles/aiplatform.user` is the smallest role for `generateContent`. The IAM page lists it as the usage role; no narrower role was confirmed.
- Whether `run.admin` can be narrowed for this deploy. Cloud Run admin is used because deploy needs create and update on services.

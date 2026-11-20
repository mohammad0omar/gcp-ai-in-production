# 01 Keyless AI app

Harbor Lane is a small team. Their FastAPI service on Cloud Run summarises support notes with Gemini. It is deployed from GitHub Actions. There is no service account key and no Gemini API key anywhere.

```text
GitHub Actions job
  -> OIDC token (id-token: write)
  -> Workload Identity Federation (pins this repo AND the main branch)
  -> impersonates the deploy service account (Cloud Run admin, Artifact Registry writer, actAs runtime)
  -> deploys Cloud Run as the runtime service account (roles/aiplatform.user only)
  -> app calls Gemini with ADC: genai.Client(vertexai=True, ...)
```

## Steps

You need a project you can bill (use a disposable one: see Clean up), `gcloud`, `terraform`, the `gh` CLI, and these permissions on the project: Project IAM Admin, Service Account Admin, Workload Identity Pool Admin, Service Usage Admin, Artifact Registry Administrator. To grant yourself invoke rights and read the service URL in step 6 you also need Cloud Run Admin (or at least `run.services.getIamPolicy`, `run.services.setIamPolicy` and `run.services.get`) on the project. The `gh api` commands need `gh auth login` first. For the optional key policy the project must sit under an organization, and you need `roles/orgpolicy.policyAdmin` granted at the organization level (it cannot be granted on a project). Skip that option if you cannot get it. These steps change your project. Run them yourself.

1. Sign in and set the variables used below. `gcloud auth application-default login` gives Terraform its credentials.
   ```bash
   gcloud auth login
   gcloud auth application-default login
   export PROJECT_ID=YOUR_PROJECT_ID REGION=europe-west1 REPO=OWNER/NAME
   gcloud config set project "$PROJECT_ID"
   export REPO_ID=$(gh api "repos/$REPO" --jq .id) OWNER_ID=$(gh api "repos/$REPO" --jq .owner.id)
   ```
   `REGION` is where Cloud Run and Artifact Registry live. Gemini is called in `global` (`GEMINI_LOCATION` in `config.py`): the Gemini 3.8 Flash model page lists `global` and the `us` and `eu` multi-regions for pay-as-you-go use, not `europe-west1`. Check the page before you change either.
2. Enable the one API Terraform needs to enable the others: `gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com`. Terraform enables the rest (see `REQUIRED_APIS` in `config.py`).
3. Create the identity setup, from the folder that holds this README:
   ```bash
   terraform -chdir=terraform init
   terraform -chdir=terraform apply -var project_id="$PROJECT_ID" -var region="$REGION" \
     -var github_repo="$REPO" -var github_repository_id="$REPO_ID" -var github_owner_id="$OWNER_ID"
   ```
   Run `plan` first if you want to read what it will create. Add `-var block_key_creation=true` to forbid service account keys in this project (needs that organization-level role; the repo of the first apply must be the one you want, because the pool trusts the numeric repository id, not the name).
4. Set repository variables in GitHub (Settings, Secrets and variables, Actions, Variables). `GCP_PROJECT_ID` is your `$PROJECT_ID` and `GCP_REGION` is your `$REGION`; take the other three from `terraform -chdir=terraform output`:
   `GCP_PROJECT_ID`, `GCP_REGION`, `WORKLOAD_IDENTITY_PROVIDER` (output `workload_identity_provider`), `DEPLOY_SERVICE_ACCOUNT` (output `deploy_service_account`), `RUNTIME_SERVICE_ACCOUNT` (output `runtime_service_account`).
5. Copy `.github-example/deploy.yml` to `.github/workflows/deploy.yml` in your repo, and `app/`, `config.py`, `Dockerfile` and `.dockerignore` to the repo root next to it. Add `gha-creds-*.json` to your own `.gitignore` too (the auth action writes a temporary `gha-creds-*.json` file, an external-account configuration with no private key, and removes it after the job; it is already in this folder's `.dockerignore`). Push to `main`. Pushes from other branches cannot get a token: the provider condition rejects them. Runs are serialized with `cancel-in-progress: false`, so a running deploy is never cut off. GitHub keeps one waiting run per group, so a newer push can replace a queued one, which is fine because the newest run deploys `main`. Do not re-run an old workflow run to redeploy; push a commit or use workflow_dispatch on main, because GitHub keeps only one pending run per group. A run fails instead of deploying when `main` has already moved on (for example when you re-run an old job).
6. Call the service. It is private, so your own account needs permission to read the service and to invoke it:
   ```bash
   gcloud run services add-iam-policy-binding note-summariser --region "$REGION" --project "$PROJECT_ID" \
     --member "user:YOU@example.com" --role roles/run.invoker
   URL=$(gcloud run services describe note-summariser --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')
   curl -X POST "$URL/summarize" \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" \
     -d '{"text": "Customer says the door code stopped working after the update."}'
   ```
   The `curl` uses your active gcloud account (`gcloud auth list`), which must be the account you granted Invoker. A new IAM binding can take a few minutes: if you get `403`, wait and retry. An unauthenticated call (the same `curl` without the header) must return `403`. Check that too.

When Gemini is busy or rate limited the service answers `503` with `Retry-After: 5`. A call that times out (30 s, the SDK's HTTP timeout) returns `504`, and an empty or blocked answer returns `502`. If your caller retries a `POST`, each retry can be billed as another Gemini call.

## Limits you should know

- The deploy account has Cloud Run Admin on the whole project. This is accepted on purpose: the workflow sets the service's invoker IAM policy (`--no-allow-unauthenticated`, `--invoker-iam-check`), which needs `run.services.setIamPolicy`, and Cloud Run Developer does not have it. Use a project that holds only this service. To narrow it later, replace `roles/run.admin` in `terraform/main.tf` with a custom role that has `run.services.create`, `run.services.update`, `run.services.get`, `run.services.getIamPolicy`, `run.services.setIamPolicy` and `run.operations.get`, and keep the `roles/iam.serviceAccountUser` binding on the runtime account (that is the `iam.serviceAccounts.actAs` permission).
- The runtime account has the predefined role `roles/aiplatform.user` (Agent Platform User), the documented role for calling Gemini. A narrower custom role, for example with only `aiplatform.endpoints.predict`, is possible, but test it on a real project before you rely on it: this repo did not.
- The pool trusts the numeric repository and owner ids and the `main` branch. If you delete and recreate the repository, the ids change and you must apply again.

## Clean up

The easiest clean up is to delete the whole project if it was created for this tutorial: `gcloud projects delete "$PROJECT_ID"`. Otherwise, from the folder that holds this README, with the same variables as in step 1:

```bash
gcloud run services delete note-summariser --region "$REGION" --project "$PROJECT_ID"
terraform -chdir=terraform destroy -var project_id="$PROJECT_ID" -var region="$REGION" \
  -var github_repo="$REPO" -var github_repository_id="$REPO_ID" -var github_owner_id="$OWNER_ID" \
  -var block_key_creation=false
```

Use the same `block_key_creation` value as in the apply (set it to `true` only if you applied it with `true`, so the policy is removed). Destroy deletes the Artifact Registry repository and its images, the pool, provider, service accounts and the bindings. It leaves the APIs enabled (`disable_on_destroy = false`); to turn them off, run `gcloud services disable` for the ones in `REQUIRED_APIS` that you did not use before. Also delete `.github/workflows/deploy.yml` and the five repository variables in GitHub. Google keeps a deleted workload identity pool for 30 days, so applying again with the same pool id inside that time fails until you undelete it. An undeleted pool is not in Terraform state after `destroy`: either import the pool and provider into state (`terraform import`) or choose new `workload_identity_pool_id` and provider ids in `terraform/main.tf`.

## What this costs

No numbers here, because prices change. Read the current pages:

- Cloud Run scales to zero, so an idle service costs nothing for compute: [Cloud Run pricing](https://cloud.google.com/run/pricing)
- Artifact Registry charges for stored images: [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)
- Gemini charges per token: [Gemini Enterprise Agent Platform pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)

The service caps input at 8,000 characters, which also caps the input tokens per call.

## How this was checked

Unit tests with a mocked Gemini client, `ruff`, and `terraform fmt -check`. `terraform init -backend=false` and `terraform validate` run in CI (`scripts/check_folder.sh` without `LOCAL_SKIP_TF_INIT`); on the author's machine the Terraform registry was not reachable, so that step was skipped there and the CI run is the evidence for it. Tests also scan the folder for keys, check that the Terraform APIs match `REQUIRED_APIS`, that the Terraform region default matches `config.py`, that the provider condition pins the repository id, owner id and `main`, and that the workflow uses `id-token: write` and no secret. Nothing was run on a live Google Cloud project. Facts and sources are in [FACTS.md](FACTS.md).

Run the checks: `scripts/check_folder.sh 01-keyless-ai-app` from the repo root.

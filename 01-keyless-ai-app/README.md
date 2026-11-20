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

You need a project you can bill, `gcloud`, and `terraform`. These steps change your project. Run them yourself.

1. Pick the project: `gcloud config set project YOUR_PROJECT_ID`.
2. Enable the first APIs Terraform needs to start: `gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com`. Terraform enables the rest (see `REQUIRED_APIS` in `config.py`).
3. Create the identity setup:
   ```bash
   cd terraform
   terraform init
   terraform plan -var project_id=YOUR_PROJECT_ID -var github_repo=OWNER/NAME
   terraform apply -var project_id=YOUR_PROJECT_ID -var github_repo=OWNER/NAME
   ```
   Add `-var block_key_creation=true` if you have the Organization Policy Administrator role and want to forbid service account keys.
4. Set repository variables in GitHub (Settings, Secrets and variables, Actions, Variables). Use the Terraform outputs:
   `GCP_PROJECT_ID`, `GCP_REGION`, `WORKLOAD_IDENTITY_PROVIDER` (output `workload_identity_provider`), `DEPLOY_SERVICE_ACCOUNT`, `RUNTIME_SERVICE_ACCOUNT`.
5. Copy `.github-example/deploy.yml` to `.github/workflows/deploy.yml` in your repo, and the `app/`, `config.py` and `Dockerfile` files with it. Push to `main`. Pushes from other branches cannot get a token: the provider condition rejects them.
6. Call the service. Cloud Run needs a caller identity because the service is private:
   ```bash
   URL=$(gcloud run services describe note-summariser --region europe-west1 --format 'value(status.url)')
   curl -X POST "$URL/summarize" \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" \
     -d '{"text": "Customer says the door code stopped working after the update."}'
   ```
   Your own account needs `roles/run.invoker` on the service.

When Gemini is busy the service answers `503` with `Retry-After: 5`.

## Clean up

```bash
gcloud run services delete note-summariser --region europe-west1
gcloud artifacts docker images list europe-west1-docker.pkg.dev/YOUR_PROJECT_ID/notes   # then delete what you see
terraform -chdir=terraform destroy -var project_id=YOUR_PROJECT_ID -var github_repo=OWNER/NAME
```

`terraform destroy` removes the pool, provider, service accounts, bindings and the Artifact Registry repository (which deletes its images). The APIs stay enabled (`disable_on_destroy = false`). Delete the repository variables in GitHub too.

## What this costs

No numbers here, because prices change. Read the current pages:

- Cloud Run scales to zero, so an idle service costs nothing for compute: [Cloud Run pricing](https://cloud.google.com/run/pricing)
- Artifact Registry charges for stored images: [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)
- Gemini charges per token: [Gemini Enterprise Agent Platform pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)

The service caps input at 8,000 characters, which also caps the input tokens per call.

## How this was checked

Unit tests with a mocked Gemini client, `ruff`, `terraform fmt -check`, `terraform init -backend=false` and `terraform validate`. There are also tests that scan the folder for keys, check that the Terraform APIs match `REQUIRED_APIS`, and check that the workflow uses `id-token: write` and no secret. Nothing was run on a live Google Cloud project. Facts and sources are in [FACTS.md](FACTS.md).

Run the checks: `scripts/check_folder.sh 01-keyless-ai-app` from the repo root.

# 06 Production RAG API

Brightmoor Legal Library keeps a library of public regulations. Staff ask questions and get answers that cite the regulation. This folder is that service: a FastAPI app on Cloud Run, Cloud SQL for PostgreSQL with pgvector, and Gemini.

```text
POST /ask {question, top_k}
  -> span "embed":    Gemini embedding (task type RETRIEVAL_QUERY, 768 dims)
  -> span "search":   pgvector cosine top-k over a private-IP Cloud SQL instance
  -> best distance above MAX_DISTANCE?  answer "I do not know", model NOT called
  -> span "generate": Gemini answers from the retrieved chunks only, with [doc_id] citations
  -> answer with no valid citation?     "I do not know"
  <- {answer, sources}
Spans go to Cloud Trace through the Telemetry API (OTLP).
```

Production touches a codelab skips: private IP only, IAM database authentication (no database password, so **no Secret Manager secret is needed**), timeouts and retries on Gemini calls, idempotent ingest (upsert by chunk id), a distance threshold that avoids paying for a model call that can only guess, and an eval that fails CI.

## Steps

You need a project you can bill, `gcloud` and `terraform`. These steps change your project. Run them yourself, from this folder (`06-production-rag-api`). A dedicated project for the tutorial is best, because Clean up can then end with deleting the whole project.

1. Sign in twice. `gcloud auth login` is for the CLI. Terraform uses Application Default Credentials, which need their own sign-in. Then pick the project and one region for every command below:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project YOUR_PROJECT_ID
   gcloud auth application-default set-quota-project YOUR_PROJECT_ID
   export PROJECT_ID=YOUR_PROJECT_ID REGION=europe-west1
   ```
2. Enable the APIs. Terraform also enables them, but enabling first avoids first-run errors:
   ```bash
   gcloud services enable \
     aiplatform.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
     cloudresourcemanager.googleapis.com cloudtrace.googleapis.com compute.googleapis.com \
     iam.googleapis.com run.googleapis.com servicenetworking.googleapis.com \
     serviceusage.googleapis.com sqladmin.googleapis.com storage.googleapis.com \
     telemetry.googleapis.com
   ```
   `cloudtrace.googleapis.com` must stay enabled: if it is off, spans sent to the Telemetry API are discarded.
3. Create the infrastructure. The first apply uses a placeholder image. Creating the Cloud SQL instance takes several minutes. Replace the invoker with you or your group:
   ```bash
   terraform -chdir=terraform init
   terraform -chdir=terraform apply -var "project_id=$PROJECT_ID" -var "region=$REGION" \
     -var db_deletion_protection=false -var invoker_member=user:YOU@example.com
   ```
   `db_deletion_protection=false` is only so Clean up works. Keep the default (true) in production. `invoker_member` grants `roles/run.invoker` on the service, so you can call it in step 8.
4. Build the image with Cloud Build. It uses the dedicated build identity and bucket Terraform made (`.gcloudignore` keeps Terraform state out of the upload). Your account needs `roles/iam.serviceAccountUser` on that build identity:
   ```bash
   REPO=$(terraform -chdir=terraform output -raw image_repository)
   BUCKET=$(terraform -chdir=terraform output -raw build_bucket)
   BUILD_SA=$(terraform -chdir=terraform output -raw build_service_account)
   gcloud builds submit --tag "$REPO/rag:v1" \
     --service-account="projects/$PROJECT_ID/serviceAccounts/$BUILD_SA" \
     --gcs-source-staging-dir="gs://$BUCKET/source" --gcs-log-dir="gs://$BUCKET/logs" .
   ```
5. Point the service and both jobs at that image:
   ```bash
   terraform -chdir=terraform apply -var "project_id=$PROJECT_ID" -var "region=$REGION" \
     -var db_deletion_protection=false -var invoker_member=user:YOU@example.com -var "image=$REPO/rag:v1"
   ```
6. Create the schema, then load the documents. The database has no public address, so both run as Cloud Run jobs inside the VPC. The bootstrap job runs as the admin identity (the only one that may `CREATE EXTENSION vector`) and grants the API identity `SELECT` and the ingest identity write access. The ingest job then makes the table match `docs/` exactly (changed documents replaced, removed documents deleted). The documents are baked into the image. To re-ingest after editing `docs/`, rebuild the image with a new tag, point the job at it, then execute it:
   ```bash
   gcloud run jobs execute rag-bootstrap --region "$REGION" --wait
   gcloud run jobs execute rag-ingest --region "$REGION" --wait
   ```
   Re-ingest later (new tag `v2`, rebuilt as in step 4):
   ```bash
   gcloud run jobs update rag-ingest --region "$REGION" --image "$REPO/rag:v2"
   gcloud run jobs execute rag-ingest --region "$REGION" --wait
   ```
   Also update the service to `v2` (`terraform apply ... -var image=...`) so both run the same code.
7. Ask a question. The service is private, so the call carries your identity token:
   ```bash
   URL=$(gcloud run services describe rag-api --region "$REGION" --format 'value(status.url)')
   curl -X POST "$URL/ask" \
     -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" \
     -d '{"question": "Can a fire exit be locked while the shop is open?", "top_k": 5}'
   ```
   Add `"jurisdiction": "city"` to filter on the metadata column. A question the library cannot answer returns `{"answer": "I do not know", "sources": []}`. When Gemini or the database is busy the service answers `503` with `Retry-After: 5`.
8. Run the golden eval against the deployed service. It asks the 10 questions in `eval/golden.json` and exits 1 if fewer than 8 answers cite the expected document:
   ```bash
   ID_TOKEN=$(gcloud auth print-identity-token) uv run python -m eval.run_eval "$URL"
   ```
   If it fails, tune `MAX_DISTANCE` in `config.py` first, then the chunk size.
9. Open Cloud Trace in the console and look for the `embed`, `search` and `generate` spans.

Two evals, two jobs. `tests/test_eval_offline.py` runs in CI with no Google calls: it sends the golden questions through the real `/ask` route with a fake embedding and an in-memory search, so it checks the wiring (threshold, citation check, scoring) and not Gemini quality. Step 8 is the manual check of real retrieval quality.

Notes on choices:

- Three identities, each a Cloud SQL IAM service account user (named by the email without `.gserviceaccount.com`): `rag-admin` (cloudsqlsuperuser, runs bootstrap only), `rag-ingest` (write on `chunks`) and `rag-api` (`SELECT` only). All three hold `roles/cloudsql.client` and `roles/cloudsql.instanceUser`. Gemini access (`roles/aiplatform.user`, Agent Platform User) goes to ingest and api; `roles/telemetry.tracesWriter` only to api.
- A returned citation is a reference check: every `[doc_id]` in the answer must be a document we retrieved, and the answer must cite at least one. It does not prove each claim is supported by the text. The question and excerpts are labelled as untrusted data in the prompt.
- Time budget (best effort, per-operation timeouts, not a hard wall-clock limit; the Cloud Run timeout is the outer bound and a request that reaches it returns 504): each Gemini call has an 8 second timeout and at most two retries (jittered backoff), the query has a 5 second statement timeout, the connector connect timeout is 30 seconds, and Cloud Run allows 90 seconds: expected worst case 30 + 2 x (3 x 8 + 1.5) + 5 = 86 seconds (`config.py`). Gemini, transport and database failures at any stage return `503` with `Retry-After`.
- A citation names a document, not a chunk. Chunk-level citation (distinct excerpt ids validated before rendering) is a possible extension.
- Known limit: two ingest runs at the same time can interleave. Run one at a time.
- Embeddings use 768 dimensions, not the 3072 default, because pgvector cannot put an HNSW index on more than 2000.

## Clean up

```bash
terraform -chdir=terraform destroy -var "project_id=$PROJECT_ID" -var "region=$REGION" -var db_deletion_protection=false
```

This deletes the Cloud Run service and jobs, the Cloud SQL instance (and its data and backups), the network, the address range, the service accounts, the Cloud Build bucket (source and logs) and the Artifact Registry repository with its images.

Cloud SQL keeps the producer resources of a deleted instance for up to four days, and the private connection cannot be removed while they exist. If destroy fails on `google_service_networking_connection`, wait and run the same destroy again. Only if an earlier run already abandoned the connection (it is gone from Terraform state but the peering remains) and the retention window has passed, delete the peering by hand, then finish the destroy:

```bash
gcloud services vpc-peerings delete --service=servicenetworking.googleapis.com --network=rag-net
terraform -chdir=terraform destroy -var "project_id=$PROJECT_ID" -var "region=$REGION" -var db_deletion_protection=false
```

Things Terraform does not own: the APIs stay enabled (`disable_on_destroy = false`, so a shared project keeps its other services), and the project's `_Trace` bucket is provisioned automatically the first time trace data arrives; it keeps spans for 30 days and is not removed. In a dedicated tutorial project, the complete teardown is `gcloud projects delete $PROJECT_ID`. In a shared project, leave the APIs and the `_Trace` bucket alone.

## What this costs

No totals here, because prices change. Read the current pages:

- Cloud SQL runs (and bills) while the instance exists, even when idle: [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
- Cloud Run scales to zero: [Cloud Run pricing](https://cloud.google.com/run/pricing)
- Gemini embeddings and generation are billed per token: [Gemini Enterprise Agent Platform pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)
- Cloud Trace and the Telemetry API: [Cloud Observability pricing](https://cloud.google.com/stackdriver/pricing)
- Cloud Build and Artifact Registry: [Cloud Build pricing](https://cloud.google.com/build/pricing), [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)

## How this was checked

Unit tests with mocks for every Google client (embedding, generation, database), `ruff`, and `terraform fmt`. CI runs `terraform validate`. The tests cover chunk overlap, the "I do not know" path where the model is not called, the reference check (including mixed valid and invented references), the prompt sent to the SDK, the three spans (with an in-memory exporter), the real search code with a fake cursor (SQL text constant, values as parameters), ingest replacing and pruning rows across two runs, error mapping to 503, the time budget, the API list matching the Terraform resource and the README enable command, and an offline run of the golden eval through `/ask`. The runtime dependencies in `app/requirements.txt` are exported from the tested `uv.lock` (`uv export --no-dev --no-hashes --no-emit-project`). This was not run against a live Google Cloud project. See `FACTS.md` for the sources and for what is unverified.

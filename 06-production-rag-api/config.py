"""Settings shared by the app, the ingest job and the checks. Model ids live here and nowhere else."""

import os

# Gemini 3.8 Flash answers questions. The model page lists it for `global`.
MODEL_ID = "gemini-3.8-flash"

# Embedding model. Same model for documents and questions, or distances mean nothing.
EMBEDDING_MODEL_ID = "gemini-embedding-001"

# gemini-embedding-001 returns 3072 dimensions by default. pgvector cannot build an HNSW
# index on more than 2000, so we ask for 768. sql/schema.sql must say vector(768) too.
EMBEDDING_DIM = 768

# Region of the Cloud Run service, job and Cloud SQL. terraform/variables.tf `region` has the same
# default; the README examples read it from one shell variable.
REGION = os.environ.get("REGION", "europe-west1")
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")

# Cosine distance runs from 0 (same direction) to 2. Above this, we say "I do not know".
# Start here, then tune it with eval/run_eval.py on your own documents.
MAX_DISTANCE = float(os.environ.get("MAX_DISTANCE", "0.45"))

TOP_K_DEFAULT = 5
TOP_K_MAX = 20
EMBED_BATCH_SIZE = 16
CHUNK_SIZE_WORDS = 800
CHUNK_OVERLAP_WORDS = 120
# Best-effort budget for one /ask (per-operation timeouts, not a hard wall-clock limit; Cloud Run's
# request timeout is the outer bound). Expected worst case: connect 30s + 2 x (3 tries x 8s + 1.5s backoff) + search 5s = 86s,
# under the 90s Cloud Run request timeout in terraform/main.tf.
GENAI_TIMEOUT_SECONDS = 8
GENAI_MAX_ATTEMPTS = 3  # the first try plus two retries, as Google recommends at most
CONNECT_TIMEOUT_SECONDS = 30
STATEMENT_TIMEOUT_MS = 5000

# Every API the Terraform enables. A test keeps this in step with terraform/ and the README.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "servicenetworking.googleapis.com",
    "serviceusage.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "telemetry.googleapis.com",
]

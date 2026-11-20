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
# Embeddings page: at most 250 texts and 20,000 input tokens per request. We approximate tokens
# as 1.5 x words, which errs on the safe side for English.
EMBED_MAX_TEXTS_PER_BATCH = 250
EMBED_TOKEN_BUDGET = 20_000
TOKENS_PER_WORD = 1.5
CHUNK_SIZE_WORDS = 800
CHUNK_OVERLAP_WORDS = 120
# Nominal sum of per-operation timeouts for one /ask (not a hard limit; Cloud Run's request timeout
# of 120s in terraform/main.tf is the outer bound): connect 30s + 2 x (3 tries x 8s + 3s backoff)
# + search 5s = 89s.
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

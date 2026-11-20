"""Settings shared by the agent and the checks. Model ids live here and nowhere else."""

import os

# Gemini 3.8 Flash. The model page lists it for `global`, not for europe-west1.
MODEL_ID = "gemini-3.8-flash"

# Region for Cloud Run.
REGION = os.environ.get("REGION", "europe-west1")

# Location for Gemini calls (read by google-genai as GOOGLE_CLOUD_LOCATION).
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")

# Hard business rules for refunds. The agent cannot talk its way past these.
MAX_REFUND_MINOR = 5000

# Time budget. Worst case for one /run request, in seconds:
#   MAX_LLM_CALLS * (MODEL_ATTEMPTS * MODEL_TIMEOUT_S + MODEL_MAX_DELAY_S) < CLOUD_RUN_TIMEOUT_S
#   4 * (2 * 30 + 4) = 256 < 300
MODEL_TIMEOUT_S = 30
MODEL_TIMEOUT_MS = MODEL_TIMEOUT_S * 1000
MODEL_ATTEMPTS = 2
MODEL_MAX_DELAY_S = 4
# Most model calls one /run request may make (lookup, refund, answer, plus one spare).
MAX_LLM_CALLS = 4
# Cloud Run request timeout. The README deploy command must use the same number.
CLOUD_RUN_TIMEOUT_S = 300

# Env var that switches on the drill fault, and the one value it understands.
FAULT_ENV = "DRILL_FAULT"
FAULT_WRONG_CURRENCY = "wrong_currency"

# Every API the setup uses. A test keeps this in step with terraform/ and the README.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "run.googleapis.com",
    "serviceusage.googleapis.com",
]

"""Settings shared by the app and the checks. The model id lives here and nowhere else."""

import os

# Gemini 3.8 Flash. The model page lists it for `global`, not for europe-west1.
MODEL_ID = "gemini-3.8-flash"

# Default region for Cloud Run and Artifact Registry (Terraform's `region` default must match; a test checks it).
REGION = os.environ.get("REGION", "europe-west1")

# Location for Gemini calls. "global" is listed for this model, so it is the default.
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")

# Every API the Terraform enables and the app uses. A test keeps this in step with terraform/.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "orgpolicy.googleapis.com",  # only used when block_key_creation = true
    "run.googleapis.com",
    "serviceusage.googleapis.com",  # needed by google_project_service itself: enable it first (README step 2)
    "sts.googleapis.com",
]

# Seconds the SDK waits for Gemini. Keep it well below the Cloud Run request timeout (300 s by default).
GEMINI_TIMEOUT_SECONDS = 30

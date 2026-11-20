"""Settings shared by the app and the checks. The model id lives here and nowhere else."""

import os

# Gemini 3.8 Flash. The model page lists it for `global`, not for europe-west1.
MODEL_ID = "gemini-3.8-flash"

# Region for Cloud Run and Artifact Registry.
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
    "run.googleapis.com",
    "sts.googleapis.com",
]

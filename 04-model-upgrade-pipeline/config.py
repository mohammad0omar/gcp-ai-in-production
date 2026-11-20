"""Settings shared by the app, the eval and the pipeline. Model ids live here and nowhere else."""

import os

# Pinned version ids, never aliases. Production runs MODEL_ID; the pipeline tests CANDIDATE_MODEL_ID.
# gemini-3.7-flash retires on 2027-01-28 (replacement: gemini-3.8-flash), so we are upgrading.
MODEL_ID = "gemini-3.7-flash"
CANDIDATE_MODEL_ID = "gemini-3.8-flash"

# Region for Cloud Run, Artifact Registry and Cloud Build.
REGION = os.environ.get("REGION", "europe-west1")

# Location for Gemini calls. "global" is the location the model page lists.
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")

# Every API the README tells you to enable. A test keeps this in step with the README.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
]

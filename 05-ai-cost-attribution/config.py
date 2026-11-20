"""Settings shared by the app and the checks. Model ids live here and nowhere else."""

import os

# Gemini 3.8 Flash. The model page lists it for `global`, not for europe-west1.
MODEL_ID = "gemini-3.8-flash"

# Region for the BigQuery dataset that receives the logs.
REGION = os.environ.get("REGION", "europe-west1")

# Location for Gemini calls.
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")

# Tidewell's three AI features. Each one becomes a request label value.
FEATURES = ("ticket_summary", "invoice_extract", "smart_reply")

# Request label keys. Billing export carries them in the `labels` column.
LABEL_FEATURE = "feature"
LABEL_CUSTOMER = "customer"

# Label rules for Gemini requests: lowercase letters, digits, underscore, dash; 1 to 63 characters.
LABEL_MAX_LEN = 63

# The salt must be at least this long (a random 32 byte value is 44 base64 chars, 43 without padding).
MIN_SALT_CHARS = 32

# Event name written in every usage log line. The log sink filter uses it.
USAGE_EVENT = "ai_usage"

# Every API the Terraform enables and the app uses. A test keeps this in step with terraform/.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
]

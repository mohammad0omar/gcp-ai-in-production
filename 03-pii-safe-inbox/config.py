"""Settings shared by the app and the checks. Model id, info types and APIs live here."""

import os

# Gemini 3.8 Flash. The model page lists it for `global`, not for europe-west1.
MODEL_ID = "gemini-3.8-flash"

# Region for Cloud Run and Firestore.
REGION = os.environ.get("REGION", "europe-west1")

# Location for Gemini calls. "global" is listed for this model.
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")

# Location for Sensitive Data Protection calls (parent is projects/P/locations/L).
DLP_LOCATION = os.environ.get("DLP_LOCATION", "global")

# Built-in infoTypes that are redacted before any model sees the text.
INFO_TYPES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD_NUMBER", "PERSON_NAME"]

# Raw emails longer than this are not processed (see README). Keeps one call small.
MAX_RAW_CHARS = 20_000

# Time budget. Pub/Sub waits ACK_DEADLINE_S for a 2xx; Cloud Run stops the request at
# REQUEST_TIMEOUT_S, which is shorter, so a slow handler is stopped before Pub/Sub resends.
# A test adds up the worst case and keeps it under REQUEST_TIMEOUT_S. The sum covers the DLP,
# Firestore and model calls, not a credential refresh, which is rare and usually fast; the gap
# up to REQUEST_TIMEOUT_S is the margin for it.
ACK_DEADLINE_S = 120
REQUEST_TIMEOUT_S = 110
AUTH_TIMEOUT_S = 5  # fetching Google's signing certificates
DLP_TIMEOUT_S = 10
MODEL_TIMEOUT_S = 15
MODEL_ATTEMPTS = 2  # first call plus one retry on invalid output
FIRESTORE_TIMEOUT_S = 10
FIRESTORE_CALLS = 2  # marker read, then one atomic write

# Every API the Terraform enables and the app uses. A test keeps this in step with terraform/.
REQUIRED_APIS = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "dlp.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
]

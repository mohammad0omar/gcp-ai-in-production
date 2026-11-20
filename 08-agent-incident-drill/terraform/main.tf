locals {
  # Keep in step with REQUIRED_APIS in ../config.py (a test checks this).
  required_apis = [
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
}

resource "google_project_service" "api" {
  for_each = toset(local.required_apis)

  service            = each.value
  disable_on_destroy = false
}

# The runtime identity: it may call Gemini and write traces, nothing else.
resource "google_service_account" "runtime" {
  account_id   = "pebble-agent"
  display_name = "Cloud Run runtime for the Pebble Post agent"

  depends_on = [google_project_service.api]
}

# The documented predefined role for calling Gemini (Agent Platform User). It is broader
# than model calls alone. A narrower custom role is possible but must be tested live.
resource "google_project_iam_member" "runtime_model" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Data Access audit logs for Gemini calls are off by default. generateContent is a
# DATA_READ method, so DATA_READ is all this drill needs.
# Admin Activity logs are always on and need no setting.
# Careful: this resource is authoritative for this service's audit config. It replaces
# any audit settings already on aiplatform.googleapis.com. Use a disposable project.
resource "google_project_iam_audit_config" "agent_platform" {
  project = var.project_id
  service = "aiplatform.googleapis.com"

  audit_log_config {
    log_type = "DATA_READ"
  }
}

locals {
  apis = [
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
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.key
  disable_on_destroy = false
}

resource "google_bigquery_dataset" "usage_logs" {
  dataset_id    = "ai_usage_logs"
  location      = var.region
  friendly_name = "AI usage logs"
  description   = "One row per Gemini call, written by the log sink."

  # Lets terraform destroy remove the tables the sink and your views created.
  delete_contents_on_destroy = true

  depends_on = [google_project_service.apis]
}

# Dataset for the joined views and the customers table. The billing export dataset is made in the console.
resource "google_bigquery_dataset" "cost" {
  dataset_id    = "ai_cost"
  location      = var.region
  friendly_name = "AI cost"
  description   = "Daily tokens, daily cost and the dashboard view."

  delete_contents_on_destroy = true

  depends_on = [google_project_service.apis]
}

# Viewers read only this dataset. It holds the dashboard view and nothing else.
resource "google_bigquery_dataset" "dashboard" {
  dataset_id    = "ai_dashboard"
  location      = var.region
  friendly_name = "AI dashboard"
  description   = "The dashboard view. Grant viewers roles/bigquery.dataViewer here."

  delete_contents_on_destroy = true

  depends_on = [google_project_service.apis]
}

resource "google_logging_project_sink" "ai_usage" {
  name                   = "ai-usage-to-bigquery"
  destination            = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.usage_logs.dataset_id}"
  filter                 = "logName=\"projects/${var.project_id}/logs/run.googleapis.com%2Fstdout\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"tidewell-ai\" AND jsonPayload.event=\"ai_usage\""
  unique_writer_identity = true

  bigquery_options {
    use_partitioned_tables = true
  }
}

# Least privilege: the sink identity can edit data in this one dataset only. This uses the dataset
# access list, like the authorized views below, so the two never overwrite each other.
resource "google_bigquery_dataset_access" "sink_writer" {
  dataset_id = google_bigquery_dataset.usage_logs.dataset_id
  role       = "roles/bigquery.dataEditor"
  iam_member = google_logging_project_sink.ai_usage.writer_identity
}

# Runtime identity of the demo service: Gemini calls only, plus its one secret.
resource "google_service_account" "runtime" {
  account_id   = "tidewell-ai-runtime"
  display_name = "Tidewell AI runtime"

  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "runtime_gemini" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# The secret container only. Add the value yourself so it never enters Terraform state.
resource "google_secret_manager_secret" "salt" {
  secret_id = "customer-hash-salt"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_salt" {
  secret_id = google_secret_manager_secret.salt.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# Authorized views: viewers need no access to the source datasets. Each view is authorized on the
# datasets it reads, and views that read other views are authorized too.
resource "google_bigquery_dataset_access" "tokens_view_reads_logs" {
  count      = var.authorize_views ? 1 : 0
  dataset_id = google_bigquery_dataset.usage_logs.dataset_id

  view {
    project_id = var.project_id
    dataset_id = google_bigquery_dataset.cost.dataset_id
    table_id   = "tokens_daily"
  }
}

resource "google_bigquery_dataset_access" "cost_view_reads_billing" {
  count      = var.authorize_views ? 1 : 0
  project    = var.billing_export_project
  dataset_id = var.billing_export_dataset

  view {
    project_id = var.project_id
    dataset_id = google_bigquery_dataset.cost.dataset_id
    table_id   = "cost_daily"
  }
}

resource "google_bigquery_dataset_access" "join_view_reads_cost_dataset" {
  count      = var.authorize_views ? 1 : 0
  dataset_id = google_bigquery_dataset.cost.dataset_id

  view {
    project_id = var.project_id
    dataset_id = google_bigquery_dataset.cost.dataset_id
    table_id   = "cost_per_customer_feature"
  }
}

resource "google_bigquery_dataset_access" "dashboard_view_reads_cost_dataset" {
  count      = var.authorize_views ? 1 : 0
  dataset_id = google_bigquery_dataset.cost.dataset_id

  view {
    project_id = var.project_id
    dataset_id = google_bigquery_dataset.dashboard.dataset_id
    table_id   = "dashboard"
  }
}

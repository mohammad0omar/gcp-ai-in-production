locals {
  # Keep in step with REQUIRED_APIS in ../config.py (a test checks this).
  required_apis = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "dlp.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
  ]
}

data "google_project" "this" {
  project_id = var.project_id

  depends_on = [google_project_service.api]
}

resource "google_project_service" "api" {
  for_each = toset(local.required_apis)

  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "inbox"
  location      = var.region
  format        = "DOCKER"

  depends_on = [google_project_service.api]
}

# Two service accounts: the app runs as one, Pub/Sub calls the app as the other.
resource "google_service_account" "runtime" {
  account_id   = "inbox-runtime"
  display_name = "Cloud Run runtime for the Fennel inbox"

  depends_on = [google_project_service.api]
}

resource "google_service_account" "pusher" {
  account_id   = "inbox-pusher"
  display_name = "Pub/Sub push identity for the Fennel inbox"

  depends_on = [google_project_service.api]
}

# Runtime roles. Nothing else: no storage, no secrets.
resource "google_project_iam_member" "runtime_dlp" {
  project = var.project_id
  role    = "roles/dlp.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_firestore_database" "default" {
  name            = "(default)"
  location_id     = var.region
  type            = "FIRESTORE_NATIVE"
  deletion_policy = "DELETE"

  depends_on = [google_project_service.api]
}

resource "google_cloud_run_v2_service" "inbox" {
  name                = "fennel-inbox"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"
  custom_audiences    = [var.push_audience]

  template {
    service_account = google_service_account.runtime.email
    timeout         = "110s" # keep in step with REQUEST_TIMEOUT_S in ../config.py

    scaling {
      max_instance_count = 5
    }

    containers {
      image = var.image

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GEMINI_LOCATION"
        value = var.gemini_location
      }
      env {
        name  = "PUSH_AUDIENCE"
        value = var.push_audience
      }
      env {
        name  = "PUSH_SERVICE_ACCOUNT"
        value = google_service_account.pusher.email
      }
    }
  }

  depends_on = [google_project_service.api]
}

# The service stays private. Only the push identity may call it.
resource "google_cloud_run_v2_service_iam_member" "pusher_invoker" {
  name     = google_cloud_run_v2_service.inbox.name
  location = google_cloud_run_v2_service.inbox.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pusher.email}"
}

resource "google_pubsub_topic" "emails" {
  name = "support-emails"

  depends_on = [google_project_service.api]
}

resource "google_pubsub_topic" "dead_letter" {
  name = "support-emails-dead-letter"

  depends_on = [google_project_service.api]
}

# A dead letter topic only keeps messages if a subscription exists on it. These messages are the
# ORIGINAL emails, not redacted. Grant roles/pubsub.subscriber on this subscription to as few people as possible.
resource "google_pubsub_subscription" "dead_letter_pull" {
  name  = "support-emails-dead-letter-pull"
  topic = google_pubsub_topic.dead_letter.id

  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }
}

resource "google_pubsub_subscription" "push" {
  name                       = "support-emails-push"
  topic                      = google_pubsub_topic.emails.id
  ack_deadline_seconds       = 120 # keep in step with ACK_DEADLINE_S in ../config.py
  message_retention_duration = "604800s"

  # Default is to delete a subscription after 31 days without activity. An empty ttl never expires.
  expiration_policy {
    ttl = ""
  }

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.inbox.uri}/pubsub"

    oidc_token {
      service_account_email = google_service_account.pusher.email
      audience              = var.push_audience
    }
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}

# Pub/Sub service agent: sign tokens as the pusher, move failed messages to the dead letter topic.
locals {
  pubsub_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_service_account_iam_member" "agent_token_creator" {
  service_account_id = google_service_account.pusher.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.pubsub_agent
}

resource "google_pubsub_topic_iam_member" "agent_publish_dead_letter" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "agent_ack_push" {
  subscription = google_pubsub_subscription.push.name
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}

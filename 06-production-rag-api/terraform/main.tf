locals {
  # Keep in step with REQUIRED_APIS in ../config.py (a test checks this).
  required_apis = [
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

  db_name = "library"

  # Three identities, three jobs. Each database user is the service account email without this suffix.
  db_users = {
    for key, account in {
      admin  = google_service_account.admin
      ingest = google_service_account.ingest
      api    = google_service_account.api
    } : key => trimsuffix(account.email, ".gserviceaccount.com")
  }

  # roles/cloudsql.client connects through the connector; roles/cloudsql.instanceUser allows IAM login.
  sql_roles = ["roles/cloudsql.client", "roles/cloudsql.instanceUser"]
  runtime_roles = {
    admin  = local.sql_roles
    ingest = concat(local.sql_roles, ["roles/aiplatform.user"]) # Agent Platform User: embeddings
    api = concat(local.sql_roles, [
      "roles/aiplatform.user",        # Agent Platform User: embeddings and Gemini
      "roles/telemetry.tracesWriter", # write spans to Cloud Trace
    ])
  }
  role_bindings = merge([
    for key, roles in local.runtime_roles : {
      for role in roles : "${key}-${role}" => { account = key, role = role }
    }
  ]...)
}

resource "google_project_service" "api" {
  for_each = toset(local.required_apis)

  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "rag"
  location      = var.region
  format        = "DOCKER"

  depends_on = [google_project_service.api]
}

# Private network: the database has no public address.
resource "google_compute_network" "main" {
  name                    = "rag-net"
  auto_create_subnetworks = false

  depends_on = [google_project_service.api]
}

resource "google_compute_subnetwork" "run" {
  name          = "rag-run"
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.10.0.0/24" # Cloud Run direct VPC egress takes addresses from here.
}

resource "google_compute_global_address" "sql_range" {
  name          = "rag-sql-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "sql" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql_range.name]
  deletion_policy         = "DELETE" # see "Clean up" in the README: Cloud SQL keeps producer resources for days

  depends_on = [google_project_service.api]
}

resource "google_sql_database_instance" "main" {
  name                = "brightmoor-library"
  region              = var.region
  database_version    = "POSTGRES_18"
  deletion_protection = var.db_deletion_protection

  settings {
    tier    = "db-custom-1-3840"
    edition = "ENTERPRISE"

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }

  depends_on = [google_service_networking_connection.sql]
}

resource "google_sql_database" "library" {
  name     = local.db_name
  instance = google_sql_database_instance.main.name
}

# Identities. No password and no Secret Manager secret exist anywhere:
# IAM database authentication replaces the database password.
resource "google_service_account" "admin" {
  account_id   = "rag-admin"
  display_name = "Brightmoor RAG bootstrap job (creates schema and grants)"

  depends_on = [google_project_service.api]
}

resource "google_service_account" "ingest" {
  account_id   = "rag-ingest"
  display_name = "Brightmoor RAG ingest job (writes chunks)"

  depends_on = [google_project_service.api]
}

resource "google_service_account" "api" {
  account_id   = "rag-api"
  display_name = "Brightmoor RAG API (reads chunks)"

  depends_on = [google_project_service.api]
}

locals {
  accounts = {
    admin  = google_service_account.admin.email
    ingest = google_service_account.ingest.email
    api    = google_service_account.api.email
  }
}

resource "google_project_iam_member" "runtime" {
  for_each = local.role_bindings

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${local.accounts[each.value.account]}"
}

# Only the admin user is a superuser role member: CREATE EXTENSION needs cloudsqlsuperuser.
# The other two start with no rights; rag/bootstrap.py grants them SELECT (api) or write (ingest).
resource "google_sql_user" "admin" {
  name           = local.db_users["admin"]
  instance       = google_sql_database_instance.main.name
  type           = "CLOUD_IAM_SERVICE_ACCOUNT"
  database_roles = ["cloudsqlsuperuser"]
}

resource "google_sql_user" "ingest" {
  name     = local.db_users["ingest"]
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_sql_user" "api" {
  name     = local.db_users["api"]
  instance = google_sql_database_instance.main.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

# Cloud Build: one bucket for source and logs, one build identity with only what a build needs.
resource "google_storage_bucket" "build" {
  name                        = "${var.project_id}-rag-build"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  depends_on = [google_project_service.api]
}

resource "google_service_account" "build" {
  account_id   = "rag-build"
  display_name = "Cloud Build for the RAG image"

  depends_on = [google_project_service.api]
}

resource "google_storage_bucket_iam_member" "build_bucket" {
  bucket = google_storage_bucket.build.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.build.email}"
}

resource "google_artifact_registry_repository_iam_member" "build_push" {
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.build.email}"
}

resource "google_project_iam_member" "build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.build.email}"
}

locals {
  db_env = {
    INSTANCE_CONNECTION_NAME = google_sql_database_instance.main.connection_name
    DB_NAME                  = local.db_name
    GOOGLE_CLOUD_PROJECT     = var.project_id
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = "rag-api"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL" # still private: callers need roles/run.invoker

  template {
    service_account = google_service_account.api.email
    timeout         = "90s" # the worst-case time budget in config.py adds up to 86s

    scaling {
      max_instance_count = 5
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image = var.image

      dynamic "env" {
        for_each = merge(local.db_env, { DB_USER = local.db_users["api"] })
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  depends_on = [google_project_iam_member.runtime, google_sql_user.api]
}

# Optional: let one person or group call the private service.
resource "google_cloud_run_v2_service_iam_member" "invoker" {
  count = var.invoker_member == "" ? 0 : 1

  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = var.invoker_member
}

# Jobs run inside the VPC. Bootstrap (admin identity) runs once; ingest (write identity) runs per update.
resource "google_cloud_run_v2_job" "bootstrap" {
  name                = "rag-bootstrap"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.admin.email
      timeout         = "300s"
      max_retries     = 1

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }

      containers {
        image   = var.image
        command = ["python", "-m", "rag.bootstrap"]

        dynamic "env" {
          for_each = merge(local.db_env, {
            DB_USER        = local.db_users["admin"]
            API_DB_USER    = local.db_users["api"]
            INGEST_DB_USER = local.db_users["ingest"]
          })
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [google_project_iam_member.runtime, google_sql_user.admin, google_sql_user.ingest, google_sql_user.api]
}

resource "google_cloud_run_v2_job" "ingest" {
  name                = "rag-ingest"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.ingest.email
      timeout         = "600s"
      max_retries     = 1

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.run.id
        }
      }

      containers {
        image   = var.image
        command = ["python", "-m", "rag.ingest"]

        dynamic "env" {
          for_each = merge(local.db_env, { DB_USER = local.db_users["ingest"] })
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [google_project_iam_member.runtime, google_sql_user.ingest]
}

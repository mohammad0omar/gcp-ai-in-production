locals {
  # Keep in step with REQUIRED_APIS in ../config.py (a test checks this).
  required_apis = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "orgpolicy.googleapis.com", # only used when block_key_creation = true
    "run.googleapis.com",
    "serviceusage.googleapis.com", # enable it by hand first (README step 2)
    "sts.googleapis.com",
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
  repository_id = "notes"
  location      = var.region
  format        = "DOCKER"

  depends_on = [google_project_service.api]
}

# Two service accounts. One deploys, one runs. Neither has a key.
resource "google_service_account" "deploy" {
  account_id   = "notes-deploy"
  display_name = "GitHub Actions deployer"

  depends_on = [google_project_service.api]
}

resource "google_service_account" "runtime" {
  account_id   = "notes-runtime"
  display_name = "Cloud Run runtime for the note summariser"

  depends_on = [google_project_service.api]
}

# Deployer: deploy Cloud Run, push images, and act as the runtime account (below).
# Cloud Run Admin, not Developer: the Cloud Run docs say changing invoker access (the
# --no-allow-unauthenticated and --invoker-iam-check flags in the workflow) needs
# run.services.setIamPolicy, which Developer lacks. Limitation: this covers every service in the
# project, so use a project that only holds this service.
resource "google_project_iam_member" "deploy_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_artifact_registry_repository_iam_member" "deploy_push" {
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_acts_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

# Runtime: the predefined Agent Platform User role, which is the documented way to call Gemini.
resource "google_project_iam_member" "runtime_gemini" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Workload Identity Federation: trust GitHub's OIDC tokens for one repo, main branch only.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.api]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  description                        = "Deploys from ${var.github_repo}, main branch only"

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.ref"                 = "assertion.ref"
  }

  # Numeric ids cannot be reclaimed by a new repository with the same name.
  # Tokens from any other repository, owner or branch are rejected before any impersonation.
  attribute_condition = "assertion.repository_id == '${var.github_repository_id}' && assertion.repository_owner_id == '${var.github_owner_id}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Let identities from that repository impersonate the deploy account.
resource "google_service_account_iam_member" "github_impersonates_deploy" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

# Optional: forbid creating service account keys at all. Needs the Organization Policy
# Administrator role, so it is off by default. Not retroactive: existing keys stay.
resource "google_org_policy_policy" "no_sa_keys" {
  count = var.block_key_creation ? 1 : 0

  name   = "projects/${data.google_project.this.number}/policies/iam.managed.disableServiceAccountKeyCreation"
  parent = "projects/${data.google_project.this.number}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.api]
}

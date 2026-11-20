variable "project_id" {
  description = "Google Cloud project that hosts the service."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Cloud SQL and Artifact Registry."
  type        = string
  default     = "europe-west1"
}

variable "image" {
  description = "Container image for the API and the ingest job. The default is a placeholder so the first apply works; see the README."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "db_deletion_protection" {
  description = "Keep true in production. The README sets false so that terraform destroy can clean up."
  type        = bool
  default     = true
}

variable "invoker_member" {
  description = "Who may call the private service, for example user:you@example.com or group:staff@example.com. Empty means nobody is granted."
  type        = string
  default     = ""
}

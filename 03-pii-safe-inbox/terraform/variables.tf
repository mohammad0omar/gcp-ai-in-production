variable "project_id" {
  description = "Google Cloud project that hosts the inbox."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and Firestore."
  type        = string
  default     = "europe-west1"
}

variable "image" {
  description = "Container image for the Cloud Run service, for example europe-west1-docker.pkg.dev/PROJECT/REPO/inbox:1."
  type        = string
}

variable "push_audience" {
  description = "Audience claim in the Pub/Sub push token. Also a custom audience of the Cloud Run service. Any URL-shaped string you own."
  type        = string
  default     = "https://inbox.fennel-health.example"
}

variable "gemini_location" {
  description = "Location for Gemini calls. The model page lists global for gemini-3.8-flash."
  type        = string
  default     = "global"
}

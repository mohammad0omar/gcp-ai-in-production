variable "project_id" {
  description = "Google Cloud project that hosts the service."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run and Artifact Registry."
  type        = string
  default     = "europe-west1"
}

variable "github_repo" {
  description = "GitHub repository allowed to deploy, as owner/name. Only used in a description."
  type        = string
}

variable "github_repository_id" {
  description = "Numeric id of that repository: gh api repos/OWNER/NAME --jq .id"
  type        = string
}

variable "github_owner_id" {
  description = "Numeric id of the repository owner: gh api repos/OWNER/NAME --jq .owner.id"
  type        = string
}

variable "block_key_creation" {
  description = "Set true to block service account key creation in this project (needs the org policy admin role)."
  type        = bool
  default     = false
}

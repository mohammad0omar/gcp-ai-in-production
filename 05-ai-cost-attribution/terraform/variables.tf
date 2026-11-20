variable "project_id" {
  description = "Google Cloud project that runs the AI features."
  type        = string
}

variable "region" {
  description = "BigQuery location of both datasets. Must equal the location of your billing export dataset, or the views cannot join across them."
  type        = string
  default     = "europe-west1"
}

variable "authorize_views" {
  description = "Set true AFTER you created the four views (README step 10). Authorizes them on their source datasets."
  type        = bool
  default     = false
}

variable "billing_export_project" {
  description = "Project that holds the billing export dataset. Only used when authorize_views is true."
  type        = string
  default     = ""
}

variable "billing_export_dataset" {
  description = "Billing export dataset id. Only used when authorize_views is true."
  type        = string
  default     = ""
}

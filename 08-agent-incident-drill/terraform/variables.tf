variable "project_id" {
  description = "Project that runs the Pebble Post agent."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run."
  type        = string
  default     = "europe-west1"
}

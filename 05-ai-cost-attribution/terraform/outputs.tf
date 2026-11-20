output "sink_writer_identity" {
  description = "Identity the log sink writes with."
  value       = google_logging_project_sink.ai_usage.writer_identity
}

output "usage_dataset" {
  value = google_bigquery_dataset.usage_logs.dataset_id
}

output "cost_dataset" {
  value = google_bigquery_dataset.cost.dataset_id
}

output "runtime_service_account" {
  description = "Use as --service-account when deploying the service."
  value       = google_service_account.runtime.email
}

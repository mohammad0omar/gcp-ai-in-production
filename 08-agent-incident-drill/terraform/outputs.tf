output "runtime_service_account" {
  description = "Pass this to gcloud run deploy --service-account."
  value       = google_service_account.runtime.email
}

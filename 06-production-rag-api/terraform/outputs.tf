output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "bootstrap_job_name" {
  value = google_cloud_run_v2_job.bootstrap.name
}

output "build_service_account" {
  value = google_service_account.build.email
}

output "build_bucket" {
  value = google_storage_bucket.build.name
}

output "ingest_job_name" {
  value = google_cloud_run_v2_job.ingest.name
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "instance_connection_name" {
  value = google_sql_database_instance.main.connection_name
}

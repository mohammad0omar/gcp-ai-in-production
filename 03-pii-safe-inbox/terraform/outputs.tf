output "service_url" {
  value = google_cloud_run_v2_service.inbox.uri
}

output "topic" {
  value = google_pubsub_topic.emails.id
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}

output "image_repository" {
  value = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

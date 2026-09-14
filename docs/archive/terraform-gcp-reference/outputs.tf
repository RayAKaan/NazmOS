output "api_load_balancer_ip" {
  description = "Global IP for the NazmOS API. Point app.nazm.ai A record here."
  value       = google_compute_global_address.api.address
}

output "api_service_url" {
  description = "Cloud Run service URL (useful for smoke tests, not public traffic)"
  value       = google_cloud_run_v2_service.api.uri
}

output "database_connection_name" {
  description = "Cloud SQL connection name for proxy/Cloud Run"
  value       = google_sql_database_instance.postgres.connection_name
}

output "redis_host" {
  description = "Memorystore Redis host"
  value       = google_redis_instance.redis.host
}

output "uploads_bucket" {
  description = "GCS bucket for file uploads"
  value       = google_storage_bucket.uploads.name
}

output "backups_bucket" {
  description = "GCS bucket for encrypted database backups"
  value       = google_storage_bucket.backups.name
}

output "secret_manager_secret_ids" {
  description = "Secret Manager secret IDs for runtime configuration"
  value = {
    secret_key           = google_secret_manager_secret.secret_key.secret_id
    db_password          = google_secret_manager_secret.db_password.secret_id
    sentry_dsn           = google_secret_manager_secret.sentry_dsn.secret_id
    openrouter_api_key   = google_secret_manager_secret.openrouter_api_key.secret_id
    foodics_webhook_secret = google_secret_manager_secret.foodics_webhook_secret.secret_id
    salla_webhook_secret = google_secret_manager_secret.salla_webhook_secret.secret_id
  }
}

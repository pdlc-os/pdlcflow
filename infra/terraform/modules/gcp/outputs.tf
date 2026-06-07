output "api_url" {
  description = "Cloud Run URL for the pdlc-engine API"
  value       = google_cloud_run_v2_service.api.uri
}

output "studio_ip" {
  description = "Global LB IP for the Studio (point your DNS here)"
  value       = google_compute_global_forwarding_rule.studio.ip_address
}

output "studio_bucket" {
  description = "Upload the built Studio SPA here"
  value       = google_storage_bucket.studio.name
}

output "db_private_ip" {
  value = google_sql_database_instance.postgres.private_ip_address
}

output "redis_host" {
  value = google_redis_instance.redis.host
}

output "artifacts_bucket" {
  value = google_storage_bucket.artifacts.name
}

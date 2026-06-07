output "api_fqdn" {
  description = "Container App ingress FQDN for the API"
  value       = azurerm_container_app.api.latest_revision_fqdn
}

output "studio_cdn_host" {
  description = "CDN endpoint host for the Studio"
  value       = azurerm_cdn_endpoint.studio.fqdn
}

output "studio_web_host" {
  description = "Storage static-website host (upload the built Studio here)"
  value       = azurerm_storage_account.main.primary_web_host
}

output "db_fqdn" {
  value = azurerm_postgresql_flexible_server.pg.fqdn
}

output "redis_host" {
  value = azurerm_redis_cache.redis.hostname
}

output "openai_endpoint" {
  value = azurerm_cognitive_account.openai.endpoint
}

output "api_url" {
  description = "Public ALB URL for the pdlc-engine API"
  value       = "http://${aws_lb.api.dns_name}"
}

output "studio_url" {
  description = "CloudFront URL for the Studio SPA"
  value       = "https://${aws_cloudfront_distribution.studio.domain_name}"
}

output "db_endpoint" {
  value = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "artifacts_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "studio_bucket" {
  description = "Upload the built Studio SPA here, then invalidate CloudFront"
  value       = aws_s3_bucket.studio.bucket
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

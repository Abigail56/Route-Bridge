output "cluster_name" {
  value = module.eks.cluster_name
}

output "configure_kubectl" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "database_url" {
  description = "Value for ROUTEBRIDGE_DATABASE_URL (store it in the cluster Secret, not in a repository)."
  value       = "postgresql+psycopg://${aws_db_instance.main.username}:${random_password.db.result}@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}?sslmode=require"
  sensitive   = true
}

output "redis_url" {
  description = "Value for ROUTEBRIDGE_REDIS_URL."
  value       = "rediss://:${random_password.redis.result}@${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
  sensitive   = true
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "s3_endpoint" {
  value = "https://s3.${var.region}.amazonaws.com"
}

output "s3_access_key" {
  value = aws_iam_access_key.media_signer.id
}

output "s3_secret_key" {
  value     = aws_iam_access_key.media_signer.secret
  sensitive = true
}

output "ecr_repositories" {
  value = { for name, repo in aws_ecr_repository.images : name => repo.repository_url }
}

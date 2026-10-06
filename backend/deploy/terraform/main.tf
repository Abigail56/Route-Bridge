locals {
  name = "routebridge-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 3)
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ---- network -----------------------------------------------------------------------------------------------------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = local.name
  cidr = var.vpc_cidr
  azs  = local.azs

  public_subnets   = [for i in range(3) : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets  = [for i in range(3) : cidrsubnet(var.vpc_cidr, 8, i + 10)]
  database_subnets = [for i in range(3) : cidrsubnet(var.vpc_cidr, 8, i + 20)]

  enable_nat_gateway     = true
  single_nat_gateway     = !var.nat_gateway_per_az
  one_nat_gateway_per_az = var.nat_gateway_per_az

  create_database_subnet_group = true
  enable_dns_hostnames         = true

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

# ---- Kubernetes --------------------------------------------------------------------------------------------------

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = local.name
  cluster_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access           = length(var.allowed_admin_cidrs) > 0
  cluster_endpoint_public_access_cidrs     = var.allowed_admin_cidrs
  cluster_endpoint_private_access          = true
  enable_irsa                              = true
  enable_cluster_creator_admin_permissions = true

  cluster_enabled_log_types = ["api", "audit", "authenticator"]

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      min_size       = var.node_min_size
      max_size       = var.node_max_size
      desired_size   = var.node_min_size
      subnet_ids     = module.vpc.private_subnets
    }
  }
}

# ---- PostgreSQL (PostGIS is created by the application's migrations: CREATE EXTENSION postgis) -----------------------

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_security_group" "db" {
  name_prefix = "${local.name}-db-"
  vpc_id      = module.vpc.vpc_id
  description = "PostgreSQL from the EKS nodes only"

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 4
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "routebridge"
  username = "routebridge"
  password = random_password.db.result

  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.db.id]
  multi_az               = var.db_multi_az
  publicly_accessible    = false

  backup_retention_period      = var.db_backup_retention_days
  backup_window                = "02:00-03:00"
  maintenance_window           = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot        = true
  deletion_protection          = var.environment == "production"
  skip_final_snapshot          = var.environment != "production"
  final_snapshot_identifier    = var.environment == "production" ? "${local.name}-final" : null
  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
}

# ---- Redis (rate limits and the live event stream; not a system of record) ------------------------------------------

resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "aws_security_group" "redis" {
  name_prefix = "${local.name}-redis-"
  vpc_id      = module.vpc.vpc_id
  description = "Redis from the EKS nodes only"

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = local.name
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = local.name
  description                = "RouteBridge ${var.environment}"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.redis_node_type
  num_cache_clusters         = var.environment == "production" ? 2 : 1
  automatic_failover_enabled = var.environment == "production"
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis.result
}

# ---- Object storage for delivery photos and signatures -------------------------------------------------------------

resource "aws_s3_bucket" "media" {
  bucket = "${local.name}-media"
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 2
    }
  }
}

# Drivers' phones upload straight to S3 with a presigned PUT, so the bucket must allow cross-origin PUTs from the app.
resource "aws_s3_bucket_cors_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  cors_rule {
    allowed_methods = ["PUT", "GET"]
    allowed_origins = var.app_origins
    allowed_headers = ["Content-Type"]
    max_age_seconds = 3000
  }
}

# The API signs presigned URLs with this identity, so it only needs object read/write on this bucket.
resource "aws_iam_user" "media_signer" {
  name = "${local.name}-media-signer"
}

data "aws_iam_policy_document" "media_signer" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.media.arn}/*"]
  }
}

resource "aws_iam_user_policy" "media_signer" {
  name   = "media-objects"
  user   = aws_iam_user.media_signer.name
  policy = data.aws_iam_policy_document.media_signer.json
}

resource "aws_iam_access_key" "media_signer" {
  user = aws_iam_user.media_signer.name
}

# ---- Container registry ----------------------------------------------------------------------------------------------

resource "aws_ecr_repository" "images" {
  for_each             = toset(["api", "web"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "images" {
  for_each   = aws_ecr_repository.images
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 30 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 30 }
      action       = { type = "expire" }
    }]
  })
}

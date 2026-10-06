variable "region" {
  description = "AWS region. af-south-1 (Cape Town) is the closest AWS region to Nigeria."
  type        = string
  default     = "af-south-1"
}

variable "environment" {
  description = "staging or production"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "kubernetes_version" {
  type    = string
  default = "1.30"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.large"]
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 6
}

variable "nat_gateway_per_az" {
  description = "One NAT gateway per AZ (resilient, costs more). Staging can use a single shared one."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_allocated_storage" {
  type    = number
  default = 50
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_backup_retention_days" {
  description = "Automated backup retention. Together with point-in-time recovery this sets the RPO (minutes)."
  type        = number
  default     = 14
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "app_origins" {
  description = "Browser origins allowed to upload delivery photos straight to the media bucket (CORS)."
  type        = list(string)
}

variable "allowed_admin_cidrs" {
  description = "CIDR ranges allowed to reach the public Kubernetes API endpoint. Use your office/VPN ranges."
  type        = list(string)
  default     = []
}

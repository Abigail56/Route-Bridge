terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Configure remote state per environment, for example:
  #   terraform init -backend-config="bucket=<state-bucket>" -backend-config="key=routebridge/<env>.tfstate" \
  #                  -backend-config="region=af-south-1" -backend-config="dynamodb_table=<lock-table>"
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "routebridge"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

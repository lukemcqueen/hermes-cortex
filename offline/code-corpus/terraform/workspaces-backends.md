---
language: terraform
tags: [workspaces, backend, s3, dynamodb, cloud]
title: Workspaces & Backends
description: Terraform workspace, s3 backend, DynamoDB locking, cloud backend.
source: pattern
---

```terraform
# --- S3 backend with DynamoDB locking ---
terraform {
  backend "s3" {
    bucket         = "myapp-terraform-state"
    key            = "infra/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-locks"
  }
}

# DynamoDB table for state locking (created outside Terraform or via a separate root)
# resource "aws_dynamodb_table" "terraform_locks" {
#   name         = "terraform-state-locks"
#   billing_mode = "PAY_PER_REQUEST"
#   hash_key     = "LockID"
#   attribute {
#     name = "LockID"
#     type = "S"
#   }
# }

# --- Workspace-aware configuration ---
locals {
  # Workspace-specific configuration
  workspace_configs = {
    default = {
      instance_type = "t3.micro"
      min_size      = 1
      max_size      = 2
    }
    dev = {
      instance_type = "t3.small"
      min_size      = 1
      max_size      = 2
    }
    staging = {
      instance_type = "t3.medium"
      min_size      = 2
      max_size      = 4
    }
    prod = {
      instance_type = "t3.large"
      min_size      = 3
      max_size      = 10
    }
  }

  config     = local.workspace_configs[terraform.workspace]
  is_prod    = terraform.workspace == "prod"
  env_prefix = terraform.workspace == "default" ? "dev" : terraform.workspace
}

resource "aws_instance" "app" {
  instance_type = local.config.instance_type
  # ...
}

# --- CLI commands ---
# terraform workspace list                 # List workspaces
# terraform workspace new staging          # Create & switch
# terraform workspace select prod          # Switch workspace
# terraform plan -out plan.tfplan          # Save plan
# terraform apply plan.tfplan              # Apply saved plan

# --- Terraform Cloud / HCP Terraform backend ---
# terraform {
#   cloud {
#     organization = "my-org"
#     workspaces {
#       tags = ["infra", "environment:dev"]
#     }
#   }
# }

```

---
language: terraform
tags: [modules, composition, module-sources, version-constraints]
title: Modules
description: Module sources, composition, module outputs, root module, version constraints.
source: pattern
---

```terraform
# --- Root module calling a child module ---
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = local.name_prefix
  cidr = "10.0.0.0/16"

  azs             = ["us-east-1a", "us-east-1b", "us-east-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  enable_vpn_gateway = var.environment == "prod"

  tags = local.common_tags
}

module "ecs_cluster" {
  source = "./modules/ecs-cluster"

  cluster_name = "${local.name_prefix}-cluster"

  tags = local.common_tags
}

# --- Child module (modules/ecs-cluster/main.tf) ---
# variable "cluster_name" { type = string }
# variable "tags"         { type = map(string) }
# resource "aws_ecs_cluster" "this" {
#   name  = var.cluster_name
#   tags  = var.tags
# }
# output "cluster_arn" {
#   value = aws_ecs_cluster.this.arn
# }

# --- Root module outputs ---
output "vpc_id" {
  description = "VPC ID from the VPC module"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnets
}

```

---
language: terraform
tags: [variables, outputs, locals, validation]
title: Variables & Outputs
description: Variable blocks, type constraints, validation, sensitive, output, local values.
source: pattern
---

```terraform
# --- Input variables ---
variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "instance_count" {
  description = "Number of EC2 instances"
  type        = number
  default     = 2
}

variable "allowed_ips" {
  description = "List of CIDRs allowed SSH access"
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default = {
    Project = "myapp"
  }
}

variable "database_config" {
  description = "Database configuration"
  type = object({
    engine         = string
    version        = string
    instance_class = string
    storage_gb     = number
    multi_az       = optional(bool, false)
  })
  sensitive = false
}

# --- Locals ---
locals {
  name_prefix = "myapp-${var.environment}"
  common_tags = merge(var.tags, {
    Environment = var.environment
  })
}

# --- Outputs ---
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "database_endpoint" {
  description = "Database connection endpoint"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

```

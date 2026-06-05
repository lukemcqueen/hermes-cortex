---
language: terraform
tags: [functions, expressions, templatefile, jsonencode, merge, lookup]
title: Functions & Expressions
description: file, templatefile, jsonencode, format, merge, flatten, lookup, concat, toset.
source: pattern
---

```terraform
# --- file & templatefile ---
locals {
  # Read raw file contents
  public_key = file("~/.ssh/id_rsa.pub")

  # Render a template with variables
  user_data = templatefile("${path.module}/templates/cloud-init.tftpl", {
    hostname    = "web-01"
    ssh_key     = local.public_key
    environment = var.environment
  })
}

# --- jsonencode & yamlencode ---
resource "aws_iam_policy" "s3_access" {
  name   = "${local.name_prefix}-s3-access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "arn:aws:s3:::myapp-${var.environment}-assets/*"
      }
    ]
  })
}

# --- format ---
locals {
  # String formatting
  name = format("%s-%s-%s", var.environment, var.project, "cluster")

  # Zero-padded numbers
  subnet_names = [for i in range(3) : format("subnet-%02d", i + 1)]
  # => ["subnet-01", "subnet-02", "subnet-03"]
}

# --- merge ---
locals {
  default_tags = {
    ManagedBy = "terraform"
    Project   = "myapp"
  }
  environment_tags = {
    Environment = var.environment
    CostCenter  = var.cost_center
  }
  all_tags = merge(local.default_tags, local.environment_tags, var.extra_tags)
}

# --- flatten ---
locals {
  # Nested list → flat list
  cidr_groups = [
    ["10.0.1.0/24", "10.0.2.0/24"],
    ["10.0.3.0/24"],
    ["10.0.4.0/24", "10.0.5.0/24", "10.0.6.0/24"],
  ]
  all_cidrs = flatten(local.cidr_groups)
  # => ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24", "10.0.4.0/24", "10.0.5.0/24", "10.0.6.0/24"]
}

# --- lookup ---
locals {
  # Safe map access with default
  instance_type = {
    dev    = "t3.micro"
    staging = "t3.small"
    prod   = "t3.large"
  }
  # Fallback to "t3.micro" if environment not found
  selected_type = lookup(local.instance_type, var.environment, "t3.micro")
}

# --- concat & toset ---
locals {
  base_security_groups = ["sg-12345678", "sg-87654321"]
  extra_sgs            = ["sg-11111111", "sg-22222222"]
  all_sgs              = concat(local.base_security_groups, local.extra_sgs)
  unique_sgs           = toset(local.all_sgs)
}

# --- element & distinct ---
locals {
  # Rotate through AZs
  azs       = ["us-east-1a", "us-east-1b", "us-east-1c"]
  subnet_az = [for i in range(5) : element(local.azs, i)]
  # => ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1a", "us-east-1b"]
}

```

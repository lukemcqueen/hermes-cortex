---
language: terraform
tags: [count, for_each, for-expression, splat]
title: Count & for_each
description: count.index, for_each on resources, for expressions, splat expressions.
source: pattern
---

```terraform
variable "user_names" {
  description = "IAM users to create"
  type        = list(string)
  default     = ["alice", "bob", "charlie"]
}

variable "subnet_configs" {
  description = "Subnet definitions"
  type = map(object({
    cidr_block = string
    az         = string
  }))
  default = {
    "web-a" = { cidr_block = "10.0.1.0/24", az = "us-east-1a" }
    "web-b" = { cidr_block = "10.0.2.0/24", az = "us-east-1b" }
    "db-a"  = { cidr_block = "10.0.3.0/24", az = "us-east-1a" }
  }
}

# --- count ---
resource "aws_iam_user" "this" {
  count = length(var.user_names)
  name  = var.user_names[count.index]
  path  = "/system/"
}

# count with conditional
resource "aws_instance" "bastion" {
  count = var.create_bastion ? 1 : 0
  # ...
}

# --- for_each ---
resource "aws_subnet" "this" {
  for_each          = var.subnet_configs
  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value.cidr_block
  availability_zone = each.value.az

  tags = {
    Name = each.key
  }
}

# for_each with set
resource "aws_security_group_rule" "http_ingress" {
  for_each          = toset(var.allowed_cidr_blocks)
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = [each.key]
  security_group_id = aws_security_group.web.id
}

# --- for expressions ---
locals {
  # Transform list: ["alice", "bob"] → ["alice@example.com", "bob@example.com"]
  user_emails = [for name in var.user_names : "${name}@example.com"]

  # Filter + transform map
  web_subnet_ids = { for k, v in aws_subnet.this : k => v.id if length(regexall("^web", k)) > 0 }

  # Count of resources created
  user_count = length(aws_iam_user.this)
}

# --- splat expressions ---
output "user_arns" {
  value = aws_iam_user.this[*].arn
}

output "subnet_id_list" {
  value = values(aws_subnet.this)[*].id
}

```

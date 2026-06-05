---
language: terraform
tags: [resources, providers, basics, terraform-block]
title: Resources & Basics
description: Resource blocks, data sources, providers, terraform block, required_providers.
source: pattern
---

```terraform
terraform {
  required_version = ">= 1.6, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Resource block
resource "aws_s3_bucket" "data" {
  bucket        = "myapp-${var.environment}-data"
  force_destroy = var.environment == "dev" ? true : false
}

resource "random_id" "suffix" {
  byte_length = 4
}

# Data source
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-24.04-*-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

```

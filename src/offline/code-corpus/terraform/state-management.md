---
language: terraform
tags: [state, remote-state, state-mv, state-rm, locking]
title: State Management
description: Terraform state commands, state mv, state rm, remote state, state locking, terraform_remote_state data.
source: pattern
---

```terraform
# --- Remote state backend (S3 + DynamoDB) ---
terraform {
  backend "s3" {
    bucket         = "myapp-terraform-state"
    key            = "infra/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-locks"
  }
}

# --- Read state from another workspace ---
data "terraform_remote_state" "shared" {
  backend = "s3"

  config = {
    bucket = "shared-terraform-state"
    key    = "networking/terraform.tfstate"
    region = "us-east-1"
  }
}

# Use remote state outputs
resource "aws_instance" "app" {
  subnet_id = data.terraform_remote_state.shared.outputs.private_subnet_ids[0]
  # ...
}

# --- CLI commands (documentation, not HCL) ---
# terraform init                        # Initialize backend & providers
# terraform plan                        # Preview changes
# terraform apply                       # Apply changes
# terraform state list                  # List resources in state
# terraform state show aws_instance.app # Show details of one resource
# terraform state mv                    # Move resource in state (e.g., after rename)
#   terraform state mv aws_s3_bucket.old_name aws_s3_bucket.new_name
# terraform state rm aws_s3_bucket.orphaned  # Remove from state (no destroy)
# terraform state pull > backup.tfstate # Pull remote state locally
# terraform state push backup.tfstate   # Push local state to remote
# terraform force-unlock LOCK_ID        # Release stuck lock

```

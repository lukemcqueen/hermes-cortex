# infra1_snippets.py — Docker (5) + Terraform (10) + Kubernetes (5) snippet module
# Total: 20 entries
# Each entry: (rel_path, language, tags, title, description, source, code)

SNIPPETS = [
    # =========================================================================
    # DOCKER (5 entries)
    # =========================================================================
    (
        "docker/dockerfile-patterns.md",
        "docker",
        ["build", "pattern", "best-practices", "multi-stage"],
        "Dockerfile Patterns & Best Practices",
        "Multi-stage builds, .dockerignore, layer caching, COPY vs ADD, HEALTHCHECK.",
        "pattern",
        """# syntax=docker/dockerfile:1.4
# ---- build stage ----
FROM golang:1.22 AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app/server .

# ---- runtime stage ----
FROM gcr.io/distroless/base-debian12
COPY --from=builder /app/server /server
USER nonroot
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1
ENTRYPOINT ["/server"]
""",
    ),
    (
        "docker/compose-multi-service.md",
        "docker",
        ["compose", "multi-service", "networks", "volumes"],
        "Docker Compose Multi-Service",
        "depends_on, volumes, networks, env_file, healthcheck, restart policies.",
        "pattern",
        """services:
  api:
    build:
      context: ./api
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    env_file:
      - ./api/.env
    volumes:
      - api-data:/app/data
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - backend
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d
    networks:
      - backend
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d myapp"]
      interval: 10s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - backend
    restart: unless-stopped

volumes:
  api-data:
  pgdata:
  redis-data:

networks:
  backend:
    driver: bridge
""",
    ),
    (
        "docker/networking-volumes.md",
        "docker",
        ["networking", "volumes", "bridge", "bind-mount", "tmpfs"],
        "Docker Networking & Volumes",
        "Bridge/host/overlay networks, named volumes, bind mounts, tmpfs mounts.",
        "pattern",
        """# Create a custom bridge network
docker network create --driver bridge --subnet 172.20.0.0/16 --gateway 172.20.0.1 app-net

# Run containers on the custom network
docker run -d --name app --network app-net --ip 172.20.0.10 nginx:alpine
docker run -d --name cache --network app-net --ip 172.20.0.20 redis:7-alpine

# Named volume with driver options
docker volume create --driver local \\
  --opt type=nfs \\
  --opt o=addr=192.168.1.100,rw \\
  --opt device=:/exported/path \\
  shared-data

# Bind mount with :ro and SELinux relabeling
docker run -d --name web \\
  -v /host/www:/usr/share/nginx/html:ro,Z \\
  nginx:alpine

# tmpfs for ephemeral state
docker run -d --name session \\
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \\
  redis:7-alpine

# Inspect network
docker network inspect app-net

# Connect running container to network
docker network connect --alias api backend api-container
""",
    ),
    (
        "docker/image-optimization-security.md",
        "docker",
        ["security", "optimization", "distroless", "non-root", "scanning"],
        "Image Optimization & Security",
        "Distroless base, non-root user, minimal layers, scanning, signing, SBOM.",
        "pattern",
        """# syntax=docker/dockerfile:1.4
# === Stage 1: build ===
FROM --platform=$BUILDPLATFORM node:20-bookworm AS builder
ARG TARGETPLATFORM
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

# === Stage 2: production ===
FROM gcr.io/distroless/nodejs20-debian12:nonroot
COPY --from=builder /app/dist /app
COPY --from=builder /app/node_modules /app/node_modules
WORKDIR /app
# read-only root filesystem
USER 65532:65532
ENV NODE_ENV=production
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s \\
  CMD ["node", "-e", "require('http').get('http://localhost:3000/health',r=>process.exit(r.statusCode!==200))"]
ENTRYPOINT ["node", "server.js"]

# === Image labels for provenance ===
LABEL org.opencontainers.image.source="https://github.com/org/app" \\
      org.opencontainers.image.version="1.2.3" \\
      org.opencontainers.image.revision="abc123def456"

# Build commands (CLI, not in Dockerfile):
# docker buildx build --sbom=true --attest type=provenance, mode=max \\
#   --platform linux/amd64,linux/arm64 -t app:latest --push .
# docker scout quickview app:latest
# docker trust sign app:latest
""",
    ),
    (
        "docker/cli-advanced.md",
        "docker",
        ["cli", "buildx", "scout", "prune", "multi-arch"],
        "Docker CLI Advanced",
        "docker system df, prune filters, buildx multi-arch, docker scout, labels.",
        "pattern",
        """# --- Disk usage & cleanup ---
docker system df
docker system df -v  # detailed per-image/volume
docker system prune --all --force --filter until=24h --filter label!=keep
docker image prune --filter dangling=true --filter until=48h
docker builder prune --all --keep-storage 2GB

# --- BuildX multi-arch ---
docker buildx create --name multiarch --driver docker-container --use
docker buildx build \\
  --platform linux/amd64,linux/arm64,linux/arm/v7 \\
  --tag myapp:latest \\
  --tag myapp:1.2.0 \\
  --push \\
  --cache-from type=gha \\
  --cache-to type=gha,mode=max \\
  --attest type=sbom,generator=docker/scout-sbom-attestation \\
  --attest type=provenance,mode=max \\
  .

# --- Docker Scout ---
docker scout quickview myapp:latest
docker scout recommendations myapp:latest
docker scout cves myapp:latest --only-fixed
docker scout sbom myapp:latest --format spdx

# --- Container management ---
docker ps -a --filter status=exited --format 'table {{.ID}}\\t{{.Image}}\\t{{.Status}}'
docker logs --tail 50 --follow --timestamps mycontainer
docker inspect mycontainer --format '{{.State.Health.Status}}'
docker stats --no-stream --format 'table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}'

# --- Labels for discoverability ---
docker run -d --name web \\
  --label org.opencontainers.image.version=1.0 \\
  --label "com.example.team=platform" \\
  --label "com.example.environment=staging" \\
  nginx:alpine
docker ps --filter label=com.example.team=platform
""",
    ),
    # =========================================================================
    # TERRAFORM / HCL (10 entries)
    # =========================================================================
    (
        "terraform/resources-basics.md",
        "terraform",
        ["resources", "providers", "basics", "terraform-block"],
        "Resources & Basics",
        "Resource blocks, data sources, providers, terraform block, required_providers.",
        "pattern",
        """terraform {
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
""",
    ),
    (
        "terraform/variables-outputs.md",
        "terraform",
        ["variables", "outputs", "locals", "validation"],
        "Variables & Outputs",
        "Variable blocks, type constraints, validation, sensitive, output, local values.",
        "pattern",
        """# --- Input variables ---
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
""",
    ),
    (
        "terraform/state-management.md",
        "terraform",
        ["state", "remote-state", "state-mv", "state-rm", "locking"],
        "State Management",
        "Terraform state commands, state mv, state rm, remote state, state locking, terraform_remote_state data.",
        "pattern",
        """# --- Remote state backend (S3 + DynamoDB) ---
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
""",
    ),
    (
        "terraform/modules.md",
        "terraform",
        ["modules", "composition", "module-sources", "version-constraints"],
        "Modules",
        "Module sources, composition, module outputs, root module, version constraints.",
        "pattern",
        """# --- Root module calling a child module ---
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
""",
    ),
    (
        "terraform/aws-resources.md",
        "terraform",
        ["aws", "ec2", "s3", "security-group", "vpc", "tags"],
        "AWS Resources",
        "aws_instance, aws_s3_bucket, aws_security_group, aws_vpc basics, tags.",
        "pattern",
        """# --- VPC ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = local.name_prefix
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 100)
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name_prefix}-public-${count.index + 1}"
  }
}

# --- Security Group ---
resource "aws_security_group" "web" {
  name        = "${local.name_prefix}-web-sg"
  description = "Allow HTTP/HTTPS inbound"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# --- EC2 Instance ---
resource "aws_instance" "bastion" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.web.id]
  key_name               = aws_key_pair.bastion.key_name

  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required" # IMDSv2
  }

  tags = {
    Name = "${local.name_prefix}-bastion"
  }
}

# --- S3 Bucket ---
resource "aws_s3_bucket" "assets" {
  bucket = "myapp-${var.environment}-assets"
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration {
    status = var.environment == "prod" ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
""",
    ),
    (
        "terraform/count-for-each.md",
        "terraform",
        ["count", "for_each", "for-expression", "splat"],
        "Count & for_each",
        "count.index, for_each on resources, for expressions, splat expressions.",
        "pattern",
        """variable "user_names" {
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
""",
    ),
    (
        "terraform/workspaces-backends.md",
        "terraform",
        ["workspaces", "backend", "s3", "dynamodb", "cloud"],
        "Workspaces & Backends",
        "Terraform workspace, s3 backend, DynamoDB locking, cloud backend.",
        "pattern",
        """# --- S3 backend with DynamoDB locking ---
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
""",
    ),
    (
        "terraform/provisioners-lifecycle.md",
        "terraform",
        ["provisioners", "lifecycle", "remote-exec", "local-exec", "ignore-changes"],
        "Provisioners & Lifecycle",
        "File/remote-exec/local-exec provisioners, create_before_destroy, prevent_destroy, ignore_changes.",
        "pattern",
        """# --- Lifecycle rules ---
resource "aws_instance" "web" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.instance_type

  root_block_device {
    volume_type = "gp3"
    volume_size = 50
    encrypted   = true
  }

  lifecycle {
    # Create replacement before destroying old
    create_before_destroy = true

    # Ignore changes to AMI (managed externally)
    ignore_changes = [
      ami,
      user_data,
    ]

    # Prevent accidental deletion of prod resources
    prevent_destroy = var.environment == "prod"
  }
}

# --- Provisioners ---

# file: copy configuration files
resource "null_resource" "app_config" {
  triggers = {
    config_hash = filesha1("${path.module}/app-config.yml")
  }

  connection {
    type        = "ssh"
    host        = aws_instance.web.public_ip
    user        = "ubuntu"
    private_key = file("~/.ssh/id_rsa")
  }

  provisioner "file" {
    source      = "${path.module}/app-config.yml"
    destination = "/etc/app/config.yml"
  }
}

# remote-exec: run commands on the resource
resource "null_resource" "setup" {
  depends_on = [aws_instance.web]

  provisioner "remote-exec" {
    inline = [
      "sudo apt-get update -y",
      "sudo apt-get install -y docker.io docker-compose-v2",
      "sudo systemctl enable --now docker",
      "sudo usermod -aG docker ubuntu",
    ]
  }

  # Destroy-time provisioner
  provisioner "remote-exec" {
    when = destroy

    inline = [
      "sudo systemctl disable --now docker",
      "sudo apt-get remove -y docker.io",
    ]
  }
}

# local-exec: run on the machine running Terraform
resource "null_resource" "register_dns" {
  provisioner "local-exec" {
    command = "aws route53 change-resource-record-sets --hosted-zone-id ZONE --change-batch file://dns-update.json"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws route53 change-resource-record-sets --hosted-zone-id ZONE --change-batch file://dns-remove.json"
  }
}
""",
    ),
    (
        "terraform/cli-commands.md",
        "terraform",
        ["cli", "init", "plan", "apply", "fmt", "validate"],
        "Terraform CLI",
        "terraform init/plan/apply/destroy/fmt/validate, .terraform.lock.hcl, upgrade.",
        "pattern",
        """# --- Initialize ---
terraform init
terraform init -upgrade                              # Upgrade providers & modules
terraform init -migrate-state                        # Migrate to new backend
terraform init -reconfigure                          # Reconfigure backend without migration

# --- Format & Validate ---
terraform fmt                                        # Format all .tf files
terraform fmt -recursive -diff -check                # Recursive diff check (CI)
terraform validate                                   # Validate configuration
terraform validate -json                             # Machine-readable validation

# --- Planning ---
terraform plan                                       # Preview changes
terraform plan -out plan.tfplan                      # Save plan to file
terraform plan -var-file=prod.tfvars                 # Use variable file
terraform plan -target=module.ecs_cluster            # Plan only specific resources
terraform plan -destroy                              # Preview destroy

# --- Apply & Destroy ---
terraform apply plan.tfplan                          # Apply saved plan
terraform apply -auto-approve                        # Apply without confirmation
terraform apply -replace="aws_instance.web"          # Force replace a resource
terraform destroy                                    # Destroy all resources
terraform destroy -target=aws_instance.web           # Destroy specific resource

# --- State & Providers ---
terraform state list                                 # List resources in state
terraform show                                       # Show state or plan
terraform output                                     # Show outputs
terraform output -json                               # Outputs as JSON
terraform providers                                  # Show provider requirements
terraform providers lock -platform=linux_amd64 .     # Generate lockfile for CI

# --- Lock file (.terraform.lock.hcl) ---
# This file is auto-generated by terraform init.
# It pins provider checksums and versions.
# Check it into version control!
""",
    ),
    (
        "terraform/functions-expressions.md",
        "terraform",
        ["functions", "expressions", "templatefile", "jsonencode", "merge", "lookup"],
        "Functions & Expressions",
        "file, templatefile, jsonencode, format, merge, flatten, lookup, concat, toset.",
        "pattern",
        """# --- file & templatefile ---
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
""",
    ),
    # =========================================================================
    # KUBERNETES / YAML (5 entries)
    # =========================================================================
    (
        "kubernetes/pod-deployment.md",
        "kubernetes",
        ["deployment", "pods", "replicas", "strategy", "probes"],
        "Pods & Deployments",
        "Deployment spec, replicas, strategy, selector, containers, ports, probes.",
        "pattern",
        """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
  namespace: production
  labels:
    app: web
    tier: frontend
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
        version: "1.2.3"
    spec:
      containers:
        - name: app
          image: myregistry.azurecr.io/web-app:1.2.3
          imagePullPolicy: Always
          ports:
            - containerPort: 8080
              protocol: TCP
              name: http
            - containerPort: 8443
              protocol: TCP
              name: https
          env:
            - name: NODE_ENV
              value: "production"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: url
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 15
            timeoutSeconds: 3
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          startupProbe:
            httpGet:
              path: /startup
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 5
            failureThreshold: 30
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 1001
            capabilities:
              drop: ["ALL"]
      terminationGracePeriodSeconds: 60
      imagePullSecrets:
        - name: registry-credentials
---
apiVersion: v1
kind: Pod
metadata:
  name: web-app-canary
  namespace: production
  labels:
    app: web
    version: canary
spec:
  containers:
    - name: app
      image: myregistry.azurecr.io/web-app:canary
      ports:
        - containerPort: 8080
""",
    ),
    (
        "kubernetes/services-ingress.md",
        "kubernetes",
        ["service", "ingress", "load-balancer", "clusterip", "tls"],
        "Services & Ingress",
        "ClusterIP, NodePort, LoadBalancer, Ingress rules, TLS, annotations.",
        "pattern",
        """---
apiVersion: v1
kind: Service
metadata:
  name: web-service
  namespace: production
  labels:
    app: web
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: http
    - name: https
      port: 443
      targetPort: https
  selector:
    app: web

---
apiVersion: v1
kind: Service
metadata:
  name: api-service
  namespace: production
spec:
  type: NodePort
  ports:
    - port: 8080
      targetPort: 8080
      nodePort: 30080
  selector:
    app: api

---
apiVersion: v1
kind: Service
metadata:
  name: admin-service
  namespace: production
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "external"
    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
spec:
  type: LoadBalancer
  ports:
    - port: 443
      targetPort: 8443
  selector:
    app: admin

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: main-ingress
  namespace: production
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - app.example.com
        - api.example.com
      secretName: example-tls
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-service
                port:
                  number: 80
    - host: api.example.com
      http:
        paths:
          - path: /v1
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 8080
""",
    ),
    (
        "kubernetes/configmaps-secrets.md",
        "kubernetes",
        ["configmap", "secret", "env", "volume-mount", "immutable"],
        "ConfigMaps & Secrets",
        "ConfigMap from literal/file, Secret, envFrom, volume mount, immutable.",
        "pattern",
        """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: production
  labels:
    app: web
immutable: false
data:
  # Literal key-value pairs
  NODE_ENV: "production"
  LOG_LEVEL: "info"
  API_PORT: "8080"
  # Structured config
  app.yaml: |
    features:
      signup: true
      dark_mode: false
    limits:
      max_upload_mb: 50
      rate_per_minute: 100

---
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
  namespace: production
type: Opaque
stringData:
  url: "postgresql://app:${DB_PASSWORD}@db.internal:5432/mydb"
  username: "app"
  password: "s3cure-p@ssword"
---
# Secrets must be encoded in base64 when not using stringData
apiVersion: v1
kind: Secret
metadata:
  name: tls-cert
  namespace: production
type: kubernetes.io/tls
data:
  tls.crt: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t...
  tls.key: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0t...

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
  namespace: production
spec:
  template:
    spec:
      containers:
        - name: app
          image: web-app:latest
          envFrom:
            - configMapRef:
                name: app-config
            - secretRef:
                name: db-credentials
          env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: password
          volumeMounts:
            - name: config-volume
              mountPath: /etc/app
              readOnly: true
      volumes:
        - name: config-volume
          configMap:
            name: app-config
            items:
              - key: app.yaml
                path: app.yaml
---
# Immutable ConfigMap (cannot be updated, only recreated)
apiVersion: v1
kind: ConfigMap
metadata:
  name: base-config
  namespace: production
immutable: true
data:
  timezone: "UTC"
  locale: "en-US"
""",
    ),
    (
        "kubernetes/persistent-volumes-claims.md",
        "kubernetes",
        ["persistent-volume", "persistent-volume-claim", "storage-class", "access-modes"],
        "Persistent Volumes & Claims",
        "PersistentVolume, PersistentVolumeClaim, StorageClass, accessModes.",
        "pattern",
        """---
# StorageClass for dynamic provisioning
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
  encrypted: "true"
  fstype: ext4
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer

---
# PersistentVolumeClaim (requests dynamic PV via StorageClass)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
  namespace: production
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: fast-ssd
  resources:
    requests:
      storage: 100Gi
  selector:
    matchLabels:
      tier: database

---
# Static PersistentVolume (pre-provisioned)
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nfs-share
  labels:
    tier: shared
spec:
  capacity:
    storage: 5Ti
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-standard
  mountOptions:
    - hard
    - nfsvers=4.1
  nfs:
    path: /exported/data
    server: 192.168.1.100

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: production
spec:
  serviceName: postgres-headless
  replicas: 3
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          envFrom:
            - secretRef:
                name: db-credentials
          ports:
            - containerPort: 5432
              name: pg
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
              subPath: pgdata
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: fast-ssd
        resources:
          requests:
            storage: 100Gi
""",
    ),
    (
        "kubernetes/helm-charts.md",
        "kubernetes",
        ["helm", "chart", "values", "templates", "helpers"],
        "Helm Charts",
        "Chart.yaml, values.yaml, templates, _helpers.tpl, with range, include, template.",
        "pattern",
        """# --- Chart.yaml ---
apiVersion: v2
name: web-app
description: A Helm chart for the web application
type: application
version: 0.1.0
appVersion: "1.2.3"
home: https://github.com/example/web-app
maintainers:
  - name: Platform Team
    email: platform@example.com
dependencies:
  - name: postgresql
    version: "~12.0"
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled
  - name: redis
    version: "~17.0"
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled

# --- values.yaml ---
replicaCount: 3

image:
  repository: myregistry.azurecr.io/web-app
  tag: "1.2.3"
  pullPolicy: Always

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: app.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: web-app-tls
      hosts:
        - app.example.com

resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

env:
  NODE_ENV: production
  LOG_LEVEL: info

postgresql:
  enabled: true
  auth:
    database: myapp
    username: app

redis:
  enabled: true
  architecture: standalone

# --- templates/_helpers.tpl ---
{{- define "web-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "web-app.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "web-app.labels" -}}
helm.sh/chart: "{{ include "web-app.name" . }}-{{ .Chart.Version }}"
app.kubernetes.io/name: "{{ include "web-app.name" . }}"
app.kubernetes.io/instance: "{{ .Release.Name }}"
app.kubernetes.io/version: "{{ .Chart.AppVersion }}"
app.kubernetes.io/managed-by: "{{ .Release.Service }}"
{{- end }}

# --- templates/deployment.yaml ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "web-app.fullname" . }}
  labels:
    {{- include "web-app.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ include "web-app.name" . }}
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {{ include "web-app.name" . }}
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: 8080
              name: http
          env:
            {{- range $key, $val := .Values.env }}
            - name: {{ $key }}
              value: {{ $val | quote }}
            {{- end }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
EOF
""",
    ),
]

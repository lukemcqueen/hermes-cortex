---
language: terraform
tags: [provisioners, lifecycle, remote-exec, local-exec, ignore-changes]
title: Provisioners & Lifecycle
description: File/remote-exec/local-exec provisioners, create_before_destroy, prevent_destroy, ignore_changes.
source: pattern
---

```terraform
# --- Lifecycle rules ---
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

```

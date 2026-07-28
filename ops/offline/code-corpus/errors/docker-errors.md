---
language: shell
tags: [errors, debugging, docker, container]
title: Common Docker Errors
description: Frequent Docker errors — port already in use, container exits immediately, permission denied volumes, exec format error, no space on device — with messages, causes, and fixes
source: pattern
---

```shell
# ---------------------------------------------------------------------------
# 1. Port already in use
# ---------------------------------------------------------------------------
# Error message:
#   docker: Error response from daemon: driver failed programming external
#   connectivity on endpoint <name>: Bind for 0.0.0.0:8080 failed:
#   port is already allocated
#   Error response from daemon: Ports are not available:
#   listen tcp 0.0.0.0:5432: bind: address already in use
#
# Cause:
#   - Another container is already using the port
#   - A host process is using the port
#   - Previous container didn't stop cleanly
#
# Fixes:

# Fix 1: Find what's using the port and kill/stop it
lsof -i :8080                # Find process on port 8080 (macOS/Linux)
sudo lsof -i -P -n | grep 8080  # More detailed
docker ps                    # Check if another container binds this port

# Stop the conflicting container
docker stop <container-id>

# Or kill the host process (Linux)
# sudo kill -9 <PID>

# Fix 2: Use a different port mapping
# docker run -p 8081:8080 my-image   # Map port 8081 externally

# Fix 3: Remove stopped containers that might still hold references
docker container prune

# Fix 4: On macOS, the port might be held by a stale process
# sudo lsof -i :8080
# kill -9 <PID>

# ---------------------------------------------------------------------------
# 2. Container exits immediately
# ---------------------------------------------------------------------------
# Error message:
#   docker run my-image
#   (container starts and exits immediately, no output)
#   docker ps -a shows "Exited (0)" or "Exited (1)"
#
# Cause:
#   - The main process completed/terminated immediately
#   - Command or entrypoint not specified correctly
#   - The container has no foreground process
#   - Application crashed on startup
#
# Fixes:

# Fix 1: Run with interactive terminal to see output
docker run -it --rm my-image bash

# Fix 2: Check logs
docker logs <container-id>

# Fix 3: Override the command
docker run --rm my-image /bin/sh -c "tail -f /dev/null"

# Fix 4: Inspect the Dockerfile — CMD must be a long-running process
# ❌ CMD ["python", "setup.py"]  # Runs once, exits
# ✅ CMD ["python", "app.py"]     # Runs a web server

# Fix 5: Check entrypoint vs CMD interaction
# docker inspect <container-id> | jq '.[0].Config.Cmd'

# ---------------------------------------------------------------------------
# 3. Permission denied on volumes / bind mounts
# ---------------------------------------------------------------------------
# Error message:
#   PermissionError: [Errno 13] Permission denied: '/app/data'
#   touch: cannot touch '/opt/app/logs/test.log': Permission denied
#   Can't create directory /var/lib/mysql: Permission denied
#
# Cause:
#   - Container user (often root, or a non-root user) doesn't have write
#     permission on the host-mounted directory
#   - SELinux context prevents access (Linux)
#   - macOS: Docker Desktop uses a VM, mounted files have different UID/GID
#
# Fixes:

# Fix 1: Match the container user to your host user
# Find your host UID
id -u   # e.g., 1000

# Run container with matching UID
docker run --rm -v $(pwd)/data:/app/data \
  --user "$(id -u):$(id -g)" \
  my-image

# Fix 2: Fix permissions on the host directory
chmod 777 ./data    # Loose but simple (dev only)
chown 1000:1000 ./data  # Match container's user

# Fix 3: In Dockerfile, create the directory and set permissions
# RUN mkdir -p /app/data && chmod 777 /app/data

# Fix 4: For Linux SELinux, add the :z or :Z flag
# docker run -v $(pwd)/data:/app/data:Z my-image

# Fix 5: Docker Desktop on macOS — files are owned by the "moby" VM user
# Use named volumes instead of bind mounts if possible
# docker volume create data-volume
# docker run -v data-volume:/app/data my-image

# ---------------------------------------------------------------------------
# 4. exec format error / standard_init_linux.go
# ---------------------------------------------------------------------------
# Error message:
#   standard_init_linux.go:228: exec user process caused: exec format error
#   /bin/sh: 1: ./entrypoint.sh: not found
#   /usr/bin/env: 'node\r': No such file or directory
#
# Cause:
#   - Binary compiled for the wrong architecture (e.g., ARM binary on AMD64)
#   - Shell script has Windows line endings (CRLF instead of LF)
#   - Missing shebang line in script
#   - File not marked as executable
#
# Fixes:

# Fix 1: Check architecture mismatch
docker inspect my-image | jq '.[0].Architecture'
# If it says arm64 and you're on amd64 (or vice versa), rebuild for the right arch
# Use --platform flag:
docker run --platform linux/amd64 my-image

# Fix 2: Fix line endings (Windows CRLF → Unix LF)
# In Dockerfile:
# RUN sed -i 's/\r$//' entrypoint.sh
# Or use dos2unix:
# RUN apt-get update && apt-get install -y dos2unix \
#     && dos2unix entrypoint.sh

# Fix 3: Add proper shebang to entrypoint scripts
#!/bin/bash
#!/usr/bin/env bash
#!/usr/bin/env python3

# Fix 4: Make the file executable
# In Dockerfile:
# COPY entrypoint.sh /entrypoint.sh
# RUN chmod +x /entrypoint.sh

# ---------------------------------------------------------------------------
# 5. No space left on device
# ---------------------------------------------------------------------------
# Error message:
#   Error response from daemon: write /var/lib/docker/overlay2/...: no space left on device
#   write /var/lib/docker/tmp/...: no space left on device
#   Error processing tar file(exit status 1): write /...: no space left on device
#
# Cause:
#   - Disk is full (containers, images, volumes accumulated)
#   - Docker overlay2 storage driver filled up
#   - Log files grew too large
#
# Fixes:

# Fix 1: Check disk usage
df -h                       # Check overall disk space
docker system df            # Check Docker disk usage

# Fix 2: Clean up Docker resources
docker system prune -a --volumes
# 🔴 NEVER use --volumes in automated scripts — destroys irreplaceable data
# Removes: stopped containers, unused networks, dangling images,
#          unused build cache, and all volumes not used by a container

# Fix 3: More targeted cleanup
docker container prune      # Remove stopped containers
docker image prune -a       # Remove unused images
docker volume prune         # Remove unused volumes
# 🔴 NEVER run in automated scripts — destroys irreplaceable data
docker builder prune        # Remove build cache

# Fix 4: Limit log file size (global config)
# /etc/docker/daemon.json:
# {
#   "log-driver": "json-file",
#   "log-opts": {
#     "max-size": "10m",
#     "max-file": "3"
#   }
# }
# Then restart Docker: sudo systemctl restart docker

# Fix 5: Move Docker storage to a larger disk (Linux)
# Edit /etc/docker/daemon.json:
# { "data-root": "/mnt/large-disk/docker" }

# Fix 6: Check for dangling build cache
docker builder prune --all

# ---------------------------------------------------------------------------
# 6. Connection refused / Cannot reach Docker daemon
# ---------------------------------------------------------------------------
# Error message:
#   Cannot connect to the Docker daemon at unix:///var/run/docker.sock.
#   Is the docker daemon running?
#   docker: dial unix /var/run/docker.sock: connect: connection refused
#
# Cause:
#   - Docker daemon not running
#   - User not in the docker group (Linux)
#   - DOCKER_HOST environment variable pointing to wrong socket
#   - Docker Desktop not started (macOS/Windows)
#
# Fixes:

# Fix 1: Start Docker daemon (Linux)
sudo systemctl start docker
sudo systemctl enable docker  # Auto-start on boot

# Fix 2: Start Docker Desktop (macOS)
# Open Docker Desktop application

# Fix 3: Add user to docker group (Linux, then re-login)
sudo usermod -aG docker $USER
# Then: newgrp docker  (or logout and back in)

# Fix 4: Check DOCKER_HOST
echo $DOCKER_HOST
# If set incorrectly: unset DOCKER_HOST

# Fix 5: Check daemon status
docker info
sudo systemctl status docker
```
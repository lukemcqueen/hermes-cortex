---
language: docker
tags: [cli, buildx, scout, prune, multi-arch]
title: Docker CLI Advanced
description: docker system df, prune filters, buildx multi-arch, docker scout, labels.
source: pattern
---

```docker
# --- Disk usage & cleanup ---
docker system df
docker system df -v  # detailed per-image/volume
docker system prune --all --force --filter until=24h --filter label!=keep
docker image prune --filter dangling=true --filter until=48h
docker builder prune --all --keep-storage 2GB

# --- BuildX multi-arch ---
docker buildx create --name multiarch --driver docker-container --use
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag myapp:latest \
  --tag myapp:1.2.0 \
  --push \
  --cache-from type=gha \
  --cache-to type=gha,mode=max \
  --attest type=sbom,generator=docker/scout-sbom-attestation \
  --attest type=provenance,mode=max \
  .

# --- Docker Scout ---
docker scout quickview myapp:latest
docker scout recommendations myapp:latest
docker scout cves myapp:latest --only-fixed
docker scout sbom myapp:latest --format spdx

# --- Container management ---
docker ps -a --filter status=exited --format 'table {{.ID}}\t{{.Image}}\t{{.Status}}'
docker logs --tail 50 --follow --timestamps mycontainer
docker inspect mycontainer --format '{{.State.Health.Status}}'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'

# --- Labels for discoverability ---
docker run -d --name web \
  --label org.opencontainers.image.version=1.0 \
  --label "com.example.team=platform" \
  --label "com.example.environment=staging" \
  nginx:alpine
docker ps --filter label=com.example.team=platform

```

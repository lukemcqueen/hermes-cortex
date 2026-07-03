---
language: docker
tags: [security, optimization, distroless, non-root, scanning]
title: Image Optimization & Security
description: Distroless base, non-root user, minimal layers, scanning, signing, SBOM.
source: pattern
---

```docker
# syntax=docker/dockerfile:1.4
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
HEALTHCHECK --interval=30s --timeout=3s \
  CMD ["node", "-e", "require('http').get('http://localhost:3000/health',r=>process.exit(r.statusCode!==200))"]
ENTRYPOINT ["node", "server.js"]

# === Image labels for provenance ===
LABEL org.opencontainers.image.source="https://github.com/org/app" \
      org.opencontainers.image.version="1.2.3" \
      org.opencontainers.image.revision="abc123def456"

# Build commands (CLI, not in Dockerfile):
# docker buildx build --sbom=true --attest type=provenance, mode=max \
#   --platform linux/amd64,linux/arm64 -t app:latest --push .
# docker scout quickview app:latest
# docker trust sign app:latest

```

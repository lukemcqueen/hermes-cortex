---
language: docker
tags: [build, pattern, best-practices, multi-stage]
title: Dockerfile Patterns & Best Practices
description: Multi-stage builds, .dockerignore, layer caching, COPY vs ADD, HEALTHCHECK.
source: pattern
---

```docker
# syntax=docker/dockerfile:1.4
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
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1
ENTRYPOINT ["/server"]

```

---
language: shell
tags: [docker, registry, maintenance, cleanup]
title: Docker Registry Maintenance
description: Garbage collection, API-based tag cleanup, storage backends, retention policies, debugging
source: pattern
---

# Docker Registry Maintenance

## Garbage Collection — Removing Deleted Blobs

```bash
# Garbage collection removes unreferenced blobs from storage
# Required after DELETE operations — manifests are deleted but blobs remain

# Dry run (shows what would be removed, does nothing)
docker exec docker-registry bin/registry garbage-collect \
  --dry-run /etc/docker/registry/config.yml

# Actual garbage collection
docker exec docker-registry bin/registry garbage-collect \
  /etc/docker/registry/config.yml

# For verbose output
docker exec docker-registry bin/registry garbage-collect \
  --verbose /etc/docker/registry/config.yml

# Output shows:
#   blobs marked: 42
#   blobs eligible for deletion: 12
#   blobs deleted: 12
#   blobs would be deleted: 12  (dry-run)

# Schedule with cron (weekly)
cat > /etc/cron.weekly/registry-gc << 'CRON'
#!/bin/bash
# Docker Registry garbage collection
docker exec docker-registry bin/registry garbage-collect \
  /etc/docker/registry/config.yml > /var/log/registry-gc.log 2>&1
CRON
chmod +x /etc/cron.weekly/registry-gc
```

## Cleaning Old Tags via Registry API

```bash
#!/bin/bash
# Delete tags older than N days from a repository
# Requires REGISTRY_STORAGE_DELETE_ENABLED: "true" in registry config

REGISTRY="registry.example.com"
REPO="myapp"
USER="adminuser"
PASS="strongpassword"
RETENTION_DAYS=30
CUTOFF=$(date -d "$RETENTION_DAYS days ago" +%s)

# Get all tags with their creation dates
TAGS=$(curl -s -u "$USER:$PASS" \
  "https://$REGISTRY/v2/$REPO/tags/list" | jq -r '.tags[]' 2>/dev/null)

for TAG in $TAGS; do
  # Skip 'latest' — keep it
  [ "$TAG" = "latest" ] && continue

  # Get manifest creation timestamp from registry
  MANIFEST=$(curl -s -u "$USER:$PASS" \
    -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
    "https://$REGISTRY/v2/$REPO/manifests/$TAG")

  CREATED=$(echo "$MANIFEST" | jq -r '.history[0].v1Compatibility' 2>/dev/null \
    | jq -r '.created' 2>/dev/null || echo "")

  if [ -n "$CREATED" ]; then
    CREATED_TS=$(date -d "$CREATED" +%s 2>/dev/null || echo 0)
    if [ "$CREATED_TS" -gt 0 ] && [ "$CREATED_TS" -lt "$CUTOFF" ]; then
      echo "Deleting $REPO:$TAG (created: $CREATED)"

      # Get digest
      DIGEST=$(curl -sI -u "$USER:$PASS" \
        -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
        "https://$REGISTRY/v2/$REPO/manifests/$TAG" \
        | grep -i "Docker-Content-Digest" | awk '{print $2}' | tr -d '\r')

      # Delete manifest
      curl -s -X DELETE -u "$USER:$PASS" \
        "https://$REGISTRY/v2/$REPO/manifests/$DIGEST"
    fi
  fi
done

echo "Tag cleanup complete. Run garbage collection to free disk space."
```

## Retention Policies

```bash
#!/bin/bash
# Retention policy script: keep N latest tags per repository

REGISTRY="registry.example.com"
USER="adminuser"
PASS="strongpassword"
KEEP_LATEST=10

# List all repositories
REPOS=$(curl -s -u "$USER:$PASS" \
  "https://$REGISTRY/v2/_catalog" | jq -r '.repositories[]')

for REPO in $REPOS; do
  # Get all tags sorted by creation date (oldest first)
  TAGS=$(curl -s -u "$USER:$PASS" \
    "https://$REGISTRY/v2/$REPO/tags/list" | jq -r '.tags[]' | sort)

  TAG_COUNT=$(echo "$TAGS" | wc -l)

  if [ "$TAG_COUNT" -gt "$KEEP_LATEST" ]; then
    # Tags to delete = all except the KEEP_LATEST newest
    TO_DELETE=$(echo "$TAGS" | head -n -$KEEP_LATEST)
    TO_KEEP=$(echo "$TAGS" | tail -n $KEEP_LATEST)

    echo "Repository: $REPO"
    echo "  Tags: $TAG_COUNT"
    echo "  Keeping ${KEEP_LATEST}: $(echo $TO_KEEP | tr '\n' ' ')"
    echo "  Deleting $(echo "$TO_DELETE" | wc -l) old tags"

    for TAG in $TO_DELETE; do
      DIGEST=$(curl -sI -u "$USER:$PASS" \
        -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
        "https://$REGISTRY/v2/$REPO/manifests/$TAG" \
        | grep -i "Docker-Content-Digest" | awk '{print $2}' | tr -d '\r')

      [ -n "$DIGEST" ] && curl -s -X DELETE -u "$USER:$PASS" \
        "https://$REGISTRY/v2/$REPO/manifests/$DIGEST"
    done
  fi
done

# Run garbage collection after policy cleanup
docker exec docker-registry bin/registry garbage-collect \
  /etc/docker/registry/config.yml
```

## Storage Backends

```yaml
# Filesystem backend (default)
storage:
  filesystem:
    rootdirectory: /var/lib/registry
    maxthreads: 100
```

```yaml
# S3 backend (AWS)
storage:
  s3:
    accesskey: YOUR_AWS_ACCESS_KEY
    secretkey: YOUR_AWS_SECRET_KEY
    region: us-east-1
    bucket: my-docker-registry
    rootdirectory: /docker/registry
    encrypt: true
    secure: true
    v4auth: true
    chunksize: 5242880
    multipartchunksize: 33554432
    multipartcopychunksize: 33554432
    multipartcopymaxconcurrency: 100
    useredundancy: false
    objectacl: private
```

```yaml
# Azure Blob Storage
storage:
  azure:
    accountname: mystorageaccount
    accountkey: your_base64_account_key
    container: docker-registry
    realm: core.windows.net
```

```yaml
# GCS backend (Google Cloud Storage)
storage:
  gcs:
    bucket: my-docker-registry
    keyfile: /etc/docker/registry/gcs-key.json
    rootdirectory: /docker/registry
    chunksize: 5242880
```

## Registry Debugging

```bash
# Check registry logs
docker logs docker-registry
docker logs docker-registry --tail 100 -f

# Increase log level (temporary — via environment)
# Set REGISTRY_LOG_LEVEL: debug in docker-compose.yml and restart

# Test connectivity
curl -v https://registry.example.com/v2/
curl -v -u adminuser:password https://registry.example.com/v2/_catalog

# Check TLS cert details
echo | openssl s_client -connect registry.example.com:443 2>/dev/null | \
  openssl x509 -noout -dates -subject -issuer

# Storage usage
du -sh /var/lib/docker/volumes/registry-data/_data/

# Debug registry configuration
docker exec docker-registry cat /etc/docker/registry/config.yml

# Test auth
docker run --rm --entrypoint htpasswd httpd:2-alpine -v 2>/dev/null
# htpasswd: verify password
docker run --rm -v $(pwd)/auth:/auth:ro --entrypoint htpasswd httpd:2-alpine \
  -v /auth/htpasswd adminuser

# Registry health endpoint
curl https://registry.example.com/debug/health  # if debug enabled

# Prometheus metrics
curl https://registry.example.com/debug/metrics  # if debug/metrics enabled

# Check which images are biggest consumers
du -sh /var/lib/docker/volumes/registry-data/_data/docker/registry/v2/blobs/sha256/*/* | \
  sort -rh | head -20
```

## Full Maintenance Script

```bash
#!/bin/bash
# Weekly registry maintenance: tag cleanup + GC + report

set -euo pipefail

REGISTRY="registry.example.com"
USER="adminuser"
PASS="strongpassword"
KEEP_TAGS=20
LOG="/var/log/registry-maintenance.log"

echo "$(date) — Starting registry maintenance" | tee -a "$LOG"

echo "=== 1. Delete tags beyond retention ===" | tee -a "$LOG"
REPOS=$(curl -s -u "$USER:$PASS" "https://$REGISTRY/v2/_catalog" | jq -r '.repositories[]')
for REPO in $REPOS; do
  TAGS=$(curl -s -u "$USER:$PASS" "https://$REGISTRY/v2/$REPO/tags/list" | jq -r '.tags[]' | sort)
  COUNT=$(echo "$TAGS" | wc -l)
  if [ "$COUNT" -gt "$KEEP_TAGS" ]; then
    echo "  $REPO: $COUNT tags, deleting $(($COUNT - $KEEP_TAGS))" | tee -a "$LOG"
    echo "$TAGS" | head -n -$KEEP_TAGS | while read TAG; do
      DIGEST=$(curl -sI -u "$USER:$PASS" \
        -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
        "https://$REGISTRY/v2/$REPO/manifests/$TAG" \
        | grep -i "Docker-Content-Digest" | awk '{print $2}' | tr -d '\r')
      [ -n "$DIGEST" ] && curl -s -X DELETE -u "$USER:$PASS" \
        "https://$REGISTRY/v2/$REPO/manifests/$DIGEST"
    done
  fi
done

echo "=== 2. Garbage collection ===" | tee -a "$LOG"
docker exec docker-registry bin/registry garbage-collect \
  /etc/docker/registry/config.yml 2>&1 | tee -a "$LOG"

echo "=== 3. Storage usage ===" | tee -a "$LOG"
du -sh /var/lib/docker/volumes/registry-data/_data/ 2>/dev/null | tee -a "$LOG"
docker exec docker-registry du -sh /var/lib/registry 2>/dev/null | tee -a "$LOG"

echo "$(date) — Maintenance complete" | tee -a "$LOG"
```
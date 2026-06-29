---
language: yaml
tags: [docker, registry, container, deployment]
title: Docker Registry Setup
description: Running registry:2 with docker-compose, htpasswd auth, TLS with certbot, push/pull
source: pattern
---

# Docker Registry Setup

## docker-compose.yml — Minimal Registry

```yaml
version: '3.8'

services:
  registry:
    image: registry:2
    container_name: docker-registry
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      REGISTRY_STORAGE_FILESYSTEM_ROOTDIRECTORY: /var/lib/registry
    volumes:
      - registry-data:/var/lib/registry

volumes:
  registry-data:
```

```bash
# Start registry
docker compose up -d

# Verify it's running
curl http://localhost:5000/v2/
# Response: {}

# Test push/pull (tag and push an image)
docker pull alpine:latest
docker tag alpine:latest localhost:5000/alpine:latest
docker push localhost:5000/alpine:latest

# List repositories
curl http://localhost:5000/v2/_catalog

# List tags for a repository
curl http://localhost:5000/v2/alpine/tags/list

# Pull from local registry
docker pull localhost:5000/alpine:latest
```

## Full Registry with Auth & TLS

```yaml
version: '3.8'

services:
  registry:
    image: registry:2
    container_name: docker-registry
    restart: unless-stopped
    ports:
      - "443:5000"        # Map host 443 → container 5000
    environment:
      # TLS
      REGISTRY_HTTP_TLS_CERTIFICATE: /certs/fullchain.pem
      REGISTRY_HTTP_TLS_KEY: /certs/privkey.pem

      # Auth (htpasswd)
      REGISTRY_AUTH: htpasswd
      REGISTRY_AUTH_HTPASSWD_REALM: Registry Realm
      REGISTRY_AUTH_HTPASSWD_PATH: /auth/htpasswd

      # Storage
      REGISTRY_STORAGE_FILESYSTEM_ROOTDIRECTORY: /var/lib/registry

      # Limits & perf
      REGISTRY_HTTP_SECRET: change-this-secret-key
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
      REGISTRY_STORAGE_MAINTENANCE_READONLY:
        enabled: false

      # Upload pacing
      REGISTRY_HTTP_RELATIVEURLS: "true"

    volumes:
      - registry-data:/var/lib/registry
      - ./certs:/certs:ro
      - ./auth:/auth:ro
      - ./config.yml:/etc/docker/registry/config.yml:ro

volumes:
  registry-data:
```

## Authentication — htpasswd

```bash
# Create auth directory
mkdir -p auth

# Create htpasswd file with bcrypt (Docker registry requires bcrypt)
docker run --rm --entrypoint htpasswd httpd:2-alpine \
    -Bbn adminuser strongpassword > auth/htpasswd

# Add more users
docker run --rm --entrypoint htpasswd httpd:2-alpine \
    -Bbn readeruser readonlypass >> auth/htpasswd

# Verify content
cat auth/htpasswd
# adminuser:$2y$05$...
# readeruser:$2y$05$...

# Test authentication
curl -u adminuser:strongpassword https://registry.example.com/v2/_catalog
curl -u adminuser:strongpassword https://registry.example.com/v2/alpine/tags/list
```

## TLS with Certbot (Let's Encrypt)

```bash
# Generate certificate (standalone mode, port 80 must be free)
sudo certbot certonly --standalone -d registry.example.com

# Copy certs to registry directory
mkdir -p certs
sudo cp /etc/letsencrypt/live/registry.example.com/fullchain.pem certs/
sudo cp /etc/letsencrypt/live/registry.example.com/privkey.pem certs/
sudo chmod 600 certs/privkey.pem
sudo chown -R $(id -u):$(id -g) certs/

# Auto-renewal hook to copy certs and restart registry
sudo mkdir -p /etc/letsencrypt/renewal-hooks/post/
cat > renew-registry-certs.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail
DOMAIN="registry.example.com"
CERT_DIR="/opt/registry/certs"
COMPOSE_DIR="/opt/registry"

cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $CERT_DIR/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $CERT_DIR/
chmod 600 $CERT_DIR/privkey.pem
cd $COMPOSE_DIR && docker compose restart registry
SCRIPT

sudo mv renew-registry-certs.sh /etc/letsencrypt/renewal-hooks/post/
sudo chmod +x /etc/letsencrypt/renewal-hooks/post/renew-registry-certs.sh

# Test renewal
sudo certbot renew --dry-run
```

## Client Configuration — Docker daemon

```bash
# Insecure registry (no TLS — dev only)
# /etc/docker/daemon.json
cat > /etc/docker/daemon.json << 'EOF'
{
  "insecure-registries": ["registry.example.com:5000"]
}
EOF
systemctl restart docker

# Self-signed cert (/etc/docker/certs.d/)
# For each registry, place CA certificate:
mkdir -p /etc/docker/certs.d/registry.example.com:5000
cp ca.crt /etc/docker/certs.d/registry.example.com:5000/ca.crt

# Docker Desktop (macOS/Windows): add cert to keychain
# sudo security add-trusted-cert -d -r trustRoot \
#   -k /Library/Keychains/System.keychain ca.crt
```

## Push & Pull to Authenticated Registry

```bash
# Login
docker login registry.example.com
# Username: adminuser
# Password: ********

# Push
docker tag myapp:latest registry.example.com/myapp:latest
docker push registry.example.com/myapp:latest

# Pull
docker pull registry.example.com/myapp:latest

# Login with a different user (read-only)
docker login registry.example.com -u readeruser -p "$READER_PASS"

# Docker credential helper (avoids storing in plain text)
# On macOS, Docker uses osxkeychain by default
```

## Registry API Usage

```bash
# Catalog (list repos)
curl -s -u adminuser:password https://registry.example.com/v2/_catalog | jq .

# List tags
curl -s -u adminuser:password https://registry.example.com/v2/myapp/tags/list | jq .

# Get manifest
curl -s -u adminuser:password \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
  https://registry.example.com/v2/myapp/manifests/latest | jq .

# Get digest from manifest
DIGEST=$(curl -s -u adminuser:password \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
  -I https://registry.example.com/v2/myapp/manifests/latest \
  | grep -i "Docker-Content-Digest" | awk '{print $2}' | tr -d '\r')
echo "Digest: $DIGEST"

# Delete manifest (requires digest, not tag)
# Requires REGISTRY_STORAGE_DELETE_ENABLED: "true"
curl -X DELETE -u adminuser:password \
  https://registry.example.com/v2/myapp/manifests/$DIGEST

# Check blob existence
curl -o /dev/null -s -w "%{http_code}" -u adminuser:password \
  https://registry.example.com/v2/myapp/blobs/$DIGEST
```

## Registry Configuration (config.yml)

```yaml
# /etc/docker/registry/config.yml — advanced options
version: 0.1
log:
  level: info
  fields:
    service: registry

storage:
  cache:
    blobdescriptor: inmemory
  filesystem:
    rootdirectory: /var/lib/registry
    maxthreads: 100

http:
  addr: :5000
  secret: change-this-secret
  headers:
    X-Content-Type-Options: [nosniff]
  debug:
    addr: :5001
    prometheus:
      enabled: true
      path: /metrics

health:
  storagedriver:
    enabled: true
    interval: 10s
    threshold: 3

auth:
  htpasswd:
    realm: Registry Realm
    path: /auth/htpasswd
```
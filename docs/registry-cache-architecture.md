# Registry Cache Architecture — Tiered Pull-Through

**Titus** (dev laptop, L1) → **Joseph** (L2) → **Docker Hub**
**Moses** (orchestrator, L1) → **Joseph** (L2) → **Docker Hub**
**Joseph** (L2 cache, 200GB) → **Docker Hub**
**Gisu** (ACME staging, L1) → **Docker Hub**
**Kustos** (ACME prod) → **Gisu** → **Docker Hub**

Two independent islands:
- **Personal island:** Titus → Joseph → Docker Hub, Moses → Joseph → Docker Hub
- **ACME island:** Kustos → Gisu → Docker Hub

## Topology

```
                    ┌──────────────────────────────────────────────┐
                    │                 Docker Hub                    │
                    │         (registry-1.docker.io)                │
                    └────────┬──────────────────┬──────────────────┘
                             │                  │
                    ┌────────┴────┐    ┌────────┴──────┐
                    │ Joseph      │    │ Gisu          │
                    │ L2: 200GB   │    │ L1: 50GB      │
                    │ proxy→Hub   │    │ proxy→Hub     │
                    └──────┬──────┘    └───────┬───────┘
                           │                   │
              ┌────────────┴──────┐    ┌───────┴───────┐
              │                  │    │               │
     ┌────────┴────┐    ┌───────┴──────┐ ┌────┴──────┐  │
     │ Titus       │    │ Moses        │ │ Kustos    │  │
     │ dev laptop  │    │ orchestrator │ │ ACME    │  │
     │ L1: local   │    │ L1: local    │ │ no cache  │
     │ proxy→Joseph│    │ proxy→Joseph │ │ mirr→Gisu │
     └─────────────┘    └──────────────┘ └───────────┘

Cache hierarchy:
  Titus  → Joseph → Docker Hub
  Moses  → Joseph → Docker Hub
  Joseph → Docker Hub
  Gisu   → Docker Hub
  Kustos → Gisu   → Docker Hub
```

## Per-Server Config

### Joseph (personal server — lots of disk, always on)

Registry proxies directly to Docker Hub. This is the shared L2 cache.

**Auth (internet-facing):** Requires basic auth. Only upstream registries (Titus, Moses) need credentials — their proxy config supplies them automatically.

```bash
# Create htpasswd file
mkdir -p /auth
htpasswd -bBc /auth/htpasswd registrycache <password>
```

```yaml
services:
  registry:
    image: registry:3
    restart: always
    ports: ["21510:5000"]
    environment:
      REGISTRY_PROXY_REMOTEURL: https://registry-1.docker.io
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
      REGISTRY_AUTH_HTPASSWD_REALM: Registry
      REGISTRY_AUTH_HTPASSWD_PATH: /auth/htpasswd
    volumes:
      - registry-data:/var/lib/registry  # ~200GB volume
      - /auth:/auth:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:21510/v2/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Gisu (ACME staging server)

Registry proxies directly to Docker Hub. ACME island's L1 cache.

**Auth (internet-facing):** Same as Joseph — basic auth via htpasswd. Kustos's proxy config supplies credentials automatically.

```bash
mkdir -p /auth
htpasswd -bBc /auth/htpasswd registrycache <password>
```

```yaml
services:
  registry:
    image: registry:3
    restart: always
    ports: ["21510:5000"]
    environment:
      REGISTRY_PROXY_REMOTEURL: https://registry-1.docker.io
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
      REGISTRY_AUTH_HTPASSWD_REALM: Registry
      REGISTRY_AUTH_HTPASSWD_PATH: /auth/htpasswd
    volumes:
      - registry-data:/var/lib/registry
      - /auth:/auth:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:21510/v2/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Moses (orchestrator server)

Chains to Joseph (`your-domain.com:21510`). Reduces WAN pulls for the orchestrator that runs the most frequent docker operations.

**Standalone binary (recommended):**
```bash
# Download and install
wget -qO /tmp/registry.tar.gz \
  https://github.com/distribution/distribution/releases/download/v3.1.1/registry_3.1.1_linux_amd64.tar.gz
cd /tmp && tar xzf registry.tar.gz
sudo install registry /usr/local/bin/registry

# Config at /etc/registry/config.yml
# (see snippet below)

# systemd service
# (see below)
```

```yaml
# /etc/registry/config.yml
version: 0.1
storage:
  cache:
    blobdescriptor: inmemory
  filesystem:
    rootdirectory: /data/registry
http:
  addr: :21510
proxy:
  remoteurl: http://your-domain.com:21510
  username: registrycache
  password: <password>
```

### Titus (dev laptop)

Standalone binary via launchd, port 21510, localhost-only. Startup wrapper at `~/docker/registry/start-registry.sh` checks Joseph first; runs standalone if unreachable for smooth Docker fallback.

```yaml
# ~/docker/registry/config.yml
version: 0.1
storage:
  cache:
    blobdescriptor: inmemory
  filesystem:
    rootdirectory: /Users/luke/docker/cache
http:
  addr: :21510
  net: tcp
```

### Kustos (ACME production server)

No local registry. Points daemon.json mirror to Gisu.

## Client daemon.json Configuration

### Titus (dev laptop)

```json
{
  "registry-mirrors": ["http://localhost:21510"]
}
```

Docker tries Titus cache first. If the standalone registry has the image (proxy mode when Joseph is reachable), served instantly. On miss, Docker falls through to Docker Hub directly. If Joseph was unreachable at startup, the registry runs standalone — images aren't cached locally but Docker's native image store handles repeated pulls.

### Moses (orchestrator server)

```json
{
  "registry-mirrors": ["http://your-domain.com:21510"]
}
```

### Joseph — daemon.json

```json
{
  "registry-mirrors": ["http://localhost:21510"]
}
```

### Personal machines (other than Joseph)

```json
{
  "registry-mirrors": ["http://your-domain.com:21510"]
}
```

### Gisu — daemon.json

```json
{
  "registry-mirrors": ["http://localhost:21510"]
}
```

### Kustos (ACME production)

```json
{
  "registry-mirrors": ["http://your-gisu-host:21510"]
}
```

## BuildKit Integration

On machines that build Docker images, add BuildKit config to route `FROM` pulls through the hierarchy.

### Titus (dev laptop) — buildkitd.toml

```toml
debug = true
[registry."docker.io"]
  mirrors = ["http://localhost:21510"]
```

```bash
docker buildx create --use --bootstrap \
  --name cache-builder \
  --driver docker-container \
  --buildkitd-config /etc/buildkitd.toml
```

### Gisu / Joseph — buildkitd.toml

```toml
debug = true
[registry."docker.io"]
  mirrors = ["http://localhost:21510"]
```

## Garbage Collection

Run monthly on each registry server:

```bash
# On each host that runs a registry:
docker exec registry registry garbage-collect /etc/docker/registry/config.yml

# Or use the helper:
bash ~/.hermes/scripts/registry-gc.sh --apply --report
```

## Disk Planning

| Server | Role | Est. monthly growth | Suggested volume |
|--------|------|--------------------|-----------------|
| Joseph | L2 cache (largest) | 5-15 GB | 200 GB |
| Moses | L1 cache (orchestrator) | 2-5 GB | 50 GB |
| Gisu | L1 cache (ACME) | 2-5 GB | 50 GB |
| Titus | L1 cache (local) | 2-5 GB | 50 GB |

Images that are pulled once and never updated (version-pinned base images) stay cached indefinitely. Only actively-changing tags (`:latest`, `:alpine`) cause churn.

## Summary

| Machine | Runs Registry? | Upstream | daemon.json mirror | BuildKit mirror |
|---------|---------------|----------|--------------------|-----------------|
| **Titus** | ✅ L1 | Joseph | `[localhost:21510]` | same |
| **Moses** | ✅ L1 | Joseph | `[joseph:21510]` | `[joseph:21510]` |
| **Joseph** | ✅ L2 | Docker Hub | `[localhost:21510]` | same |
| **Gisu** | ✅ L1 | Docker Hub | `[localhost:21510]` | same |
| **Kustos** | ❌ | — | `[your-gisu-host:21510]` | `[your-gisu-host:21510]` |

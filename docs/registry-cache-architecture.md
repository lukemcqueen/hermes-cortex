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

```yaml
services:
  registry:
    image: registry:3
    restart: always
    ports: ["5000:5000"]
    environment:
      REGISTRY_PROXY_REMOTEURL: https://registry-1.docker.io
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
    volumes:
      - registry-data:/var/lib/registry  # ~200GB volume
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:5000/v2/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Gisu (ACME staging server)

Registry proxies directly to Docker Hub. ACME island's L1 cache.

```yaml
services:
  registry:
    image: registry:3
    restart: always
    ports: ["5000:5000"]
    environment:
      REGISTRY_PROXY_REMOTEURL: https://registry-1.docker.io
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
    volumes:
      - registry-data:/var/lib/registry
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:5000/v2/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Moses (orchestrator server)

Chains to Joseph. Reduces WAN pulls for the orchestrator that runs the most frequent docker operations (monitoring, auto-remediation, service recovery).

```yaml
services:
  registry:
    image: registry:3
    restart: always
    ports: ["5000:5000"]
    environment:
      REGISTRY_PROXY_REMOTEURL: http://joseph:5000  # chain to Joseph
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
    volumes:
      - registry-data:/var/lib/registry
```

### Titus (dev laptop)

Chains to Joseph. Anything Titus pulls is added to Titus's local cache AND is already cached on Joseph for other machines.

```yaml
services:
  registry:
    image: registry:3
    restart: always
    ports: ["127.0.0.1:5000:5000"]  # localhost-only — don't expose dev laptop
    environment:
      REGISTRY_PROXY_REMOTEURL: http://joseph-host:5000  # chain to Joseph
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
    volumes:
      - registry-data:/var/lib/registry
```

### Kustos (ACME production server)

No local registry. Points daemon.json mirror to Gisu.

## Client daemon.json Configuration

### Titus (dev laptop)

```json
{
  "registry-mirrors": [
    "http://localhost:5000",
    "http://joseph:5000"
  ]
}
```

Docker tries L1 (Titus cache) first. On miss, falls through to L2 (Joseph). On miss there, falls through to Docker Hub natively.

### Moses (orchestrator server)

```json
{
  "registry-mirrors": ["http://joseph:5000"]
}
```

### Joseph & personal machines

```json
{
  "registry-mirrors": ["http://joseph-host:5000"]
}
```

### Gisu (ACME staging)

```json
{
  "registry-mirrors": ["http://localhost:5000"]
}
```

### Kustos (ACME production)

```json
{
  "registry-mirrors": ["http://gisu-host:5000"]
}
```

## BuildKit Integration

On machines that build Docker images, add BuildKit config to route `FROM` pulls through the hierarchy.

### Titus (dev laptop) — buildkitd.toml

```toml
debug = true
[registry."docker.io"]
  mirrors = ["http://localhost:5000", "http://joseph:5000"]
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
  mirrors = ["http://localhost:5000"]
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
| **Titus** | ✅ L1 | Joseph | `[localhost:5000, joseph:5000]` | same |
| **Moses** | ✅ L1 | Joseph | `[joseph:5000]` | `[joseph:5000]` |
| **Joseph** | ✅ L2 | Docker Hub | `[localhost:5000]` | same |
| **Gisu** | ✅ L1 | Docker Hub | `[localhost:5000]` | same |
| **Kustos** | ❌ | — | `[gisu:5000]` | `[gisu:5000]` |

# Langfuse v3 Migration

**Commits:** `650fc94` (added v2) → `a51c3a0` (upgraded to v3)

## Key Changes v2 → v3

| Dimension | v2 (old) | v3 (current) |
|-----------|----------|--------------|
| Image tag | `:latest` | `:3` |
| Web port | 3000 | 3001 (internal 3000 mapped to host 3001) |
| Containers | 5 (web, worker, postgres, redis, minio) | 6 (+ **clickhouse**) |
| Database | Postgres only | Postgres + ClickHouse |
| Required env vars | SALT, SECRET_KEY, NEXTAUTH_SECRET | + ENCRYPTION_KEY, CLICKHOUSE_*, S3_* |
| Health endpoint | `/api/health` | `/api/public/health` |
| Migration URL | Not used | `CLICKHOUSE_MIGRATION_URL: clickhouse://clickhouse:9000` |

## docker-compose.langfuse.yml — Critical Config

### Required Environment Variables

```yaml
# Langfuse auth
SALT: ${LANGFUSE_SALT:?required}
ENCRYPTION_KEY: ${LANGFUSE_ENCRYPTION_KEY?required}  # 64-char hex

# ClickHouse (new for v3)
CLICKHOUSE_URL: http://clickhouse:8123
CLICKHOUSE_MIGRATION_URL: clickhouse://clickhouse:9000  # Go driver TCP, NOT http://
CLICKHOUSE_USER: ${CLICKHOUSE_USER:-clickhouse}
CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-clickhouse}
CLICKHOUSE_CLUSTER_ENABLED: false  # MUST be false without Zookeeper
CLICKHOUSE_DB: default

# Redis
REDIS_HOST: redis
REDIS_PORT: 6379
REDIS_AUTH: ${LANGFUSE_REDIS_AUTH:?required}

# MinIO / S3 event uploads (REQUIRED by v3 Zod schema)
LANGFUSE_S3_EVENT_UPLOAD_BUCKET: langfuse
LANGFUSE_S3_EVENT_UPLOAD_REGION: auto
LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: ${LANGFUSE_MINIO_ACCESS_KEY:-minioadmin}
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_MINIO_SECRET_KEY:-minioadmin}
LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT: http://minio:9000
LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE: true

# MinIO / S3 media uploads
LANGFUSE_S3_MEDIA_UPLOAD_BUCKET: langfuse
LANGFUSE_S3_MEDIA_UPLOAD_REGION: auto
LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID: ${LANGFUSE_MINIO_ACCESS_KEY:-minioadmin}
LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_MINIO_SECRET_KEY:-minioadmin}
LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT: http://minio:9000
LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE: true
```

### Initial Project / Org / User (v3 feature)

```yaml
LANGFUSE_INIT_ORG_ID: hermes-cortex
LANGFUSE_INIT_ORG_NAME: Hermes Cortex
LANGFUSE_INIT_PROJECT_ID: hermes-agent
LANGFUSE_INIT_PROJECT_NAME: ${LANGFUSE_INIT_PROJECT_NAME:-Hermes Agent}
LANGFUSE_INIT_PROJECT_PUBLIC_KEY: ${LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-}
LANGFUSE_INIT_PROJECT_SECRET_KEY: ${LANGFUSE_INIT_PROJECT_SECRET_KEY:-}
LANGFUSE_INIT_USER_EMAIL: ${LANGFUSE_INIT_USER_EMAIL:-}
LANGFUSE_INIT_USER_NAME: ${LANGFUSE_INIT_USER_NAME:-}
LANGFUSE_INIT_USER_PASSWORD: ${LANGFUSE_INIT_USER_PASSWORD:-}
```

### ClickHouse Container

```yaml
clickhouse:
  image: clickhouse/clickhouse-server:24.8
  restart: always
  healthcheck:
    test: ["CMD", "wget", "--spider", "-q", "http://localhost:8123/ping"]
    interval: 5s
    timeout: 5s
    retries: 5
  volumes:
    - langfuse-clickhouse-data:/var/lib/clickhouse
  environment:
    CLICKHOUSE_DB: default
    CLICKHOUSE_USER: ${CLICKHOUSE_USER:-clickhouse}
    CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-clickhouse}
  ulimits:
    nofile:
      soft: 262144
      hard: 262144
```

## Typical Failure Modes

### 1. ZodError on Startup — Missing S3 Bucket

```
Error: ZodError: [
  {
    "code": "invalid_type",
    "expected": "string",
    "received": "undefined",
    "path": ["LANGFUSE_S3_EVENT_UPLOAD_BUCKET"],
    "message": "Required"
  }
]
```

**Fix:** Add all `LANGFUSE_S3_EVENT_UPLOAD_*` env vars to the compose file. Even pointing at MinIO with dummy keys works — they just must exist.

### 2. ClickHouse Migration Fails — Wrong URL Protocol

```
Error: connect ECONNREFUSED clickhouse:8123
```

**Fix:** Use `CLICKHOUSE_MIGRATION_URL: clickhouse://clickhouse:9000` (Go driver on TCP port 9000), NOT `http://clickhouse:8123` (HTTP port).

### 3. ClickHouse Migration Fails — ON CLUSTER

```
Error: Code: 339. DB::Exception: Table engine `ReplicatedMergeTree` requires Zookeeper
```

**Fix:** Set `CLICKHOUSE_CLUSTER_ENABLED: false` so it uses `MergeTree` instead of `ReplicatedMergeTree`.

### 4. Web Container Crash Loop — Encryption Key

```
Error: ENCRYPTION_KEY must be a 64-character hex string
```

**Fix:** Generate with `openssl rand -hex 32` and set `ENCRYPTION_KEY`.

### 5. Worker Container Crash Loop — Queue Delay

```
Error: LANGFUSE_INGESTION_QUEUE_DELAY_MS missing
```

**Fix:** Add tuning vars (or remove them if undefined — the v3 image ships with defaults):
```yaml
LANGFUSE_INGESTION_QUEUE_DELAY_MS: 100
LANGFUSE_INGESTION_CLICKHOUSE_WRITE_INTERVAL_MS: 1000
```

## Full Container Restart Required

Env var changes in the compose file are NOT picked up by `docker compose up -d` if the containers already exist. You MUST:

```bash
docker compose down
docker compose up -d
```

## Port Change

Langfuse v3 compose maps container port 3000 to host port **3001** to avoid conflict with any other service on 3000. The nginx upstream must match:

```nginx
server {
    listen 11002 ssl;
    location / {
        proxy_pass http://127.0.0.1:3001;
    }
}
```

## Dashboard Default Host

The Cortex Dashboard (`server.py`) defaults `LANGFUSE_HOST` to `http://localhost:3001`. Set `LANGFUSE_HOST` env var to override.

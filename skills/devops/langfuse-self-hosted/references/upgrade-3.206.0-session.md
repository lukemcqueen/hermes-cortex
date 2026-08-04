# Langfuse 3.200.0 → 3.206.0 Upgrade Session

## Date
2026-07-09

## Environment
- Deployment path: `~/langfuse/` (NOT `~/hermes-cortex/deploy/`)
- Env file: `~/langfuse/.env`
- Previous version: `langfuse/langfuse:3.200.0`, `langfuse/langfuse-worker:3.200.0`
- Upgrade via: `docker compose pull` + `docker compose down && docker compose up -d`

## Pitfalls Encountered

### 1. Silent web server exit on first deploy

The web server started, ran migrations, registered MCP features, then exited silently after ~2 minutes:

```
Langfuse server exited. Container staying alive.
```

**Root cause:** The ClickHouse compatibility settings migration (`Applying ClickHouse compatibility settings`) was the first task on a fresh 3.206.0 start. After it completed, the Node.js process exited. The container stayed alive because the Docker entrypoint uses `|| true` followed by `tail -f /dev/null`:

```
node ./web/server.js --keepAliveTimeout 110000 || true; echo "Langfuse server exited."; tail -f /dev/null
```

**Fix:** `docker compose down && docker compose up -d` — second start has no pending migrations and stays up.

### 2. Irreversible ClickHouse forward migration

After 3.206.0 ran its ClickHouse compatibility settings, rolling back to 3.200.0 failed with:

```
error: no migration found for version 35: read down for version 35 .: file does not exist
Applying clickhouse migrations failed.
```

**Lesson:** Once a new Langfuse version runs ClickHouse migrations, the schema is forward-migrated. You cannot downgrade without restoring ClickHouse from backup.

### 3. Dual deploy paths (repo vs live)

`cortex-update.sh` triggered a Langfuse restart but targeted `~/hermes-cortex/deploy/docker-compose.langfuse.yml`, while the actual running stack is at `~/langfuse/docker-compose.yml`. Both compose files had the same content (3.206.0 image tags) but the `.env` file was only at `~/langfuse/.env`, causing variable interpolation failures from the repo path.

### 4. Large image pull timeout

Each Langfuse image is ~1GB. `docker compose pull` easily exceeds the default 120s terminal timeout. Use a longer timeout or background the pull.

### 5. Recurring PostHog crash (3.206.0, not just first-deploy)

After the upgrade, the web server continued to crash every 2-3 minutes even on the second+ start. This was a **recurring PostHog telemetry timeout** — not a one-time migration exit:

```
Error while flushing PostHog Error [PostHogFetchNetworkError]: Network error while fetching PostHog
...
Langfuse server exited. Container staying alive.
```

The PostHog flush to `eu.posthog.com` timed out after ~30s and killed the Node.js process via unhandled rejection. The `|| true; tail -f /dev/null` CMD pattern masked the crash from Docker.

**Fix applied:**
```yaml
# In the langfuse-web environment block:
POSTHOG_HOST: "http://127.0.0.1:1"

# Replace the CMD to let Docker detect the crash:
command: /bin/sh -c 'exec node ./web/server.js --keepAliveTimeout 110000'

# Add healthcheck:
healthcheck:
  test: ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1:3000/api/public/health || exit 1"]
  interval: 15s; timeout: 10s; retries: 3; start_period: 240s

# Change restart policy:
restart: unless-stopped
```

### 6. Traces endpoint crash (3.206.0)

After upgrading to 3.206.0, the REST API endpoint `/api/public/traces?fromTimestamp=...` crashed the Node.js server with `RemoteDisconnected` or unhandled `InvalidRequestError`. The llm-judge-scorer cron job (which queries this endpoint) consistently crashed the server.

**Fix:** Upgrade to langfuse/langfuse:3.207.0.

## Verification

After successful upgrade:
- HTTP 200 on `http://localhost:3000`
- All 6 containers healthy (checked via `docker ps`)
- New Prisma migrations applied (9 new migrations from 3.206.0)
- No pending migrations on second start

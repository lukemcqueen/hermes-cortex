---
name: langfuse-self-hosted
version: 1.0.0
description: Deploy, configure, and wire Langfuse v3 with ClickHouse for LLM observability — Docker compose, SIGSEGV-safe ClickHouse tuning, Hermes Langfuse plugin setup, OTLP endpoint troubleshooting.
---

## When to use

When setting up Langfuse from scratch, upgrading an existing deployment, troubleshooting missing traces, reconfiguring ClickHouse, or wiring Hermes Agent to send observability data to a self-hosted Langfuse instance.

## Architecture

```
Hermes Agent ──SDK v4.12.0──┐
                             │ OTLP
                             ▼
                    Langfuse v3.200.0+
                    /api/public/otel/v1/traces
                    │
              ┌─────┼─────────┐
              │     │         │
         Postgres  CH   Redis  MinIO
         (metadata) (analytics) (queue) (S3 storage)
```

The Langfuse Python SDK v4+ exports traces via OpenTelemetry OTLP protocol (HTTP), not REST API. The Langfuse server must have the OTLP endpoint active at `/api/public/otel/v1/traces`. This endpoint was added in later v3.x releases.

## Docker Compose deployment

### File structure

```
~/langfuse/
├── docker-compose.yml              # Main compose file (copy from deploy/)
├── .env                            # Secrets (chmod 600)
└── clickhouse-config.d/
    ├── 01-log-level.xml             # Logger level: warning
    ├── 02-low-memory.xml            # Thread pool tuning (SIGSEGV-safe)
    └── 03-profile-defaults.xml      # Per-query limits (users.d/)
```

Source of truth for compose + configs: `hermes-cortex/deploy/`:
- `docker-compose.langfuse.yml`
- `clickhouse-config.d/*.xml`
- `README-langfuse-clickhouse.md`

### Critical: File permissions

ClickHouse runs as a non-root user inside the container. Config files mounted with `:ro` MUST be world-readable:

```bash
chmod 644 ~/langfuse/clickhouse-config.d/*.xml
```

If any file is chmod 600, ClickHouse fails with:
```
Failed to merge config with ...: Access to file denied
```

### Critical: ClickHouse 25.5 SIGSEGV bug

Reducing more than 2 background pool settings simultaneously triggers SIGSEGV (exit 139) or exit code 36 during initialization.

**Safe settings (the only two that work together):**
```xml
<background_pool_size>13</background_pool_size>           <!-- floor 13; <=12 crashes -->
<background_schedule_pool_size>16</background_schedule_pool_size>  <!-- default 512 -->
```

**Do NOT reduce these (cause crash when combined with above):**
- `background_common_pool_size` (keep default 8)
- `background_buffer_flush_schedule_pool_size` (keep default 16)
- `background_distributed_schedule_pool_size` (keep default 16)
- `background_fetches_pool_size` (keep default 16)
- `background_move_pool_size` (keep default 8)
- `max_thread_pool_size` (keep default 10000)
- `thread_pool_queue_size` (keep default 10000)

**If ClickHouse crashes on restart**, you've either set a pool below its floor or reduced too many simultaneously. Comment out all pool overrides except the two safe ones, then retry.

### Restart procedure

**`docker compose restart` does NOT re-read env vars or config file changes.** Always use:

```bash
cd ~/langfuse
docker compose down
docker compose up -d
```

### Updating image tags

Check latest tags: `https://hub.docker.com/r/langfuse/langfuse`

Current pinned tags (as of last update):
- `langfuse/langfuse:3.207.0`
- `langfuse/langfuse-worker:3.207.0`
- `clickhouse/clickhouse-server:25.5-alpine`
- `postgres:16-alpine`
- `redis:7-alpine`
- `minio/minio:latest`

### Upgrade workflow (e.g. 3.200.0 → 3.206.0)

When upgrading to a new Langfuse version, follow this sequence to avoid the common pitfalls:

**1. Update image tags** in `~/langfuse/docker-compose.yml`.

**2. Pull new images** — each image is ~1GB and the pull can exceed the default 120s timeout. Use a generous timeout or background the pull:
   ```bash
   cd ~/langfuse && docker compose pull
   ```

**3. Full down + up** — `docker compose restart` does NOT re-read env vars or pick up new images. Always:
   ```bash
   docker compose down
   docker compose up -d
   ```

**4. Server may exit after starting (known behavior):** After `up -d`, the web server may exit silently ~30s-2min after starting. The log shows:
   ```
   Langfuse server exited. Container staying alive.
   ```
   Two possible causes:
   - **(First deploy)** ClickHouse compatibility migration runs and the process exits cleanly after. Re-run `docker compose down && up -d`.
   - **(PostHog timeout, recurring)** The container cannot reach `eu.posthog.com` for telemetry. See "PostHog telemetry crash" in Troubleshooting below.
   
   If `curl localhost:3000` returns HTTP 200 after a re-deploy, the server is up.

**5. 🔴 ClickHouse forward-migration is irreversible.** Once the new version runs ClickHouse compatibility migrations, you CANNOT downgrade to an older Langfuse version. The ClickHouse schema is forward-migrated. If you need to roll back, you must restore ClickHouse data from backup.

**6. Verify:**
   ```bash
   docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep langfuse
   curl -sL -o /dev/null -w "%{http_code}" http://localhost:3000
   ```

**7. Verify external connectivity** through nginx gateway:
   ```bash
   curl -sL -o /dev/null -w "%{http_code}" https://your-domain.com:PORT/api/public/health
   ```

## Hermes Langfuse plugin setup

### Step-by-step

1. **Enable the plugin:**
   ```bash
   hermes plugins enable observability/langfuse
   ```

2. **Install the Python SDK:**
   ```bash
   pip install langfuse
   ```
   (Use `--break-system-packages` if PEP 668 is active.)

3. **Generate an API key pair in Postgres:**
   ```bash
   docker exec langfuse-postgres-1 psql -U postgres -d postgres -c "
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   INSERT INTO api_keys (id, project_id, public_key, hashed_secret_key,
     fast_hashed_secret_key, display_secret_key, note, created_at)
   SELECT
     'cmqkey-' || gen_random_uuid()::text,
     'default-project',
     'pk-lf-' || encode(gen_random_bytes(16), 'hex'),
     crypt('sk-lf-' || encode(gen_random_bytes(16), 'hex'), gen_salt('bf')),
     encode(sha256('sk-lf-' || encode(gen_random_bytes(16), 'hex')::bytea), 'hex'),
     'sk-lf-' || encode(gen_random_bytes(16), 'hex'),
     'Hermes Agent tracing key',
     CURRENT_TIMESTAMP;
   "
   ```
   Record the public and secret keys from the SQL output.

4. **Set env vars in `~/.hermes/.env`:**
   The plugin reads `HERMES_LANGFUSE_*` vars first, then falls back to `LANGFUSE_*`.
   Only these vars are consumed by the plugin:
   ```
   HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-...
   HERMES_LANGFUSE_SECRET_KEY=sk-lf-...
   HERMES_LANGFUSE_BASE_URL=http://localhost:3000
   HERMES_LANGFUSE_ENV=local
   HERMES_LANGFUSE_RELEASE=v1
   HERMES_LANGFUSE_SAMPLE_RATE=1.0
   ```
   Other `*_ENABLED=true` vars seen in older versions are inert.

5. **Restart Hermes** (`/reset` or new session) — the plugin only activates on next session start.

### SDK version compatibility

The Langfuse Python SDK v4+ exports traces via OTLP. Langfuse server versions before ~v3.150 did NOT have the OTLP endpoint at `/api/public/otel/v1/traces`. If traces don't appear:

1. Check the server version: `curl http://localhost:3000/api/public/health`
2. Test OTLP endpoint existence (should return 401, not 404):
   ```bash
   curl -s -o /dev/null -w "%{http_code}" -X POST \
     "http://localhost:3000/api/public/otel/v1/traces"
   ```
3. If 404 — the endpoint doesn't exist. **Upgrade Langfuse** (update image tags, `docker compose down && docker compose up -d`).
4. If 401 — the endpoint exists. Verify credentials.

The SDK v4.12.0 + server v3.200.0 is a known-working combination. No manual `OTEL_EXPORTER_OTLP_ENDPOINT` env var is needed — the SDK auto-discovers the OTLP path from `base_url`.

### Verification

```python
from langfuse import Langfuse
import requests

client = Langfuse(
    public_key='pk-lf-...',
    secret_key='sk-lf-...',
    base_url='http://localhost:3000'
)

trace_id = client.create_trace_id(seed='verify-test')

with client.start_as_current_observation(
    trace_context={'trace_id': trace_id},
    name='verify test', as_type='chain',
    input='test', end_on_exit=True,
):
    with client.start_as_current_observation(
        trace_context={'trace_id': trace_id},
        name='llm call', as_type='generation',
        input='prompt', output='response',
    ):
        pass

client.flush()
import time; time.sleep(2)

auth = requests.auth.HTTPBasicAuth('pk-lf-...', 'sk-lf-...')
r = requests.get(f'http://localhost:3000/api/public/observations?trace_id={trace_id}', auth=auth)
if r.json().get('data'):
    print('DATA FLOW: OK')
```

## Migrating from v3.1.0 to v3.200.0+

Langfuse v3.1.0 does not serve the OTLP endpoint. Upgrade by:

1. Update image tags in `docker-compose.yml` to `:3.200.0` (or `:3` for auto-upgrade within v3)
2. Remove old containers: `docker compose down`
3. Start with new images: `docker compose up -d --pull always`
4. Verify: `curl http://localhost:3000/api/public/health` returns `3.200.0`
5. Verify OTLP endpoint now exists (returns 401, not 404)

## ⚠️ Critical: Merge size default causes OOM in 2 GiB containers

ClickHouse's default `max_bytes_to_merge_at_max_space_in_pool` is **150 GB**.
In a 2 GiB container, a single merge task tries to process >100 GiB of parts,
which always hits the server memory cap (1.8 GiB = 90% of 2 GiB). Symptoms:
`TotalMergeFailures` climbs relentlessly (2000+), `MergeTreeBackgroundExecutorThreadsActive=45`
stuck, `Merge=0`, log showing `MEMORY_LIMIT_EXCEEDED`.

**This is the single most important fix.** Before any other tuning, cap merge sizes:

- `max_bytes_to_merge_at_max_space_in_pool`: **500 MB** (was 150 GB)
- `max_bytes_to_merge_at_min_space_in_pool`: **50 MB** (was 1 MB)
- `merge_max_block_size`: **512** (was 8192)
- `number_of_free_entries_in_pool_to_lower_max_size_of_merge`: **0** (was 8)

**Always verify `changed=1`** in `system.server_settings` and `system.merge_tree_settings`
after applying. If `changed=0`, the config file wasn't read (common cause: stale
deployed copy in `~/langfuse/clickhouse-config.d/`).

For the full config reference, see `hermes-cortex/ops/install/deploy/README-langfuse-clickhouse.md`
and the `auto-remediation` skill's `references/clickhouse-low-memory-tuning.md`.

## Troubleshooting

### PostHog telemetry crash (v3.206.0)

The langfuse-web container uses PostHog for telemetry. If the container cannot reach `eu.posthog.com` (firewall, DNS, or network isolation), the PostHog flush will time out after ~30s. This fires an unhandled rejection that crashes the Next.js server process.

**Symptom:** Server starts, responds to health checks for ~2 minutes, then log shows:
```
Error while flushing PostHog Error [PostHogFetchNetworkError]: Network error while fetching PostHog
...
Langfuse server exited. Container staying alive.
```
The container stays "Up" but `curl localhost:3000` returns nothing — only the health endpoint works for a few seconds before the crash.

**Fix:** Add `POSTHOG_HOST` pointing to a local address that fails fast (connection refused instead of 30s timeout):

```yaml
# In the langfuse-web environment block:
POSTHOG_HOST: "http://127.0.0.1:1"
```

This makes PostHog connection attempts fail in <1s with ECONNREFUSED instead of timing out.

### Healthcheck + crash-loop protection

The langfuse-web container's upstream entrypoint uses `|| true; echo "Langfuse server exited."; tail -f /dev/null` which **masks the server exit code** from Docker. The container stays "Up" with a dead server and `restart: on-failure` never triggers.

**Three-layer defense:**

1. **Replace the synthetic CMD** so the container exits on server death:
   ```yaml
   command: /bin/sh -c 'exec node ./web/server.js --keepAliveTimeout 110000'
   ```

2. **Add a Docker healthcheck** so `docker ps` shows `(unhealthy)`:
   ```yaml
   healthcheck:
     test: ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1:3000/api/public/health || exit 1"]
     interval: 15s
     timeout: 10s
     retries: 3
     start_period: 240s
   ```

3. **Use `restart: unless-stopped`** (not `on-failure:2`):
   ```yaml
   restart: unless-stopped
   ```

### /api/public/traces endpoint crash (v3.206.0)

In v3.206.0, the traces endpoint (`/api/public/traces?fromTimestamp=...`) can crash the Node.js server with an unhandled `InvalidRequestError` or `RemoteDisconnected`. **Upgrade to 3.207.0+ to resolve.**

### Web crash-loop: "no migration found for version N: read down" (2026-08-09)

The web container crash-loops at startup with:
```
error: no migration found for version 36: read down for version 36 .: file does not exist
Applying clickhouse migrations failed.
```

The CH `schema_migrations` table has a version (e.g. 36) the running image
doesn't ship (3.206.0 ships only to 0035). ClickHouse forward-migration is
irreversible — the schema was migrated by a NEWER image, then the compose was
downgraded. **Fix: upgrade Langfuse to the version that ships that migration
(3.207.0 ships 0036_add_ingested_sdks_to_analytics_scores).** Verify the image
contains the version before upgrading:
```bash
docker run --rm --entrypoint sh langfuse/langfuse-worker:<tag> -c \
  'ls .../clickhouse/migrations/unclustered/ | grep -oE "^[0-9]+" | sort -un | tail -3'
```
Also note: the worker container tolerates the mismatch (it doesn't run the
migration check) — only web crash-loops, so `docker ps` showing the worker
"Up" is misleading.

### Traces created but never appear in Langfuse
The SDK fails silently with "Failed to export span batch code: 404, reason: Not Found". This means the OTLP endpoint is missing. Upgrade Langfuse server version.

### Langfuse UI blank / "Loading..."
This is the Next.js SPA loading state — not an error. Wait 10-15s for the JS bundle. If it never loads, check browser console for API fetch errors.

### API key insertion fails
The `api_keys` table schema changed between Langfuse versions. For v3.200.0, the required columns are: `id`, `project_id`, `public_key`, `hashed_secret_key`, `fast_hashed_secret_key`, `display_secret_key`, `note`, `created_at`. The `fast_hashed_secret_key` uses SHA-256; `hashed_secret_key` uses bcrypt (via pgcrypto).

### Hermes .env has stale `_ENABLED=true` vars
Earlier versions of the setup script wrote 40+ env vars to `~/.hermes/.env`, most of which (`HERMES_LANGFUSE_TRACING_ENABLED`, `HERMES_LANGFUSE_SCORING_ENABLED`, etc.) are inert. The Langfuse plugin only reads the 7 vars listed in step 4 above. Safe to delete the stale ones.

## Memory-constrained operation (below v3 minimum spec)

Langfuse v3 minimum spec for the web container is **2 CPU, 4 GiB memory**. If you're running with less (e.g. 1 CPU, 1-1.5 GiB), the `next-server` Node.js process inside the langfuse-web container will OOM-kill under load. The process appears in `ps aux` as `next-server (v16.2.9)` running as uid 101001 (Docker container user).

### Crash signature

Check `/var/crash/` for core dumps:
```
-rw-r----- core.next-server(v1.101001...).zst  → ~119MB each
```
The process `next-server` crashes repeatedly when memory usage approaches the container limit. Each crash writes a ~119MB core dump to disk.

### Immediate fixes

These env vars reduce memory pressure without upgrading hardware:

| Env var | Default | Recommended | Why |
|---------|---------|-------------|-----|
| `LANGFUSE_S3_CONCURRENT_WRITES` | 50 | 10 | Each S3 write socket costs memory. Reduce to 10. |
| `LANGFUSE_SKIP_INGESTION_CLICKHOUSE_READ_MIN_PROJECT_CREATE_DATE` | unset | `"2025-01-01"` | Skip ClickHouse reads during ingestion — major memory saving for OTel-only projects. |
| `LANGFUSE_SKIP_FINAL_FOR_OTEL_PROJECTS` | false | `"true"` | Skip FINAL modifier on OTel project reads (memory + CPU). |
| `LANGFUSE_API_CLICKHOUSE_DISABLE_OBSERVATIONS_FINAL` | false | `"true"` | Global FINAL disable (if ALL projects use OTel). |
| `LANGFUSE_CLICKHOUSE_DELETION_TIMEOUT_MS` | 600000 | 300000 | Shorter deletion timeout (5min vs 10min). |
| `LANGFUSE_INIT_PROJECT_RETENTION` | unset | `"7"` | Auto-delete data older than 7 days. Only applies on project creation. |

### Resource config

```yaml
# In the langfuse-web service block:
mem_limit: 1.5g          # or whatever your max is, minimum 1.5g recommended
memswap_limit: 1.5g
cpus: 1.0
ulimits:
  core: 0                # disable core dumps (prevents disk flood on crash)
NODE_OPTIONS: "--max-old-space-size=1024 --max-semi-space-size=64 --unhandled-rejections=warn"
```

The `max-old-space-size` should be roughly 2/3 of `mem_limit`. With 1.5g limit, 1024 MB is about right.

### Determine retentaion for existing projects

The `LANGFUSE_INIT_PROJECT_RETENTION` env var only sets retention on **project creation**. For existing projects, set retention in the Langfuse UI (Project Settings → Retention) or via the API with an org-scoped key:

```bash
curl -X PATCH "http://localhost:3000/api/public/projects/<project-id>" \
  -u "<org-pk>:<org-sk>" \
  -H "Content-Type: application/json" \
  -d '{"retentionDays": 7}'
```

Project-scoped API keys return a 403 for this endpoint — you need an organization-scoped key.

### Data retention effect

Nightly cleanup deletes traces, observations, scores, and media assets older than the configured retention period. This directly reduces ClickHouse disk usage and the memory needed to serve queries.

### Core dump prevention

Add to docker-compose.yml for the web container:
```yaml
ulimits:
  core: 0
```

And system-wide:
```bash
echo "fs.suid_dumpable=0" | sudo tee /etc/sysctl.d/99-disable-coredump.conf
sudo sysctl -w fs.suid_dumpable=0
```

### Identifying the crash culprit

When the `next-server` process crashes, it's the Langfuse web container's Node.js process. To confirm:
```bash
# Check process identity
cat /proc/<PID>/cgroup
```
Expected: `0::/system.slice/docker-<container-id>.scope`

```bash
# Check container memory pressure
docker stats langfuse-langfuse-web-1 --no-stream
```

## User management (post-deployment)

Langfuse v3 stores user credentials in the `users` table of its PostgreSQL database. The `LANGFUSE_INIT_USER_*` env vars only take effect on first launch. To update an existing user's email or password:

### Find existing users

```bash
docker exec langfuse-postgres-1 psql -U postgres -c "SELECT id, name, email, admin FROM users;"
```

### Generate a bcrypt password hash

Install bcrypt if not present, then hash the password:

```bash
pip install bcrypt
python3 -c "
import bcrypt
hashed = bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt(rounds=8)).decode()
print(hashed)
"
```

The output is a bcrypt hash like `$2b$08$...` — this is the format NextAuth expects.

> ⚠️ **Cost factor:** `rounds=8` is the default for Langfuse/NextAuth. Higher rounds (10-12) are more secure but slower. Use 8 to match what Langfuse generates internally.

### Update user credentials

```bash
docker exec langfuse-postgres-1 psql -U postgres -c "
UPDATE users SET
  email = 'new@email.com',
  name = 'New Name',
  password = '\$2b\$08\$HASH...',
  admin = true,
  updated_at = CURRENT_TIMESTAMP
WHERE email = 'old@email.com';
"
```

> ⚠️ **Bash escaping:** The `$` in the bcrypt hash must be escaped as `\$` inside double-quoted shell strings. Alternatively, use single quotes and a heredoc.

### Persist across container rebuilds

The `.env` file (`~/langfuse/.env`) controls initial user creation on first launch. Sync it after updating the database:

```bash
sed -i 's/^LANGFUSE_INIT_USER_EMAIL=.*/LANGFUSE_INIT_USER_EMAIL=new@email.com/' ~/langfuse/.env
sed -i 's/^LANGFUSE_INIT_USER_NAME=.*/LANGFUSE_INIT_USER_NAME=New Name/' ~/langfuse/.env
sed -i 's/^LANGFUSE_INIT_USER_PASSWORD=.*/LANGFUSE_INIT_USER_PASSWORD=new_password/' ~/langfuse/.env
```

## References

- `hermes-cortex/deploy/README-langfuse-clickhouse.md` — Full deployment guide
- `hermes-cortex/deploy/docker-compose.langfuse.yml` — Canonical compose file
- `hermes-cortex/deploy/clickhouse-config.d/` — ClickHouse config files
- `hermes-cortex/ops/scripts/cortex-setup-langfuse.sh` — Automated setup script
- `references/clickhouse-merge-failure-repair.md` — Diagnose and fix CHECKSUM_DOESNT_MATCH merge loops
- `references/clickhouse-oom-max-memory-conflict.md` — Diagnose per-query max_memory_usage exceeding server max_server_memory_usage (silent OOM loop)
- `references/clickhouse-stale-huge-parts-nuke.md` — **NEW:** Nuke data volume when low-memory config is deployed but OLD parts from the pre-config era cause MEMORY_LIMIT_EXCEEDED on every merge
- `references/low-memory-scaling.md` — Langfuse v3 memory optimization for constrained environments (below 4GB minimum spec)
- Langfuse docs: https://langfuse.com/docs/deployment/docker
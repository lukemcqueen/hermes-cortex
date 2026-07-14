# Langfuse + ClickHouse — Deployment Guide

> **Location:** `deploy/docker-compose.langfuse.yml`
> **Config files:** `deploy/clickhouse-config.d/`
> **Setup script:** `src/scripts/cortex-setup-langfuse.sh`

This directory deploys [Langfuse v3](https://langfuse.com) with ClickHouse, PostgreSQL,
Redis, and MinIO for local LLM observability (tracing, scoring, cost tracking).

---

## File Structure

```
deploy/
├── docker-compose.langfuse.yml      # Main compose file
├── clickhouse-config.d/
│   ├── 01-log-level.xml             # Reduces log level to warning
│   ├── 02-low-memory.xml            # Thread pool + log table tuning
│   └── 03-profile-defaults.xml      # Per-query limits (profiles → users.d/)
├── config/                          # Optional: Hermes Cortex dashboard config
├── nginx/                           # Optional: nginx proxy snippets
├── patches/
│   └── hermes-langfuse-cost-fixes.patch.md   # Historical: cost tracking fixes
└── extract_langfuse_env.py          # Utility: extract env from running stack
```

### Where Config Files Mount

| File | Mount Target | Purpose |
|------|-------------|---------|
| `01-log-level.xml` | `config.d/` | Server-level: reduce ClickHouse logging |
| `02-low-memory.xml` | `config.d/` | Server-level: tune thread pools, disable verbose system tables |
| `03-profile-defaults.xml` | `users.d/` | Profile-level: per-query memory, threads, block size |

---

## Resource Limits

All containers have resource limits to prevent CPU/RAM contention with
other services on the host:

| Container     | CPU cap | Memory cap | Why |
|---------------|---------|------------|-----|
| ClickHouse    | 1.0 CPU | 2 GB       | Analytics DB — biggest memory consumer; capped generously |
| Langfuse Web  | 0.5 CPU | 1.5 GB     | Next.js UI + API server; needs extra headroom for ClickHouse model-match cache init |
| Langfuse Worker | 0.5 CPU | 512 MB   | Background trace processor; comfortably above idle usage (~400 MB) |
| Postgres      | —       | —          | Minimal by nature (~47 MB) — no limit needed |
| Redis         | —       | —          | Minimal (~11 MB) — no limit needed |
| MinIO         | —       | —          | Minimal outside of large uploads (~143 MB) — no limit needed |

These limits are defined in `docker-compose.langfuse.yml` via
`cpus:` and `mem_limit:` / `memswap_limit:` on each service.
To adjust for your hardware, edit those values and restart:

```bash
cd ~/langfuse
docker compose down
# edit docker-compose.yml
docker compose up -d
```

> **Note:** `docker compose restart` does NOT re-read resource limits.
> You must use `down` + `up -d` for changes to take effect.

---

## ⚠️ Critical: File Permissions

ClickHouse runs as a **non-root user** inside the container. Config files
mounted from the host MUST be world-readable:

```bash
chmod 644 deploy/clickhouse-config.d/*.xml
```

If any file is `600` (owner-only), ClickHouse will fail to start with:

```
Poco::Exception. Code: 1000, ... Failed to merge config with ...
/etc/clickhouse-server/config.d/01-log-level.xml: Access to file denied
```

This applies to ALL three XML files — `01-log-level.xml`, `02-low-memory.xml`,
and `03-profile-defaults.xml`.

---

## ⚠️ Critical: ClickHouse 25.5 SIGSEGV Bug

ClickHouse 25.5-alpine has a bug where **reducing more than 2 background pool
settings simultaneously** causes SIGSEGV (exit 139) or exit code 36 during
initialization.

**Safe settings (the only two that work together):**

```xml
<background_pool_size>13</background_pool_size>            <!-- floor 13; ≤12 crashes -->
<background_schedule_pool_size>16</background_schedule_pool_size>  <!-- default 512 → 16 saves 496 threads -->
```

**Do NOT reduce these (they combine with above to trigger the crash):**

- `background_common_pool_size` (keep default 8)
- `background_buffer_flush_schedule_pool_size` (keep default 16)
- `background_distributed_schedule_pool_size` (keep default 16)
- `background_fetches_pool_size` (keep default 16)
- `background_message_broker_schedule_pool_size` (keep default 16)
- `background_move_pool_size` (keep default 8)
- `max_thread_pool_size` (keep default 10000)
- `thread_pool_queue_size` (keep default 10000)

**If ClickHouse crashes with SIGSEGV on restart**, you've either:
1. Set a background pool below its floor, or
2. Reduced too many background pool settings simultaneously

Comment out all pool overrides except `background_pool_size` and
`background_schedule_pool_size`, then retry.

---

## First-Time Setup

### 1. Generate Secrets

Create `~/langfuse/.env` with all required secrets:

```bash
# Run the automated installer (recommended)
bash src/scripts/cortex-setup-langfuse.sh --start
```

Or generate manually:

```bash
mkdir -p ~/langfuse
cat > ~/langfuse/.env << 'EOF'
LANGFUSE_SALT=$(openssl rand -hex 32)
LANGFUSE_SECRET_KEY=$(openssl rand -hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)
LANGFUSE_POSTGRES_PASSWORD=$(openssl rand -hex 20)
LANGFUSE_CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)
LANGFUSE_REDIS_AUTH=$(openssl rand -hex 32)
LANGFUSE_MINIO_ACCESS_KEY=$(openssl rand -hex 16)
LANGFUSE_MINIO_SECRET_KEY=$(openssl rand -hex 32)
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-$(openssl rand -hex 16)
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-$(openssl rand -hex 32)
LANGFUSE_INIT_PROJECT_NAME=Hermes Agent
EOF
chmod 600 ~/langfuse/.env
```

### 2. Copy Config Files

```bash
cp -r deploy/clickhouse-config.d ~/langfuse/
cp deploy/docker-compose.langfuse.yml ~/langfuse/docker-compose.yml

# CRITICAL: fix file permissions
chmod 644 ~/langfuse/clickhouse-config.d/*.xml
```

### 3. Start the Stack

```bash
cd ~/langfuse
docker compose up -d
```

**Wait** 30-60 seconds for ClickHouse to initialize. Verify:

```bash
docker ps --filter name=langfuse --format 'table {{.Names}}\t{{.Status}}'
# All 6 containers should show "Up" and "healthy"
```

If ClickHouse enters a restart loop, check logs:

```bash
docker logs langfuse-clickhouse-1
```

### 4. Generate a Hermes API Key

After the stack is running, create a Langfuse API key pair for Hermes:

```bash
# Via the setup script
bash src/scripts/cortex-setup-langfuse.sh

# Or manually via Postgres (after enabling pgcrypto):
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

Record the public and secret keys shown.

### 5. Wire Hermes

```bash
# Enable the plugin
hermes plugins enable observability/langfuse

# Install the SDK
pip install langfuse

# Add to ~/.hermes/.env:
cat >> ~/.hermes/.env << EOF
HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-... (from step 4)
HERMES_LANGFUSE_SECRET_KEY=sk-lf-... (from step 4)
HERMES_LANGFUSE_BASE_URL=http://localhost:3000
HERMES_LANGFUSE_ENV=local
HERMES_LANGFUSE_SAMPLE_RATE=1.0
EOF
chmod 600 ~/.hermes/.env
```

### 6. Restart Hermes

The plugin takes effect on **next session**. Do `/reset` in chat or start a
new `hermes` session. LLM calls will now appear in Langfuse at:
- Local: http://localhost:3000
- Behind nginx (port 13002, auth_basic)

---

## Restarting After Config Changes

**IMPORTANT:** `docker compose restart` does NOT re-read environment variables
or config file changes. Always use:

```bash
cd ~/langfuse
docker compose down
docker compose up -d
```

---

## Updating Images

The compose file uses specific version tags. To check for newer versions:

```bash
docker compose pull    # pulls new images per docker-compose.yml tags
docker compose down && docker compose up -d
```

Current image tags:
- `langfuse/langfuse:3.200.0`          — Web UI
- `langfuse/langfuse-worker:3.200.0`   — Background worker
- `clickhouse/clickhouse-server:25.5-alpine` — Analytics DB
- `postgres:16-alpine` — Metadata DB
- `redis:7-alpine` — Queue & cache
- `minio/minio:latest` — S3-compatible storage

---

## Common Issues

### "Access to file denied" during ClickHouse startup
Config files are `chmod 600`. Fix: `chmod 644 ~/langfuse/clickhouse-config.d/*.xml`

### ClickHouse crashes with SIGSEGV / exit code 139
Too many background pool settings reduced simultaneously.
Fix: Keep only `background_pool_size` and `background_schedule_pool_size`.
Restore all others to defaults.

### ClickHouse merge failures (`MEMORY_LIMIT_EXCEEDED`, `TotalMergeFailures` climbing)

**Symptom:** Watchdog reports `TotalMergeFailures` climbing rapidly. `system.errors` shows `MEMORY_LIMIT_EXCEEDED: (total) memory limit exceeded: would use 1.80 GiB ... maximum: 1.80 GiB`. No active merges run despite many unmerged parts.

**Root cause:** ClickHouse cache defaults are tuned for 64+ GiB servers (`uncompressed_cache_size` = 8 GiB, `mark_cache_size` = 5 GiB). In a 2 GiB Docker container, these caches consume the bulk of available memory before background merges can start. Every merge attempt immediately hits the memory limit, and the `TotalMergeFailures` counter climbs with no recovery.

**Diagnosis:**
```bash
# 1. Check merge failure count
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT name, value FROM system.metrics WHERE name IN ('TotalMergeFailures', 'NonAbortedMergeFailures', 'Merge')"

# 2. Check cache sizes (should show changed=1 if capped)
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT name, value, changed FROM system.server_settings WHERE name IN ('uncompressed_cache_size','mark_cache_size','cache_size_to_ram_max_ratio')"

# 3. Check memory pressure
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT name, formatReadableSize(value) FROM system.metrics WHERE name IN ('MemoryTracking','MMappedFileBytes')"

# 4. Check which tables have the most parts
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT database, table, count() as parts, formatReadableSize(sum(bytes_on_disk)) as size FROM system.parts WHERE active=1 GROUP BY database,table ORDER BY parts DESC LIMIT 10"
```

**Fix (no memory increase needed):**

1. **Cap cache sizes** in `clickhouse-config.d/02-low-memory.xml`:
   ```xml
   <uncompressed_cache_size>268435456</uncompressed_cache_size>  <!-- 256 MB -->
   <mark_cache_size>134217728</mark_cache_size>                  <!-- 128 MB -->
   <cache_size_to_ram_max_ratio>0.4</cache_size_to_ram_max_ratio>
   ```

2. **Restart ClickHouse** (container must be recreated for config re-read):
   ```bash
   docker restart langfuse-clickhouse-1
   ```

3. **Drop stale partitions** if system log tables accumulated old data:
   ```bash
   docker exec langfuse-clickhouse-1 clickhouse-client --query \
     "ALTER TABLE system.trace_log DROP PARTITION '202606'"
   ```

4. **Verify merge recovery:** After restart, check `TotalMergeFailures` is 0 and merges start running. The `Merge` metric should show >0 and `MergeParts` events appear in `system.part_log`.

---

### ClickHouse merge failures (`CHECKSUM_DOESNT_MATCH`)

**Symptom:** `system.text_log` repeatedly shows `Exception in merge_task: Checksum doesn't match: corrupted data. Reference: <hash1>. Actual: <hash2>`. The same part path (`/var/lib/clickhouse/store/.../data.bin`) appears in every error. Merges stall indefinitely on that table.

**Root cause:** Data corruption in a ClickHouse part — the on-disk checksum stored at write time doesn't match a re-read. Common causes:
- Host crash or power loss during a merge
- Disk/filesystem errors (transient or permanent)
- Restart during an active write

**Diagnosis:**
```bash
# 1. Find the corrupted part (check system.text_log for the part name)
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT event_time, message FROM system.text_log WHERE level='Error' AND message LIKE '%checksum%' ORDER BY event_time DESC LIMIT 3" --vertical

# 2. Check if the corrupted part is still active
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT database, table, name, active, level, bytes_on_disk FROM system.parts WHERE name LIKE '%<PART_NAME>%'"

# 3. List all parts for the affected table to find the corruption lineage
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT database, table, name, active, level FROM system.parts WHERE database='system' AND table='part_log' ORDER BY level DESC"
```

**Fix:**

1. **Drop the corrupted base part:**
   ```bash
   docker exec langfuse-clickhouse-1 clickhouse-client --query \
     "ALTER TABLE <database>.<table> DROP PART '<corrupted_part_name>'"
   ```
   The part name is the first segment in the error path (e.g. `202607_1_1737_794` from path `.../202607_1_1737_794/data.bin`).

2. **Check for derivative parts** (higher level that includes the corrupted data). The error may reference a different part name after each failed retry — these are new merge attempts that read the corrupted parent. Check `system.parts` for inactive parts at similar levels:
   ```bash
   docker exec langfuse-clickhouse-1 clickhouse-client --query \
     "SELECT name, active, level FROM system.parts WHERE table='<affected_table>' AND level > 700 ORDER BY level"
   ```

3. **Remove orphan directories** from the store path directly:
   ```bash
   docker exec langfuse-clickhouse-1 bash -c \
     "rm -rf /var/lib/clickhouse/store/<uuid>/<orphan_part>"
   ```

4. **Restart merge queue** to clear stale merge tasks:
   ```bash
   docker exec langfuse-clickhouse-1 clickhouse-client --query "SYSTEM STOP MERGES"
   sleep 2
   docker exec langfuse-clickhouse-1 clickhouse-client --query "SYSTEM START MERGES"
   ```

5. **Verify recovery:**
   ```bash
   docker exec langfuse-clickhouse-1 clickhouse-client --query \
     "SELECT count() as errors_last_minute FROM system.text_log WHERE level='Error' AND message LIKE '%merge%' AND event_time > NOW() - INTERVAL 1 MINUTE"
   ```
   Should return `0`. New merges should appear in `system.merges` within seconds.

6. **System tables auto-recover:** Tables like `system.part_log`, `system.trace_log`, `system.asynchronous_metric_log` are internal — dropping a corrupted part loses only the affected log entries. New entries accumulate in fresh parts automatically.

---

### Langfuse Web crashes with OOM / `JavaScript heap out of memory`
The web container's Node.js process hits the heap limit during startup, typically during ClickHouse model-match cache initialization. The log shows `FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory`.

**Fix:** Increase the memory limits in `~/langfuse/docker-compose.yml`:
- `mem_limit: 1g` → `1.5g` (container level)
- Add `NODE_OPTIONS: "--max-old-space-size=1024"` under `langfuse-web.environment`

Then recreate the container:
```bash
cd ~/langfuse
docker compose up -d --force-recreate langfuse-web
```

Note: 1.5g container + 1024 MB Node heap is the minimum tested fix. If you have more RAM available, `2g` / `1536` is safer.

### Langfuse shows no traces
1. Plugin enabled? `hermes plugins list | grep langfuse`
2. SDK installed? `python3 -c "import langfuse; print(langfuse.__version__)"`
3. Env vars set? `grep LANGFUSE ~/.hermes/.env`
4. New session? Plugin only activates on next `/reset` or fresh `hermes` call.
5. API key valid? Check `api_keys` table in Postgres — keys must have `pk-lf-`/`sk-lf-` prefix.

### Langfuse API returns 401
Regenerate the API key pair. The Hermes plugin validates key prefixes
at startup and will refuse credentials without the `pk-lf-`/`sk-lf-` prefix.

### Hermes .env grows many unused variables
Only these are actually consumed by the Hermes Langfuse plugin:
- `HERMES_LANGFUSE_PUBLIC_KEY` (or `LANGFUSE_PUBLIC_KEY`)
- `HERMES_LANGFUSE_SECRET_KEY` (or `LANGFUSE_SECRET_KEY`)
- `HERMES_LANGFUSE_BASE_URL` (or `LANGFUSE_BASE_URL`)
- `HERMES_LANGFUSE_ENV`
- `HERMES_LANGFUSE_RELEASE`
- `HERMES_LANGFUSE_SAMPLE_RATE`
- `HERMES_LANGFUSE_DEBUG`

All other `*_ENABLED=true` vars are inert — leftovers from earlier tooling.

---

## LLM Judge Scorer — Automated Trace Evaluation

A scheduled script that evaluates Hermes conversation traces using a local Ollama model and posts quality scores to Langfuse.

### How It Works

1. **Fetches unscored traces** from Langfuse (last 14 days, up to 5 per run)
2. **Judges each trace** using `qwen2.5-coder:3b` running locally via Ollama
3. **Posts scores** to Langfuse: `helpfulness` (1-5), `clarity` (1-5), `depth` (1-5), `overall` (1-10)

### Prerequisites

| Requirement | Check | Install |
|-------------|-------|---------|
| Ollama running | `curl -s http://localhost:11434/api/tags` | `systemctl start ollama` |
| Judge model | `ollama list \| grep qwen2.5-coder` | `ollama pull qwen2.5-coder:3b` |
| Embeddings model | `ollama list \| grep nomic-embed-text:v1.5` | `ollama pull nomic-embed-text:v1.5` |
| Langfuse .env | `cat ~/.hermes-cortex/.env` | See "Step 5" below |
| Langfuse running | `curl -s -o /dev/null -w '%{http_code}' http://localhost:3000` | `docker compose up -d` |

### Setup

**Step 1 — Pull the judge model:**

```bash
ollama pull qwen2.5-coder:3b
```

**Step 2 — Create the Langfuse `.env` for the scorer:**

The scorer reads Langfuse API keys from `~/.hermes-cortex/.env`. Extract them from your existing Hermes config:

```bash
grep -E 'HERMES_LANGFUSE_(PUBLIC|SECRET)_KEY' ~/.hermes/.env > ~/.hermes-cortex/.env
```

Or extract from the running Docker container:

```bash
python3 ~/hermes-cortex/deploy/extract_langfuse_env.py > ~/.hermes-cortex/.env
```

**Step 3 — Deploy the script:**

```bash
# Scripts auto-deploy via cortex-update.sh --force-all
# Or copy manually:
cp ~/hermes-cortex/src/scripts/llm-judge-scorer.py ~/.hermes-cortex/scripts/
chmod +x ~/.hermes-cortex/scripts/llm-judge-scorer.py

# Also deploy the model health watchdog (recommended):
cp ~/hermes-cortex/src/scripts/model-health-watchdog.py ~/.hermes-cortex/scripts/
chmod +x ~/.hermes-cortex/scripts/model-health-watchdog.py
```

**Step 4 — Create the crons:**

```bash
# Create the LLM judge scorer cron (twice daily on weekdays)
hermes cron create --name llm-judge-scorer-weekday \
  --no-agent --script llm-judge-scorer.py \
  --schedule "0 12,20 * * 1-5" --deliver origin

# Create weekend scorer (once on Saturday/Sunday)
hermes cron create --name llm-judge-scorer-weekend \
  --no-agent --script llm-judge-scorer.py \
  --schedule "0 22 * * 0,6" --deliver origin

# Create model health watchdog (daily 7am — silent when healthy)
hermes cron create --name model-health-watchdog \
  --no-agent --script model-health-watchdog.py \
  --schedule "0 7 * * *" --deliver origin
```

**Step 5 — Verify everything works:**

```bash
# Dry-run the scorer
python3 ~/.hermes-cortex/scripts/llm-judge-scorer.py --dry-run

# Check model health (default: nomic-embed-text:v1.5 + qwen2.5-coder:3b)
python3 ~/.hermes-cortex/scripts/model-health-watchdog.py

# Check with a custom judge model (e.g., Titus' model)
python3 ~/.hermes-cortex/scripts/model-health-watchdog.py --judge-model mannix/qwen2.5-coder:7b-iq3_xs

# Via env var (comma-separated for multiple)
JUDGE_MODEL="mannix/qwen2.5-coder:7b-iq3_xs,qwen2.5-coder:3b" \\
  python3 ~/.hermes-cortex/scripts/model-health-watchdog.py --quiet

# Verify crons are scheduled
hermes cron list | grep -E 'llm-judge|model-health'
```

### Error Handling

The scorer checks prerequisites before starting:

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `Cannot reach Ollama` | Ollama not running | `systemctl start ollama` |
| `Judge model 'qwen2.5-coder:3b' not found` | Model not pulled | `ollama pull qwen2.5-coder:3b` |
| `Could not read Langfuse project keys` | Missing `.env` | Create `~/.hermes-cortex/.env` |
| `HTTP 401` on Langfuse POST | Stale API keys | Regenerate in Langfuse UI |

The `model-health-watchdog` cron (daily 7am) alerts you if any models are missing,
with a descriptive message including the `ollama pull` commands needed.

The watchdog supports custom judge models via:
- `--judge-model <name>` (CLI flag, repeatable for multiple models)
- `JUDGE_MODEL` environment variable (comma-separated for multiple)
- Defaults to `qwen2.5-coder:3b` if neither is set
- `nomic-embed-text:v1.5` is always required and always checked

Use the `extract_langfuse_env.py` utility to regenerate the `.env` file from the running
Docker stack if keys ever need updating:

```bash
python3 ~/hermes-cortex/deploy/extract_langfuse_env.py > ~/.hermes-cortex/.env
```
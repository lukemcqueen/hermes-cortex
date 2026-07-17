# Langfuse + ClickHouse — Deployment Guide

> **Location:** `deploy/docker-compose.langfuse.yml`
> **Config files:** `deploy/clickhouse-config.d/`
> **Setup script:** `ops/scripts/install/cortex-setup-langfuse.sh`

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
| `02-low-memory.xml` | `config.d/` | **Default low-memory config** — thread pools, merge size caps, cache caps, system log TTL. Designed to run stably in a **2 GiB container**. See "Configuration Reference" below for all settings. |
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
bash ops/scripts/install/cortex-setup-langfuse.sh --start
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
bash ops/scripts/install/cortex-setup-langfuse.sh

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

### ClickHouse merge failures (`MEMORY_LIMIT_EXCEEDED`, `TotalMergeFailures` climbing, stuck bg threads)

**Symptom:** Watchdog reports `TotalMergeFailures` climbing rapidly (hundreds per hour). Server log shows:
```
MergeTreeBackgroundExecutor: Exception while executing background task:
Code: 241. (total) memory limit exceeded: would use 1.80 GiB
(attempt to allocate chunk of 4.16 MiB bytes), current RSS: 492.07 MiB,
maximum: 1.80 GiB.
```
`MergeTreeBackgroundExecutorThreadsActive` shows many threads (45+) but `Merge` metric is 0 — threads stuck retrying merges that always fail. No recovery without intervention.

**Root cause (three compounding issues, must fix all):**

1. **Merge size far exceeds RAM (the real killer):** ClickHouse's default `max_bytes_to_merge_at_max_space_in_pool` is **150 GB**. In a 2 GiB container, a single merge task tries to process parts totaling >100 GiB. It always hits the server memory cap (1.8 GiB = 90% of 2 GiB). Every attempt fails with `MEMORY_LIMIT_EXCEEDED`. The fix: cap each merge to **500 MB** so it fits in 1/4 of available memory.

2. **Cache defaults assume 64+ GiB RAM:** ClickHouse defaults `uncompressed_cache_size` to 8 GiB and `mark_cache_size` to 5 GiB. In a 2 GiB container, these caches consume almost all memory before background merges can start. Fix: cap caches at 256 MB / 128 MB respectively.

3. **Merge pool never reduces sizes:** The default `number_of_free_entries_in_pool_to_lower_max_size_of_merge = 8` waits for 8 free pool slots before shrinking merge sizes. With all 26 pool slots saturated by retrying failed merges, the size is never lowered — death spiral. Fix: set to 0 (immediately lower merge sizes).

**Diagnosis:**

```bash
# 1. Check server log for exact memory limit error
docker exec langfuse-clickhouse-1 grep "MEMORY_LIMIT\|memory limit exceeded" \
  /var/log/clickhouse-server/clickhouse-server.err.log

# 2. Check merge failure count
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT metric, value FROM system.metrics \
   WHERE metric IN ('TotalMergeFailures','NonAbortedMergeFailures','Merge')"

# 3. Check current merge size cap (should be 536870912 = 500 MB)
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT name, value FROM system.merge_tree_settings \
   WHERE name LIKE '%max_byte%merge%'"

# 4. Check cache size caps applied (changed=1 means config took effect)
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT name, value, changed FROM system.server_settings \
   WHERE name IN ('uncompressed_cache_size','mark_cache_size', \
                  'cache_size_to_ram_max_ratio')"

# 5. Check memory pressure
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT metric, formatReadableSize(value) FROM system.metrics \
   WHERE metric = 'MergesMutationsMemoryTracking'"

# 6. Check which tables have the most parts (cleanup candidates)
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT database, table, count() as parts, \
   formatReadableSize(sum(bytes_on_disk)) as size \
   FROM system.parts WHERE active=1 \
   GROUP BY database,table ORDER BY parts DESC LIMIT 10"
```

**Fix — apply these settings in `clickhouse-config.d/02-low-memory.xml`:**

```xml
<!-- ── Merge size: the critical fix ── -->
<merge_tree>
    <!-- Each merge capped to ~500 MB (default 150 GB!) so it fits in memory -->
    <max_bytes_to_merge_at_max_space_in_pool>536870912</max_bytes_to_merge_at_max_space_in_pool>
    <!-- 500 MB -->
    <max_bytes_to_merge_at_min_space_in_pool>52428800</max_bytes_to_merge_at_min_space_in_pool>
    <!-- 50 MB -->
    <!-- Smaller blocks = less memory per merge operation -->
    <merge_max_block_size>512</merge_max_block_size>
    <!-- Immediately reduce merge sizes when pool is busy (avoid death spiral) -->
    <number_of_free_entries_in_pool_to_lower_max_size_of_merge>0</number_of_free_entries_in_pool_to_lower_max_size_of_merge>
    <!-- Faster retry after failed merge attempts -->
    <merge_selecting_sleep_ms>1000</merge_selecting_sleep_ms>
</merge_tree>

<!-- ── Merge memory: hard cap ── -->
<!-- Stop scheduling new merges when they've consumed 512 MB -->
<merges_mutations_memory_usage_soft_limit>536870912</merges_mutations_memory_usage_soft_limit>

<!-- ── Cache caps ── -->
<uncompressed_cache_size>268435456</uncompressed_cache_size>    <!-- 256 MB -->
<mark_cache_size>134217728</mark_cache_size>                    <!-- 128 MB -->
<cache_size_to_ram_max_ratio>0.4</cache_size_to_ram_max_ratio>
```

**After editing, APPLY THE CHANGE (container must be recreated):**

```bash
# Stop and restart (restart alone does NOT re-read config files)
cd ~/langfuse
docker compose stop clickhouse
docker compose up -d clickhouse

# Wait for healthy
sleep 15
docker compose ps clickhouse

# Verify all settings applied
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT name, value FROM system.merge_tree_settings WHERE changed = 1 \
   ORDER BY name"
```

**Verify recovery:**

```bash
# TotalMergeFailures should be 0 after restart
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT metric, value FROM system.metrics \
   WHERE metric IN ('TotalMergeFailures','NonAbortedMergeFailures','Merge')"
```

If `TotalMergeFailures` starts climbing again within hours, the config wasn't applied (check `changed=1` in `system.server_settings`). Common cause: the deployed `~/langfuse/clickhouse-config.d/` copy is stale — copy from repo:

```bash
cp ~/hermes-cortex/ops/install/deploy/clickhouse-config.d/02-low-memory.xml \
   ~/langfuse/clickhouse-config.d/
chmod 644 ~/langfuse/clickhouse-config.d/*.xml
# Then stop + up -d as above
```

**Why `background_merges_mutations_concurrency_ratio` is NOT reduced:**

Ideally we'd set `<background_merges_mutations_concurrency_ratio>1</background_merges_mutations_concurrency_ratio>` to halve concurrent merges (from 26 to 13). However, **ClickHouse 25.5-alpine crashes** (exit code 36) if more than 2 background pool settings are reduced simultaneously. `background_pool_size=13` and `background_schedule_pool_size=16` are already reduced. Adding a third triggers the bug. The default ratio of 2 is acceptable with the 500 MB merge cap — each merge uses much less memory so 26 concurrent tasks don't OOM.

---

### ClickHouse — Configuration Reference

All settings in `02-low-memory.xml` — this is the **default low-memory configuration** for a **2 GiB container**. Each setting is tuned for stability over performance.

#### MergeTree Settings (govern merge behavior)

| Setting | Value (Default) | Why |
|---------|-----------------|-----|
| `max_bytes_to_merge_at_max_space_in_pool` | **500 MB** (150 GB) | **Critical.** Caps the total size of parts in a single merge. 150 GB always OOMs in 2 GiB. 500 MB fits in 1/4 of available RAM. |
| `max_bytes_to_merge_at_min_space_in_pool` | **50 MB** (1 MB) | Minimum merge size threshold. Avoids merging tiny parts individually. |
| `merge_max_block_size` | **512** (8192) | Rows per merge block. Smaller = less memory per merge. |
| `number_of_free_entries_in_pool_to_lower_max_size_of_merge` | **0** (8) | Immediately shrink merge sizes when pool is busy. Default of 8 means the pool needs 8 free slots before reducing — in a saturated pool, that never happens (death spiral). |
| `merge_selecting_sleep_ms` | **1000** (5000) | How long to wait between merge selection attempts. Faster retry after failures. |

#### Server Settings (server-level config)

| Setting | Value (Default) | Why |
|---------|-----------------|-----|
| `background_pool_size` | **13** (16) | Threads for background merges & mutations. Floor is 13 in CH 25.5 (≤12 crashes). |
| `background_schedule_pool_size` | **16** (512) | Threads for periodic ops (replication, DNS, cleanup). Default 512 is excessive; 16 saves 496 threads + stacks (~2 GB of virtual address space). |
| `max_concurrent_queries` | **25** (1000) | Max simultaneous queries. Reduces memory contention with background merges. |
| `merges_mutations_memory_usage_soft_limit` | **512 MB** (0=unlimited) | Hard cap: stop scheduling new merges when existing merges use >512 MB total. |
| `merges_mutations_memory_usage_to_ram_ratio` | **0.25** (0.3) | Fallback ratio if soft_limit is 0. Conservative to leave headroom for queries. |
| `uncompressed_cache_size` | **256 MB** (8 GB) | Cache for decompressed data blocks. |  
| `mark_cache_size` | **128 MB** (5 GB) | Cache for index marks (sparse index lookups). |
| `cache_size_to_ram_max_ratio` | **0.4** (0.5) | Max fraction of RAM usable by all caches combined. |

#### System Log TTL (prevent part accumulation)

| Setting | Value | Why |
|---------|-------|-----|
| `trace_log_ttl` | 7 days | Auto-expire log entries. Without TTL, system tables accumulate parts forever, causing more merges. |
| `metric_log_ttl` | 7 days | Same. |
| `asynchronous_metric_log_ttl` | 7 days | Same. |
| `query_log_ttl` | 7 days | Same. |
| `text_log_ttl` | 14 days | Error logs kept longer for debugging. |

#### What NOT to Change (CH 25.5-alpine crash risk)

| Setting | Keep at | Reason |
|---------|---------|--------|
| `background_merges_mutations_concurrency_ratio` | **2** (default) | Reducing to 1 would be ideal (halves concurrent merges), but adding a 3rd reduced bg pool setting triggers SIGSEGV / exit 36 at startup. |
| `background_common_pool_size` | 8 (default) | Same bug — >2 reduced bg pool settings crash. |
| `background_fetches_pool_size` | 16 (default) | Same. |
| `background_move_pool_size` | 8 (default) | Same. |
| `max_thread_pool_size` | 10000 (default) | Same — reducing triggers crash when combined with reduced bg pools. |
| `background_pool_size` | **≥13** | Floor is 13 in CH 25.5. Values ≤12 crash with SIGSEGV. |

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
cp ~/hermes-cortex/ops/scripts/manage/llm-judge-scorer.py ~/.hermes-cortex/scripts/
chmod +x ~/.hermes-cortex/scripts/llm-judge-scorer.py

# Also deploy the model health watchdog (recommended):
cp ~/hermes-cortex/ops/scripts/health/model-health-watchdog.py ~/.hermes-cortex/scripts/
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
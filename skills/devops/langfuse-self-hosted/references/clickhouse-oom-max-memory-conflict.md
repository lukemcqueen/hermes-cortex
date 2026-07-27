# ClickHouse OOM: Per-query max_memory_usage vs Server max_server_memory_usage

## When to suspect this problem

All ClickHouse low-memory tuning is applied (merge sizes capped at 256-500 MB,
background pools reduced, caches shrunk), but `TotalMergeFailures` continues to
climb with `MEMORY_LIMIT_EXCEEDED` errors.

## The root cause

ClickHouse has **two independent memory limits**, and causing them to conflict
produces silent persistent merge failures:

| Limit | Where set | Purpose |
|---|---|---|
| `max_memory_usage` | Profile `users.d/` | Per-query/user memory cap |
| `max_server_memory_usage` | Server `config.d/` | Total server-wide memory cap (90% of container `mem_limit` by default) |

When `max_memory_usage` > `max_server_memory_usage`, every merge task that tries
to allocate its full budget gets killed by the server-level cap before it can
complete. The merge scheduler keeps retrying, every attempt OOMs, and
`TotalMergeFailures` climbs forever.

## Diagnosis

### 1. Check both values

```bash
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT 'per-query max_memory_usage' as setting, value, formatReadableSize(value)
FROM system.settings WHERE name = 'max_memory_usage'
UNION ALL
SELECT 'server max_server_memory_usage', value, formatReadableSize(value)
FROM system.server_settings WHERE name = 'max_server_memory_usage'
"
```

### 2. Interpret the result

- If `max_memory_usage` ≤ 50% of `max_server_memory_usage` → the conflict is NOT the issue here
- If `max_memory_usage` > `max_server_memory_usage` → this IS the cause

**Example from a real failure (3 GiB container with wrong profile):**

```
per-query max_memory_usage       | 6000000000 (5.59 GiB)
server max_server_memory_usage   | 2899102924 (2.70 GiB)
```

Here the per-query limit (6 GiB from a stale profile default) was more than
double the server's total capacity (2.7 GiB). Every merge that tried to use its
full budget was immediately killed.

### 3. Check server log for MEMORY_LIMIT_EXCEEDED

```bash
docker exec langfuse-clickhouse-1 grep "MEMORY_LIMIT" \
  /var/log/clickhouse-server/clickhouse-server.err.log | tail -3
```

The error line shows `would use X GiB` (the per-query limit) vs `maximum: Y GiB`
(the server max). If X > Y, this diagnosis is confirmed.

## Fix

### 1. Calculate the right per-query limit

In a container with `mem_limit: 3g`:
- `max_server_memory_usage` ≈ 2.7 GiB (90% — automatic)
- Per-query limit should be ≤50% = ~1.5 GiB to allow 2 concurrent merges

```xml
<max_memory_usage>1500000000</max_memory_usage>
```

### 2. Update the profile defaults config file

Edit `~/langfuse/clickhouse-config.d/03-profile-defaults.xml`:

```bash
# Change the max_memory_usage value
sed -i 's|<max_memory_usage>[0-9]*</max_memory_usage>|<max_memory_usage>1500000000</max_memory_usage>|' \
  ~/langfuse/clickhouse-config.d/03-profile-defaults.xml
```

### 3. Restart ClickHouse (stop + up, NOT restart)

```bash
cd ~/langfuse
docker compose stop clickhouse
docker compose up -d clickhouse
```

### 4. Verify the fix

```bash
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT name, value, formatReadableSize(value) as human, changed
FROM system.settings WHERE name = 'max_memory_usage'
"
# changed should be 1, value should match your new limit
```

### 5. Wait for merge background tasks to drain

After restart, `TotalMergeFailures` will climb for 1-3 minutes as old retry
tasks from the background executor pool fail. Do not panic — this is expected.
When the counter stabilizes (no increase for 30+ seconds) and no merges are
active (`Merge = 0`), the fix is working.

### 6. Reset the watchdog state file

If a health-check cron tracks `TotalMergeFailures`:

```bash
# Get the current (stable) failure count
FAILURES=$(docker exec langfuse-clickhouse-1 clickhouse-client \
  --query "SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures'")
echo "$FAILURES" > ~/.hermes-cortex/state/langfuse-ch-merge.state
```

The next watchdog run will compare against this new baseline and report healthy.

## Prevention

When creating or updating the per-query profile defaults XML:

```xml
<max_memory_usage>1500000000</max_memory_usage>
<!-- Rule: must be ≤50% of (container_mem_limit * 0.9) to allow concurrent merges -->
```

The comment serves as a guardrail for future changes. If the container memory
limit changes, recalculate: `new_limit = container_gb * 0.9 * 0.5` (e.g.
4 GiB container → 4 × 0.9 × 0.5 = 1.8 GiB).

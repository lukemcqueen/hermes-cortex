# ClickHouse Merge Failure Repair

## When to use

When ClickHouse logs show merge failures (e.g. watchdog alerts, system.errors with MERGE or CHECKSUM errors), or when Langfuse traces stop appearing and ClickHouse has checksum errors.

## Detection

### Approach A: Live errors via `system.text_log` (preferred — catches all failures)

The `system.text_log` table records ClickHouse server-level events including merge
failures in real time. Unlike `system.part_log` (which may have retention limits),
`text_log` is reliable for catching ongoing problems even when part_log shows
nothing recent.

```bash
# 1. Check merge state — poll TotalMergeFailures rate
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT 
    (SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures') AS total_failures,
    (SELECT value FROM system.metrics WHERE metric = 'Merge') AS active_merges,
    (SELECT value FROM system.metrics WHERE metric = 'MergeTreeBackgroundExecutorThreadsActive') AS bg_active,
    now() AS time
FORMAT Vertical
"

# Poll every 2s to distinguish historic (stable) vs ongoing (climbing)
for i in 1 2 3 4 5; do
  echo -n "$(date +%H:%M:%S) "
  docker exec langfuse-clickhouse-1 clickhouse-client \
    --query "SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures'"
  sleep 2
done
# Climbing ~2-7/sec = ongoing merge loop. Stable = historic/resolved.

# 2. If climbing, find the failing table + part from text_log
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT event_time, message
FROM system.text_log
WHERE level >= 'Error'
  AND message LIKE '%Exception while executing background task%'
  AND event_time > now() - INTERVAL 5 MINUTE
ORDER BY event_time DESC
LIMIT 3 FORMAT Vertical
"

# 3. Extract UUID and part name from the error message
# Pattern: /var/lib/clickhouse/store/<UUID>/<part_name>/<column>.bin
# Two common error signatures:
#   - `UNKNOWN_CODEC` — zeroed-out compressed block header (physical corruption).
#     The compressed data header reads 000000000... which means the file was
#     truncated or never properly written.
#   - `CHECKSUM_DOESNT_MATCH` — data corruption detected during merge read.

# 4. Map UUID to table name
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT uuid, database, name
FROM system.tables
WHERE uuid = '<extracted-uuid>'
"
```

### Approach B: Cumulative error counters (system.errors — slower to detect)

```bash
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT name, value, last_error_time, substring(last_error_message, 1, 300) as msg
FROM system.errors
ORDER BY value DESC
LIMIT 10
"
```

Key patterns to look for:
- **CHECKSUM_DOESNT_MATCH** — a data part has corruption. Most common cause of merge loops.
- **UNKNOWN_CODEC** — zeroed-out compressed block header. **Equally serious** as checksum.
- **CANNOT_READ_FROM_FILE_DESCRIPTOR** — usually benign (e.g. missing /sys/block stats). Ignore if low count.
- **UNKNOWN_IDENTIFIER** — query error, not a system problem. Ignore.

### Critical subtlety: `part_log` can be unreliable

`system.part_log` may show 0 recent failures even when `TotalMergeFailures` is
climbing rapidly (2-7/sec). This happens because:
- `part_log` has retention limits and older failures rotate out
- The merge background task retries so fast that individual attempts may not
  all create `part_log` entries
- The `system.metrics` counter is always accurate — it is the ground truth

**DO NOT rely on part_log alone to confirm the fix.** Always poll
`TotalMergeFailures` over a 10-15 second window to verify stability.

### Quick check: is the merge STILL failing after your fix?

After attempting a fix, verify quickly by checking recent errors:

```bash
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT count() FROM system.text_log 
WHERE level = 'Error' 
  AND message LIKE '%merge%' 
  AND event_time > now() - INTERVAL 2 MINUTE
"
```

If 0, the fix worked. If >0, the retry loop is still active.

### Verify the corrupt part exists in system.parts

```bash
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT database, table, name, partition_id, rows, bytes_on_disk, active
FROM system.parts
WHERE name = '<part_name>'
"
```

If the part no longer exists but `TotalMergeFailures` is still climbing, the
corrupted part has already been consumed into a larger merged part (see
"Variant: part already consumed" below).

## Fix

### 1. Check if safe to drop

Parts in `system.*` tables are auto-generated ClickHouse internals — always safe to drop.
Known auto-regenerating system tables (data regenerates automatically after drop):
- `system.trace_log` — sampling query profiler
- `system.query_log` — query history
- `system.query_thread_log` — per-thread query execution
- `system.text_log` — server-level error/event log
- `system.metric_log` — periodic metric snapshots
- `system.asynchronous_metric_log` — async metric snapshots
- `system.opentelemetry_span_log` — OpenTelemetry spans

Parts in user tables (traces, observations, scores, etc.) contain actual data —
always verify data can be re-ingested before dropping.

### 2. Determine if the part still exists

```bash
# Check if the part is present in ClickHouse's view
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT name FROM system.parts WHERE table = '<table_name>' AND name = '<part_name>'
"

# Check on disk directly
docker exec langfuse-clickhouse-1 ls -la /var/lib/clickhouse/store/<uuid-first-3>/<full-uuid>/ 2>&1 | grep '<part_name>'
```

**If the part shows "No such part in committed state" and doesn't exist on disk:**
The part was already cleaned up. The merge failures are clickhouse's retry loop
trying to merge a now-vanished part. Skip straight to "Restart ClickHouse" (step 4).

**Variant: part already consumed** — if the part doesn't exist in `system.parts`
but `TotalMergeFailures` is still climbing, the corruption was absorbed into a
larger merged part. Each retry re-reads the corruption. In this case also skip
to step 4 to clear the in-memory retry queue.

### 3. Drop the corrupt part (if it still exists)

```bash
docker exec langfuse-clickhouse-1 clickhouse-client --query "
ALTER TABLE <database>.<table> DROP PART '<part_name>'
"
```

Example:
```sql
ALTER TABLE system.trace_log DROP PART '202607_7281_8462_83'
```

### 4. Restart ClickHouse

This clears the in-memory error counters and resets the merge scheduler:

```bash
docker restart langfuse-clickhouse-1
```

### 5. Verify

```bash
# Check for new errors (should be 0)
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT count() FROM system.text_log 
WHERE level = 'Error' 
  AND message LIKE '%merge%' 
  AND event_time > now() - INTERVAL 2 MINUTE
"

# Check errors cleared
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT name, value FROM system.errors WHERE name LIKE '%CHECKSUM%' OR name LIKE '%MERGE%'
"

# Confirm part gone
docker exec langfuse-clickhouse-1 clickhouse-client --query "
SELECT name FROM system.parts WHERE table = '<table_name>' AND name = '<part_name>'
"  # Should return nothing

# End-to-end check
curl -sL -o /dev/null -w '%{http_code}' https://your-domain.com/langfuse/
# Expect: 301 (redirect) or 200 (OK)
```

## Merge loop watchdog

### Reset watchdog state file after repair

The `langfuse-health-watchdog` cron (Hermes-managed, runs hourly) tracks
`TotalMergeFailures` via a state file at
`~/.hermes-cortex/state/langfuse-ch-merge.state`. After dropping a corrupted
part, the state file still holds the old high failure count. Reset it to the
current live value:

```bash
echo "$(docker exec langfuse-clickhouse-1 \
  clickhouse-client --query \
  \"SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures'\")\" \
  > ~/.hermes-cortex/state/langfuse-ch-merge.state
```

Otherwise the watchdog will either (a) report a phantom increase on next run,
or (b) fail to detect future increases because the baseline is inflated.

### Verify watchdog clears

```bash
python3 ~/.hermes/scripts/langfuse-health-watchdog.py; echo "EXIT=$?"
# Expect: no output, exit code 0 (silent = healthy)
```

If exit code 0, the watchdog is satisfied and will stay silent until a new
failure occurs.

**Note: the doctor checks the cron's last_status from the scheduler, not the
script's exit code.** After fixing, run the cron once to refresh the status:
```bash
cronjob action='run' job_id=$(cronjob action='list' | grep langfuse | grep -oP 'job_id=\K[a-f0-9]+')
```
Then re-run the doctor to see the updated status.

## Prevention

- Ensure enough disk space for merges (ClickHouse needs 2x the largest part during merge)
- The langfuse-self-hosted skill's ClickHouse tuning (background_pool_size, etc.) reduces OOM-related corruption
- Monitor system.trace_log size: if it grows large, consider dropping old partitions

## See also

- `langfuse-self-hosted` skill — ClickHouse config, SIGSEGV-safe tuning
- ClickHouse docs: ALTER TABLE DROP PART

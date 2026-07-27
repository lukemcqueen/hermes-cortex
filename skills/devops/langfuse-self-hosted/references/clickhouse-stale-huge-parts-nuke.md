# ClickHouse Stale Huge Parts — Nuke Data Volume

## When to use

The low-memory config (`02-low-memory.xml`) is **already deployed and confirmed**
(`system.server_settings` shows `changed=1`), but `TotalMergeFailures` still
climbs with all background threads stuck and every merge attempt failing with
`MEMORY_LIMIT_EXCEEDED`.

Root cause: data parts created **before** the low-memory config was deployed
are still on disk, and they're too large to merge in a 2 GiB container.
The config caps future merges at 256-500 MB, but old parts (created at
150 GB default) can never be merged within available memory.

## Symptoms

```
Metric                          | Stale-parts scenario
--------------------------------|--------------------
TotalMergeFailures              | >100 and climbing
Merge                           | 0 (no merges completing)
MergeTreeBackgroundExecutor...  | 45 (pool size — all threads stuck)
Server error log                | "memory limit exceeded: would use 2.70 GiB"
02-low-memory.xml               | deployed, confirmed changed=1
trace_log / text_log size       | 275+ MiB (pre-tuning parts persist)
```

The config is correct but the DATA was created before it existed.

## Fix: Nuke and restart

```bash
# 1. Find the correct volume name
docker volume ls --filter "name=clickhouse" --format "{{.Name}}"
# Usually: langfuse_langfuse-clickhouse-data or <project>_clickhouse-data

# 2. Stop dependent services first, then clickhouse
cd ~/langfuse
docker compose stop langfuse-worker langfuse-web clickhouse
docker compose rm -f clickhouse

# 3. Remove the data volume
docker volume rm <volume-name-from-step-1>

# 4. Start clickhouse fresh (creates new empty volume)
docker compose up -d clickhouse

# 5. Wait for healthy
for i in $(seq 1 30); do
  status=$(docker inspect langfuse-clickhouse-1 --format '{{.State.Health.Status}}' 2>/dev/null)
  if [ "$status" = "healthy" ]; then echo "Healthy after ${i}s"; break; fi
  sleep 2
done

# 6. Start the rest
docker compose up -d langfuse-worker langfuse-web

# 7. Verify TotalMergeFailures = 0
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT value FROM system.metrics WHERE metric='TotalMergeFailures'"

# 8. Reset watchdog state file
echo "0" > ~/.hermes-cortex/state/langfuse-ch-merge.state
```

## Verification

```bash
# All containers running
docker ps --filter "name=langfuse" --format "{{.Names}} {{.Status}}"

# ClickHouse healthy
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT metric, value FROM system.metrics WHERE metric IN ('TotalMergeFailures','Merge')"

# Web UI responding
curl -sI http://localhost:3000 | head -1
# → HTTP/1.1 200 OK

# Tables recreated fresh
docker exec langfuse-clickhouse-1 clickhouse-client --query \
  "SELECT database, name, formatReadableSize(total_bytes) AS size FROM system.tables WHERE database NOT IN ('system','INFORMATION_SCHEMA','information_schema') ORDER BY total_bytes DESC"
```

## Data loss

All Langfuse traces, observations, scores, and event logs are dropped.
Acceptable on staging/trial instances where data regenerates. For production:
verify backup before proceeding.

## Prevention

Once the low-memory config (`02-low-memory.xml`) is deployed and new data
creates parts within the 256-500 MB cap, this scenario never recurs. The
only trigger is: config applied AFTER data already contains huge pre-tuning
parts.

## See also

- `references/clickhouse-merge-failure-repair.md` — Corrupt part (CHECKSUM/UNKNOWN_CODEC), drop part + restart. Different cause, different fix.
- `references/clickhouse-oom-max-memory-conflict.md` — Per-query max_memory_usage exceeding server max_server_memory_usage. Different cause, different fix.

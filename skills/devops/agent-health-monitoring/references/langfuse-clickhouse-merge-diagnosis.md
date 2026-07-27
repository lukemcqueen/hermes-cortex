# ClickHouse Merge Failure Diagnosis

When `langfuse-health-watchdog` exits non-zero with ClickHouse merge failures, it feeds `no_errored_crons = -1` (vector index 2) in the health endpoint.

## Detection path

1. External health URL shows `[*, *, -1, *, ...]` at index 2
2. `cronjob action='list'` shows `langfuse-health-watchdog` with `last_status: error`
3. Read its output: `~/.hermes/cron/output/<job_id>/latest.md`
4. Output shows: `TotalMergeFailures: N` and possibly `Stuck: X bg threads active`

## Quick diagnosis

```bash
# Check merge failures metric
docker exec langfuse-clickhouse-1 clickhouse-client -q "
SELECT metric, value FROM system.metrics
WHERE metric IN ('TotalMergeFailures', 'NonAbortedMergeFailures', 'Merge',
'BackgroundMergesAndMutationsPoolTask', 'MergeTreeBackgroundExecutorThreadsActive')"

# Check system errors
docker exec langfuse-clickhouse-1 clickhouse-client -q "
SELECT name, count() as cnt FROM system.errors GROUP BY name ORDER BY cnt DESC LIMIT 10"

# Check disk space
docker exec langfuse-clickhouse-1 clickhouse-client -q "
SELECT name, formatReadableSize(free_space) as free,
       round(free_space*100/total_space,1) as free_pct
FROM system.disks"

# Check container memory limits
docker stats langfuse-clickhouse-1 --no-stream
```

### Memory budget diagnosis (when MEMORY_LIMIT_EXCEEDED persists)

```bash
# 1. Check CH's cgroup-aware server memory limit vs container mem_limit
docker exec langfuse-clickhouse-1 clickhouse-client -q "
SELECT name, value, description FROM system.server_settings
WHERE name IN ('max_server_memory_usage', 'cgroup_memory_watcher_hard_limit_ratio')"

# 2. Check ASYNC metrics for actual cgroup/docker memory
docker exec langfuse-clickhouse-1 clickhouse-client -q "
SELECT metric, value FROM system.asynchronous_metrics
WHERE metric LIKE '%CGroupMemory%' OR metric LIKE '%MemoryResident%'"

# 3. Check three-way balance: merge size + cache must fit in merge soft limit
docker exec langfuse-clickhouse-1 clickhouse-client -q "
SELECT name, value, changed FROM system.server_settings
WHERE name IN ('merges_mutations_memory_usage_soft_limit',
               'uncompressed_cache_size', 'mark_cache_size',
               'cache_size_to_ram_max_ratio')"
docker exec langfuse-clickhouse-1 clickhouse-client -q "
SELECT name, value, changed FROM system.merge_tree_settings
WHERE name = 'max_bytes_to_merge_at_max_space_in_pool'"

# 4. Check the actual CH server error log for the specific error text
docker exec langfuse-clickhouse-1 grep "MEMORY_LIMIT" /var/log/clickhouse-server/clickhouse-server.err.log | tail -3
```

The error pattern: `(total) memory limit exceeded: would use X GiB (attempt to allocate chunk of Y MiB bytes), current RSS: Z MiB, maximum: X GiB`

Key insight: CH's cgroup watcher calculates `max_server_memory_usage = mem_limit × cgroup_memory_watcher_hard_limit_ratio` (default 0.95). A 3g Docker limit → CH sees only 2.70 GiB. After caches (uncompressed 256 MiB + mark 128 MiB = 384 MiB) consume their share within the 1 GiB merge soft limit, a 768 MiB merge can't allocate its write buffers. The three levers (container `mem_limit`, `max_bytes_to_merge_at_max_space_in_pool`, and cache sizes) must all balance — fixing only one is usually insufficient.

## Common causes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| High TotalMergeFailures, bg threads active but no merges running | Memory limit in container (1GB default). ClickHouse needs headroom for merge operations. | Increase container memory limit in docker-compose. Check `max_server_memory_usage` setting. |
| MEMORY_LIMIT_EXCEEDED in system.errors | Merge operation exceeded available memory | Increase memory limit or reduce `max_memory_usage` for merge operations |
| Disk space < 10% | No room for merge output | Free disk space or add storage |
| NOT_AN_AGGREGATE errors | Query syntax issue (benign, from diagnostic queries) | No action needed |
| TotalMergeFailures climbing, settings show changed=0 | Deployed ClickHouse config file is stale — repo has cache caps and TTL, but `~/langfuse/clickhouse-config.d/02-low-memory.xml` still has the old defaults | Copy repo config and restart: `cp ~/hermes-cortex/ops/install/deploy/clickhouse-config.d/02-low-memory.xml ~/langfuse/clickhouse-config.d/ && chmod 644 ~/langfuse/clickhouse-config.d/*.xml && docker restart langfuse-clickhouse-1`. Then verify `changed=1` on `uncompressed_cache_size`, `mark_cache_size`, `cache_size_to_ram_max_ratio`. |
| TotalMergeFailures climbing despite low-memory config applied (changed=1) | **Docker mem_limit too tight** — CH's cgroup watcher caps `max_server_memory_usage` at 95% of container limit. If mem_limit=3g, CH only sees ~2.7 GiB. Merging 768 MB parts exceeds available memory after caches consume 384 MiB of the 1 GiB merge soft limit. | **Three levers must balance:** (1) Bump `mem_limit` in docker-compose (e.g. 3g→6g on a 16 GiB host), (2) Reduce `max_bytes_to_merge_at_max_space_in_pool` to fit within remaining budget (e.g. 512 MB with 1 GiB soft limit and 384 MiB caches), (3) `docker compose down && docker compose up -d` (restart alone won't re-read mem_limit). |
| After compose down+up, web container stuck (health: starting) with CH migration errors | **Image version downgrade** — running container was version X, but compose file pins version Y (< X). Compose pulls the older Y on up. Older version can't handle schema migrations already applied by X. Error: `error: no migration found for version 36: read down for version 36` | Update image tags in docker-compose.yml to match the previously running version. `docker compose up -d langfuse-web langfuse-worker` to recreate only those containers. Check running version before restarting: `docker inspect <container> --format '{{.Config.Image}}'`. |

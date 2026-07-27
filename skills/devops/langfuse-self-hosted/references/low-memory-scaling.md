# Langfuse v3 Memory Optimization for Constrained Environments

> Research compiled from the official Langfuse scaling docs:
> https://langfuse.com/self-hosting/configuration/scaling

## Minimum Infrastructure Requirements (v3)

| Service | Minimum Spec |
|---------|-------------|
| Web container | 2 CPU, 4 GiB |
| Worker container | 2 CPU, 4 GiB |
| ClickHouse | 2 CPU, 8 GiB |
| PostgreSQL | 2 CPU, 4 GiB |
| Redis | 1 CPU, 1.5 GiB |

## What consumes memory in the web container

1. **S3 write sockets** — `LANGFUSE_S3_CONCURRENT_WRITES` (default 50). Each socket has memory overhead for the HTTP client.
2. **ClickHouse reads during ingestion** — Per default, the worker reads the existing event from ClickHouse and merges it. For OTel-only projects, this is unnecessary.
3. **FINAL modifier on observations** — `ReplacingMergeTree` appends `FINAL` by default, adding query-time merge work.
4. **PostHog telemetry timeouts** — Connection attempts to `eu.posthog.com` time out after 30s if unreachable, consuming memory during the wait.
5. **Ingestion queue** — Backlogged ingestion increases memory as the worker holds events in memory.

## Env var reference

### LANGFUSE_S3_CONCURRENT_WRITES
- **Default:** 50
- **Recommended for constrained:** 10
- **Effect:** Each socket is an HTTP client connection to S3/MinIO. At 50 concurrent, memory pressure is significant. Reduce to 10.
- **Signal to increase:** `@smithy/node-http-handler:WARN - socket usage at capacity=150` in logs

### LANGFUSE_SKIP_INGESTION_CLICKHOUSE_READ_MIN_PROJECT_CREATE_DATE
- **Default:** unset
- **Recommended:** `"2025-01-01"` (or a date before your first project was created)
- **Effect:** Skips reading the existing event from ClickHouse during ingestion. For OTel-only projects that never migrated from v2, ClickHouse reads are optional because full event history is in S3.
- **Risk:** Late updates to events combined with S3 lifecycle rules could cause duplicates.

### LANGFUSE_SKIP_FINAL_FOR_OTEL_PROJECTS
- **Default:** false
- **Recommended:** true
- **Effect:** Per-project tracking: when a project ingests via OTel, marks it in Redis (24h TTL), and subsequent observation reads skip FINAL.
- **Note:** The TTL refreshes on every OTel call, and expires automatically if the project stops sending OTel traffic.

### LANGFUSE_API_CLICKHOUSE_DISABLE_OBSERVATIONS_FINAL
- **Default:** false
- **Recommended:** true (only if ALL projects use OTel exclusively)
- **Effect:** Global drop of FINAL modifier without Redis lookup.
- **Warning:** Do NOT enable if any project still uses legacy ingestion — stale/duplicate rows.

### LANGFUSE_CLICKHOUSE_DELETION_TIMEOUT_MS
- **Default:** 600000 (10 min)
- **Recommended:** 300000 (5 min)
- **Effect:** Client-side timeout for ClickHouse delete/retention operations.

### LANGFUSE_INIT_PROJECT_RETENTION
- **Default:** unset (indefinite)
- **Recommended:** 7
- **Effect:** Auto-deletes traces/observations/scores/media older than N days. Only takes effect on **project creation** — does NOT change existing projects.

## Disk usage optimization

### S3 lifecycle rules
Set lifecycle rules on blob storage to automatically remove old event data:
- 30 days is recommended for most deployments
- **Do NOT** set retention on the media bucket — it breaks file references in traces
- Use Langfuse's built-in data retention feature for media files instead

### ClickHouse TTL
```sql
-- Add TTL to traces, observations, scores, event_log tables
ALTER TABLE traces MODIFY TTL timestamp + INTERVAL 30 DAY;
```

### ClickHouse system log tables
These tables (`trace_log`, `text_log`, `metric_log`, etc.) dominate disk usage with no TTL by default. Disable them:

```xml
<clickhouse>
    <trace_log remove="1"/>
    <text_log remove="1"/>
    <opentelemetry_span_log remove="1"/>
    <asynchronous_metric_log remove="1"/>
    <metric_log remove="1"/>
    <latency_log remove="1"/>
</clickhouse>
```

## Core dump investigation

The `next-server` process is the Langfuse web container's Node.js process (`node ./web/server.js`). When it OOM-kills:

1. Check `/var/crash/` for core dumps: `ls -lh /var/crash/core.next-server*`
2. Verify it's the Langfuse container: `cat /proc/<PID>/cgroup | grep docker`
3. Check container memory usage: `docker stats langfuse-langfuse-web-1 --no-stream`
4. Disable core dumps in compose: `ulimits: core: 0`
5. Apply the env vars above to reduce memory pressure

## Restart procedure

`docker compose restart` does NOT re-read env vars or config changes. Always:
```bash
docker compose down
docker compose up -d
```

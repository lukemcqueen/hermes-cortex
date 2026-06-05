# Decisions

## ADR-001: Langfuse v3 Upgrade with ClickHouse

**Date:** 2026-06-05
**Status:** Accepted

### Context
Langfuse v3 introduced mandatory env vars and a new Zod schema validator that caused container crashes on startup. The existing compose file was a v2-era config missing ClickHouse, S3 upload vars, encryption keys, and cluster settings.

### Decision
Rewrite `docker-compose.langfuse.yml` to match the official Langfuse v3 reference:

- Add ClickHouse as a mandatory backend (replaces in-process OLAP)
- Add MinIO S3 buckets for event uploads, media uploads, and batch exports
- Add `CLICKHOUSE_MIGRATION_URL` using Go driver protocol (`clickhouse://clickhouse:9000` — TCP, not HTTP)
- Set `CLICKHOUSE_CLUSTER_ENABLED: false` to avoid Zookeeper dependency for single-node
- Generate and store `LANGFUSE_ENCRYPTION_KEY` (32-byte hex) in `~/langfuse/.env`
- Pin images to `:3` tag (deterministic) instead of `latest`
- Expose port `3001:3000` to avoid conflicts with other services on 3000

### Consequences
- 6 containers now required (postgres, redis, clickhouse, minio, web, worker)
- All mandatory env vars validated at startup — container fails immediately instead of later
- Assets/large traces stored in MinIO instead of DB
- Migration path: existing data in PG-only setup must be replayed via Langfuse API

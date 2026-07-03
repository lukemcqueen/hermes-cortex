---
language: sql
tags: [postgres, performance, tuning, monitoring]
title: PostgreSQL Performance Tuning
description: Slow query log, EXPLAIN ANALYZE, pg_stat_statements, connection pooling, and config tuning.
source: pattern
---

```sql
-- Enable query statistics (requires pg_stat_statements)
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Top 10 queries by total time
SELECT queryid,
       LEFT(query, 80) AS query_preview,
       calls,
       ROUND(total_exec_time::numeric, 1) AS total_ms,
       ROUND(mean_exec_time::numeric, 1) AS avg_ms,
       ROUND((100 * total_exec_time / SUM(total_exec_time) OVER ())::numeric, 1) AS pct
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;

-- Current running queries
SELECT pid, state, now() - query_start AS duration,
       LEFT(query, 120) AS query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;

-- Table bloat estimate
SELECT schemaname, tablename,
       n_live_tup, n_dead_tup,
       ROUND(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100, 1) AS dead_pct
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;

-- Missing indexes (sequential scans on large tables)
SELECT schemaname, relname, seq_scan, seq_tup_read,
       idx_scan, n_live_tup
FROM pg_stat_user_tables
WHERE seq_scan > 1000 AND n_live_tup > 10000
ORDER BY seq_scan DESC;

-- Connection pool with PgBouncer
-- pgbouncer.ini:
-- [databases]
-- mydb = host=localhost port=5432 dbname=mydb
-- [pgbouncer]
-- pool_mode = transaction
-- max_client_conn = 200
-- default_pool_size = 20
-- listen_port = 6432
```

```bash
# Enable slow query log (postgresql.conf)
# log_min_duration_statement = 1000     # log queries > 1 second
# log_line_prefix = '%t [%p-%l] %u@%d '
```

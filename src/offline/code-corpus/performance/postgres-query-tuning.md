---
language: sql
tags: [postgres, performance, tuning, queries]
title: PostgreSQL Query Performance Tuning
description: EXPLAIN ANALYZE, index-only scans, join strategies, work_mem, and effective_cache_size
source: pattern
---

# PostgreSQL Query Performance Tuning

## EXPLAIN ANALYZE Interpretation

```sql
-- Basic EXPLAIN ANALYZE — actual execution times, not estimates
EXPLAIN ANALYZE
SELECT u.email, o.total
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.created_at >= '2025-01-01';

-- Key metrics to read:
--   "cost=0.00..432.10"   — planner's estimate (startup..total)
--   "actual time=0.023..4.512" — real wall-clock (startup..total)
--   "rows=1250"            — actual row count vs "rows=998" estimate
--   "loops=5"              — Nested Loop executor re-ran this node
--   "Buffers: shared hit=840 read=23" — cache efficiency

-- BUFFERS adds cache hit / read details
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM large_table WHERE status = 'active';

-- Look for: high "read" buffers → index or work_mem tuning needed
```

## Index-Only Scans & Seq Scan Avoidance

```sql
-- Index-only scan requires covering index (all queried columns in index)
CREATE INDEX idx_orders_covering ON orders (user_id, created_at) INCLUDE (total, status);

-- Now this can use index-only scan if visibility map is up to date:
EXPLAIN ANALYZE
SELECT user_id, created_at, total
FROM orders
WHERE user_id = 42;

-- Force index scan when planner chooses seq scan on large table
SET enable_seqscan = off;  -- debug only, never in production
EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id = 42;
RESET enable_seqscan;

-- Detect seq scans in real-time
SELECT relname, seq_scan, seq_tup_read, idx_scan
FROM pg_stat_user_tables
WHERE seq_scan > 1000 AND seq_tup_read > 1000000
ORDER BY seq_tup_read DESC;
```

## Join Strategies

```sql
-- Nested Loop (good for small inner side, index-driven)
--   ->  Nested Loop  (cost=0.29..1432.10 rows=1250 width=64)
--         ->  Index Scan using idx_orders_user_id on orders
--         ->  Index Scan using users_pkey on users

-- Hash Join (good for large unindexed joins, one side hashed)
--   ->  Hash Join  (cost=8420.50..15200.80 rows=50000 width=64)
--         ->  Seq Scan on orders
--         ->  Hash
--               ->  Seq Scan on users

-- Merge Join (good for pre-sorted large datasets)
--   ->  Merge Join  (cost=0.85..18500.40 rows=50000 width=64)
--         ->  Index Scan using users_pkey on users
--         ->  Index Scan using idx_orders_created on orders

-- Force join type for debugging (off in production)
SET enable_hashjoin = off;
SET enable_mergejoin = off;
EXPLAIN ANALYZE SELECT ...;
RESET enable_hashjoin;
RESET enable_mergejoin;

-- Check current join stats
SELECT name, setting, unit, context
FROM pg_settings
WHERE name LIKE 'enable_%join' OR name LIKE 'enable_%scan';
```

## work_mem Tuning

```sql
-- work_mem per sort / hash operation — too low causes disk temp files
-- Too high risks OOM with many concurrent connections

-- Check current
SHOW work_mem;  -- default 4MB

-- Diagnose disk sorts (should be zero in healthy system)
SELECT *
FROM pg_stat_database
WHERE temp_files > 0;

-- Find queries creating temp files
SELECT datname, temp_files, temp_bytes,
       pg_size_pretty(temp_bytes) as temp_size
FROM pg_stat_database
WHERE temp_files > 0
ORDER BY temp_bytes DESC;

-- Per-connection tuning (increase for reporting queries)
SET work_mem = '64MB';
-- Complex reporting query here
RESET work_mem;

-- Global recommendation: 2-4% of RAM per connection
-- High-end: 64-256MB for analytical workloads
-- OLTP default: 4-16MB
```

## effective_cache_size

```sql
-- Tells planner how much memory the OS/filesystem caches
-- Setting too low = planner underestimates index scan speed

-- Check current
SHOW effective_cache_size;  -- default 4GB

-- Rule of thumb: 50-75% of total system RAM
-- 16GB server → effective_cache_size = '12GB'
ALTER SYSTEM SET effective_cache_size = '12GB';

-- random_page_cost should align:
-- SSD: 1.0-1.1 (fast random reads)
-- HDD: 4.0 (seek penalty)
-- NVMe: 1.0
SHOW random_page_cost;

ALTER SYSTEM SET random_page_cost = 1.1;  -- SSD / NVMe
-- Requires reload: pg_ctl reload or SELECT pg_reload_conf()
```

## Maintenance & Statistics

```sql
-- Update planner statistics
ANALYZE orders;

-- Increase statistics target for columns with skewed data
ALTER TABLE orders ALTER COLUMN status SET STATISTICS 1000;

-- Vacuum schedule for bloat management
VACUUM (VERBOSE, ANALYZE) orders;

-- Check table bloat (approximate)
SELECT
  schemaname, tablename,
  n_dead_tup, n_live_tup,
  round(n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1), 2) AS dead_pct
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
ORDER BY n_dead_tup DESC;
```
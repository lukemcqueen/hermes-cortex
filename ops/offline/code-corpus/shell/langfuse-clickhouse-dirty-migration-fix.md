---
language: shell
tags: [langfuse, clickhouse, migration, docker]
title: Langfuse ClickHouse Dirty Migration Fix
description: Fix Langfuse ClickHouse dirty migration after Docker crash. Clear dirty flags and insert missing migration entries to recover from a corrupted migration state.
source: learned
---

```shell
# Fix Langfuse ClickHouse dirty migration
# 1. Clear dirty flags in schema_migrations
docker exec langfuse-clickhouse-1 clickhouse client --query "ALTER TABLE default.schema_migrations DELETE WHERE dirty=1"
# 2. Re-insert all migration records (1-34 for v3.200.0)
docker exec langfuse-clickhouse-1 clickhouse client --query "
INSERT INTO default.schema_migrations (version, dirty, sequence) VALUES
(1,0,1),(2,0,2),(3,0,3),(4,0,4),(5,0,5),(6,0,6),
(7,0,7),(8,0,8),(9,0,9),(10,0,10),(11,0,11),(12,0,12),
(13,0,13),(14,0,14),(15,0,15),(16,0,16),(17,0,17),(18,0,18),
(19,0,19),(20,0,20),(21,0,21),(22,0,22),(23,0,23),(24,0,24),
(25,0,25),(26,0,26),(27,0,27),(28,0,28),(29,0,29),(30,0,30),
(31,0,31),(32,0,32),(33,0,33),(34,0,34)
"
# 3. Restart web container (auto-restarts with restart:always policy)
```

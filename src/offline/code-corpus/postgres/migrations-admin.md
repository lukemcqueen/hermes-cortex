---
language: sql
tags: [postgres, backup, migration, admin, management]
title: PostgreSQL Migrations & Administration
description: pg_dump, pg_restore, VACUUM, roles, grants, extensions, and maintenance.
source: pattern
---

```bash
# ── Backup & Restore ──
pg_dump -h localhost -U postgres -d mydb > mydb.sql              # plain SQL dump
pg_dump -h localhost -U postgres -F c -f mydb.dump mydb          # custom format (compressed)
pg_dump -h localhost -U postgres -F d -f /backup/dir mydb        # directory format (parallel)

pg_restore -h localhost -U postgres -d mydb mydb.dump            # restore custom format
pg_restore -h localhost -U postgres -d mydb --clean --if-exists mydb.dump  # drop + recreate
pg_dump -h localhost -U postgres -t users mydb > users.sql       # single table

# ── VACUUM & Maintenance ──
VACUUM;                                  # reclaim storage (safe, concurrent)
VACUUM FULL;                             # rewrite table (locks, intensive)
VACUUM ANALYZE;                          # vacuum + update statistics
ANALYZE;                                 # update planner statistics
REINDEX TABLE users;                     # rebuild indexes
CLUSTER users USING idx_users_email;    # reorder table by index

# ── Roles & Permissions ──
CREATE ROLE app_user WITH LOGIN PASSWORD 'securepass';
GRANT CONNECT ON DATABASE mydb TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_user;
REVOKE DELETE ON sensitive_table FROM app_user;

# ── Extensions ──
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;     # query performance
CREATE EXTENSION IF NOT EXISTS uuid-ossp;              # UUID generation
CREATE EXTENSION IF NOT EXISTS pg_texample;                # fuzzy text search (trigram)
CREATE EXTENSION IF NOT EXISTS postgis;                # geospatial

# ── Config tuning (postgresql.conf) ──
# shared_buffers = 1/4 of RAM
# effective_cache_size = 1/2 of RAM
# work_mem = 32MB (per sort/hash operation)
# maintenance_work_mem = 256MB
# wal_buffers = 64MB
# max_connections = 100
```

---
name: postgres-docker
version: 1.0.0
category: devops
description: Tune and configure PostgreSQL running inside Docker containers — custom configs, mounts, command overrides, and the listen_addresses pitfall.
---

# PostgreSQL in Docker — Configuration Guide

When running PostgreSQL in Docker containers with a custom `postgresql.conf`, there are critical Docker-specific details that differ from bare-metal Postgres administration.

## Custom Config via Mount

The recommended pattern for tuning Postgres in Docker:

```yaml
  postgres01:
    volumes:
      - "pgdata:/var/lib/postgresql"
      - "./path/to/postgresql.conf:/etc/postgresql/postgresql.conf:ro"
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

## Critical: listen_addresses = '*'

**The official Docker Postgres entrypoint** normally sets `listen_addresses = '*'` during container initialization (by appending it to the default `postgresql.conf`). When you bypass the PGDATA config by providing a custom `config_file` via the command, the entrypoint's auto-configuration does NOT apply — you must set `listen_addresses = '*'` yourself, or the container will only listen on `127.0.0.1` inside its own network namespace and every external connection will fail with:

```
connection to server at "127.0.0.1", port 5432 failed: Connection refused
```

### Symptoms of the pitfall
- `docker compose exec postgres01 psql -U postgres -c 'SHOW listen_addresses;'` → `localhost` (wrong)
- Host-side clients get `connection refused` even though `docker compose ps` shows the container healthy
- The port maps fine (`5432:5432`) but nothing connects

### Fix
Add to your custom `postgresql.conf`:

```ini
listen_addresses = '*'
```

Then restart: `docker compose restart postgres01` (config is read at startup).

## Mount Path Subtleties

- **`/var/lib/postgresql` is the PGDATA root in the official image** — a named volume there persists both the data and any config files you write into it.
- A read-only config mount (`:ro`) plus `command: postgres -c config_file=...` keeps the config file out of the volume — clean and reproducible.
- **Do NOT mount your own `postgresql.conf` directly over `/var/lib/postgresql/data/postgresql.conf`** — the entrypoint expects to manage the data dir layout, and image upgrades change the default config path (`/var/lib/postgresql/data/postgresql.conf` vs `/etc/postgresql/postgresql.conf`). The `-c config_file=` override is the stable, version-proof approach.

## Other Common Tuning Flags

```ini
# Memory (set within container RAM budget)
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB

# WAL / durability for dev containers
synchronous_commit = off          # dev only — trades durability for speed
wal_level = replica               # required for replication/logical decoding

# Connection limits
max_connections = 200
```

## Verifying After Startup

```bash
# In-container check — should show '*' if correctly configured
docker compose exec postgres01 psql -U postgres -c "SHOW listen_addresses;"

# Host-side connectivity test
PGPASSWORD=... psql -h 127.0.0.1 -p 5432 -U postgres -c "SELECT 1;"
```

## Related
- `postgres-schema-design` — schemas, RLS, roles, migrations
- `pipeline-debugging` / `local-pipeline-debugging` — check the data store before changing code

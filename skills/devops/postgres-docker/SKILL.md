--- Full content (truncated) ---
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

**The official Docker Postgres entrypoint** normally sets `listen_addresses = '*'` during container initialization (by appending it to the default `postgresql.conf`). When you bypass the PGDATA config by providing a custom `config_file` v
... [truncated]
--- End skill ---
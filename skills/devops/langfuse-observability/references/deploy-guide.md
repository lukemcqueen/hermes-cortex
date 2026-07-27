# Langfuse + ClickHouse Deployment Guide

This reference documents the full deployment, config, and troubleshooting for
the self-hosted Langfuse stack used with Hermes Agent. The canonical compose
file and XML configs live in `hermes-cortex/deploy/`.

## File Structure

```
deploy/
├── docker-compose.langfuse.yml      # Main compose file (copy to ~/langfuse/docker-compose.yml)
├── clickhouse-config.d/
│   ├── 01-log-level.xml             # Reduces log level to warning
│   ├── 02-low-memory.xml            # Thread pool + log table tuning
│   └── 03-profile-defaults.xml      # Per-query limits in users.d/
└── README-langfuse-clickhouse.md    # Full step-by-step guide
```

## Where Config Files Mount

| File | Mount Target | Purpose |
|------|-------------|---------|
| `01-log-level.xml` | `/etc/clickhouse-server/config.d/` | Server-level: reduce logging |
| `02-low-memory.xml` | `/etc/clickhouse-server/config.d/` | Server-level: tune thread pools |
| `03-profile-defaults.xml` | `/etc/clickhouse-server/users.d/` | Profile-level: per-query limits |

## Critical: File Permissions

ClickHouse runs as non-root inside the container. Config files MUST be 644:

```bash
chmod 644 ~/langfuse/clickhouse-config.d/*.xml
```

600 causes `Access to file denied: /etc/clickhouse-server/config.d/*.xml`
and ClickHouse enters a restart loop.

## Critical: ClickHouse 25.5 SIGSEGV Bug

Reducing more than 2 background pool settings simultaneously crashes with
SIGSEGV (exit 139) or exit code 36. Only two settings are safe to reduce:

- `background_pool_size=13` (floor 13; ≤12 crashes)
- `background_schedule_pool_size=16` (default 512 — biggest savings)

Do NOT reduce any other pool settings — they trigger the crash when combined
with the above. The `max_thread_pool_size` / `thread_pool_queue_size` must
remain at defaults (10000).

## Profile Defaults in users.d/

Per-query defaults (`max_threads=2`, `max_memory_usage=500MB`,
`max_block_size=4096`) live in `03-profile-defaults.xml` mounted at
`/etc/clickhouse-server/users.d/` — NOT config.d/.

## Restart Procedure

`docker compose restart` does NOT re-read env vars or config files.
Always use:

```bash
cd ~/langfuse
docker compose down
docker compose up -d
```

## Image Tags

| Service | Tag |
|---------|-----|
| langfuse-web | `langfuse/langfuse:3.200.0` |
| langfuse-worker | `langfuse/langfuse-worker:3.200.0` |
| ClickHouse | `clickhouse/clickhouse-server:25.5-alpine` |
| PostgreSQL | `postgres:16-alpine` |
| Redis | `redis:7-alpine` |
| MinIO | `minio/minio:latest` |

**Version matters for OTLP support.** Langfuse server MUST be v3.200.0+ to
expose the OTLP HTTP endpoint at `/api/public/otel/v1/traces`. Older versions
(v3.1.0) lack this endpoint, causing the Python SDK v4's OTel-based trace
export to fail silently with `Failed to export span batch code: 404`.
Always check the version after upgrade:

```bash
curl -s http://localhost:3000/api/public/health
# → {"status":"OK","version":"3.200.0"}
```

## Hermes Setup via cortex-setup-langfuse.sh

The repo's setup script at `ops/scripts/cortex-setup-langfuse.sh` automates:
- Copying docker-compose.yml and config files
- Generating all required secrets (.env)
- Creating a Langfuse API key pair in Postgres
- Wiring Hermes env vars
- Installing the langfuse Python SDK
- Enabling the observability plugin

Usage:
```bash
bash ops/scripts/cortex-setup-langfuse.sh            # generate + wire
bash ops/scripts/cortex-setup-langfuse.sh --start    # generate + docker compose up
```

## Only These Env Vars Matter

The Hermes Langfuse plugin only reads these vars from `~/.hermes/.env`:

```
HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-<hex>    # or LANGFUSE_PUBLIC_KEY
HERMES_LANGFUSE_SECRET_KEY=sk-lf-<hex>    # or LANGFUSE_SECRET_KEY
HERMES_LANGFUSE_BASE_URL=http://localhost:3000  # or LANGFUSE_BASE_URL
HERMES_LANGFUSE_ENV=local
HERMES_LANGFUSE_RELEASE=v1
HERMES_LANGFUSE_SAMPLE_RATE=1.0
```

All other `_ENABLED=true` vars from earlier versions are inert — do not add them.

## Common Issues Quick Reference

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| ClickHouse crash loop | Config files `600` | `chmod 644 *.xml` |
| ClickHouse SIGSEGV | Too many pool settings reduced | Keep only 2, restore rest to defaults |
| No traces in Langfuse | Plugin not enabled or not on new session | Enable + `/reset` |
| SDK fails to export (404) | Langfuse server too old (< v3.200.0) | Upgrade images, `down && up -d` |
| Langfuse API 401 | Wrong API key | Regenerate key pair |
| Worker silent | Post-ClickHouse migration restart needed | Restart worker container |
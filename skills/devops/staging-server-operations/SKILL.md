---
name: staging-server-operations
description: "Safe operational practices for Docker-based staging servers — volume management, change verification, and database recovery patterns."
version: 1.19.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [docker, staging, recovery, volumes, operations]
---

# Staging Server Operations

This skill covers the recurring maintenance operations for the client staging
server: hermes-cortex pull-and-integrate, Docker volume management, cron
auditing, database recovery, and change verification.

## Principle: No Cutting Corners

The user has been emphatic: **implement everything from the repo — do not cut corners.**
A checklist item that says "skip if laborious" is permission to fail. When a task has 9
items and you do 7, the 2 you skipped will surface as drift, then as debt, then as fire.
Implement every step, verify every outcome. If a step can't be completed, escalate it —
don't silently skip it.

## Core Operations

### 1. Pull and integrate hermes-cortex

```bash
cd ~/hermes-cortex
git pull --ff-only origin main
bash ops/scripts/cortex-update.sh
python3 ops/scripts/manage/cortex-doctor.py --quiet
```

### 2. Docker volume management

Volumes hold the only state that matters (databases, uploads). Rules:
- **Never `docker volume rm` without checking what's inside** — `docker run
  --rm -v <vol>:/v alpine ls /v` first.
- **Name volumes explicitly** in compose — anonymous volumes drift on re-create.
- **Backup before destructive ops** — `docker run --rm -v <vol>:/data -v
  $(pwd):/backup alpine tar czf /backup/<vol>-$(date +%F).tgz /data`.

### 3. Cron auditing

- List crons: `cronjob action=list`
- Every cron must have a fleet prefix (`agent-` / `orch-` / `local-`) and be
  present in its installer's uninstall array (the doctor's truth source).
- A cron in the create section but missing from the uninstall array silently
  escapes doctor validation — fix before it fails unnoticed.

### 4. Database recovery

```bash
# Safe restore pattern (Postgres example)
# 1. Stop the app container so it can't write during restore
docker compose stop app
# 2. Restore from the latest backup
docker exec -i <db-container> psql -U postgres < backup.sql
# 3. Verify row counts / checksums BEFORE starting the app
docker exec -i <db-container> psql -U postgres -c "SELECT count(*) FROM ..."
# 4. Start the app and confirm health
docker compose start app && curl -sf http://localhost:PORT/health
```

## Change Verification

Every change ends with verification, not assumption:

```bash
# After a compose change
docker compose config --quiet && docker compose up -d && docker compose ps

# After a config change
curl -sf <health-endpoint> && echo OK

# After a DB change
<query that exercises the changed path>
```

## Pitfalls

- ❌ **Skipping "laborious" checklist items** — they surface as drift later.
- ❌ **Anonymous volumes** — data is lost on `docker compose down -v`.
- ❌ **Restoring over a live app** — the app writes during restore, corrupting it.
- ❌ **Unverified claims** — "should be fine" is not a verification. Show output.

## Related
- `server-administration` — daily health checks and admin mindset
- `postgres-docker` — Postgres-in-Docker specifics
- `docker-management` — general Docker operations

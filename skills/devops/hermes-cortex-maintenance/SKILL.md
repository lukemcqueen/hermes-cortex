---
name: hermes-cortex-maintenance
version: 1.36.0
category: devops
description: >-
  Maintain an installed Hermes Cortex instance — update both the upstream
  Hermes Agent and the cortex repo layer, merge diverged histories, sync
  skills safely, and troubleshoot common issues. Covers the dual-update
  workflow (hermes update + cortex-update.sh), encrypted brain data backup,
  mycortex import, and recovery techniques.
---

# Hermes Cortex Maintenance v1.36.0

> **Maintaining your Hermes Cortex install** — pulling upstream changes,
> updating mycortex, syncing skills, and recovering when things go wrong.

## Prerequisites

- Hermes Cortex installed at `~/hermes-cortex/`
- Bun at `~/.bun/bin/bun`
- mycortex at `~/.bun/bin/mycortex`
- Ollama running as a systemd user service (or equivalent)

## Daily Auto-Update Timer (3am)

Hermes Cortex includes a **daily auto-update timer** that replaces all
standalone maintenance cron jobs.

### Install the timer

```bash
# Copy the systemd user unit + timer
cp ~/hermes-cortex/ops/install/hermes-cortex-update.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes-cortex-update.timer
```

Verify it's scheduled:

```bash
systemctl --user list-timers | grep hermes-cortex-update
```

## Dual-Update Workflow (manual)

### 1. Update upstream Hermes Agent

```bash
hermes update --yes
```

### 2. Update the cortex repo layer

```bash
cd ~/hermes-cortex
git pull --ff-only origin main
bash ops/scripts/cortex-update.sh
```

### 3. Merge diverged histories (if pull fails)

If `git pull` fails with diverged branches:

```bash
git fetch origin
git log --oneline HEAD..origin/main | head    # what's new upstream
git log --oneline origin/main..HEAD | head    # what's local-only
git merge origin/main                          # or: git rebase origin/main
# Resolve conflicts, then re-run cortex-update.sh
```

## Encrypted Brain Data Backup

Back up the brain data directory with encryption before major changes:

```bash
BACKUP_DIR=~/backups
mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/brain-$(date +%F).tgz" ~/brain
# If encrypted-at-rest storage is required, use gpg/age:
gpg --symmetric --cipher-algo AES256 "$BACKUP_DIR/brain-$(date +%F).tgz"
```

Restore:

```bash
tar xzf "$BACKUP_DIR/brain-<date>.tgz" -C ~
# or first: gpg --decrypt <file> | tar xz -C ~
```

## mycortex Import

```bash
# Import brain pages into mycortex
cd ~/brain && mycortex import --recursive . 2>&1 | tail -5
# Verify
mycortex search "test query" | head
```

## Langfuse cost tracking (3.206+) — pricing tiers, not legacy columns

> **User directive (2026-08-11):** consult the repo guidance FIRST for any
> Langfuse/ClickHouse work — `~/hermes-cortex/ops/install/deploy/README-langfuse-clickhouse.md`,
> `docs/troubleshooting.md`, `deploy/patches/` — before reverse-engineering
> the running containers. Caveat: `docs/troubleshooting.md` §23's
> `INSERT INTO models (..., input_price, output_price, ...)` is stale for
> 3.206+ — it produces no cost. Use the pricing-tier recipe below.

Cost is NOT computed from legacy `models.input_price`/`output_price` columns in Langfuse 3.206+. The ingestion worker reads the `prices` + `pricing_tiers` tables. A model inserted with only the legacy columns yields `cost_details = {}` and `total_cost = NULL` — **silently, no error**. Recipe (prices are per-token USD; DeepSeek V4 Flash = $0.14/1M in, $0.28/1M out → 0.00000014 / 0.00000028):

1. `INSERT INTO public."models"` (project_id NULL = global) with match_pattern like `(?i)^(deepseek-v4-flash)$`
2. `INSERT INTO public.pricing_tiers` — id = `<model_id>_tier_default`, name 'Standard', is_default true, priority 0, conditions `'[]'::jsonb`
3. `INSERT INTO public.prices` — usage_type `input`/`output` ONLY (never a `total` row — double-counts when usage carries input+output+total)
4. Clear Redis model-match cache (`model-price-tiers:*` keys) + `docker restart langfuse-langfuse-worker-1` — a cached NOT_FOUND token survives worker restarts
5. Backfill existing rows via ClickHouse `ALTER TABLE observations UPDATE cost_details = map(...), total_cost = ...` (async mutation; rows with `usage_details = {}` correctly stay NULL)
6. Verify via ClickHouse (`WHERE name='cost-verify3'`), NOT the API list endpoint (loose trace_id filtering returns your own live session's rows)

API field names in 3.206+: `costDetails`, `calculatedTotalCost` — NOT legacy `totalCost`. `/api/public/traces` requires `fromTimestamp` in 3.207+ (400 `InvalidRequestError` without it). Full SQL and the docker-compose sync recipe: `references/langfuse-cost-tracking-pricing-tiers.md`.

## Troubleshooting Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `cortex-update.sh` purges the governance lock | Known side effect (Pitfall 2) | Re-acquire with `begin_change`; score pending cycles first |
| Skills not deploying | Stub guard blocked repo stub → deployed full | Restore full skill content first |
| Ollama cold-start slow | Model unloaded after idle | `OLLAMA_KEEP_ALIVE >= 5m` in the systemd unit |
| Doctor checksum mismatch | SOURCE header adds 3 lines to deployed files | Use `_content_md5()` (strips header) |
| Gateway restart needed after plugin change | File-on-disk ≠ change-live | Restart session/gateway, verify the change is loaded |

## Recovery Techniques

- **Corrupted deployed copy** → re-run `cortex-update.sh` (it re-syncs from repo)
- **Stuck governance lock** → never force-clear without `end_change` first;
  score the cycle, then `end_change`, then force-clear only if it rejects
- **Missing skill content** → restore from the bus archive or official registry
  (see the skill-restoration workflow)

## Related
- `hermes-cortex` — install/configure guide
- `cortex-preflight` — pre-change checks and deploy pitfalls
- `hermes-recovery` — disaster recovery
- `doc-freshness` — keeping AGENTS.md/SOUL.md current

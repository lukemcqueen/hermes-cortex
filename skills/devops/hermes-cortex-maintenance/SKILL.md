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
- mycortex at `~/.hermes-cortex/scripts/mycortex`
- Ollama running as a systemd user service (or equivalent)

## Daily Auto-Update Timer (3am)

Hermes Cortex includes a **daily auto-update timer** that replaces all
standalone maintenance cron jobs.

### Install the timer

```bash
# Install via cortex update cron script
bash ~/hermes-cortex/ops/scripts/install/install-cortex-update-cron.sh
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
# Sync brain pages into mycortex
cd ~/brain && mycortex sync --dir . 2>&1 | tail -5
# Verify
mycortex search "test query" | head
```

## Langfuse cost tracking (3.206+) — pricing tiers, not legacy columns

> **User directive (2026-08-11):** consult the repo guidance FIRST for any
> Langfuse/ClickHouse work — `~/hermes-cortex/ops/install/deploy/README-langfuse-clickhouse.md`,
> `docs/troubleshooting.md`, `deploy/patches/` — before reverse-engineering
> the running containers. Caveat: the `docs/troubleshooting.md` entry *"Langfuse costs show $0.00"*'s
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
| Gateway restart needed after plugin change | File-on-disk ≠ change-live | Restart session/gateway, verify the change is loaded. The deploy cannot always read the gateway's start time and then FAILS CLOSED as restart-required even when nothing changed — treat it as pending, hand the restart to the host operator (it must run from a shell OUTSIDE the gateway process), and do not loop retrying or edit the deployed copy |

## Stranded skills — the DEPLOYED copy can be NEWER than the repo

`cortex-update.sh` refuses to overwrite a deployed skill whose copy is newer than the repo source,
and the doctor reports `⚠️ Skill drift: <path>`. This is usually not drift but a LESSON: the lesson
pipeline writes into the DEPLOYED copy, so the deployed side often carries knowledge the repo does
not have. Never resolve it by copying repo → deployed, and never by deleting the deployed copy.

```bash
python3 ~/hermes-cortex/ops/scripts/manage/reconcile-stranded-skills.py          # report first
python3 ~/hermes-cortex/ops/scripts/manage/reconcile-stranded-skills.py --apply  # pure supersets only
```

- The report classifies each file. A PURE SUPERSET can be applied mechanically; **REVIEW** means the
deployed copy also DROPS lines, and those must be read before you take the deployed side:
`diff -u <repo-path> <deployed-path>`. A paragraph that was rewritten or condensed reports a drop
whose content is still present in another form — that is the expected answer. A drop of content
that exists NOWHERE on the deployed side is a real regression to hand-merge, not to accept.
- Land the deployed content as its OWN commit, byte-identical, BEFORE adding any edit of your own —
mixing them makes the reconciliation unreviewable.
- **Assert, don't eyeball.** After copying, verify `sha256` equality on BOTH sides, and parse the
copied frontmatter for a non-empty `description` FIRST: a skill whose deployed copy lost its
description becomes UNLOADABLE, and every session silently stops seeing it. Refuse the copy rather
than land that.
- Then deploy (`cortex-dogfood.sh --force`) and confirm the doctor's skill-drift line is ✅.

## Recovery Techniques

- **Corrupted deployed copy** → re-run `cortex-update.sh` (it re-syncs from repo)
- **Stuck governance lock** → never force-clear without `end_change` first;
  score the cycle, then `end_change`, then force-clear only if it rejects
- **Abandoned PENDING cycle after an interrupted session** → score it honestly
  (`feedback_accept` with zeros + a note that the work was never done). The doctor
  FAILs on unscored PENDING cycles; scoring zero is the honest close and clears it.
  Do NOT invent scores to avoid reporting zeros — an interrupted task carried no
  completed work, and the PENDING cycle is how the doctor surfaces it.
- **Missing skill content** → restore from the bus archive or official registry
  (see the skill-restoration workflow)

## Related
- `hermes-cortex` — install/configure guide
- `cortex-preflight` — pre-change checks and deploy pitfalls
- `hermes-recovery` — disaster recovery
- `doc-freshness` — keeping AGENTS.md/SOUL.md current

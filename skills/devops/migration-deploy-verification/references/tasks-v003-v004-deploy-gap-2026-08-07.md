# Session trace — tasks v003/v004 deploy-map gap (2026-08-07)

## Bug report received (partially stale)

Root-cause chain claimed:
1. Live DB `task_upsert` still had old `WHEN 'cancelled' THEN 'done'` derivation
   → violates `tasks_check` (only permits 'done' with status='completed').
2. cortex-update.sh registered only v001+v002 (lines 215-216); v003/v004
   missing from the deploy map; migrate.py (scanning the deployed dir) never
   applies them. "DB stuck at version 2."

## What verification actually showed

- **Live DB was ALREADY at version 4** on this host:
  `schema_version` rows 1-4, v3 applied 06:17:58 UTC, v4 06:19:44 UTC,
  `applied_by=mycortex` — both BEFORE the commit that added the files
  (commit 544b9046 at 06:26 UTC). Someone hand-applied the SQL (or ran
  migrate.py against the repo dir) 9 minutes before committing.
- Live function derivation was already the NEW one
  (`WHEN 'completed' THEN 'done'`, cancelled → NULL).
- Deployed schema dir `~/.hermes-cortex/services/tasks/schema/` had ONLY
  v001+v002 — the deploy-map gap was real.
- Deployed migrate.py == repo (only a blank-line diff) — the runner was fine;
  it just never saw v003/v004 because link 2 (deploy map) was missing.

**Lesson:** claim #1 was stale locally (hand-migrated), claim #2 was the
durable fleet-wide bug. Verify the live DB before trusting the narrative.

## Diagnosis commands that worked

```bash
# Deploy map (link 2):
grep -n "v00[0-9]" ops/scripts/cortex-update.sh
# → only v001, v002 for tasks; mycortex had v002/v003/v004 registered (sibling
#   service registered ALL its migrations — the pattern to copy)

# Deployed dir (link 3):
ls -la ~/.hermes-cortex/services/tasks/schema/

# Live DB (link 5):
docker exec -i mycortex-postgres psql -U mycortex -d mycortex -c \
  "SELECT version, applied_at, applied_by FROM tasks.schema_version ORDER BY version;"

# Function state:
docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A \
  -c "SELECT pg_get_functiondef('tasks.task_upsert'::regproc);" | grep -A 8 "v_column :="
```

Note: `LIKE '%WHEN ''cancelled'' THEN ''done''%'` false-negatives on
multi-space formatting — grep the actual function def rather than pattern-match
with exact single spaces.

## The fix

Added to `ops/scripts/cortex-update.sh` after the v002 line:

```bash
register "ops/services/tasks/schema/v003__cancel-column-null.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v003__cancel-column-null.sql"
register "ops/services/tasks/schema/v004__cancel-update-column.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v004__cancel-update-column.sql"
```

Also fixed stale "v001+v002" comments in `tests/test-tasks-schema.sh` (header
+ AC-L1-1 echo) → "v001–v004".

## Verification evidence

- L1 hermetic test: **35/35 passed** on scratch DB `tasks_test`, including
  "update→cancelled derives column=NULL (regression v004)".
- Live write-probe: `task-db.py add` → `update <id> --status cancelled`
  → psql row check: `cancelled||` (column NULL, no CHECK violation).
  Cleanup: `task-db.py save-end` archived it; probe rows deleted from
  `tasks.task_archive`.
- Re-deploy attack test: ran cortex-update.sh twice; v003/v004 persisted in
  the deployed dir; migrate.py reported "version 4 — no-op".
- A4 adversarial gates passed on both changed files (cortex-update.sh is an
  enforcement script → A4; tests/ → A4). Pre-push gate required
  `adversarial-verifier` skill loaded.
- Doctor: 303 pass · 2 warn · 0 fail (warns pre-existing: AGENTS.md size,
  unrelated cron run-evidence).
- Commit cc048173 pushed to origin/main.

## Governance notes

- `begin_change` → survey → patch → deploy → verify → commit → push →
  `cycle_query` → `feedback_accept` (cycle 2160, MOVE_ON) → `end_change`.
- Pre-commit hook auto-creates its own cycle; score any PENDING cycles from
  cycle_query before end_change.

## Pre-existing issue noticed (not this fix)

cortex-update printed `Failed to update job: Cron workdir must be an absolute
path (got 'false')` from install-orch-crons.sh — a separate workdir bug in the
cron installer, worth its own cycle. Flagged to Luke.

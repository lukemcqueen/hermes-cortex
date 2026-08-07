---
name: migration-deploy-verification
description: "Use when a repo migration is missing from the live DB."
version: 1.0.0
category: devops
platforms: [linux, macos]
---

# Migration Deploy Verification

Versioned SQL migrations in this fleet deploy through a chain of FIVE
independent links. Any one link missing silently breaks the whole chain —
the repo can carry the fix while every host keeps the old broken function.

```
ops/services/<svc>/schema/vNNN__*.sql        (1) repo file committed
  → register() line in cortex-update.sh      (2) deploy map
  → ${CORTEX_DEPLOY_HOME}/services/<svc>/schema/vNNN__*.sql   (3) deployed dir
  → migrate.py (globs the DEPLOYED dir)      (4) migration runner
  → <svc>.schema_version row                 (5) live DB applied
```

## The critical fact: migrate.py scans the DEPLOYED dir, not the repo

`ops/services/<svc>/migrate.py` discovers migrations with
`schema_dir.glob("*.sql")` where schema_dir is its **sibling deployed**
directory (`~/.hermes-cortex/services/<svc>/schema/`). A migration committed
to the repo but missing its `register()` line never reaches the deployed dir,
so the version-gated runner NEVER applies it — even though the file "exists"
in the repo and tests pass against the repo path.

## Verify all 5 links (never stop at link 1)

```bash
# 1. Repo has the migration?
ls ops/services/<svc>/schema/vNNN__*.sql

# 2. Deploy map has it?  (MISSING = the bug)
grep -n 'register.*vNNN' ops/scripts/cortex-update.sh

# 3. Deployed dir has it?
ls ~/.hermes-cortex/services/<svc>/schema/

# 4. Runner sees it — run from the DEPLOYED path, not the repo:
python3 ~/.hermes-cortex/services/<svc>/migrate.py   # expect "up to date (version N)" or applies

# 5. Live DB applied it?
docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A \
  -c "SELECT version, applied_at, applied_by FROM <svc>.schema_version ORDER BY version;"
```

## Masking trap: hand-migrated DB hides the gap

`schema_version.applied_by=mycortex` + `applied_at` EARLIER than the commit
timestamp = someone applied the SQL to the DB by hand (or pointed migrate.py
at the repo dir). The local host LOOKS fixed ("schema_version is at N!"), but
every other host is still broken — the deploy map was never updated. A
"root cause confirmed" report can be partially stale: **verify the live DB
before trusting the narrative**, then fix the durable gap (link 2).

Real case 2026-08-07: tasks v003 (cancelled→column NULL) and v004 (ON
CONFLICT column preservation) sat in the repo with their L1 test while
cortex-update.sh shipped only v001+v002. Local DB was hand-migrated 9
minutes before the commit; fleet hosts stayed at version 2 with the broken
`WHEN 'cancelled' THEN 'done'` derivation (any cancel → tasks_check
violation). The deploy-map gap was the real remaining bug.

## Fix pattern (orchestrator lane)

1. Add the missing lines to `ops/scripts/cortex-update.sh`:
   ```bash
   register "ops/services/<svc>/schema/vNNN__foo.sql" "${CORTEX_DEPLOY_HOME}/services/<svc>/schema/vNNN__foo.sql"
   ```
2. Deploy via the sanctioned invocation: `bash ~/hermes-cortex/ops/scripts/cortex-update.sh`
3. Confirm migrate.py on the already-migrated host reports a no-op (idempotent):
   `tasks schema up to date (version N) — no-op`
4. Commit + push. Every host's next cortex-update deploys the files and
   migrate.py takes their DB to the top version automatically.

## Verification pattern (prove it, then attack the premise)

- **Hermetic L1 test** on a scratch DB (`bash tests/test-tasks-schema.sh`
  style): fresh DB v001→vNNN, assert `schema_version == count of repo v*.sql
  files`, assert the fixed behaviour (e.g. cancelled→column NULL).
- **Live write-probe** through the real CLI: create → update status → verify
  row state via psql → clean up (CLI save-end archives; delete the probe row
  from the archive table).
- **Re-deploy attack test**: run cortex-update.sh TWICE, confirm the new
  files persist in the deployed dir — registered files survive re-deploys,
  one-off manual copies get dropped/overwritten.
- **A4 adversarial gates** on cortex-update.sh (enforcement script) and any
  tests/ file before push.

## Trigger

Use this skill when:
- A migration "exists" but the DB schema_version is stuck below it
- Adding/renumbering a migration (walk the chain before committing)
- A bug report claims the "fix is in the repo" but the live DB still misbehaves
- Any "committed but not deployed" symptom for schema files

## References

- `references/tasks-v003-v004-deploy-gap-2026-08-07.md` — full session trace: masking, diagnosis, fix, verification evidence

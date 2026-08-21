---
name: sweep-verification
version: 1.0.0
category: devops
description: "Verify a decommission sweep removed every file and ref."
author: Esther
license: MIT
platforms: [linux, macos]
---

# Sweep Verification — proving a removal is COMPLETE

Use when asked to "double check / make sure X is completely removed" after a
rename or decommission sweep (gbrain→mycortex, legacy-brain decommission,
service renames). Performing the sweep is `rename-sweep`'s job; THIS skill is
the independent verification pass that finds the leftovers the sweep missed.

## Surface checklist — sweep ALL of these, in this order

1. **Repo tracked content**: `git grep -il <token> -- .` (count + list)
2. **Repo tracked file NAMES**: `git ls-files | grep -i <token>`
3. **Repo worktree** (incl. untracked): `grep -rli` excluding `.git/__pycache__/.venv/node_modules`, plus `find . -iname '*<token>*'`
4. **Deployed tree** `~/.hermes-cortex`: grep excluding logs/__pycache__/backups. Deploy never prunes → stale files linger here (see pitfall 1)
5. **~/.hermes live config**: `cron/jobs.json` (0 expected), `cron/scripts`, `plugins/`, `config.yaml`, `memories/`, `SOUL.md`, `AGENTS.md`, `skills/` (deployed copies), **`agent-profiles/*/SOUL.md`** (profile templates seed other hosts' SOULs — a stale ref here ships to the fleet)
6. **~/.hermes historical** (count, do NOT delete): logs, `sessions/`, `state-snapshots/`, `cron/output/` (old run records)
7. **~/.hermes-cortex/data + state**: `loop-events/*.jsonl`, `loop-governance.db` (audit trail — task IDs legitimately mention the token), `state/` (dead state files with old keys, e.g. agent-health-data.json — check readers before deleting)
8. **~/brain**: lesson files (historical knowledge — keep)
9. **Tasks DB**: `SELECT ... WHERE content ILIKE '%<token>%' AND status IN ('pending','in_progress')` (active rows should be 0)
10. **Bus archives** (primary host): count of subjects/bodies mentioning token (historical messages — keep)

## Classification — the load-bearing rule

Every hit is one of three buckets; treat them differently:

| Bucket | Examples | Action |
|---|---|---|
| **LIVE** | deployed scripts, cron, config, SOUL profiles, registry/health-vector keys, stale deployed files, dead state files | **Fix/remove now** |
| **HISTORICAL** | brain lessons, dated skill event records, logs, session dumps, backups (dumps, deploy-backups, scripts-unique-backup-*), loop audit trail, bus archives, curator metadata | **Keep — deleting destroys the fleet's record** (the file itself may even say "it IS the record") |
| **CREDENTIAL** | `.env` values whose NAME contains the token (e.g. `CORTEX_BUS_PG_PASS=gbrain_pg_pass`) | **Flag only — never touch a live credential mid-task**; rotation is a deliberate multi-host change |

The audit's own files classify stale refs as "historical doc/log/skill text →
leave as-is (it IS the record)". Deleting history to reach zero violates the
keep-logs precedent and permanently destroys knowledge that exists nowhere
else (many such files are deployed-only, never in git).

## Pitfalls (all hit in real sweeps)

1. **Deploy registers but NEVER prunes.** Files removed from the repo stay
   deployed forever: `~/.hermes-cortex/services/mycortex/import-gbrain.py`,
   stale skill `references/*.md`, old `__pycache__/*.pyc`. Find them with
   `comm -13 <(ls repo-dir | sort) <(ls deployed-dir | sort)` — deployed-only
   extras are stale unless proven otherwise. Delete stale deployed files even
   though git status stays clean.
2. **Guard tests must self-exclude.** A `test_no_<token>_refs` test that runs
   `git grep -il <token>` fails on its OWN source. Fix:
   `git grep -il <token> -- . ':(exclude)tests/<guard-file>.py'`.
3. **Stale state files carry old keys.** Dead state JSON (mtime weeks old, no
   readers) can still hold old service keys. Verify no reader
   (`grep -rln "<name>" scripts/`) before deleting.
4. **Profile copies seed the fleet.** `~/.hermes/agent-profiles/<agent>/SOUL.md`
   is a template merged into that agent's SOUL — a stale ref there reaches
   another host. Check ALL profiles, not just your own.
5. **Post-sweep, retrieval goldens drift.** A mass content rewrite changes FTS
   ranking: parity/known-answer fixtures fail on ranking (expected docs still
   exist; new top hits are relevant). Refresh the stale golden with evidence
   and a note — it's drift from an intentional change, not a regression.
6. **Validation tests exercise the DEPLOYED copy.** L2 fleet tests
   (test-task-fleet.sh, test-mycortex-schema.sh) run against
   `~/.hermes-cortex/scripts/`, not the repo. Unit tests pass against repo
   source while L2 fails → the fix isn't deployed. Run `cortex-update.sh`
   (ops/scripts/) before L2, then re-run.

## Steps

1. Begin governance cycle (terminal needs a lock).
2. Run the surface checklist (batch greps; count AND list).
3. Fix/remove every LIVE hit; leave HISTORICAL; flag CREDENTIAL in the report.
4. Re-verify: re-run the live-surface greps → 0.
5. Run the guard test (`pytest tests/test_repo_structure.py -q`) + full suite.
6. Post-sweep validation: run the component's own battery (e.g. mycortex:
   CLI doctor, sources/stats, schema battery, crons, parity fixture, doctor
   Deploy+Repo sync) to prove the component still works after the purge.
7. Report: verified-clean surfaces, what was removed, what was kept (counts),
   flagged items. Score + close cycle.

Session detail (gbrain sweep, 2026-08-21): `references/gbrain-sweep-2026-08-21.md`

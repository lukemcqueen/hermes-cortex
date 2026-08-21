# gbrain Sweep Verification — 2026-08-21 (Esther)

Session transcript for the gbrain→mycortex sweep verification: what was found
where, what was removed vs kept, and the numbers behind the classification
rules in the SKILL.md.

## Verified clean (zero gbrain)

- Repo tracked content — EXCEPT the guard test `tests/test_repo_structure.py`
  (intentional: it greps for the token and must mention it; self-excluded via
  `:(exclude)` pathspec)
- Repo tracked file names, untracked files, file names anywhere in worktree
- Deployed scripts: `orch-fleet-watchdog.py`, `orch-health-report.py`,
  `health-vector-push.sh` — all use `mycortex_sources_ok`
- Live cron: `~/.hermes/cron/jobs.json` (0), `cron/scripts` (0)
- `~/.hermes/plugins/`, `config.yaml`, `memories/`, `SOUL.md`, `AGENTS.md`
- Tasks DB active rows (pending/in_progress): 0
- `ops/scripts/cortex-update.sh` register map: 0

## Removed (LIVE leftovers)

| File | Why |
|---|---|
| `~/.hermes-cortex/services/mycortex/import-gbrain.py` | stale deployed orphan — repo stopped shipping it, nothing called it |
| `__pycache__/import-gbrain.cpython-311.pyc` (repo + deployed) | stale bytecode of the deleted module |
| `~/.hermes-cortex/state/agent-health-data.json` | dead Jul-15 state file (pre-sweep), no readers, held `"gbrain"`/`"gbrain_sources_ok"` keys |
| 6 stale skill reference files (hermes-cortex skill ×4: `gbrain-cron-maintenance.md`, `gbrain-npm-collision.md`, `gbrain-source-migration-export.md`, `pglite-lock-contention.md`; hermes-cortex-setup ×2: `gbrain-squatter.md`, `health-server-external.md`) | old skill versions the repo no longer carries |
| `~/.hermes/agent-profiles/titus/SOUL.md` line: "Ollama, gbrain, inbox" → mycortex | profile template seeds Titus's host SOUL |
| banner cache, pytest cache nodeids | regenerable |

## Kept (HISTORICAL, by design)

- 94 brain lesson files (July migration/debugging records — e.g. "check_services()
  checks for gbrain-autopilot.service but our service is named gbrain-sync.service")
- ~15 deployed skill knowledge files: dated event records (gbrain-reference-audit,
  fleet-migration-verification-ledger, gbrain-health-false-positive,
  gbrain-to-mycortex-2026-08-21) and the rename-sweep skill whose canonical
  worked example IS the purge. The audit file itself says historical skill text
  "IS the record — leave as-is". These are deployed-only, never in git — deleting
  destroys knowledge permanently.
- Logs, session dumps (`~/.hermes/sessions/`), state snapshots, cron outputs,
  loop-events jsonl + loop-governance.db (audit trail — pre-commit task IDs
  like "purge-all-gbrain-references" legitimately carry the token)
- Backups: 2 old dumps (`gbrain_public_20260802.dump`,
  `gbrain-migration-20260805.dump`), `scripts-unique-backup-20260802/`,
  `deploy-backups/*.bak` (rollback safety)
- Bus archives: 34 subjects mentioning gbrain (historical messages)
- Skill curator metadata (`.usage.json`, `.curator_ledger.jsonl`,
  `.hub/index-cache`), `state/remediate-seen.txt` (dedup watermark)

## Flagged (CREDENTIAL)

- `.env` line: `CORTEX_BUS_PG_PASS=gbrain_pg_pass` — the Postgres password's
  NAME is a gbrain remnant. Live credential: rotating means primary DB + all
  6 hosts' .env in sync. Flag, never touch mid-task.

## How the surfaces were found

- `git grep -il gbrain` (tracked), `git ls-files | grep -i` (names),
  `find . -iname '*gbrain*'` (any file name), `grep -rli --exclude-dir=...`
  per tree (repo worktree, `~/.hermes-cortex`, `~/.hermes`, `~/brain`)
- Category rollups via `sed 's|<prefix>||' | cut -d/ -f1 | sort | uniq -c`
- Deployed-only skill extras: `comm -13 <(ls repo/refs | sort) <(ls deployed/refs | sort)`
- Key-consistency: `grep -n "sources_ok"` across registry template + watchdog
  + health report + push script (rename drift breaks fleet health aggregation)

## Follow-up: post-sweep mycortex validation (all green)

Container healthy :15432 · CLI doctor (schema v4, 6 RLS policies, all synced) ·
3 sources / 1861 pages / 31755 chunks / 0 failed · search live · schema battery
15/15 · all mycortex crons registered · brain dirs non-empty · watchdog +
health-report rc=0 · parity 100%/100% after HC-008 golden refresh (content
rewrite shifted FTS ranking — refreshed with evidence, committed `240d0628`) ·
plugin enabled · doctor 323 pass / 0 fail, Deploy+Repo sync clean.

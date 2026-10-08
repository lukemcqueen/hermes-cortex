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
rename or decommission sweep (legacy-brain → mycortex, service renames).
Performing the sweep is `rename-sweep`'s job; THIS skill is
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
11. **Ignore rules and VCS config**: `grep -n <token> .gitignore` plus `.git/info/exclude`
    and any tracked ignore file. A rule matching a path you REMOVED is itself a leftover
    reference, and a worse one than the others — see pitfall 10.

## Classification — the load-bearing rule

Every hit is one of three buckets; treat them differently:

| Bucket | Examples | Action |
|---|---|---|
| **LIVE** | deployed scripts, cron, config, SOUL profiles, registry/health-vector keys, stale deployed files, dead state files | **Fix/remove now** |
| **HISTORICAL** | brain lessons, dated skill event records, logs, session dumps, backups (dumps, deploy-backups, scripts-unique-backup-*), loop audit trail, bus archives, curator metadata | **Keep — deleting destroys the fleet's record** (the file itself may even say "it IS the record") |
| **CREDENTIAL** | `.env` values whose NAME contains the token (e.g. `CORTEX_BUS_PG_PASS=<legacy>_pg_pass`) | **Flag only — never touch a live credential mid-task**; rotation is a deliberate multi-host change |

The audit's own files classify stale refs as "historical doc/log/skill text →
leave as-is (it IS the record)". Deleting history to reach zero violates the
keep-logs precedent and permanently destroys knowledge that exists nowhere
else (many such files are deployed-only, never in git).

## Pitfalls

**`git add -A` does NOT mean the file was added.** `*.log` is in `.gitignore`, so
a "committed execution log" was silently skipped and a commit message claimed a
file that did not exist — the audit caught it, not the author. Any sweep or
evidence artifact must confirm tracking from the tree, not from intent:
`git ls-tree --name-only HEAD <dir>` (or `git diff --cached --name-only` before
committing). Prefer the repo's existing artifact extension (`.txt` here) and check
`git check-ignore -v <path>` when a file mysteriously does not stage. (all hit in real sweeps)

1. **Deploy registers but NEVER prunes.** Files removed from the repo stay
   deployed forever: `~/.hermes-cortex/services/mycortex/import-<legacy>.py`,
   stale skill `references/*.md`, old `__pycache__/*.pyc`. Find them with
   `comm -13 <(ls repo-dir | sort) <(ls deployed-dir | sort)` — deployed-only
   extras are stale unless proven otherwise. Delete stale deployed files even
   though git status stays clean.
   - **Deleting a file without deleting its `register()` line is a doctor FAIL**
     (`Deploy source missing`). After the sweep, assert every registration still points
     at a real file: parse the `^register(?:_orch)?\s+"<source>"\s+"<dest>"` lines from
     `ops/scripts/cortex-update.sh` and stat each source path. One missing source means
     either a leftover line to drop or a file to restore — never leave it standing, and
     re-run the doctor (it exits FAIL, so the push is blocked too).
   - **Deployed SKILLS are preserved, not pruned.** A skill deleted from the repo stays
     deployed, and the next deploy reports it as a stale "deployed-only skill" instead of
     deleting it (the deploy cannot tell an orphan from a local skill someone depends on).
     The explicit cleanup must remove the deployed skill directory as well, or the
     warning — and the doctor's stale-skill WARN — reappears on every run.
1b. **Removing the artifact is not removing the FEATURE — revert the key that
   selects it.** A component wired by config (e.g. `cron.provider: <plugin>`) keeps
   pointing at something that no longer exists once its directory is deleted: the
   consumer falls back to its built-in default but logs a warning on every tick, and
   the user reads that warning as "that thing is still causing issues". Grep
   `~/.hermes/config.yaml` for the component name and drop the selecting keys
   (provider + its sub-blocks) in the same sweep.
1c. **Consumers are part of the sweep.** A component usually outlives itself in its
   readers — a watchdog that queries its DB, a report script that imports it, a cron
   manifest entry, an installer that re-creates it, a doctor check that asserts on it.
   Grep the repo for the artifact names and fix every consumer in the same pass; one
   left behind keeps firing (or re-creates the artifact at the next deploy), which is
   how a "removed" feature generates fresh alerts.
7. **The deletion set comes from a grep, not from memory.** Enumerate the names across
   the repo (`grep -rl`) AND the deployed tree first, then check dependents
   (`~/.hermes/cron/jobs.json`, `ops/install/cron-manifest.yaml`, installers, doctor
   checks, tests) before removing anything. Report the surviving mentions explicitly
   (dated reports, advisory docs) so the user can decide on those rather than
discovering them in a later grep.
8. **A destructive sweep is one APPROVED step, and consent is per-command.** A compound
   `git rm` of many paths (or one `rm -rf` over several artifact dirs) can trip the
   approval gate; if that prompt times out, NOTHING ran — do not retry it, do not reword
   it, do not reach the same outcome another way. Report the exact removal set plus the
   edit sites, and wait for an explicit go. Confirm the tree is untouched
   (`git status --porcelain`) so "nothing ran" is evidence rather than assumption.
9. **Do not hold a governance lock while you wait on the user.** A decommission spanning
   turns leaves the cycle's lock held, which blocks every peer session from taking one.
   Score the cycle you have (a low completeness score and a factual "inventory only,
   blocked on consent, no files changed" note is honest and correct), release it, and
   take a fresh lock for the actual removal.
10. **Removing a path but KEEPING its ignore rule makes its return invisible.** When a
   directory is deleted by design, delete the `.gitignore` rules matching it in the SAME
   sweep. While those rules remain, the directory can reappear and `git status` stays
   clean — so the recurrence you are verifying absence of is the one thing the ignore
   rule conceals, and the sweep reports "clean" over a directory that is back. Leave a
   one-line comment where the rules were, saying they were removed on purpose, so a
   future reader does not helpfully restore them. **Name directories by their FULL path
   when reporting**: a runtime directory and a same-named directory inside the repo
   differ by one leading dot, so "the directory came back" without the path reads as a
   claim about the runtime copy — which is correct and expected — and alarms the reader
   for no reason.

   **A removed directory can survive as an EMPTY SHELL — verify with `find`, not `git
   status`.** `git rm -r` deletes TRACKED files only, so a directory still holding an
   untracked file (a lock, a log, a state file) is left standing, and the worktree
   reports clean because the remainder is untracked — and if an ignore rule is also
   still in place, invisible on top of that. Confirm the removal with an explicit
   existence check after the sweep (`test -e <path>`, or the `search_files` tool with
   `target='files'`); a clean `git status` is not evidence the directory is
   gone. This is also why "it reappeared" can be the wrong diagnosis: a directory the
   sweep never actually emptied reads exactly like a directory something recreated.

   **Never wrap the removal in `try: rmdir(d) except OSError: pass`.** That construction
   swallows precisely the partial removal above: the loop finishes, the report says
   removed, and the directory is still there. Report what was removed from a POST-STATE
   check, never from the loop having run to completion.

   **Give the removal a check that FAILS on its return.** A one-off deletion is a
   snapshot; absence that nothing asserts is absence only until the next process
   recreates it. Add a check — doctor or CI — that PASSes when the path is absent and
   FAILs naming the offending entries when it is present (including whether the
   state/governance file inside it is back), and prove the check CAN fail by driving it
   against a temp fixture in every state. Then the recurrence reports itself instead of
   waiting for a hand audit.
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
   Deploy+Repo sync) to prove the component still works after the purge. When the
   sweep removed config, exercise the path that REPLACED it — e.g. after deleting a
   cron provider, run the scheduling surface (`hermes cron list`) and confirm no
   fallback warning, which is the only proof the default is really in charge.
7. Report: verified-clean surfaces, what was removed, what was kept (counts),
   flagged items. Score + close cycle.

Session detail (legacy-brain sweep, 2026-08-21): `references/legacy-brain-sweep-2026-08-21.md`

---
name: hermes-cortex-repo-deploy
version: 1.0.0
category: devops
description: "Use when committing to the hermes-cortex repo."
platforms: [linux, macos]
---

# Hermes Cortex Repo — Deploy & Push Gates

Workflow for landing changes in `~/hermes-cortex` (shared public repo). The
repo's own AGENTS.md governs governance mechanics; this skill carries the
deploy-order and manifest pitfalls that cost time when missed.

## Push sequence (gates run in this order)

1. `git pull --rebase origin main` — REQUIRES a clean tree. Peer/other-session
   unstaged changes block the rebase AND the push's built-in dogfood. Stash
   ONLY the specific peer files (name them explicitly, never `git stash` bare),
   rebase/push, then `git stash pop` immediately. Never stash, clean, or commit
   a peer's work.
2. `git push` runs a doctor gate — it fails on ANY doctor ❌. Most common
   blocker: `Deploy sync` / `Checksum: <file>` FAIL because the deployed copy
   predates the pushed commit. Fix by running `cortex-update.sh`, re-running
   the doctor (expect 0 fail), then retrying the push. Never bypass.
3. After the push lands, run `cortex-update.sh` once more so the deployed tree
   includes the just-pushed commit (the push gate's internal deploy can trail
   the newest commit).

## New shared module → register() entry in the SAME commit

A new module that an existing deployed script imports (e.g. a helper under
`cortex_doctor/`) must get its own `register()` line in `cortex-update.sh`,
placed next to its importer's. `register()` copies ONLY listed files — a
missing entry makes the next deploy break every importer with
`ModuleNotFoundError: No module named '<module>'` at the deploy's verification
step. Symptom to recognize in the deploy log; fix by adding the entry,
deploying, re-running the doctor.

## Cron manifest: create_cron vs uninstall arrays

- `parse_expected_crons()` (cortex_doctor/config.py) reads **create_cron**
  blocks, role-filtered (non-orch hosts exclude orch crons). Uninstall arrays
  are the CLEANUP list, not the expected list.
- When a cron moves from universal (`install-crons.sh`) to orchestrator-only
  (`install-orch-crons.sh`), KEEP its name in the universal uninstall array as
  a legacy-cleanup entry — non-orch hosts still need to uninstall the stale
  cron, and the doctor is unaffected. Drop orch-prefixed names that never had
  a universal create_cron.
- `fix-cron-duplicates.py --fix` aligns uninstall arrays to create_cron
  EXACTLY and strips legacy-cleanup entries. Do not run `--fix` blindly after
  adding one; either accept the warning or whitelist uninstall-only names in
  the tool first.
- After any manifest change: `bash -n <install script>`, run
  `fix-cron-duplicates.py` (no `--fix`) to check sync, deploy, run the doctor.

## Peer in-flight work

`git status` before staging. Modified files that aren't yours belong to a
concurrent session — leave them unstaged, commit only your files by explicit
path. The push-gate dogfood diffs the whole tree, so their in-flight edits
can trip doc-friendliness heuristics; coordinate rather than cleaning.

## Reversing your own wrong fix

If a just-pushed correction turns out to be the wrong direction (e.g. you
removed an uninstall-array entry that was serving legacy cleanup), supersede
it with a new commit in the same session — a known-wrong commit on main
propagates to every host on their next pull.

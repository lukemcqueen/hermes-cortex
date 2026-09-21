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

## Perpetually-dirty pipeline file + push races

`ops/install/deploy/nginx/blocked_ips.add` is rewritten by the
`agent-nginx-threat-pipeline` cron on every tick — it is *always* modified at
commit time, and the pipeline both stages it and pushes its own commits. So
on the hermes-cortex repo:

- Expect this file to block `git pull --rebase` ("Please commit or stash
them") on nearly every push. Stash just that path by name, rebase, pop.
- Expect the push itself to be raced: the pipeline can land a new
  `auto: block N suspect IPs` commit between your `pull --rebase` and your
  `push`, so the push is rejected as non-fast-forward. `git pull --rebase`
  again and retry the push — once it shows `A..B  main -> main` it has
  landed even if a later command in the same chain printed an earlier
  failure line. Verify with `git log --oneline -1 origin/main`.

## Reversing your own wrong fix

If a just-pushed correction turns out to be the wrong direction (e.g. you
removed an uninstall-array entry that was serving legacy cleanup), supersede
it with a new commit in the same session — a known-wrong commit on main
propagates to every host on their next pull.

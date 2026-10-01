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

1. `git pull --rebase origin main` — REQUIRES a clean tree. ANY unstaged
   change blocks the rebase AND the push's built-in dogfood — your own edits
   included, not just a peer's. Stash the specific blocking files by name
   (never `git stash` bare), rebase/push, then `git stash pop` immediately —
   pop your own files back FIRST so your edits are restored before the next
   step. Never stash, clean, or commit a peer's work, and never stage a
   file you did not edit.
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

## Cron scope/prompt change = three surfaces in one pass

Changing a cron's scope, prompt, or schedule touches three places; a partial
update leaves each layer contradicting the others:

1. **Live prompt** — `~/.hermes/cron/jobs.json`, updated via the cronjob tool
   (`action='update'`); installer edits never rewrite an existing job's
   prompt.
2. **Installer `create_cron` block** — the durable source for non-`local-`
   crons.
3. **Doc tables** — `docs/fleet-reference.md` AND `docs/cron-schedules.md`
   each carry one row per cron describing its scope. A `local-` cron has NO
   installer block, so its doc row is the repo's only record of the job's
   scope — commit the row update in the same push.

Verify the live prompt by reading it back out of jobs.json (the update
response shows only a truncated preview), grep both docs for the old scope
term to catch sibling rows, and fire one real run (`cronjob action='run'`)
so the scheduler's last_status reflects the new prompt.

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

## Doctor skill-drift: deployed newer than repo = sync INTO the repo

The doctor warns `Skill drift: <skill> — Deployed copy is newer than repo
source` when accumulated lessons live only in `~/.hermes/skills/` (Hermes
skips Hermes-default skills, but deployed skills sourced from the repo drift
every time a session adds a lesson locally without committing). Fix direction
is deployed → repo, NOT repo → deployed (that would erase the lessons):

1. `diff skills/<cat>/<skill>/SKILL.md ~/.hermes/skills/<cat>/<skill>/SKILL.md`
   and read it — confirm the delta is lesson additions, no PII.
2. Copy the deployed SKILL.md (and any deployed `references/` files the repo
   copy lacks) into the repo, stage ONLY those paths, commit through the hook.
3. `cortex-update.sh`, doctor, push. The drift warning clears when deployed
   matches repo again.

Do not "fix" drift by deleting the deployed copy or re-deploying over it —
both discard the lessons the doctor is pointing you at.

## Publishing a new skill to the fleet (end-to-end)

Skills reach every agent only through the repo: identify → vet → copy →
clobber-check → commit → deploy → doctor → push → FLEET_NOTICE.

1. **Identify the skill.** `find ~/.hermes/skills -name SKILL.md
   -newermt '<N days>'` and `cmp` each hit against the repo copy; grep
   `~/.hermes/logs/agent.log` for the session that touched it so you publish
   the skill the user means, not just the newest-looking file.
2. **Vet before publishing** — skill-vetting checklist: read the FULL
   SKILL.md (stub body, scripts, injection, exfil, undeclared services),
   `bash ops/scripts/secret-leak-detector.sh`. Copy LICENSE and
   `references/` along with the skill, using `cp` — byte-identical is the
   verification; a hand-typed rewrite can silently drift.
3. **Clobber check before deploying.** cortex-update's delta engine pushes
   the REPO copy over the deployed skill, so any lesson that exists only in
   `~/.hermes/skills/` — including ones other sessions added the same day,
   to skills you are not publishing — is erased by the publish deploy. Diff
   every recently-changed skill deployed vs repo and sync deployed → repo
   first. cortex-update's `⚠ SKILL DRIFT: deployed copy is newer than repo
   source` entries name them; each is content to copy in, never `--force`
   past.
4. **Commit → deploy → doctor → push.** Pull with `--autostash`; expect the
   fleet push race (rebase onto new origin/main, retry). After a race-rebase
   your commit gets a new sha, so Deploy sync FAILs again — run
   `bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force`, push, then
   verify `git ls-remote origin main` == HEAD.
5. **Verify the deployed tree** — `diff -r ~/hermes-cortex/skills/<name>
   ~/.hermes/skills/<name>` identical — then broadcast FLEET_NOTICE per the
   fleet-commands skill (self-test on yourself, one message per agent with
   `--self-tested`, verify with `hc inbox` peeks).

## Transient doctor FAILs — verify live before treating as host debt

- **`Bus stuck msgs` FAIL can be a sampling artifact.** The doctor probes
  the LIVE bus over HTTP, and a message sitting between the handler's read
  and its early archive fails the check once, then clears. Confirm with the
  live endpoint before fixing handler debt:
  `curl -s -u "$CORTEX_BASIC_AUTH" "$CORTEX_BUS_URL/api/pgmq/queue/inbox_<agent>"`
  (both vars in `~/hermes-cortex/.env`) — `depth: 0,
  processing: 0` = clean, just push again. The path is singular `queue/`;
  `/queues/<name>` 404s. Don't conclude from local psql — on the backup
  orchestrator the local mycortex-postgres is a stale REPORTS MIRROR.
- **`hc` is not on PATH** — call it as `~/.hermes-cortex/scripts/hc`.

## Reversing your own wrong fix

If a just-pushed correction turns out to be the wrong direction (e.g. you
removed an uninstall-array entry that was serving legacy cleanup), supersede
it with a new commit in the same session — a known-wrong commit on main
propagates to every host on their next pull.

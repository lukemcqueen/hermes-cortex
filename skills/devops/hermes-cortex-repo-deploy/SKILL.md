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

   **Never let a rebase run over unpushed commits.** With local commits ahead
   of origin, or on a conflicted rebase, `pull --rebase` moves HEAD to origin
   and leaves the repo mid-rebase: the local commits drop out of HEAD and
   survive only in the reflog, while the working tree reverts to origin. The
   same hazard lives inside tooling — a pre-push gate that pulls for you can
   orphan your work the moment it fails. Recover with `git rebase --abort`
   (restores the pre-rebase HEAD exactly); do not re-author the commits. Before
   pulling on a working branch, check `git log --oneline origin/main..HEAD`: if
   it lists anything, SKIP the pull — the local work is precisely what you are
   about to verify and push, so it must not be rebased under.
2. `git push` runs a doctor gate — it fails on ANY doctor ❌. Most common
   blocker: `Deploy sync` / `Checksum: <file>` FAIL because the deployed copy
   predates the pushed commit. Fix by running `cortex-update.sh`, re-running
   the doctor (expect 0 fail), then retrying the push. Never bypass.
3. After the push lands, run `cortex-update.sh` once more so the deployed tree
   includes the just-pushed commit (the push gate's internal deploy can trail
   the newest commit).

## A failed deploy: read the log's FIRST line, and check the lock after

`cortex-update.sh` sources the host env early, so a broken env file kills the run
before any deploy work and the exit code says nothing specific. Diagnose from the
log's first line, not the exit code:

- **`rc=127` whose entire output is `.../.env: line N: <token>: command not found`**
  — the env file is CORRUPT, not the script. A comment line that lost its leading
  `#` makes the shell execute the remainder (a bare date fragment is the usual
  first token). Inspect structure WITHOUT printing values: report each line's key
  (text before the first `=`) with its length, and list the lines that are neither
  blank, nor start with `#`, nor contain `=`. Watch for one absurdly long line — a
  botched append glues a whole blob onto line 1 with no newline, so the header
  comment swallows kilobytes while every real key still sits on later lines.
  Repair is surgical and lossless: restore ONLY the damaged leading lines from the
  newest `.env.bak-*`, leave the rest byte-for-byte, then confirm the key count is
  unchanged and the mode is still `0600`. A corrupt env breaks EVERY deploy on
  that host, so treat it as urgent.
- **`✗ Not a git repository: <path>`** — a git WORKTREE has a `.git` file, not a
  directory, and the script's repo check rejects it. Deploy from the primary
  working tree (or set `REPO_DIR=`); a session worktree can hold the work and
  push, but it cannot deploy.

**After ANY failed deploy, check the enforcement files before doing anything
else** — a run that dies after unlocking leaves them modifiable. `sudo -n
hermes-plugin-lock lock` relocks every target in one call, and the doctor's
`Immutable:` lines are the authoritative confirmation.

## Quoting in commit messages

Never put backticks in a shell-quoted commit message: the shell substitutes them
before git sees the text, mangling the message and leaking fragments onto the
command line. Observed consequence: an empty file literally named `=` was created
at the repo root, tracked, and flagged as scope drift by the reviewer before I
noticed it. Write the message to a FILE and use `git commit -F <file>` for any message, not only
one containing code formatting: the command is scanned as a whole, so a policy that
pattern-matches command text can refuse the entire commit over words in the MESSAGE
(a gateway-lifecycle guard rejecting a message that merely mentions a restart), and
the refusal names the command rather than the cause. Then run `git status --short`
and check for surprise paths before pushing.

## Restoring a file you swapped in: `git checkout --` restores the INDEX

To reproduce a failure against an older revision you may copy that revision over a working
file (`git show <rev>:<path> > <path>`). Restoring it with `git checkout -- <path>` gives
back the **index** copy, not the working tree — so any edit you made but had not staged is
silently discarded, and the command reports success. Observed: a comment fix was reverted
this way, and the commit that followed carried only the evidence file, so the reviewer's
finding it addressed came straight back on the next close.

- Copy the file aside FIRST (`cp <path> <scratch>/mine.py`) and restore from that copy, or
  use `git checkout HEAD -- <path>` when HEAD's version is the one you want.
- Then **grep for the edit** before committing. A clean `git status` proves nothing here:
  a discarded edit leaves the tree cleaner, not dirtier.

## Edit the REPO source, never the deployed tree

`cortex-update.sh` copies every `register()` source over its deployed destination,
and the deployed file says so in its own header (`# SOURCE: <repo path>` /
`# Do NOT edit this file`). An edit aimed at a deployed path SUCCEEDS silently and
looks right — the file is right there, and every test still passes, because the
tests import the REPO tree. The next deploy reverts it, since repo → deployed is
the only direction a deploy copies.

**On an IMMUTABLE target the write does not even succeed** — the enforcement surface
(the enforcer plugin, the git hooks, the loop-governance MCP server) carries the
kernel immutable flag, so a direct write fails with `PermissionError: [Errno 1]
Operation not permitted`, or `EPERM` from a shell. That is the write-protection layer
working, not a permissions bug to escalate: you are editing the wrong side. Verify
with `lsattr <deployed path>` (expect `----i---------e-------`, see
`enforcement-immutability`), then put the change in the REPO source and let
`cortex-update.sh` deploy it — the deploy owns the unlock/relock around the copy, so
it is the only sanctioned way to change one. A `cp`/`python` write to a deployed path
is the same wrong move whichever way it fails, loudly or silently.

- **Patch by REPO path only.** Anything under `~/.hermes-cortex/` is an artifact;
  the editable twin is `~/hermes-cortex/ops/scripts/…`. A `patch` call resolves the
  path it is given, so a deployed path applies cleanly and gives no hint it will be
  thrown away.
- **The deploy's drift guard is the backstop, and it fails CLOSED.** When a deployed
  file differs from its source the run stops with `Copy the deployed changes to the
  repo source first, then commit` (one line per file) and the doctor reports
  `Deploy sync` FAIL. That is the guard working: a blind overwrite would destroy
  whichever side would lose. Resolve it by making the REPO carry the change and
  deploying again — never by copying the deployed file over the source, which
  discards the edits already in the source.
- **Work out which side is ahead before choosing a direction:**
  `diff <repo path> <(tail -n +4 <deployed path>)` (the deployed copy carries a
  3-line header, so skip it). Edits only in the deployed copy must be synced INTO
  the repo; edits only in the repo just need a deploy.
- **After deploying, confirm the deployed file actually took the repo's version** —
  the same `diff` above returning nothing — before reporting the change as live.
  A deploy that printed `rc=0` also prints drift warnings for files it did NOT sync;
  read the run's summary, not just its exit code.

## New shared module → register() entry in the SAME commit

A new module that an existing deployed script imports (e.g. a helper under
`cortex_doctor/`) must get its own `register()` line in `cortex-update.sh`,
placed next to its importer's. `register()` copies ONLY listed files — a
missing entry makes the next deploy break every importer with
`ModuleNotFoundError: No module named '<module>'` at the deploy's verification
step. Symptom to recognize in the deploy log; fix by adding the entry,
deploying, re-running the doctor.

The same rule covers a script the deployed code loads **by path at runtime**
rather than importing (`importlib.util.spec_from_file_location`, a subprocess
call, a plugin lookup): the loader finds nothing on hosts, so the feature is
silently absent there while it works perfectly in the repo. Register both the
script AND every file it resolves **relative to itself** — a config beside it
(`Path(__file__).parent / "<name>.yaml"`) is not deployed by registering the
script alone. A loader written to try the repo path first then the deployed
path will pass every local test and fail only on hosts.

Note `importlib.util.spec_from_file_location` returns an Optional: guard
`spec is None or spec.loader is None` before `module_from_spec`, or a bad path
becomes an AttributeError at the first call instead of a clean skip.

**A CLI ENTRYPOINT is the third shape of the same rule.** A script the fleet is
told to RUN from the deployed path (an agent-side tool, a reply primitive, a
maintenance command) is imported by nothing, so a missing register entry breaks
no import and no deploy step — the host simply has no such file, and the whole
suite stays green because the tests load it by REPO path. The feature is not
"silently degraded" here, it is absent: the documented way to do the job does not
exist on any host. Add the register line beside its siblings and pin it with a
test that asserts the entry AND the exact destination AND the premise (that its
test still loads it from the repo — that is what makes a green suite
uninformative). Then run the DEPLOYED copy before reporting, and say which path
you exercised.

**Guard register-vs-directory agreement, and verify on the DEPLOYED tree.** The repo's
tests import the REPO tree while the host runs the DEPLOYED tree, so a module that is
committed, imported by a deployed script, and never registered keeps a GREEN suite while
the host dies at startup (observed: `RuntimeError: cortex_bus queue.py not found (bus core
missing)` out of `bot_locks`, whose loader probes `~/.hermes-cortex/queue.py` — so that
DESTINATION, not just some deployed copy, is the contract). Assert agreement in BOTH
directions (an unregistered module; a register entry whose source no longer exists), assert
the guard's PREMISE (that the deployed script really does import what it protects), and add
a control that fails on a wrong destination — a guard that cannot fail is
indistinguishable from one that is not looking. Then exercise the deployed copy, not the
repo one, before reporting the fix.

**A register entry in `cortex_gateway/` must be a `.py` module.** The guards compare
`registered` against `cortex_gateway/*.py` in BOTH directions, so registering a shell
helper beside the modules makes the reverse check fire —
`register names files that do not exist: ['<x>.sh']` — even though the file is right
there, because the module glob only ever yields `.py`. Shell runners and evidence
scripts in that directory are therefore repo-only, exactly like the existing ones:
leave them out of the register and run them from the repo (they read the DEPLOYED
tree, so running them from the repo still tests what the host runs).

**A new register entry changes numbers the suite asserts.** `docs/deploy-registry-pattern.md`
quotes the register-map total, the derivable count and the no-rule count, and a test
recomputes all three from `cortex-update.sh`. Adding one line fails that test until the
doc is updated — do it in the SAME change, and derive the numbers from the script rather
than adjusting the old ones by hand.

## Register at the RIGHT SCOPE — universal vs orchestrator-only

`register()` deploys to every host; `register_orch()` deploys only to orchestrator
hosts. A file every agent needs but registered orch-only is simply ABSENT on
non-orchestrator hosts, and nothing fails loudly — an installer that expects it warns
and carries on, so the integration is silently partial (a Pi setup registering 3 of 4
MCP servers, a bus client with no bus server) and the on-host repair is a hand-copy
that the next agent repeats.

- **Decide by who consumes it, and read the consumer's contract.** A server whose
tools are all CLIENT tools, whose consumers declare client access, and that an
installer requires by path belongs on EVERY host. A dashboard, an orchestration loop,
a launchd plist, or something only the orchestrator's own crons call stays orch-only.
- **Exactly one class per source.** Registering a file with BOTH `register` and
  `register_orch` is the natural residue of "promote this to every host" — the new
  line added, the old one forgotten. The two entries look authoritative and disagree;
  delete the replaced entry in the same edit.
- **Guard the class with a test**: parse both `register` and `register_orch` out of
  `cortex-update.sh`, then assert (a) every `mcp-servers/*.py` is registered, (b) the
  ones every agent needs use the plain form, (c) no source appears in two classes.
  Add CONTROLS that run the guard against a modified COPY of the script — one that
  flips a universal registration back to orch-only, one that adds a duplicate — and
  assert the guard fires. A scope guard that cannot fail is indistinguishable from one
  that is not looking.

## A registered source can be silently GITIGNORED — confirm it is tracked

`git add -A` skips ignored files with NO error and NO warning, so a `register()`
entry can ship while its source file does not. The deploy still succeeds on YOUR
host — it copies from the working tree — while every other host fails with a
source-missing warning, which is exactly why the defect is invisible locally. The
repo's gitignore carries deliberate secret guards (`*secret*`, `*credential*`,
`*cred*`, `*token*`, `*.p12`), so ANY artifact whose NAME matches one is affected —
tests included: a test named after a secret-ish artifact never reaches CI, and its
green local run becomes evidence nobody else can reproduce.

- **Rename the artifact out of the guard's pattern** (preferred). `git add -f` is
  never the answer: an ignored file stays invisible to every OTHER agent's
  `git add -A`, so the manifest breaks again on the next artifact and the special case
  multiplies. A targeted `!` negation is the repo's EXISTING convention for a script
  that legitimately carries such a name — `.gitignore` already negates the leak
  detector and the leak watchdog by full path, each with a comment saying why — so if
  you negate, negate a FULL PATH beside those and never a wildcard; expect a rename to
  be the smaller thing to explain later.
- **Confirm with** `git check-ignore -v <path>` (prints the .gitignore line that
  matched) and `git log --all -- <path>` — EMPTY output means it was never committed,
  no matter how many times you ran it locally.
- **Guard the whole class with a test**, not just your file: parse `^register "([^"]+)"`
  out of `cortex-update.sh` and require every source to exist AND satisfy
  `git ls-files --error-unmatch <path>`, naming the matched ignore rule in the failure
  message. Measure the entry count and the current untracked total BEFORE asserting, so
  the test is not fighting legitimate exceptions; run it against a still-untracked
  artifact as a control — if a fresh file passes, the test is not inspecting what you
  think it is.
- **After `git add -A`, read `git status --short`.** A path you meant to add but that
  shows no `A`/`M` was skipped silently; a missing error message is not evidence of a
  staged file.

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

## Never edit the repo while YOUR OWN ship is running

`cortex-update.sh` → `cortex-dogfood.sh` → `git push` can run for several minutes. Editing
files in that window — even "just a small fix" — races the ship: it commits (`git add -A`
seizes your half-written edit), then its `pull --rebase`/push meets a tree that changed
under it and fails with `error: Please commit or stash them.` or a non-fast-forward. The
symptom looks like a remote race, so the cause is easy to misread.

- **Before editing anything, ask the ship:** `pgrep -f "cortex-update.sh|cortex-dogfood.sh"`
  — if it prints anything, STOP and wait (bounded loop: `for i in $(seq 1 60); do pgrep -q ... || break; sleep 5; done`). Reading is always safe; writing is not.
- **After any ship, verify the landing**: `pgrep` empty, then `git log --oneline -1
  origin/main` and `git log --oneline origin/main..HEAD | wc -l` == 0. A ship that printed
  `deploy rc=0` can still have failed to push.
- **A push blocked with `unpushed: N` and a clean tree is already fixed** — just push again;
  the failure was the race, not the commit.

## Verify the DELIVERY, not the queue

A message that reached a queue is not a message that reached a human, and `depth: 0` after
a send means *something consumed it* — including your own probe. Two false greens observed
on this path in one night: (1) a queue drained to 0 was read as "delivered" while the
consumer was the test harness calling `poll_replies()` before `drain_outbound()` saw it;
(2) a provider `/models` endpoint answering 200 was read as "credential valid" — that
endpoint is public and answers 200 for a revoked key (a real chat/completion call is the
test).

- Capture the DOWNSTREAM RECEIPT: spy the transport's `_api` and record the
  `message_id` the platform returns, or read the value back from the system you wrote to.
- Measure the thing you claim. "Drained" needs a consumed-and-archived fact; "delivered"
  needs the receiver's id; "queued" needs the queue to still hold it.
- **Verify on the endpoint the CONSUMER uses, not the one your write preferred.** A client
  with a primary URL plus a silent fallback can WRITE to a different instance than the
  reader READS: a stale credential rejected at the primary sends the write to the fallback,
  the send still returns a `msg_id`, and a consumer pointed at the primary never sees it —
  a message that vanishes on a success response. Read the value back from the consumer's
  endpoint (or log which endpoint served the write) before reporting delivery, and when a
  write and a read disagree about existence, suspect TWO endpoints before suspecting the
  queue.
- When a check can't verify (no receipt available), say COULD NOT VERIFY rather than
  reporting the nearest green signal.

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
- **A 401/404 from that endpoint is a PROBE error, not proof the bus is
  unverifiable.** nginx demands Basic auth and ignores a Bearer token, so a bearer
  request — or the plural `/queues/<name>` path — answers 401/404 while the queue is
  perfectly readable with `CORTEX_BASIC_AUTH`. Retry the documented form before
  reporting a dispatch as "sent, unverified", and if it still fails, name the exact
  probe that failed instead of implying the queue cannot be checked. Check the probe
  before doubting the system.
- **`hc` is not on PATH** — call it as `~/.hermes-cortex/scripts/hc`.

## Reversing your own wrong fix

If a just-pushed correction turns out to be the wrong direction (e.g. you
removed an uninstall-array entry that was serving legacy cleanup), supersede
it with a new commit in the same session — a known-wrong commit on main
propagates to every host on their next pull.

**Before re-pushing into a contested area, check whether upstream still contains your
change.** Peers work the same defects from the same symptoms, so a fix can be landed
AND reverted while you are still mid-cycle; `git log --oneline origin/main -5` plus
`git show --stat <sha>` tell you whether a `Revert` has taken your work out, and
whether the current upstream state is coherent (source present, manifest pointing at
it). Push onto a verified base and raise the revert as a decision — do not silently
re-land a change someone deliberately reversed, and do not re-argue it by loop.

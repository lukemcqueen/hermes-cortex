# Backlog run 2026-10-26 (22:21 KST) — 482de205: the reflexion gate refused a JOB, not a session

Evidence for the `orch-bus-worker` cron run (job `1954deb5ad76`, session
`cron_1954deb5ad76_20261026_222143`, governance cycle **#13823**). Host-derived
identity: **esther** (orchestrator). Every line below is raw tool output from this
run; nothing is inherited from a prior session's claim.

## Why this row

Backlog at run time (`tasks.task_board repo=hermes-cortex include_untagged=true`):
claimable **15**, other-kind pending **7**, stories **3**, in_progress **0**.
`482de205` is the earliest priority-2 open row that is orchestrator-local and
finishable here. Its own text: *"Reflexion gate is unsatisfiable for a cron/bg
session that lacks the skill_view tool."* Re-measured LIVE today: the 07:00
`orch-task-morning-pass` job recorded at 07:37 that its evidence commit was refused
with `NOT-LOADED reflexion-check (session cron_f6694d02d29c_20261026_073743)`
(`docs/evidence/morning-task-pass-2026-10-26/README.md`).
*(That bundle is committed — `664a1020 evidence(morning-pass): land the 2026-10-25 and
2026-10-26 orchestrator passes`. The job's "sits uncommitted" line describes its own
07:37 state before a sibling pass landed it.)*

## Root cause — the JOB's toolset allowlist (measured, not inferred)

The gate asks the HC store whether this session invoked `skill_view`
(`mycortex_mem.sessions.loaded_skill`, keyed to the session id). That row is written
by the enforcer pre-tool hook, so it exists only if the session was given the
`skills` toolset. Whether a cron session gets it is decided per job by
`cron/scheduler.py::_resolve_cron_enabled_toolsets()`: a per-job
`enabled_toolsets` allowlist is authoritative.

Comparing the two orchestrator jobs in the DEPLOYED store (`~/.hermes/cron/jobs.json`):

```
orch-task-morning-pass | id f6694d02d29c
    enabled_toolsets = ['terminal', 'web', 'file']      <- explicit allowlist, NO 'skills'
    skills = []            skill = None
orch-bus-worker | id 1954deb5ad76
    enabled_toolsets = None                             <- None => platform_toolsets.cron
    skills = ['orch-bus-worker']   skill = orch-bus-worker
```

`orch-bus-worker` is the sibling job whose session DOES satisfy the gate (live, this
run):

```
$ python3 ops/scripts/hc-reflexion-check.py --session cron_1954deb5ad76_20261016_142149
LOADED reflexion-check (session cron_1954deb5ad76_20261016_142149)
rc=0
```

`skills` is a real Hermes toolset — `hermes_cli/tools_config.py:80`:
`("skills", "📚 Skills", "list, view, manage")`. So the gate is **not** structurally
unsatisfiable; one job on this host is mis-wired, and the refusal told its agent to
do something it could not do ("Load the skill … `skill_view(name='reflexion-check')`").

## The change (additive; no gate relaxation)

`ops/scripts/hc-reflexion-check.py` only:

1. `automated_session_job_hint(session_id, jobs_file=None)` — returns a bounded list of
   diagnostic lines on POSITIVE evidence alone (SOUL §32 discipline): the session id is
   automated (`cron_`/`bg_`), its embedded job id resolves in the cron store, and that
   job carries an explicit `enabled_toolsets` allowlist that omits `skills`. Unknown job,
   absent/unreadable store, `None` allowlist, interactive session → `[]` (no speculation).
2. `main()` prints those lines to the refusal stream **only** when the verdict is
   NOT-LOADED (rc 1).

Exit codes are untouched: `0` loaded / `1` not loaded / `2` usage / `3` store
unreachable, and the rc-3 branch stays a single line (pinned by
`tests/test-reflexion-gate-repoint.sh` AC10 — still green below).

## Evidence

### 1. RED — the new test against the pre-change verifier (named failures)

```
$ $HOME/.hermes-cortex/venv/bin/python -m pytest tests/test_reflexion_check_cron_diagnostic.py -q
collected 10 items
tests/test_reflexion_check_cron_diagnostic.py F........F                 [100%]
FAILED test_cron_session_without_skills_toolset_names_the_job_and_the_fix
       AssertionError: the refusal must name the config field
       assert 'enabled_toolsets' in 'NOT-LOADED reflexion-check (session cron_f6694d02d29c_20261026_073743)\n'
FAILED test_helper_requires_positive_evidence
       AssertionError: automated_session_job_hint is missing from hc-reflexion-check.py
2 failed, 8 passed in 0.74s
```

The 8 passers are the negative/unchanged contracts (no hint for an interactive
session, for an allowlist that HAS `skills`, for a null allowlist, for a broken store,
for a LOADED session, and the rc-3 single-line pin) — they *should* hold on both
revisions, which is why they are separated from the two decisive failures.

### 2. GREEN — after the change (hermetic: stub store + temp jobs.json)

```
$ $HOME/.hermes-cortex/venv/bin/python -m pytest tests/test_reflexion_check_cron_diagnostic.py -q
tests/test_reflexion_check_cron_diagnostic.py ..........                 [100%]
10 passed in 0.68s
```

### 3. The existing gate contract still holds

```
$ bash tests/test-reflexion-gate-repoint.sh
  ... AC7 real verifier refuses a session with no evidence ✅
  ... AC9 store unreachable → rc 3, names the fix ✅
  ... AC10 store raises mid-query → rc 3, no stack dump ✅
  ✅ gate output stays a single line (no raw dump)
  ✅ no run-time store-path override exists in the verifier
  17 passed, 0 failed
```

### 4. LIVE, on the real store and the real cron config (the 07:37 job's own session)

```
$ python3 ops/scripts/hc-reflexion-check.py --session cron_f6694d02d29c_20261026_073743
NOT-LOADED reflexion-check (session cron_f6694d02d29c_20261026_073743)
  This session's cron job 'orch-task-morning-pass' (f6694d02d29c) carries an explicit
  enabled_toolsets allowlist without 'skills' (terminal, web, file),
  so no skill tool is registered and a load can never be recorded.
  Fix the JOB, not the gate: give it the 'skills' toolset — set it for that job
  via the cron API, or add 'skills' to platform_toolsets.cron in config.yaml
  ('hermes cron edit' has no --enabled-toolsets flag).
rc=1
```

## What this does and does NOT do

- DOES: every future refusal of this class now names the job, its current allowlist and
  the exact fix, instead of telling a tool-less agent to load a tool it does not have.
- DOES **NOT** unblock the 07:00 job by itself. The unblocking action is one config
  change on that job (`enabled_toolsets` → include `skills`, or clear it so the job
  follows `platform_toolsets.cron`).
- Why the config change was NOT made here: `--enabled-toolsets` is not a CLI flag
  (`ops/scripts/install-crons.sh:352`), so it means the cron API (needs the `cronjob`
  toolset, which cron sessions are denied by design) or hand-editing the live
  `~/.hermes/cron/jobs.json`. Both are operator/interactive-session territory —
  dispatched to Luke as a decision, not taken unattended. `482de205` stays **open** in
  the backlog with this diagnosis attached.

## Plan review (Luke's standing rule) — and how its findings were answered

The plan was submitted BEFORE building, as CONTENT (never a path), to the governed
reviewer: `ops/scripts/orch-bus/adversarial-review.py --cycle-id 13823 --review
--reviewer-id adv-review-cron-1954deb5ad76-13823` → row
`adversarial_reviews.review_id 6c9f1f14-e001-45cf-8c22-0a6c06e3302e`,
model `deepseek/deepseek-v4-pro`, verdict **FINDINGS**, both findings
`technique=unverified-claim`, severity high:

1. `ADV-13823-1` — the quoted `~/.hermes/cron/jobs.json` excerpt had no committed record.
   → Answered by `jobs-config-reading.txt` (same directory): the raw reading, with the
   exact source path/size/mtime and the exact fields, re-runnable by the reader.
   The file it reads is a DEPLOYED live store, so the capture is the only committable record.
2. `ADV-13823-2` — the plan pointed at `docs/evidence/morning-task-pass-2026-10-26/` as
   "uncommitted". → That was the 07:37 job's own state; the bundle is committed as
   `664a1020`. Corrected above.

No finding objected to the design; the reviewer raised no scope, injection or
gate-weakening issue. The cycle's review row is UNIQUE and frozen (Rule 22), so this
disposition is recorded here rather than by re-review.

## Re-run

```bash
cd ~/hermes-cortex
$HOME/.hermes-cortex/venv/bin/python -m pytest tests/test_reflexion_check_cron_diagnostic.py -q   # expect 10 passed
bash tests/test-reflexion-gate-repoint.sh                                                                # expect 17 passed, 0 failed
python3 ops/scripts/hc-reflexion-check.py --session cron_f6694d02d29c_20261026_073743                     # expect rc 1 + the job's config named
```

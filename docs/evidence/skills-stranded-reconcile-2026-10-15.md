# Stranded skill reconciliation — 2026-10-15

Task: task-db `054aac1e-2208-44c2-956d-371674620023` (“Resolve the stranded skill
files”). Governed cycle: `skills-stranded-reconcile-20261015`.

PROVENANCE: every block below was captured by `~/.hermes/cache/scratch/gen-evidence.py`
from live runs on this host on 2026-10-15 (tip at capture: `fefbc662`) — each command
beside its own exit code, measured unpiped, home path redacted to `~` at the
generator. Volatile by design: the in-sync/skipped COUNTS are snapshots of a moving
fleet tree; the stranded verdict is the claim.

## 1. Decision: the deployed side is a content superset for all 4 files

The repo side is pinned to revision `1d5af71e` (the pre-change tip), never to HEAD —
HEAD now IS the change, so a HEAD-based comparison could not be re-run. For every
REMOVED line the probe reports whether its exact text is still a contiguous substring
of the deployed copy; where it is not (2 of 4 files) it reports how many of that
line's characters survive and which clause does not — the clauses are empty, i.e. the
paragraph was extended in place, not shortened. The reconciler's `would drop 1 line`
is a whole-line artifact of exactly that.

```
$ python3 ~/.hermes/cache/scratch/stranded-diff-at.py 1d5af71e
repo side = git 1d5af71e (pinned pre-change revision); deployed = ~/.hermes/skills
=== devops/enforcement-change-safety/SKILL.md: deployed adds 10 line(s), removes 0; removed-lines-whose-exact-text-is-ABSENT=0
    --- repo@1d5af71e
    +++ deployed
    @@ -1233,2 +1233,12 @@
     
    +- **The gate's ADVERTISED contract is part of the enforcement surface — pin it to the behaviour.**
    +  The prose every caller reads (a tool `description`, a `--help` line, a block message) is what an
    +  outside harness author codes against, and it is written somewhere other than the rule it
    +  describes, so it drifts silently: a predicate narrowed to match on the RESOLVED path went on
    +  advertising a name-match fallback for a full cycle after the code stopped honouring it, which
    +  makes the gate read as MORE permissive than it is — the direction callers rely on. Re-read the
    +  description in the same change that changes the rule, and pin the pair with a test that parses
    +  the registration out of the source and asserts the description cannot advertise a removed
    +  behaviour (mechanism in `mcp-server-building` §10).
    +
     Worked example, including the block-capable `tool_call` hook shape: the `pi-coding-agent`
=== devops/task-queue-workflow/SKILL.md: deployed adds 6 line(s), removes 1; removed-lines-whose-exact-text-is-ABSENT=0
    --- repo@1d5af71e
    +++ deployed
    @@ -120,3 +120,8 @@
     - **Sequential backlog** (slices gated on a prerequisite phase completing) →
    -  normal backlog, not cruft.
    +  normal backlog, not cruft. This binds the WORKER too: before claiming a slice, check that its
    +  inputs EXIST — if every prerequisite slice is still `pending`, the deliverable can only be
    +  invented, so `unclaim` with the gap named and let the queue advance in order. Do not author the
    +  artifact from imagination to look productive (that is fabrication), and do not `cancel` a
    +  client-facing deliverable to clear your board (the owner's call, and it destroys real work):
    +  release the claim and name the prerequisite that unblocks it.
     - **Exact duplicates** (two slices describing the same deliverable) → the only
=== software-development/change-checklist/SKILL.md: deployed adds 4 line(s), removes 1; removed-lines-whose-exact-text-is-ABSENT=1
    REMOVED-LINE 88/88 chars still present in deployed; unmatched clause(s): []
    --- repo@1d5af71e
    +++ deployed
    @@ -309,3 +309,6 @@
           in the artifact, never recalled**: a line/file total must be the one the artifact's own
    -      `wc -l` / `grep -c` printed, at the revision it cites. **And name the comparison's exact
    +      `wc -l` / `grep -c` printed, at the revision it cites — and NEVER a count read off
    +      `git show --stat`: it TRUNCATES long paths behind a leading `...`, so a file list taken from
    +      it is silently SHORT (four paths shown for eight files changed) while looking complete. Use
    +      `--name-only` whenever the FILE SET is the claim; `--stat` is for shape only. **And name the comparison's exact
           strength** — "identical modulo the deploy banner (N leading lines stripped)", never
=== software-development/mcp-server-building/SKILL.md: deployed adds 1 line(s), removes 1; removed-lines-whose-exact-text-is-ABSENT=1
    REMOVED-LINE 257/257 chars still present in deployed; unmatched clause(s): []
    --- repo@1d5af71e
    +++ deployed
    @@ -282,3 +282,3 @@
     | **A notification has no `id` and gets NO response** | Answering one is a protocol error. Branch on the presence of `id`, not on the method name. |
    -| **One dispatch, two surfaces** | Generate `tools/list` AND any CLI/`--help` from the same table of operations. Two hand-written descriptions of one tool drift, and the drift is invisible until an agent calls a tool differently from how it is advertised. |
    +| **One dispatch, two surfaces** | Generate `tools/list` AND any CLI/`--help` from the same table of operations. Two hand-written descriptions of one tool drift, and the drift is invisible until an agent calls a tool differently from how it is advertised — the tool list then reads as MORE permissive than the code, which is the direction a caller relies on. Since the description and the behaviour live in different places, nothing ties them together: PIN them with a test that parses the registration out of the source (`ast`, the `Tool(name=..., description=...)` call) and asserts the text advertises no removed rule and no missing field. |
     | **Exit codes are contract for the CLI side** | Distinguish "ran and failed" (1) from "could not verify / not configured" (3). An agent branches on this: one is worth retrying, the other means this host is not set up. |
rc=0
```

## 2. Landing the deployed bytes (sha256 asserted both sides)

Idempotent: `already-landed` means the repo copy already carries the deployed bytes.

```
$ python3 ~/.hermes/cache/scratch/land-stranded-skills.py
OK  devops/enforcement-change-safety/SKILL.md (already-landed)
     repo-before=6f5fc86e74f7 repo-after=6f5fc86e74f7 deployed=6f5fc86e74f7
OK  devops/task-queue-workflow/SKILL.md (already-landed)
     repo-before=63234632628c repo-after=63234632628c deployed=63234632628c
OK  software-development/change-checklist/SKILL.md (already-landed)
     repo-before=6998d3c3385d repo-after=6998d3c3385d deployed=6998d3c3385d
OK  software-development/mcp-server-building/SKILL.md (already-landed)
     repo-before=9fc75bc161c3 repo-after=9fc75bc161c3 deployed=9fc75bc161c3

files=4 failures=0
rc=0
```

## 3. Detector after — the acceptance claim

```
$ python3 ops/scripts/manage/reconcile-stranded-skills.py
Detector verdict: PASS · stranded: 0
Nothing stranded: repo and deployed trees agree on content.
rc=0
```

## 4. Parity artifact regenerated and re-checked (against the COMMITTED artifact)

```
$ python3 ops/scripts/manage/check-skill-drift-parity.py --check
artifact matches the live derivation
rc=0
```

## 5. Doctor — the skill-drift block is gone

Doctor's OWN exit code and warning count, measured unpiped (the piped `rc` below is
the grep's, so both are printed):

```
$ python3 ops/scripts/manage/cortex-doctor.py --quiet > /tmp/doctor-strand.out 2>&1; echo doctor_rc=$?; echo warn_glyph_lines=$(grep -c '⚠️' /tmp/doctor-strand.out); grep -E 'Skill drift|Stranded slices|Repo sync|Repo clean|Overall' /tmp/doctor-strand.out; echo grep_rc=$?
doctor_rc=1
warn_glyph_lines=5
  ⚠️  Repo clean
  ✅ Repo sync
  ✅ Skill drift
  ✅ Stranded slices
  ⚠️  Overall: WARNING  (465 pass · 3 warn · 0 fail · 3 info)
grep_rc=0
rc=0
```

Doctor's own summary line reads `3 warn`; `warn_glyph_lines` counts every line that
carries the glyph (the summary line and the REQUIRED-ACTIONS header included), so the
two numbers are not the same measure. `Repo clean` is the only ⚠️ this change could be
mistaken for, and it is the evidence document ITSELF sitting untracked while it is
being written — shown rather than asserted:

```
$ git status --short
?? docs/evidence/skills-stranded-reconcile-2026-10-15.md
rc=0
```

The other two ⚠️ are `Cron status (orch-daily-regression-gate)` and `loop-gov daemon`
(running stale code — gateway restart pending), both pre-existing on this host.

## 6. Units that cover the reconciliation (capability-resolved interpreter)

The ambient `python3` cannot run the suite (no pytest) — resolved via the fleet
helper rather than by routing around it, and the runner is probed against a target
that cannot succeed so a green line cannot be vacuous.

```
$ bash ops/scripts/lib/python-with-module.sh pytest -m pytest tests/test_skill_drift_parity.py -q -p no:cacheprovider
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: ~/hermes-cortex
configfile: pytest.ini
plugins: anyio-4.15.1
collected 1 item

tests/test_skill_drift_parity.py .                                       [100%]

============================== 1 passed in 5.87s ===============================
rc=0
```

Negative probe of the same runner (a test name that does not exist):

```
$ bash ops/scripts/lib/python-with-module.sh pytest -m pytest tests/test_skill_drift_parity.py -q -p no:cacheprovider -k definitely_not_a_real_test_name
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: ~/hermes-cortex
configfile: pytest.ini
plugins: anyio-4.15.1
collected 1 item / 1 deselected / 0 selected

============================ 1 deselected in 0.08s =============================
rc=5
```

## 7. Landing verified (push receipt)

```
$ git log --oneline -1 origin/main
fefbc662 skills: land 4 deployed-only lessons into the repo (stranded reconciliation)
rc=0
```

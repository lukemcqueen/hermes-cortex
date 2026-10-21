# Backlog run — top-task selection record (2026-10-20, orch-bus-worker)

**Purpose.** The close review of cycle 12714 filed `ADV-12714-1` (scope-drift,
medium): a backlog pass must action a **task row** and document *why that row*.
This file is that documentation, committed so the selection can be judged rather
than asserted. Task ids are shortened to 8 characters so no row text has to be
elided by the write-time PII gate (see `cf8f8e8d`).

Run: governance session `cron_1954deb5ad76_20261020_222126`, cycle **13464**.

## 1. Queue census (verbatim tool output)

```
mcp__tasks__task_board(repo=hermes-cortex, include_untagged=true)
  pending (claimable): 17
  pending (not claimable, other kind): 14
  pending (story, not claimable): 3
  In review: none
```

```
mcp__tasks__task_list(status=paused)  -> 10 rows, all priority 0, content
                                          'ISSUES'/'PROPOSAL' (bare tokens)
mcp__tasks__task_list(status=waiting) -> No tasks found.
mcp__tasks__task_list(status=blocked) -> 3 rows: 66914fe1 [queue/1],
                                          cf8f8e8d (PII gate FP),
                                          2fc4d871 [queue/3]
mcp__tasks__task_list(status=in_progress) -> No tasks found.
```

This is the orchestrator's own store only (`hermes-cortex` label); fleet rows
minted on other hosts are **not visible here**, so this is not a fleet-wide claim.

## 2. Why the top row is not the actionable row

Sort order is (priority desc, created_at). Priority 3 = the cost story
`c579ef95`; every one of its slices is waiting/blocked/escalated (`[cost/1]`
`5e875477` has no live spend source — the cost stack was removed 2026-10-06;
`[queue/1]` `66914fe1` is blocked on a Luke decision, restated in §5).

Priority 2 opens with the KAESA fleet slices (2026-08-23), whose own first slice
(`1d09760f`, discovery audit) needs a client stakeholder interview — not an
unattended cron action. Then come the orchestrator-local rows.

## 3. The row actioned: `3cc049e8` (priority 2, personal)

> "Broken skill references: repo `skills/devops/llm-cost-optimization/SKILL.md`
> cites 4 reference files that do NOT exist in the repo … they exist only in the
> deployed skill tree."

It is the first row in sort order that is orchestrator-local, finishable
unattended, and verifiable. Premise re-verified before touching anything — the
repo carried 4 of the 8 files its own SKILL.md routed to:

```
$ ls skills/devops/llm-cost-optimization/references/     # before
daemon-restart-peak-pins-2026-08-21.md  deepseek-cache-economics.md
fleet-cost-levers-verified.md           opencode-relay-pricing.md
```

The 10-17 pass committed the detector that measures this class (`b805a92c`) and
deliberately left recovery open; this cycle makes the recovery decision for the
four files **by content**, not by copying blindly.

### The change

The four files are restored to the repo from the deployed tree **with their
removed-stack claims corrected** — the deployed copies still presented
`cron-costs.db`, `install-cron-cost-tracking.py` and the `orch-daily-cost-report`
cron as live, though all were removed 2026-10-06
(`docs/evidence/cost-removal-2026-10-06.md`). Restored:

- `references/fleet-cost-data-sources.md` — removed stores/burn marked REMOVED
  2026-10-06; the digest section kept as design rules.
- `references/interactive-session-cost-state-db.md` — state.db `sessions`
  table kept (still the live interactive source); `cron-costs.db` marked gone.
- `references/session-telemetry-reporting.md` — trap 3 re-labelled historical
  with the generalisable lesson kept; trap 1/2 (epoch cutoff, `Tokens:` redactor
  masking) are live and unchanged.
- `references/openrouter-model-catalogue.md` — restored verbatim; no
  removed-stack claims (verified by reading it before copying).

Prune was rejected: these files carry knowledge nothing else in the repo
repeats (the model-market survey is cited from SKILL.md's free-tier pitfall).

### Verification (verbatim)

Every link the repo SKILL.md cites now resolves inside the repo:

```
$ python3 <probe: extract 'references/*.md' from repo SKILL.md, assert each exists>
links cited in repo SKILL.md: 8
missing: 0
repo references/ files: 8 ['daemon-restart-peak-pins-2026-08-21.md',
 'deepseek-cache-economics.md','fleet-cost-data-sources.md',
 'fleet-cost-levers-verified.md','interactive-session-cost-state-db.md',
 'opencode-relay-pricing.md','openrouter-model-catalogue.md',
 'session-telemetry-reporting.md']
```

The detector that measures the class confirms the move — `dropped-from-repo`
fell 6 → 3 and the four files left the absent list:

```
$ python3 ops/scripts/manage/check-skill-drift-parity.py
| Stranded in place (path in repo, content only deployed) | 11 |
| Absent from the repo (deployed under a repo-owned skill) | 132 |
|   ↳ path dropped from repo history | 3 |
|   ↳ path never committed | 129 |
| Files in sync | 832 |
| Skipped (Hermes defaults, or repo ahead) | 508 |
**Verdict: FAIL**          # expected: 132 absent rows remain, see §5
```

```
$ bash tests/run-tests.sh tests/test_skill_drift_parity.py -q
tests/test_skill_drift_parity.py .                                       [100%]
============================== 1 passed in 11.39s ==============================
run-tests.sh: interpreter=$HOME/.hermes-cortex/venv/bin/python3 rc=0

$ bash ops/scripts/manage/run-skill-parity-verify.sh
✅ GATE_PASSED — no critical/high findings
**Verdict: PASS**
```

`docs/evidence/skill-drift-parity.txt` is regenerated as part of this cycle; its
numbers above are that artifact's.

## 4. Also closed this run

**`f97dcffe`** — "Detector gap: stranded-skill detection covers SKILL.md only."
The detector extension it asks for is committed (`b805a92c`, support files under
repo-owned skill dirs reported as `dropped-from-repo` / `never-committed`) and
was exercised twice this cycle: the checker still reports the class (§3) and its
test passes. The row's remaining half — deciding the measured files by content —
is what §3 started and is tracked separately below; the detector itself is done.

## 5. Left open (reported, not silently dropped)

- **`c579ef95` / `5e875477` [cost/1]** — no live spend source; blocked as §2.
- **`66914fe1` [queue/1]** — needs a Luke decision: the paused class is now 10
  bare-token rows (all priority 0, content `ISSUES`/`PROPOSAL`), all minted from
  self-test inbox traffic (`caed9076` diagnoses the mint). Cancelling them
  unattended is forbidden by the row's own plan and by the destructive-default
  rule, so this stays escalated.
- **`2fc4d871` [queue/3]** — blocked: no `depends_on` update surface exists
  (same gap as `9fb2ddb6`).
- **`9fb2ddb6` / `caed9076`** — both require adversarial review *before*
  building (Luke's standing rule); not started here.
- **`762379ca`** (briefing checker gate) — untouched this run; the next pass's
  candidate.
- **129 files absent from the repo** under repo-owned skill dirs remain (was
  131): the four here are decided; the rest — incl. `redactor-tokens-label-masking.md`
  under this same skill — need the same per-file content decision, which is its
  own governed change.
- Known defect spotted, **not** fixed (out of this row's scope): the repo
  SKILL.md's Pitfalls section has two mangled bullets (lines ~140 and ~162-171,
  text lost mid-sentence). Recorded as an issue rather than widened into this
  cycle.

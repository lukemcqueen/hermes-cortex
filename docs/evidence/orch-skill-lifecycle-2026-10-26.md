# orch-skill-lifecycle — 2026-10-26 (esther)

Cycle: #13796 · Session: cron_8a46f1b96b7d_20261026_043944
Run time: 2026-10-26 04:39 KST (`date '+%Y-%m-%d %H:%M %Z'`)
Outcome: **NO-OP** (verified — every reported change is already committed and
already deployed; no unapplied content exists).

---

## Phase 1 — Collection

Authoritative input: `~/.hermes-cortex/state/learning-reports/` (1621 files),
scoped to the last 48h by the body's `Generated:` timestamp, parsed after
unwrapping the outer `{"topic","text"}` JSON envelope (see the 2026-10-19
pitfall — a naive parse silently reports 0).

```
files scanned=1621  unique_reports_48h=12  skipped=0
agents: Counter({'esther': 4, 'joseph': 3, 'gisu': 2, 'kustos': 2, 'titus': 1})
[MOD]: [('detached-worker-pattern', 3), ('cortex-bus', 3), ('fleet-commands', 2),
        ('shared-repo-push-gates', 2), ('shell-scripting', 2), ('soul-refinement', 2),
        ('skill-vetting', 2), ('change-checklist', 2), ('orch-bus-worker', 1)]
[NEW]: []
```

- **gisu** and **titus** delivered heartbeats only (no changes, agents alive).
- **Zero** `[NEW]` skills in the window → nothing to upstream.
- Ledger intake (F-006):
  `python3 ops/scripts/manage/learning-ledger.py list --status pending`
  → `No learnings found.` (nothing to dispose; nothing left pending).

## Phase 2 — Evaluation

All 9 `[MOD]` names are **recurrences of one already-committed drift-sync**, not
independent discoveries — the exact false-consolidation signal the skill warns
about. Each maps to a commit on main within the last 3 days, and each deployed
copy is byte-identical to its repo source:

| skill | commits since 2026-10-23 | last | repo vs deployed |
|---|---|---|---|
| cortex-bus | 2 | 2026-10-25 | MATCH |
| change-checklist | 3 | 2026-10-23 | MATCH |
| soul-refinement | 3 | 2026-10-25 | MATCH |
| detached-worker-pattern | 1 | 2026-10-24 | MATCH |
| fleet-commands | 2 | 2026-10-24 | MATCH |
| shared-repo-push-gates | 2 | 2026-10-23 | MATCH |
| shell-scripting | 2 | 2026-10-23 | MATCH |
| skill-vetting | 2 | 2026-10-23 | MATCH |
| orch-bus-worker | 1 | 2026-10-23 | MATCH |

The collector re-reports a hash-delta until the deployed copy settles, so a name
appearing in 2–3 reports is one event observed repeatedly. Nothing to classify.

## Phase 3 — Upgrade

**No action taken.** Evidence of a clean tree:

```
$ python3 ops/scripts/manage/cortex-doctor.py --quiet | grep -i 'skill drift'
  OK Skill drift - 386 skills in sync, 135 Hermes defaults skipped

$ python3 ops/scripts/manage/reconcile-stranded-skills.py
Detector verdict: PASS - stranded: 0
Nothing stranded: repo and deployed trees agree on content.

$ python3 ops/scripts/manage/learning-ledger.py list --status pending
No learnings found.

$ md5sum loop, repo vs ~/.hermes/skills (9 reported [MOD] skills)
  MATCH: detached-worker-pattern, fleet-commands, shared-repo-push-gates,
         shell-scripting, skill-vetting, change-checklist, orch-bus-worker,
         cortex-bus, soul-refinement
```

Doctor overall: `490 pass · 6 warn · 0 fail · 3 info`. None of the 6 warnings is
this pipeline's to act on today; each is already dispositioned as deferred to
esther by a previous run (`Repo clean` 2 uncommitted, `CLAUDE.md (dev repos)`,
`Script run evidence`, `Cron status (agent-mycortex-dream-nightly)`,
`Cron bridge migration (1)`, `loop-gov daemon`).

## Pushback record (SOUL Principle 5)

Before acting, the following were challenged and **deliberately NOT executed**:

- **Not patching** any `[MOD]` skill — repo == deployed, so a patch would add
  content that already exists. Double-patching a settled drift-sync is exactly
  the failure mode the 2026-10-19 pitfall names.
- **Not pruning or deleting** any skill and **not rewriting `~/.hermes/SOUL.md`** —
  no evaluation item justified either; the pushback contract defaults to no-op
  when in doubt.
- **Not touching peer drift** — `cortex-bus` (3d6d20c4) is a peer's in-flight
  bus-MCP change; SOUL Principle 9 forbids racing it.
- **Not committing** the untracked `docs/evidence/morning-task-pass-2026-10-25/`
  and `docs/evidence/weekly-dream-content-2026-10-24.md.tmp` — those belong to
  peers' passes (morning-task-pass, weekly-dream), not to this pipeline.

## Adversarial review

`ops/scripts/orch-bus/adversarial-review.py --cycle-id 13796 --review
--reviewer-id esther` → deepseek/deepseek-v4-pro, verdict **FINDINGS**:
`ADV-0-1 (high, unverified-claim)` — the reviewer received only the path
`/tmp/advrev.txt`, never the content; a bare file path is not a reviewable
artifact. **Finding accepted as valid.** Corrected here: all evidence is inlined
above and the verification is a committed pair of scripts, not a transcript.

## Verification (committed, runnable)

Per the skill's 2026-10-16 rule, the evidence is not prose — it is a PAIR:

- `ops/scripts/manage/verify-orch-skill-lifecycle.sh` — exits non-zero (1) when
  the no-op stops being justified: doctor `Skill drift` not clean, `stranded`
  count > 0, or any reported skill's deployed copy differing from its repo
  source. Exits 2 with an explicit `COULD NOT VERIFY` when a dependency cannot
  be judged (truncated doctor, crashed reconciler, missing script).
- `ops/scripts/manage/test-verify-orch-skill-lifecycle.sh` — the negative
  harness. Induces ONE failure per case and asserts the check notices:
  6 probes, **0 blind spots**, including the case that matters most here —
  a reconciler printing `verdict: PASS` alongside `stranded: 6` must still FAIL
  (the pass condition is the **count**, never the verdict word).
- `tests/test_orch_skill_lifecycle_contracts.py` — the CONTRACT test for the two
  invariants the checker borrows from OTHER components: (a) the doctor's
  run-evidence bar — >=100 non-empty lines AND at least one per-check verdict
  line, measured 518/503 on the live tree; (b) the reconciler's
  `stranded: <int>` output format. Both are asserted against the LIVE components,
  never a copy: a contract test against a stand-in proves nothing about the thing
  that actually runs. Without this file the checker would silently degrade to
  `COULD NOT VERIFY` on every run if either upstream format moved.

The last item exists because the push-time adversarial review refused an earlier
close: ADV-13796-1 (high) and ADV-13796-2 (medium), both `unverified-claim` — a
load-bearing threshold and an output-format dependency asserted with no committed
test. Both were valid; an invariant borrowed from another component is not
verified by the fact that it happens to be true today.

All three were run on the live tree this cycle:

```
$ bash ops/scripts/manage/verify-orch-skill-lifecycle.sh
OK   doctor:
OK   stranded: 0
checking 9 reported skill(s): window=48h
  OK   change-checklist (repo==deployed) ... (9/9 OK)
PASS: no unapplied skill content in the window          (rc=0)

$ bash ops/scripts/manage/test-verify-orch-skill-lifecycle.sh
probes run: 6 · noticed: 6 · blind spots: 0
HARNESS PASS: 6 probes, 0 blind spots                   (rc=0)

$ python3 tests/test_orch_skill_lifecycle_contracts.py
doctor: rc=1 nonempty_lines=518 verdict_lines=503
reconciler: rc=0 stranded=0 (format present)
PASS: both contracts hold on the live tree              (rc=0)
```

Writing the harness caught **three real defects in the checker itself**, each of
which would have made it a blind spot: `rec_rc` referenced after its assignment
was removed (`unbound variable`, rc=1 on EVERY input); a doctor with no per-check
verdict line slipping past the line-count bar; and the checker resolving its
dependencies relative to a copied path. This is the "probe the probe" rule
earning its keep — the first draft looked green on the healthy case and was
wrong on four others.

## Why the deployed-vs-repo drift detector is the detector that matters

Skill parity is measured in both directions: `reconcile-stranded-skills.py`
sees content that exists only on the deployed tree (`stranded: 0` today), while
the doctor's `Skill drift` also sees the repo-ahead direction — a lesson
committed to the repo that no deploy has propagated. Both are clean this run,
which is what makes the no-op defensible rather than merely convenient.

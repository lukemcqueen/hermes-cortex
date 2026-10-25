# Orchestrator morning task pass — 2026-10-25 (evidence)

Evidence for the `orch-task-morning-pass` cron run (07:37 KST, job `f6694d02d29c`,
dispatch `07:37:39`, fire claim `07:38:42`). Host-derived identity: **esther**
(orchestrator). Governance cycle **#13782**, session id
`cron_f6694d02d29c_20261025_073742`.

> ⚠️ **NOT YET COMMITTED — and this pass the *reads* were also gated.** The
> documented read command (`python3 ~/.hermes-cortex/scripts/task-db.py list …`)
> is now refused by the enforcer's two-gate terminal check; see "Gate finding"
> below. The survey was therefore taken from the equivalent MCP surface
> (`tasks.task_list` / `task_list_claimable` / `task_board`), which reports the
> same board. Nothing was bypassed, no lock was fabricated, no gate was weakened.

## What the pass did

| Step | Result |
|---|---|
| Survey pending stories | 3 stories, **all already sliced** (0 unsliced) |
| Survey claimable (`--repo ALL --claimable --limit 50`) | **15** (16 on 2026-10-23) |
| Decompose unsliced stories | **0** — no `add --parent` writes needed |
| Write executable plans into slices | **0 — blocked by the write surface** (unchanged) |
| Dispatch urgent (pr 2-3) worker-lane slices | **0 — deliberate hold** (each reason below) |
| Orchestrator-only work self-claimed | **0** |

Stories (3 stories / 18 open fleet slices = 15 pending + 3 blocked):

- `c579ef95` — Fleet cost <$10/day + halve review queue → 4 slices (2 pending, 2 blocked)
- `82310c5e` — KAESA 90-Day Content Challenge → 6 slices (all pending, sequential)
- `00562f6c` — KAESA Client Engagement (pilot #1) → 8 slices (all pending)

## The one change since 2026-10-23: `[cost/4]` is now `blocked`, on real evidence

Claimable pool **16 → 15**; the only row that moved is `6b7d9b8a` **[cost/4]
Fleet-wide cost coverage — per-host audit-log adapter**, `pending` → `blocked`.
That is the story `c579ef95`'s *only worker lane*, and 2026-10-24 produced the
measurement that blocks it (`docs/evidence/cost4-host-cost-adapter/`):

- The adapter landed and is proven **on esther**: `cron-cost-metrics.py
  --json-summary --since 2026-10-06` → `rc=0`, one JSON object, `rows=1777`,
  `18 days`, `spend.available=True` (`verify.txt`, RED→GREEN over a pinned
  pre-change baseline, `adversarial-verify.py --gate` PASS).
- The EXEC dispatch to the four worker hosts returned **0 of 4 aggregates**
  (`dispatch-2026-10-24.txt`): joseph / kustos / titus answer
  `error: the following arguments are required: --prometheus` — a **stale
  deployed `cron-cost-metrics.py`**, predating `--json-summary`; **gisu** answers
  `Script not found: cron-cost-metrics.py`.
- The UPDATE_REQUESTs meant to ship the new script to those hosts
  **all timed out at 1800 s** (`update-verify-2026-10-24.txt`): the
  bridge-`KillMode` defect — the tick cgroup SIGTERMs the detached UPDATE worker —
  already tracked as pending row **`3c94beac`** (esther repaired and proven at
  `102d7386`; joseph/gisu/kustos/titus still unrepaired).

So `[cost/4]` is blocked on **the fleet update path, not on dispatch**: until
each worker host gets the KillMode repair *and* the new script, another EXEC
round would reproduce 0-of-4. `3c94beac` itself states it is not bus-actionable
(EXEC cannot run the `systemctl --user daemon-reload` half) and needs a helper
script registered in `cortex-update.sh` or an operator pass. **No re-dispatch
this pass** — a 3rd identical round would be noise.

## Gate finding: the documented read path is refused for this cron job

Measured this pass (three probes, no workaround attempted at the enforcer level):

- `ls` / `git log` / `git status` → **exit 0** (read primitives stay lock-free, as documented).
- `python3 ~/.hermes-cortex/scripts/task-db.py list …` from `~` → refused:
  *"No governed repo could be resolved for this call"*.
- Same command with `workdir=~/hermes-cortex` → refused: *"GOVERNANCE LOCK REQUIRED —
  GATE 2 of 2; gate 1 is the skills gate (all 7 always-section skills loaded via
  `skill_view`)"*.

Gate 1 is **unsatisfiable in this job**: the catalog exposes no `skill_view` tool
to this session, and `~/.hermes/cron/jobs.json` shows job `f6694d02d29c` carries
`enabled_toolsets: ["terminal","web","file"]` — **no `skills` toolset**. Same root
cause class as tracker row `482de205` (the reflexion gate), one gate over: an
automated session is required to present proof from a tool it does not have.

Consequence: the pass's step 1 as written ("run the DEPLOYED copy from `~` to stay
lock-free") no longer holds — the deployed copy under `~/.hermes-cortex/` resolves
to the host-canonical `hermes-cortex` repo and demands both gates. The MCP task
surface is the working read path:

`mcp__tasks__task_list(repo='ALL', status=…, include_untagged=true)`,
`mcp__tasks__task_list_claimable(repo='ALL', limit=50)`,
`mcp__tasks__task_board(repo='ALL', include_untagged=true)`.

Board cross-check (identical to the documented queries): claimable **15**,
pending other-kind **13** (7 orchestrator-personal + 6 bare-token
`ISSUES`/`PROPOSAL` rows), stories **3** → 31 pending rows total.

## Held (with reason — not dispatched)

| Slice | Lane | Disposition |
|---|---|---|
| `6b7d9b8a` [cost/4] | worker (4 hosts) | now `blocked`; 10-24 evidence = 0/4 hosts, blocked on `3c94beac` → hold |
| `3c94beac` | fleet update path | needs a `cortex-update.sh` helper or an operator pass; not bus-actionable → hold |
| `40cb307d` [cost/2] | orchestrator | cross-host config change; needs the standing plan review; `plan IS NULL` → hold |
| `ca282975`, `72dc920b` | joseph | dispatched 10-11 + 10-18, consumed, no closure → issue **#86** thrash → hold |
| `c711e28d`/`4f099ae2`/`a40e0282`/`a512e32a`/`0008c2ce` | worker | sequential wk 3-12, gated on Phase 1 (dispatched, consumed) → hold |
| `1e8737fc`, `5c2f135b` | orchestrator | case-study authoring = orchestrator work (task-model-v3 §2.1) |
| `1d09760f`..`cbba59f8` (KAESA 1/6-5/6, pr 1) | worker | below the pr 2-3 bar; slice 1 needs a human stakeholder interview |
| `2fc4d871`, `66914fe1` | — | `blocked`, not pending |

## Step 2 is still not executable: the plan write surface does not exist

Re-measured: the deployed `~/.hermes-cortex/scripts/task-db.py` (mtime
2026-10-24 23:38) contains **no `--plan`** — the only occurrence of `plan` is a
read (`"COALESCE(t.plan, '')"` at line 981). Writing plans by raw SQL remains
forbidden (bypasses the single write path). Tracked as row `9fb2ddb6`
(adversarial review before building, per Luke's standing rule). The one path that
*can* carry a plan today is the dispatch envelope:
`inbox_send_task(..., plan="…")` — used by no slice this pass, because nothing
new was dispatchable.

## Standing state

Claimable pool 16 → 15, and the movement is a **legitimate block**, not progress:
18 open fleet slices, 0 closed today, 0 decomposed. The bottleneck is still
structural (no cross-host row transport; no hand-out/plan write path), and the
cost story's remaining unblocked lane is now provably gated on the fleet bridge
repair (`3c94beac`). No new issue row opened — both gaps are already tracked.

## Re-run

```bash
# documented path — EXPECT a refusal on this job (gate 1, no skills toolset):
python3 ~/.hermes-cortex/scripts/task-db.py list --repo ALL --claimable --limit 50
# working path:
#   mcp__tasks__task_list_claimable(repo='ALL', limit=50)   # expect claimable: 15
#   mcp__tasks__task_board(repo='ALL', include_untagged=true)
#   expect: claimable 15, other-kind 13, stories 3
# deployed esther copy carries the adapter (measured 2026-10-25: 4 matches):
grep -c -- '--json-summary' ~/.hermes-cortex/scripts/cron-cost-metrics.py   # expect >0 on esther
```

Read-only on the live bus and on the task DB: **no sends, no probes, no task-db
writes** this pass.

## Artifacts

- `README.md` — this file
- `survey-claimable-2026-10-25.txt` — today's claimable pool (MCP surface)
- `delta-vs-2026-10-23.txt` — the pool diff (16 → 15, the only change)
- `captured-at.txt` — capture timestamp

## Open item for the operator

1. Job `f6694d02d29c` needs either the `skills` toolset added (so gate 1 is
   satisfiable) or an audited automated-session path through the terminal gate;
   until then the documented step-1 read command cannot be run by this job.
2. `3c94beac` (fleet bridge KillMode rollout) is now the gating item for the
   cost story — it needs a `cortex-update.sh` helper or an operator pass.

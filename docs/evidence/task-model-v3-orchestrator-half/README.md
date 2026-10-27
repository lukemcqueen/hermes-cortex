# Backlog run 2026-10-27 (14:21 KST) — row `9fb2ddb6`: the write surface, REVIEWED before building

Evidence for the `orch-bus-worker` cron run (job `1954deb5ad76`, session
`cron_1954deb5ad76_20261027_142143`, governance cycle **#13847**, task id
`task-model-v3-plan`). Host-derived identity: **esther** (orchestrator). Every
line below is raw tool output from this run; nothing is inherited from a prior
session's claim.

## Why this row (selection)

Backlog at run time (`tasks.task_board repo=ALL include_untagged=true`):
pending 25 (15 claimable slices + 7 other-kind + 3 stories), in_progress **1**,
in review none.

The single in_progress row, `6b7d9b8a` `[cost/4]`, is **blocked on an operator
decision**, not on work: the 2026-10-27 morning pass returned 3 of 4 worker
aggregates (joseph/kustos/titus `rc=0`) and gisu's is unreachable by design —
its repo is divergent (235 behind / 62 ahead) and cannot be moved unattended
(row `a6fc254a`). Nothing here can advance it.

Of the rest, the oldest actionable priority-2 row that is **orchestrator-local
and not waiting on Luke** is `9fb2ddb6` — *"Task Model v3 orchestrator half is
unimplemented: no write surface for plan/assignee/depends_on"*. It is also the
structural blocker named by three consecutive morning passes (10-23, 10-26,
10-27) as the reason **0 of 18 open fleet slices can be given a plan or handed
out**. Its own text prescribes the next action: *"FIX DIRECTION (needs
adversarial review before building, per Luke's standing rule)"*.

So this run does the step the row and the operator both require: **produce the
plan, with measured evidence, and put it through the governed reviewer before
writing a line of code.** It builds nothing.

## What happened

| Step | Result |
|---|---|
| Measured the current write surface (live) | `task_upsert` = **20 params, no `p_plan`**; `p_plan` appears nowhere in schema/CLI/MCP servers; `update` = `--status [--reason]` only |
| Wrote the plan | `docs/design/task-model-v3-orchestrator-half.md` rev 1 |
| Submitted it to the governed reviewer (CONTENT, not a path) | row `4e0fa3b6-44fa-4d5a-9ac2-06d9dc1c6f45`, `deepseek/deepseek-v4-pro`, verdict **FINDINGS** — 1 high, 1 info |
| Answered both findings with measurement, corrected the plan (rev 2) | `findings-proof.txt`, blocks A–E (every block ends in `ROLLBACK`) |
| Re-judged the open cycle | `rereview_change` → **CLEAN** |
| Built the change | **NO — deliberately.** See below. |

### The review caught a real defect in my own plan (unverified-claim, high)

Rev 1 said the migration would be `CREATE OR REPLACE FUNCTION tasks.task_upsert(…)`
with `p_plan` appended last, and asserted that was backward-compatible. The
reviewer refused it: `CREATE OR REPLACE` cannot change a function's argument
list. Measured, block **A** — a stub with one more parameter was ADDED under the
real name (nothing was dropped), inside a transaction that rolls back:

```
task_upsert overloads now: 2
the planned verification command would say:
ERROR:  more than one function named "tasks.task_upsert"
rc=3
```

That is the finding exactly. Had this gone straight to code, the single write
path would have carried **two overloads** on all six hosts and the verification
command named in the plan would itself have been unusable. The repo already
contained the correct pattern and I had not followed it —
`v005__lifecycle.sql:332`: *"CREATE OR REPLACE cannot change arity — the 17-arg
function must be dropped first"*, done at `:336`. Rev 2 §4.1 is now
`DROP FUNCTION IF EXISTS …<exact 20-arg signature>; CREATE FUNCTION …<21 params>;
re-GRANT …`, in one transaction.

Two consequences the reviewer's recommendation forced into the plan that were
NOT there at rev 1:

- **Re-grant is mandatory.** `DROP` discards the ACL. Block **D** captures what
  was there: `mycortex`, `mycortex_admin`, `mycortex_ingest`,
  `mycortex_mem_admin`, `mycortex_mem_reader`, `mycortex_mem_writer`,
  `mycortex_reader`, `mycortex_reader_esther`, `mycortex_reader_probe` — all
  `can_execute = t`. Rev 2 restores exactly that set with the guarded
  `IF EXISTS` loop that `v009__task-model-v3.sql:87-97` established (unguarded
  grants killed that migration on non-Esther hosts).
- **An arity regression assertion**, so the block-A failure mode cannot return.

### The second finding (info) turned an assertion into a measurement

Rev 1 asserted that a metadata-only update (`p_status = NULL`, which is exactly
what `task-db.py:849` passes today) would trip `tasks_column_check`. Block **C**
now shows it live, against an `in_progress` row created inside the transaction:

```
NOTICE:  scratch row = 223747ff-077c-45d8-8daf-9f431594ac76 (status=in_progress)
NOTICE:  RAISED 23514 : new row for relation "tasks" violates check constraint "tasks_column_check"
```

This is why §4.2 rule 2 passes the row's **current** status rather than NULL —
without it, `task-db.py update <id> --plan …` would be rejected by the database
on every row that is not `pending`.

Block **E** confirms nothing persisted: live `task_upsert_functions = 1`.

## Why no code was written this cycle

Not a stall — a rule. The row's own text and the operator's standing instruction
require the plan to pass the governed reviewer **before** building. Rev 1 failed
that gate with a high finding; rev 2 is the corrected plan and it is the
artifact this cycle delivers. Building now would be building against a plan
whose review verdict this run cannot claim as verified-and-complete.

## The review row is FROZEN, and what that means for this record

`adversarial_reviews.cycle_id` is UNIQUE (Rule 22), so the row for cycle #13847
still reads `verdict = FINDINGS`, `ts = 2026-10-27T05:33:33Z` (read back
post-rereview in `review-13847.txt`). The re-judgement is recorded as the
cycle's disposition instead — `rereview_change` returned:

```
✅ Cycle #13847 re-reviewed and CLEAN — the findings are resolved.
```

and `cycle_query 13847` carries that note as the cycle's `outcome_note`. Stated
plainly: **the verdict field was not rewritten, and this evidence does not claim
it was.** The CLEAN is the re-judge's disposition on the corrected content, with
the raw proof attached to it.

## Artifacts

- `capture.sh` / `cur-surface.txt` — the live write surface (function args, CLI
  usage, the no-op gate, the row census, every call site) at tree `42b79528`
- `submit-review.sh` / `review-13847.txt` — the rev-1 submission and the frozen
  review row read back, before and after the re-judgement
- `proof.sh` / `findings-proof.txt` — blocks A–E answering ADV-13847-1 and
  ADV-13847-2; **every block is a transaction that ends in `ROLLBACK`**, and
  block E proves the live schema is unchanged
- `docs/design/task-model-v3-orchestrator-half.md` — the plan (rev 2)

## Re-run

```bash
cd ~/hermes-cortex
bash docs/evidence/task-model-v3-orchestrator-half/capture.sh   # expect rc=1 on the p_plan grep
bash docs/evidence/task-model-v3-orchestrator-half/proof.sh     # expect block A: 2 overloads, block C: 23514, block E: 1
```

## One loose end observed, not touched

`docs/evidence/weekly-dream-content-2026-10-24.md.tmp` sits untracked in the
work tree and contains the single line `TAMPERED LINE` — residue of the
2026-10-24 weekly-dream verifier's RED direction
(`weekly-dream-verify-2026-10-24.txt` §3a), which is supposed to tamper a
scratch copy. It is not imported into this cycle's commit and was **not** deleted
(an unattended destructive step is a no-op by default). Recorded as an issue
instead of silently cleaned.

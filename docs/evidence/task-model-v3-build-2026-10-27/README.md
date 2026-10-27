# Backlog run 2026-10-27 (22:2x KST) — row `9fb2ddb6`: the write surface, BUILT

Evidence for the `orch-bus-worker` cron run (job `1954deb5ad76`, session
`cron_1954deb5ad76_20261027_222139`, governance cycle **#13866**, task id
`task-model-v3-build`). Host-derived identity: **esther** (orchestrator).
Every line is raw tool output from this run.

## Why this row (selection)

The 14:21 run of this same cron (cycle **#13847**) delivered the **plan** for row
`9fb2ddb6` — reviewed, one high finding fixed, re-judged CLEAN — and
deliberately built nothing, because the operator's standing rule is *review the
plan before building*. The plan being CLEAN and unchanged, the next step is the
build. So this run builds it.

Of the rest of the pool: the other `in_progress` row (`6b7d9b8a`, `[cost/4]`) is
blocked on an operator decision (`a6fc254a`, gisu's divergent repo), and the
three stories are all already sliced. `9fb2ddb6` is the structural blocker three
consecutive morning passes named as the reason **0 of 18 open fleet slices can
be given a plan or handed out**.

## What changed

| File | Change |
|---|---|
| `ops/services/tasks/schema/v016__task-upsert-plan.sql` | **NEW.** `DROP FUNCTION tasks.task_upsert(<exact 20-arg>)` then `CREATE FUNCTION …21 params…` with `p_plan` appended LAST, re-granting the measured holder set in a guarded `IF EXISTS` loop — one `BEGIN; … COMMIT;` |
| `ops/scripts/manage/task-db.py` | `V5_MIN_SCHEMA=16` + `_require_v5`; `UPSERT_SQL` gains the 21st slot; new `UPSERT_META_SQL` for metadata-only writes; `cmd_add(plan=…)`; `cmd_update` rewritten — `--status` optional, plus `--plan/--assignee/--depends-on/--correlation-id`, with a post-write read-back recheck |
| `ops/scripts/cortex-update.sh` | v016 added to the register map (**the register map IS the deploy** — without this line no other host can ever reach v016) |
| `tests/test-tasks-schema.sh` | AC-L1-26: single-overload / 21-param / round-trip / coherence / trap / grant assertions |
| `tests/test_task_db_unit.py` | 12 new tests; the shared-UPSERT pin updated for the 21st slot |

## Evidence

### RED → GREEN, schema battery (`tests/test-tasks-schema.sh`)

The new block's RED run is the pre-change tree (v016 file moved out of
`schema/` for the duration): `red-before-v016.txt` → **130 passed, 4 failed**,
all four in AC-L1-26 (arity, round-trip, coherence, the NULL-status trap).
GREEN (`green-after-v016.txt`) → **134 passed, 0 failed**. Baseline before this
change was 127 — the block adds 7 assertions, 3 of which are regression guards
that are expected to hold on both sides (`exactly one overload`, the grant
read-back, the reader-call check).

### RED → GREEN, unit suite (`tests/test_task_db_unit.py`)

`unit-red-before.txt` → **13 failed, 80 passed** against the pre-change CLI
(the run is hermetic: the pre-change `task-db.py` was restored from `HEAD` for
the duration, then the changed copy put back — `git diff --stat` confirms it).
`unit-green-after.txt` → **100 passed, 0 failed**, including `test_task_db_v4.py`.

### Live round trip (`live-roundtrip.sh` → `live-roundtrip.txt`)

Against the LIVE store, through the CLI, every value read back with an
independent psql query:

- `add --plan 'step one; step two'` → row reads back `pending | col=todo | plan=step one; step two`.
- `--status in_progress` → `in_progress | col=in_progress` (ordinary lifecycle unchanged).
- **metadata-only** `update <id> --plan … --assignee joseph --correlation-id … --depends-on <uuid>` on an `in_progress` row → `in_progress | col=in_progress | plan=revised plan; more detail | assignee=joseph | corr=corr-rt-v016 | deps=1`.
  The §3 trap: the write carries the row's CURRENT status, so `column` stays
  coherent. Section 6 of the transcript proves the trap is *real* — the same
  call with `p_status` omitted still fails inside `task_upsert`.
- **same-status + metadata** is not swallowed by the no-op gate (it was, before).
- Four honesty gates refuse: empty update, blank `--plan`, bad `--depends-on`
  uuid, path-smelling `--assignee`.
- **The hand-out claim (plan §4.3) is verified**: a pending slice assigned to
  `joseph` appears in `list --assigned` and is correctly absent from the
  claimable pool. (First attempt at this check was wrong — the view prints
  `id[:8]` while the check grepped the full uuid; corrected in §8b, not
  reported as a defect.)
- Cleanup: both scratch slices cancelled, and the scratch story auto-completed.

## Corrections to the plan, made from measurement (not from memory)

1. **The re-grant is defence-in-depth, not a repair.** The plan (§4.1, and the
   review's ADV-13847-1 note) says a `DROP` "discards the ACL" and the re-grant
   is therefore mandatory. Measured on host esther: `proacl` on
   `tasks.task_upsert` is **NULL** — the DEFAULT acl, i.e. EXECUTE to owner and
   PUBLIC — so the ten roles that hold EXECUTE hold it *through PUBLIC*, and a
   freshly created function gets the same default back. The re-grant is still
   included (it re-asserts the measured set, so a later revocation of PUBLIC
   cannot silently lock the writers out) but the migration says what it is.
   **No ACL regression occurred, and none is claimed.**
2. **The live DB was already at v016 before this run's own `--apply-schema`.**
   See the finding below — it is not a mystery left open.

## FINDING (recorded, not silently absorbed): the doctor applies the REPO tree's migrations to production

At `2026-10-27 13:25:35Z` — ~50 s after the v016 **file** was written and before
it was committed, before it was registered, and while the DEPLOYED schema dir
still ended at v015 — the LIVE `mycortex` database went to schema version 16
(`tasks.schema_version`: `16 | 2026-10-27 13:25:35.338611+00 | mycortex`).

Cause, located and reproduced:

- `ops/scripts/manage/cortex_doctor/checks.py:5354` — `check_task_lifecycle_v2`
  runs `task-db.py --apply-schema` **as a health check** (timeout 120). The
  doctor runs on every `agent-message-handler` tick (every 5 min).
- `task-db.py`'s `cmd_apply_schema()` resolves `migrate.py` by *candidate list*,
  and `Path.home()/"hermes-cortex"/ops/services/tasks/migrate.py` — the **repo
  working tree** — is preferred over the deployed copy. `migrate.py` discovers
  migrations **by file** in its own sibling `schema/`, and defaults to the
  `mycortex` database.

Consequences, each measured rather than argued:

- A **check mutates production schema**. (This is the same class of defect that
  `ops/scripts/manage/task-queue-evidence.py:116` already documents —
  "`--apply-schema` MUTATES" — but the doctor still calls it.)
- It **bypasses the register map**. `cortex-update.sh:446` states the contract:
  *"The register map IS the deploy. migrate.py discovers migrations by FILE —
  the repo applying cleanly proves nothing about any other host."* The doctor
  path makes the repo working tree authoritative for DDL on that host, so an
  **uncommitted** migration reaches production.
- It is host-asymmetric: a host whose repo tree is dirty or ahead applies DDL
  the fleet has never reviewed.

Reproduction performed this run (production-safe, `--db-name <scratch>`):
`v017__probe-noop.sql` written, `python3 ops/services/tasks/migrate.py --db-name
tasks_dbg2` → `tasks_dbg2` went 15→17 while **`mycortex` stayed at 16**. So the
runner itself honours `--db-name`; the leak is specifically the doctor's
default-database, repo-path invocation. The probe file was deleted immediately
after the measurement.

**Not fixed this cycle.** Fixing it means changing the doctor's DDL behaviour
(and probably `cmd_apply_schema`'s candidate order) — a separate, reviewable
change that belongs with its own plan; changing an enforcement/health check
under the same cycle as a schema change is exactly what `enforcement-change-safety`
warns against. Recorded as a governance issue.

## What this change does NOT do (reported, not silently dropped)

- **The MCP surface** (`mcp-servers/task-mcp.py`) still exposes no `plan` /
  `assignee` / `depends_on` write — the plan scoped §4.2 to the CLI. An agent
  reaching for the MCP tool cannot write a plan yet.
- **Cross-host row transport** — the second half of `9fb2ddb6`'s "fleet-scope
  slices are invisible to workers". Unchanged; it is the git-backed transport
  roadmap, not a write-surface change.
- **Fleet hosts are still at v015.** They need `cortex-update.sh` (now that
  v016 is registered) to gain the 21-arg function. Until then `--plan` fails
  cleanly with `requires tasks schema v16+` — the `_require_v5` gate — rather
  than a raw `function does not exist`.

## Re-run

```bash
cd ~/hermes-cortex
bash tests/test-tasks-schema.sh                        # expect 134 passed, 0 failed
/home/esther/.hermes-cortex/venv/bin/python -m pytest tests/test_task_db_unit.py tests/test_task_db_v4.py -q
bash docs/evidence/task-model-v3-build-2026-10-27/live-roundtrip.sh
```

# Review-Queue Diagnosis — 2026-10

**Task:** `[review/1]` (task `90b30c9c`), second half of story `c579ef95`
("Fleet cost under $10/day avg + **halve review queue**").
**Scope:** DIAGNOSE ONLY. Per the slice's own bound, no review-pipeline
automation is built here; fix paths are proposed, not implemented.
**Measurement window:** 2026-10-14, read-only SQL against the local `tasks`
schema (`schema_version` = 12) on the orchestrator host, plus `task-db.py`
CLI reads.

## Provenance

Every number below comes from a read-only query run against the live store.
The query set and its verbatim output are committed beside this file as
`docs/evidence/backlog-run-2026-10-14-triage.txt`. Volatile by design: the
census is a point-in-time snapshot, so re-running the queries later will
produce different counts for the *live* rows — the historical facts (the
review-queue zero, the archive composition) are stable.

## Run scope (what this cycle did and did not do)

This was a backlog-run cycle whose top actionable task was a LOCAL DIAGNOSIS
(`[review/1]`), not a fleet action:

- **Done:** pulled pending + in_progress; classified every live row; worked the
  top actionable slice; cancelled and archived the 3 stale `doctor-probe` rows;
  delivered this document and its evidence artifact.
- **Not done, deliberately: no `EXEC` was dispatched over the bus.** No pending
  task had an `EXEC <script>` / diagnostic-on-a-remote-host shape, and the
  orchestrator contract forbids dispatching fleet commands no task asks for.
  An unsolicited EXEC sent to satisfy a cycle description would be traffic,
  not work.
- **Not done, per the slice's own bound:** no review-pipeline automation. The
  fix paths below are proposed, not implemented.
- **Blocked, needs the operator:** the 51-day stale claim `1e8737fc`, the KAESA
  duplicate-ownership decision, and the store-level archive/audit-trail change.

**Prior attempt, stated rather than left silent.** Cycle 12614 was REFUSED at
close as scope-drift — its task id claimed the F-023 backlog-driver deliverable
while the change was a diagnose-only doc — plus two evidence gaps. Those gaps
are fixed in the evidence artifact (the dwell query is now constrained to the
`pending → in_progress` transition; the "legal but unused status" claim is
evidenced from the live constraints), and the work was re-framed under this
correctly-named cycle. The refused commit is inside this range. That is a fixed
finding, not a laundered one: a refused cycle whose work reappears under a new
name is exactly what a hollow receipt looks like, so it is named here.

## The headline: there is no review queue to halve

The slice asks for slices that "sat in `review` >24h". **No row on this host
has ever entered `review`, in any of the three tables that could record it.**

| Where | Rows ever in `review` |
|---|---|
| `tasks.tasks`, `status = 'review'` | 0 |
| `tasks.tasks`, `"column" = 'review'` | 0 |
| `tasks.task_archive`, `status = 'review'` | 0 |
| `tasks.task_archive`, `"column" = 'review'` | 0 |
| `tasks.task_events`, `to_status = 'review'` | 0 |
| `tasks.task_events`, `from_status = 'review'` | 0 |

This is not a broken queue — the machinery is present and the path is open:

- `review` is a legal status (`tasks_status_check` admits it) and a legal
  column (`tasks_column_check` admits `review` for status
  `pending`/`in_progress`/`review`).
- The transition matrix **permits** the arc: `transition_allowed('in_progress',
  'review')` returns true.
- The writers exist: `tasks.report_done()` (worker marks done, slice →
  `review`) and `tasks.verify_slice()` (orchestrator-only, `review` →
  `completed`).
- **Neither has ever been called.** The only two event types recorded in the
  whole history are `created` (43) and `status_changed` (41). There is no
  `report_done`/`verify_slice` event of any kind.

So the queue is **idle, not blocked**. Nothing was ever submitted for
verification, which means nothing could pile up in it and nothing can be
halved by working it. The "halve the review queue" half of the story has no
subject on this host.

## What is actually backing up: the parked class

Census of the live store at measurement time (46 rows):

| Status | Count |
|---|---|
| `pending` | 25 |
| `paused` | 18 |
| `waiting` | 2 |
| `in_progress` | 1 |
| `review` | 0 |

Classification of those 46 rows against the slice's own taxonomy:

### Parked — 18 rows (dominant class)

All 18 are `project = hermes-cortex`, all `priority = 0`, and all carry
`untrusted = true` (they were minted from inbound PROPOSAL / ISSUES content).
The auto-pause signature is unmistakable — dwell time between the
`pending → in_progress` event and the `in_progress → paused` event:

- 16 of 18 sit in the band **60.1–65.0 minutes**
- 2 are shorter (30.5, 25.5 minutes)
- age at measurement: **2.3 to 44.5 days** paused

That is a session-TTL park, not a decision: a cron session claims a slice,
runs out its hour, and the slice is left `paused`. Nothing resumed them.

The transition to return them was made legal by migration
`v012__parked-rows-return-to-pool.sql` — `paused → pending`, `blocked →
pending`, `waiting → pending` — whose own header records that the same thing
was found and hand-cleaned once before ("Observed directly while cleaning up
six rows parked since 2026-08-23 … `ERROR: illegal task transition: waiting ->
pending`"). The arc exists; **nothing calls it**. The manual cleanup was not
turned into a routine, so the class refilled to 18.

### Parked (legitimate dependency) — 2 rows

`[cost/2]` and `[cost/3]`, both slices of this same story, are `waiting` on
`[cost/1]`. Worth noting: **`depends_on` is empty on all four cost slices.**
The dependency is carried in the prose of the task body only, so no query can
see it and nothing can auto-resume when the blocker clears. That is why they
sit in `waiting` rather than being recognised as blocked-by-a-named-task.

### Stale — 3 rows (test residue), now resolved

Three `pending` rows whose content is literally `doctor-probe <hex>` and whose
`source = 'doctor-probe'` (created 2026-10-14 10:25Z, 10:30Z, 10:35Z). These
are leaked rows from the doctor's own Task-DB write-probe: `check_task_db()`
seeds a probe row, then walks it `in_progress → completed → archive`, and
reports `PASS` — but it never checks the exit code of those three cleanup
calls, so a failed cleanup still reports a passing probe.

**Action taken in this cycle:** all three cancelled with reason `stale` and
archived (`save-end` → "Archived 3 completed/cancelled task(s)"). Post-state:
live rows matching `doctor-probe %` = 0; the three rows are in
`task_archive` with `status = 'cancelled'`. Live census after triage: 43 rows
(pending 22, paused 18, waiting 2, in_progress 1).

### Stale claim — 1 row

`1e8737fc` (`Case study + client-sales artifacts`, a `kaesa-engagement` slice)
has been `in_progress` since 2026-08-23 22:08 — **51 days** — with
`session_id = NULL`. No session holds it; it is claimed but not being worked.
Not released here: releasing another workflow's claim is a decision for the
story owner, not a diagnostic action.

### Duplicate / overlapping — 3+ rows (needs a de-dup decision)

The two KAESA stories overlap on three deliverables:

| `kaesa-engagement` slice | overlaps with `kaesa-90day` |
|---|---|
| `[3/6]` content engine (IG/TikTok/YouTube pipeline) | Phases 1–6, the 12-week content sprint |
| `[4/6]` email automation (welcome sequence, cadence) | Phase 3 "email welcome sequence live" |
| `[5/6]` analytics dashboard (followers, engagement, signups) | Phase 6 "performance review (followers, engagement, signups, sales)" |

Presented as an overlap to decide, not as a defect: both stories are live, and
which one owns each deliverable is a product call.

### Mis-projected — 7 rows (data integrity)

Seven slices carry a `project` that disagrees with their parent story's:

| Slice | slice project | story project |
|---|---|---|
| `72dc920b` Phase 1 Foundation | `hermes-cortex` | `kaesa-90day` |
| `ac53a833` `[2/6]`, `02c20c1a` `[3/6]`, `17471ede` `[4/6]`, `cbba59f8` `[5/6]`, `5c2f135b` `[6/6]` | `hermes-cortex` | `kaesa-engagement` |
| `1d09760f` Slice 1 discovery audit | `hermes-cortex` | `kaesa-engagement` |

Consequence: the `hermes-cortex` backlog count is inflated. Of the 17
`pending` rows filed under `hermes-cortex`, **7 are KAESA slices** — so the
repo's apparent backlog is 10 rows, not 17. Any "work the backlog" pass sorts
on this number.

## A finding that changes what the archive can be trusted for

`tasks.task_archive` holds 14,694 rows, but the composition is not a work
ledger:

| `source` | rows |
|---|---|
| `doctor-probe` | 13,858 |
| `manual` | 712 |
| `inbox` | 111 |
| `session` | 9 |
| `governance` | 3 |
| `dream` | 1 |

**94.3% of the archive is the doctor's own write-probe** (a 5-minute cadence).
The real work ledger is 836 rows. Any historical metric computed over
`task_archive` — completion rate, throughput, "how long did things take" — is
measuring the health check, not the work.

Two consequences measured in the same pass:

1. **Archiving destroys the audit trail.** `task_events` holds 84 rows: 84
   belong to *live* tasks, **0 to archived tasks**, 0 orphans. Archiving
   deletes the row from `tasks.tasks` (see `task_archive_old`), and the
   cascade takes its events with it. Measured directly: the three `stale`
   cancellations above each printed the CLI's success tick and each landed in
   the archive with a fresh `status_changed_at` — and `task_events` gained
   **zero** rows, with the `--reason` text stored nowhere. The reason a task
   was cancelled is unrecoverable the moment it is archived.
2. **`save-end` archives by `created_by`**, so a `--reason`-carrying
   cancellation is only auditable in the window between the update and the
   next `save-end`.

## Cheapest remedy (proposed only — not implemented)

Ordered by cost, cheapest first. Nothing here is built by this cycle.

1. **Do nothing to the review pipeline.** It is idle, not blocked. Building
   review automation would automate a path no row uses — which is exactly the
   scope-crossing change this slice forbids.
2. **Return the 18 parked rows to the pool** — one `paused → pending` pass,
   which `v012` already makes legal. This is the whole of the available queue
   reduction: 18 → 0, with no pipeline change. Then make it a routine, because
   the same cleanup was done by hand once already and the class refilled.
3. **Stop the source.** Whatever parks a slice at session end should return it
   to `pending` (or leave it `in_progress` with a heartbeat) instead of
   `paused`. Without this, step 2 is a treadmill.
4. **Cancel the leaked doctor-probe rows and make the probe's cleanup honest** —
   check the exit code of the three cleanup calls and fail the probe when the
   row does not actually leave `pending`. Otherwise every doctor run that
   cannot clean up leaves a permanent backlog row.
5. **Correct the 7 mis-projected slices** so the per-project backlog count is
   honest. Cheap, and it stops the backlog pass from mis-sorting.
6. **Record real dependencies in `depends_on`** for the cost slices so
   `waiting` becomes machine-readable.
7. **Escalate the archive/audit-trail finding** (94% probe residue + events
   destroyed on archive) as its own upstream change — it is a store-level
   property, not a queue one, and it silently degrades every historical metric
   the fleet computes.

## What this diagnosis does NOT claim

- **No fleet-wide claim.** Task rows are locally present only; this is the
  orchestrator host's store. Another host's `review` queue is not measured
  here and is not inferred.
- **No cause claimed for the missing events.** The three cancellations
  produced no `task_events` row. Whether the event was never written or was
  removed with the archived row is not distinguished by this run — both leave
  the same signature. The `task_events`-for-archived-tasks count of 0 is
  consistent with either.
- **No claim that `review` is unused fleet-wide**, only that it is unused in
  the history this host can see.

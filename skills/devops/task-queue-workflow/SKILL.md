---
name: task-queue-workflow
version: 1.0.0
category: devops
description: "Use when claiming task-db slices under task model v3."
author: Hermes Cortex
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tasks, task-model-v3, orchestrator, worker, claim, verify, review, board]
    related_skills: [orch-bus-worker, postgres-schema-design, loop-governance, change-test-loop]
---

# Task Queue Workflow — Task Model v3 (orchestrator-intelligence / worker-execution)

## When to Use

- Any agent claiming or executing a slice from the task queue
- Orchestrators decomposing stories, dispatching, or verifying completions
- Reading the task board or daily digest
- Design: `docs/design/task-model-v3.md`; schema: `ops/services/tasks/schema/` (a version-gated runner; the highest `vNNN__` file present wins — see the migration pitfall below)

## The Model

Two tiers, not role-locked domains (Luke 2026-08-24):

- **Orchestrators (esther/moses) = the intelligence layer** — decompose
  stories → planned slices, dispatch urgent work, VERIFY every completion.
  Strategy/research/verification/case-study authoring are orchestrator work.
- **Every other agent = a general worker** — may claim and execute ANY slice
  (build, refactor, research, docs, infra). No role-lock.
- A worker may claim any pending slice; **only the orchestrator may verify**.

## Lifecycle

```
pending → (claim) → in_progress → (report) → review → (verify) → completed
              └── (unclaim) ──┘                    └── (verify --reject) → in_progress
```

- `review` = worker-done-AWAITING-VERIFICATION. **Not done, and nothing completes it for you.**
  Verification is enforced in the DB rather than by convention: `tasks.verify_slice` is SECURITY
  DEFINER with a moses/esther allowlist INSIDE the function, and no other profile holds EXECUTE on
  it — so a worker's `permission denied for function verify_slice` is permanent. It is not a retry
  hint, and it is not a signal that someone else is about to act. The scheduled orchestrator pass
  is what drains the queue, so **confirm that pass exists on the host** (`hermes cron list`) rather
  than assuming the documented schedule is installed: where it is absent, paused, or never fires,
  the slice sits in `review` indefinitely. So follow up in the SAME breath as the report — name the
  slice id and its evidence to moses/esther (bus, or escalate for a decision only the operator
  holds) — instead of stopping at `report` and waiting. A slice stuck >24h in review gets
  auto-re-queued by the handler's stale sweep (Arm 3) — never auto-completed.
- **A description that names WHO may run a tool, without naming WHAT refused the caller or what to
  do next, invites the reader to assume a passive actor will do it.** Agent-facing text (tool
  descriptions, check messages, warnings) must state the enforcement and the next ACTION: "only the
  orchestrator may run this, and no job does it automatically — report, then hand the slice over",
  never a bare label like "ORCHESTRATOR-ONLY". An agent that reads the label as "someone will pick
  this up" stops working on a slice nobody is coming for.
- **The tasks store is HOST-LOCAL, so a peer's stuck slice is NOT yours to verify.** The grants are
  per-profile roles inside EACH host's own store, so `--board --repo ALL` lists only YOUR host's rows:
  measured, an agent elsewhere reported a slice stuck in `review` while this host's fleet-wide board
  read `In review: none`. "An orchestrator will clear it" is therefore true only where a verifier
  identity EXISTS on that host, and the drain has to be installed PER HOST — a sweep running here
  cannot reach a peer's store, and routing their slice to a remote orchestrator is not a mechanism
  that exists. Do not promise a peer host will act, and do not offer to verify it yourself: say which
  host must clear it, and for a host with no verifier identity escalate to the operator.
- **Widening WHO may verify is a SCHEMA decision, never a config tweak.** The EXECUTE grant AND the
  `profile_of` allowlist inside the SECURITY DEFINER function both have to change — `transition_allowed`
  is role-agnostic, so it does not gate this at all and reading it will not tell you who may verify.
  And the tempting shortcut is the wrong shape: letting a worker complete its OWN slice deletes the
  reason `review` exists, because self-graded work then becomes indistinguishable from verified work.
  Prefer provisioning a verifier identity per host over relaxing the rule.

## Worker commands (any agent)

```bash
task-db.py list --claimable                    # the worker queue: pending slices, no assignee, by priority
task-db.py claim <slice-id>                    # atomic pending→in_progress, assignee=me (self-only)
task-db.py unclaim <slice-id> --reason "<gap>" # return to pending (blocker, tool gap) — never fake progress
task-db.py report <slice-id> --evidence "<test output / measured numbers>"
                                               # in_progress→review, awaiting orchestrator verify
```

- Execute the orchestrator's PLAN (written in the slice content), don't
  improvise strategy. Too big or lacks a tool → unclaim with the gap named.
- Report with EVIDENCE, not prose (test output, measured numbers).

## Orchestrator commands (esther/moses only)

```bash
task-db.py verify <slice-id> --approve --note "<what was checked>"
task-db.py verify <slice-id> --reject --note "<the gap>"   # → back to in_progress
task-db.py list --board                                     # counts + per-agent + review queue
task-db.py list --board --repo ALL                          # the FLEET view (explicit)
```

- **Never trust a self-reported done.** Verify the evidence is real (test
  output, measured numbers) before approving.
- Reject with the gap named — the slice returns to in_progress for the worker.
- **Task queries are repo-scoped, STRICT by default** (2026-10-19): `list`,
  `pending`, the claimable/handed-out pools and `--board` show the CALLER's repo
  and NOTHING else — untagged (pre-tag) rows are excluded, because when the store
  is mostly untagged a scoped query returned the whole fleet backlog (the "too
  broad" report from a pi session). Two explicit switches widen it:
  `--include-untagged` (your repo + the untagged rows — use this when you are
  scanning the pool for untagged FLEET slices) and `--repo ALL` (the
  orchestrator's fleet-wide view; omitting the parameter is never the fleet
  view). A session whose repo cannot be resolved gets NOTHING, by design.
  A task you ADD with no `--repo` inherits your session repo, so it stays
  visible in your own strict view.

## Automated layers (no manual action needed)

- **orch-task-morning-pass** — 07:00 KST: decompose stories → planned slices,
  dispatch urgent via bus.
- **orch-task-evening-pass** — 19:00 KST: verify all review slices.
- **Stale sweep Arm 3** (agent-message-handler): review >24h → verify(false,
  'verify-stale') re-queues to in_progress.
- **Daily digest + board query** satisfy the visibility requirement (Luke:
  "1) visibility for tasks easily viewable 2) agents working truly
  autonomously and efficiently").

## Board maintenance — "how old is this task?" / "should we drop it?"

To answer age/staleness questions, the board MCP (`task_board`/`task_list`/
`task_pending`) and `task-db.py list` do NOT surface timestamps — query the
Postgres store directly with the read-only reader role:

```bash
docker exec -i mycortex-postgres psql -U mycortex_reader_<profile> -d mycortex \
  -F'||' -c "SELECT status, kind, priority, left(created_at::text,10) AS created, \
  left(status_changed_at::text,10) AS last_chg, \
  round(extract(epoch from now()-created_at)/86400) AS age_days, left(content,60) \
  FROM tasks.tasks WHERE status NOT IN ('completed','cancelled') AND \
  (kind IN ('story','slice') OR kind IS NULL) ORDER BY created_at;"
```

- Reader role = `mycortex_reader_<profile>` (never superuser); container
  `mycortex-postgres`; database `mycortex`; table `tasks.tasks`. Age columns
  `created_at` (age) and `status_changed_at` (last state move — use this, not
  `updated_at`, to see real movement since a row's `updated_at` updates on any
  touch). The board's in_progress count is a snapshot; the table is the truth.

**Drop decision — classify, don't mass-drop; actual deletion is the owner's call.**
- **Parked by design** (owner explicitly deferred, or env-gated on a human/
  restart window) → keep but re-tag to `blocked`/`waiting` so the board reads
  honestly; do not burn cycles re-attempting. **Parking REMOVES the row from the
  claim pool** — `claim` takes `pending` only — so a parked slice comes back only
  through the parked→`pending` arc. State the unblock condition in the row, or it
  parks indefinitely; prefer `waiting` for a genuinely external dependency, and
  re-tag back to `pending` the moment the condition clears rather than leaving it
  parked because nothing forced a decision.
- **Live work just untouched** (in_progress with an assignee on an active
  workstream, stale 1–3 weeks) → poke/re-claim the owner, never cancel their work.
- **Sequential backlog** (slices gated on a prerequisite phase completing) →
  normal backlog, not cruft. This binds the WORKER too: before claiming a slice, check that its
  inputs EXIST — if every prerequisite slice is still `pending`, the deliverable can only be
  invented, so `unclaim` with the gap named and let the queue advance in order. Do not author the
  artifact from imagination to look productive (that is fabrication), and do not `cancel` a
  client-facing deliverable to clear your board (the owner's call, and it destroys real work):
  release the claim and name the prerequisite that unblocks it.
- **Exact duplicates** (two slices describing the same deliverable) → the only
  safe dedupe: keep the fuller plan, cancel the other, with explicit go.
- **Scope-crossing work — CANCEL, don't improvise** (standing Luke rule). A
  slice whose real deliverable requires changing BASE Hermes, the
  metrics/cost telemetry pipeline, or the fleet review-pipeline automation is
  not slice work — those belong as an explicit upstream/base change (or
  upstream PR), never a partial implement crammed into a task slice. Before
  claiming a slice "do it yourself," check whether its genuine deliverable
  crosses that boundary ("per-cron token/spend cost tagging", "model-tier
  routing config", "auto-approve review automation" all do). When it does,
  `--status cancelled` the slice and flag the scope boundary for the owner
  rather than building. Pure business research (a brand audit, a competitor
  gap analysis) is safe to do inline — zero Hermes code.

## Metadata correction — retagging a row (repo / project / tags / assignee)

`update` carries status/reason only, so the ONE sanctioned surface for changing a
row's metadata is:

```bash
task-db.py restore <json>   # per row: the row's CURRENT values, with only the
                            # field(s) you are correcting changed
```

It writes through `tasks.task_upsert()` — the single write path. Never
`UPDATE tasks.tasks SET repo = ...` by raw SQL: that bypasses the function's
derivation CHECK and RLS path, and every orchestrator plan restates the rule.

- **Restore PRESERVES the columns it does not carry.** `repo`, `assignee`,
  `target`, `due`, `tags` and `correlation_id` are read back from the store and
  re-written when your JSON omits the key; only an explicit empty value
  (`"tags": []`, `"repo": null`) clears one. This is load-bearing: a restore
  written for an unrelated correction used to NULL all six, so "retag one column"
  was a data-loss operation and a tag could not be set after the fact at all.
- **Read every field you DO carry out of the store; never retype it** — `source`
  especially, because restore defaults it to `session` and a stored `manual` then
  becomes a false statement about the row's provenance.
- **Snapshot → probe → batch → re-read.** Snapshot the ids' full row state to a
  file, apply ONE row and read it back, then the rest, then re-read all of them and
  assert that no field outside the one you meant to change differs. The probe also
  costs one row if the statement is wrong.
- **Group legacy/untagged rows by what the ROW says, not by who wrote it.** A tag is
  a claim about where the work lands: rows naming a file, migration, cron or doc of
  repo X are `repo=X`; client/content deliverables whose output is a document belong
  to no repo; mint-residue rows are cancels, not tags. Tagging by the writer's own
  session repo is the false-claim version of the same mistake.

## Pitfalls

- **verify is orchestrator-only** — the function checks
  `profile_of(session_user) IN ('moses','esther')`; workers get `false`.
- **Claim is self-only** — `p_assignee` must equal `profile_of(session_user)`;
  you can claim only FOR YOURSELF, never assign work to others.
- **A claimed slice can't be re-claimed** — the single claimer holds it until
  unclaim/report.
- **A slice that is `pending` WITH an assignee is STRANDED: unclaimable and
  unwatched.** The pool requires `assignee IS NULL` and the row is not
  `in_progress`, so no worker can take it, nobody is working it, and the board still
  counts it as ordinary pending work. Assigning a slice is NOT the same as starting
  it. Find them with `list --assigned` (MCP `task_list_handed_out`); release them
  with `unclaim <id> --reason "<why>"`, which now clears the assignee on a PENDING
  row as well as returning an `in_progress` one — a hand-off nobody started used to
  be unreleasable, which is how six slices sat stuck for six weeks.
- **A bare `pending` count overstates the queue.** It mixes claimable slices,
  assigned-but-unstarted slices, and stories (never claimable — the pool takes
  slices only). An actionable count is the split: `pending (claimable)` /
  `pending (assigned, not started)` / `pending (story)`. A count nobody can act on
  is what hides rot inside it.
- **A cancel MOVES the row to `tasks.task_archive`; it does not leave
  `status='cancelled'` in `tasks.tasks`.** So `count(*) FROM tasks.tasks WHERE
  status='cancelled'` is 0 even when the cancellation worked — verify or audit a
  cancel against `tasks.task_archive` (which carries `archived_at`). The live table
  is open work only.
- **The store is UTC; the host usually is not.** A date filter written from the
  LOCAL calendar day is midnight UTC and silently excludes every row written earlier
  that UTC day — a 09:00 KST change lands on the previous UTC date. Filter on a UTC
  date or compare the timestamp, and check the boundary before believing a 0-row
  result (a cutoff only hours away from the data is the failure shape).
- **A migration that is not in `cortex-update.sh`'s `register()` map is NEVER
  deployed** — the register map IS the deploy. The version-gated runner only sees
  migrations present in the DEPLOYED schema dir, so an unregistered one leaves every
  host silently behind while the repo looks correct. Register each migration in the
  same change, then confirm the host reports the new version (`task-db.py
  --apply-schema` is a no-op at the right version).
- **The MCP status filter must accept every status the STORE uses.** An enum
  narrower than `STATUSES` makes those rows unqueryable through MCP: they exist, are
  counted nowhere, and cannot be asked for. Extend the tool enums in the same change
  that adds a status.
- **Changing what a QUERY returns is a CLASS change — sweep the writers and the
  read-backs, not just the query.** Consumers that WRITE with one scope and then
  READ with a filter break silently when the filter is tightened: a probe/doctor
  check that added its row untagged and read it back through a scoped list reports
  a broken write path that is healthy, and a dedup guard that relied on seeing
  those rows compares against an EMPTY set and stops guarding while still
  "passing". Before shipping a scope change: grep for the add path (`cmd_add`, the
  inbox/dream mints, every `add` invocation) and for each reader that filters, fix
  them in the SAME cycle, and give a probe row the SAME label on the write and the
  read-back side. A unit test on the query alone cannot see any of it.
- **A mocked `psql` proves the call's SHAPE, not the SQL — exercise the real store
  once before committing.** Casts and column types are invisible to a mock:
  `p_session_id` is TEXT while `p_parent_id` is uuid in the SAME call, and an id
  list needs `= ANY(ARRAY[?]::uuid[])` or the store answers `operator does not
  exist: uuid = text`. Hand-writing a second copy of an existing upsert call is how
  such a mistake happens — share ONE SQL constant across the writers, pin the casts
  in a test that renders the SQL with sentinel values, and make the first real write
  a probe on a single row.
- **Unclaim/claim/report work on YOUR OWN rows** — `created_by` must match the
  caller; you can't unclaim or report someone else's work.
- **Schema v009+ required** — these commands `_require_v4` (schema 9). On an
  older host, run `bash cortex-update.sh` first; the version-gated runner applies
  the pending migrations, and a migration missing from `register()` is never
  carried (see the migration pitfall below).
- **report/verify set the derivation column too** — the functions keep the
  column-derivation CHECK in sync; hand-written UPDATEs that don't will fail.
- **review ≠ done** — reporting puts work in a queue, it does not close it.
  The orchestrator's evening pass is the closer.
- **A peer reporting "N stuck delegations / nothing claimable" is usually a
  wrong-lane mis-route, not lost work — verify the fleet DB before
  re-delivering.** When a worker says its queue holds delegation rows that
  consumed with `correlation_id=None` and never became claimable, do NOT take
  "re-deliver the slices" at face value (a reply that duplicates or re-mis-routes
  is the worst outcome). Query `tasks.tasks` for the cited slice IDs first: if
  the real rows exist and are already correctly homed (created_by=orchestrator,
  `source=manual`, scope=`fleet`, under their owning story and the right lane),
  the peer's copies are orphaned tracking residue from a delegation pointed at
  the wrong agent type (e.g. content-marketing slices handed to a staging-ops
  agent with a null correlation_id). The fix is the peer ARCHIVES its copies
 (they are not its deliverables, not claimable, not actionable) + you confirm
 the real work is intact — never a re-delivery. Judge the lane from the slice
 subject, not from the peer's framing.

## Compete mode (opt-in, orchestrator)

Slices can run as parallel candidates: `orch-compete-run.py <slice-id> --plan
"APPROACH: ..."` (≥2 approaches). Candidates judged DETERMINISTICALLY:
acceptance criteria met → fewest adversarial findings → lowest cost →
fastest. Never "which sounds better" (consistent with O4 autonomy rules).

## References

- `references/v009-schema-lessons.md` — the SQL/RLS gotchas behind the schema
  (SECURITY DEFINER + session_user, column-derivation CHECK, guarded grants)
- `docs/design/task-model-v3.md` — the full design

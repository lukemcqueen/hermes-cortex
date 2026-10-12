# Orchestrator morning task pass — 2026-10-12 (evidence)

Evidence for the `orch-task-morning-pass` cron run (07:37 KST,
job `f6694d02d29c`). Host-derived identity: **esther** (orchestrator).
Governance cycle **#12187**, session id `cron_f6694d02d29c` (started 2026-10-12).

> ⚠️ **NOT YET COMMITTED (2026-10-12).** This directory and the DOCS-INDEX row
> are written and staged but could not be committed: the pre-commit reflexion
> gate (`hc-reflexion-check.py`) requires a `mycortex_mem.tool_events` row for
> `skill_view('reflexion-check')` in this session, and this cron job
> (`f6694d02d29c`, `skills=[]`, `enabled_toolsets=[terminal,web,file]`) gets no
> `skill_view` tool at all — the harness answered "Tool 'skill_view' does not
> exist" for it. Same gate, 17 refusals across >=6 cron sessions since 10-04.
> The close was then blocked by the self-adversarial reviewer
> (ADV-12187-1/2/3) for exactly that missing committed diff. Recorded as
> loop-governance issue **#95** (high); the lock auto-releases at TTL
> (~08:37 KST). Nothing was bypassed and no gate was weakened.

## What the pass did

| Step | Result |
|---|---|
| Survey pending stories | 3 stories, **all already sliced** (0 unsliced) |
| Survey claimable | **16** (15 fleet slices + 1 personal row) |
| Decompose unsliced stories | **0** — no `add --parent` writes needed |
| Dispatch urgent (pr 2-3) worker-lane slices | **0 — deliberate hold**, see below |
| Orchestrator-only work self-claimed | **0** |

Stories (3 stories / 18 slices, unchanged since 10-08):

- `c579ef95` — Fleet cost <$10/day + halve review queue → 4 slices (`slices-cost.txt`; 2 `pending`, 2 `waiting` on `[cost/1]`)
- `82310c5e` — KAESA 90-Day Content Challenge → 6 slices (`slices-kaesa-90day.txt`)
- `00562f6c` — KAESA Client Engagement (pilot #1) → 8 slices (`slices-kaesa-engagement.txt`); 1 `in_progress` (`1e8737fc`, case-study artifacts)

## New finding: the repeat-dispatch loop is *consumption-driven*, not delivery-driven

Yesterday's pass (10-11) re-sent `ca282975` (pre-order landing + payment →
joseph) and `72dc920b` (KAESA Phase 1 Foundation → joseph) and proved them
queued in `inbox_joseph` (depth 2). Today, on the live bus:

1. **`inbox_joseph` depth 0** — the worker's handler *consumed* both requests
   (`bus-consumption-2026-10-12.txt`).
2. **Both fleet slice rows are still `pending` on esther** — no closure came
   back. This is expected, not a defect: `task-db.py` states the honest-fleet
   semantic (B-3) that `--scope fleet` stores the row **on the originating host
   only**; a bus-received `TASK_REQUEST` creates a *worker-local* row
   (`agent-message-handler.py`, "Bus → tasks bridge": `TASK_REQUEST` is in
   `TASK_CREATING_SUBJECTS`, `source='inbox'`), so the worker's completion
   closes the *worker's* row, never esther's slice. So each morning the
   orchestrator sees the same pending slice and has no signal that it was
   already dispatched and consumed.
3. **Why yesterday's re-send was *allowed*** — the send-side dedup gate in
   `hc.py cmd_send` is **pending-scoped**: it refuses only when an *identical
   message is already pending in `inbox_<agent>`* (`pending = bus_peek(...)`,
   line 531). The moment the worker drains its queue, the guard no longer
   matches, so the *identical* slice send goes through again. That is the exact
   mechanism behind the >=5-morning thrash (loop-governance issue #86); it is
   not a worker-availability problem.
4. **No supported post-hoc hand-out** — `task-db.py update` exposes only
   `--status/--reason` (no `--assignee`), and `ops/services/tasks/schema` has
   no `handout`/`assign` function. A slice therefore *cannot* be marked
   "handed out" after decomposition, stays in the claimable pool
   (`task_list_handed_out`: "no unstarted hand-offs"), and invites the next
   identical re-dispatch.

**Decision this pass: dispatch 0.** Re-sending would be the 5th identical
`TASK_REQUEST` to `joseph` for slices whose prior copies were already consumed,
creating another duplicate worker-side row (the bridge creates one row per
receipt) with no path back to esther's slice — pure noise plus a Telegram ping.
This matches the 10-10 hold and closes the "were the 10-11 messages lost?"
question from 10-11: they were **consumed, and no result has returned**.

### Remedy options (needs an owner decision — not silently applied here)

1. **Cheapest guard (send side):** make dedup consult the dispatch ledger
   (`bus.record_dispatch` is already written on every `hc send`) instead of
   queue depth alone — refuse a re-send of the *same slice id* while an
   earlier dispatch for it is still un-acknowledged/within timeout.
2. **Orchestrator-side:** record the dispatch *on the slice row* (requires an
   `update --assignee`/hand-out path, which does not exist today) so the slice
   leaves the claimable pool and appears in `task_list_handed_out`.
3. **Root cause (roadmap):** fleet task transport (git-backed, private repo —
   `task-db.py` header). Until rows replicate, a cross-host dispatch can never
   close the originator's slice, so any of (1)/(2) is a stop-bleed, not a fix.

Standing rule observed: a review-pipeline/transport automation change is
scope-crossing (skill:`task-queue-workflow`) and an unattended fleet-wide
enforcement change is not made from a cron — recorded as an issue instead.

## Re-run

```bash
bash docs/evidence/morning-task-pass-2026-10-12/verify-consumption.sh
# EXPECT: sections 1-5 PASS, VERDICT: PASS
```

Read-only: no sends, no probes, nothing queued anywhere.

## Artifacts

- `survey-stories.txt`, `survey-claimable.txt`, `summary-*.txt`, `slices-*.txt`, `in-progress.txt`, `waiting.txt` — task-db survey output
- `bus-consumption-2026-10-12.txt` — live-bus peek via moses (`hc status` + `inbox joseph` + `inbox esther`): all agent queues empty, `inbox_joseph depth=0`
- `verify-consumption.sh` / `verify-output.txt` — re-runnable proof + captured run (VERDICT: PASS)
- `captured-at.txt` — capture timestamp
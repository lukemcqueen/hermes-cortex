# Agent Bus Overnight Inbox Check - Evidence (Titus, 2026-10-08)

Read-only bus inbox check for the agent-bus-overnight cron. Raw verbatim tool
output in the sibling `.raw.txt` file (captured from `lib.cortex_bus`). This
note summarizes and interprets it.

## Bus state (capture 14:40 UTC)

- DLQ queue `inbox_orchestrator_dlq`: depth **0** (only DLQ, no backlog).
- `inbox_titus` (this agent): depth **0**, `peek` returns 0 messages.
- `broadcast`: depth **0**. No queue has `processing > 0`.
- Peer lanes `inbox_orchestrator` (depth 4) and `inbox_health_check` (depth 2)
  are another agent's lanes. Their depths fluctuate across today's captures
  (orchestrator 5-8-3-4; health_check 1-2), i.e. being drained by their owners.
- Bus health endpoint: status `ok`, backend `pgmq`, 13 queues.

## ACL read-isolation (verified at the HTTP layer)

This agent's read access is restricted by ACL design: a direct
`_bus_get('/api/pgmq/peek/<queue>')` returns **HTTP 403** for every queue
**except its own** (`inbox_titus`). Probed queues: broadcast,
inbox_orchestrator, inbox_health_check, inbox_moses, inbox_esther,
inbox_fleet, inbox_joseph, inbox_gisu, inbox_kustos, and the DLQ — all
403-BLOCKED. So the two non-zero peer lanes are genuinely out of scope for
this cron by ACL, and this agent cannot read their contents.

> Caveat: `lib.cortex_bus.bus_peek()` silently returns `[]` on a 403 (it
> catches `ConnectionError`), so it cannot distinguish "empty" from
> "403-blocked". This check probes with `_bus_get` at the HTTP layer to make
> the isolation explicit. (Initial raw capture misread this as read-access —
> corrected here, cleanup-commit-regression-check 2026-10-08.)

## Findings by task area

1. Pending / urgent / critical (this agent) - `inbox_titus` and `broadcast`
   depth 0, none.
2. DLQ items - `inbox_orchestrator_dlq` depth 0, no backlog.
3. Blocked workflows - none reachable to this agent (no `processing > 0`; the
   two non-zero peer lanes are 403-ACL-isolated and their owners are draining
   them). Fleet bus backend reports health `ok`.
4. Peer-queue isolation - confirmed by a 403 on every peer/DLQ peek.

## Decision

No pending, urgent, critical, DLQ, or blocked-workflow items in this agent's
scope. Bus health `ok` -> cron output `[SILENT]`.
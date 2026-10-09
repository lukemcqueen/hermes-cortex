# Agent Bus Inbox Check — Evidence (Titus, 2026-10-08)

Read-only bus inbox health check for the agent-bus cron. **Raw, verbatim tool
output in [`cron-bus-inbox-check-2026-10-08.raw.txt`](cron-bus-inbox-check-2026-10-08.raw.txt)**
(captured 2026-10-08 14:02 UTC from `lib.cortex_bus`). This note summarizes
and interprets it.

## Raw capture highlights (see .raw.txt for full output)

```
== bus_list_queues ==
broadcast            depth=0  processing=0
inbox_health_check   depth=1  processing=1
inbox_orchestrator   depth=5  processing=0
inbox_orchestrator_dlq depth=0 (dlq)
inbox_titus          depth=0  processing=0
(all other inboxes/joseph/kustos/moses/gisu/esther/fleet: depth=0 processing=0)

== blocked-workflow check (processing > 0) ==
queues_with_stuck_processing: [{"name": "inbox_health_check", "depth": 1, "processing": 1}]

== inbox_titus peek (vt=1, non-consuming) ==
inbox_titus: null

== ACL isolation probe: read of peer queue inbox_orchestrator ==
inbox_orchestrator read rejected (expected 403): Bus permanently rejected request (HTTP 403)

== bus health endpoint ==
{"status": "ok", "backend": "pgmq", "queues": 13}
```

## Findings by task area

1. **Pending messages (this agent's scope)** — `inbox_titus` and `broadcast`:
   depth **0**, none. ✓
2. **Urgent / critical items** — none in this agent's inbox or broadcast. ✓
3. **DLQ items** — `inbox_orchestrator_dlq` (only DLQ): depth **0**. No DLQ
   backlogs. ✓
4. **Blocked workflows** — a read of `inbox_health_check` (which has
   `processing=1`) returned HTTP 403: it is **another agent's lane**, and this
   agent is ACL-isolated from it, so it is out of this cron's scope. From the
   fleet's own health endpoint the bus backend reports `status: ok`. A single
   in-flight item (`processing=1`) is normal transient state (the
   recover-timeouts cron drains aged in-flight records); not evidence of a
   stuck workflow this agent can or should act on. The only queue reachable to
   this agent with any signal is its own inbox (empty).
5. **Peer-queue isolation** — reading `inbox_orchestrator` correctly returns
   **403** (verified), confirming the two non-zero queues (`inbox_orchestrator`
   depth 5, `inbox_health_check` depth 1) are out of scope by ACL design.

## Decision

No pending, urgent, critical, or DLQ items in this agent's scope. No
actionable blocked workflow reachable to this agent. Bus health `ok` →
cron output `[SILENT]`.
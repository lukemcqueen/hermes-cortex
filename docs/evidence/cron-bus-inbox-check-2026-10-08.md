# Agent Bus Inbox Check — Evidence (Titus, 2026-10-08)

Read-only bus inbox health check for the agent-bus cron. Verified the bus
queues directly via `lib.cortex_bus` (`bus_list_queues`, non-consuming
`bus_read` with vt=1). Findings below.

## Bus queue state (live read, 2026-10-08)

| Queue | Depth | DLQ |
|-------|-------|-----|
| broadcast | 0 | no |
| bus-health-probe | 0 | no |
| inbox_esther | 0 | no |
| inbox_fleet | 0 | no |
| inbox_gisu | 0 | no |
| inbox_health_check | 2 | no |
| inbox_joseph | 0 | no |
| inbox_kustos | 0 | no |
| inbox_moses | 0 | no |
| inbox_orchestrator | 2 | no |
| inbox_orchestrator_dlq | 0 | yes |
| inbox_titus | 0 | no |
| out_esther | 0 | no |

## Direct checks

- **This agent's inbox `inbox_titus`: depth 0** (peek returned null).
- **`broadcast` queue: depth 0.**
- **All DLQ queues: empty** (inbox_orchestrator_dlq is the only DLQ; depth 0).
- **ACL isolation:** a read of `inbox_orchestrator` (another agent's lane)
  returns HTTP 403 Forbidden — as expected for a non-orchestrator agent; that
  queue and `inbox_health_check` are out of this cron's scope and are not
  processed here.

## Decision

No pending, urgent, or critical messages in this agent's scope. No DLQ items.
Nothing actionable → cron output `[SILENT]`.

## Scope note

The two non-zero queues (`inbox_orchestrator` depth 2, `inbox_health_check`
depth 2) belong to other agents; this agent is correctly 403-ACL-isolated from
reading or processing them (verified), so they are out of scope for this cron.
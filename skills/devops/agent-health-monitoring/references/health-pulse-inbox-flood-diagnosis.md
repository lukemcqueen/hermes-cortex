# Health Pulse Inbox Flood — Diagnosis & Remediation

## When to Use This Reference

When you find hundreds of unread health check messages from an agent (typically
Titus) accumulated in the local agent's inbox. All are healthy (vector all-1s,
`h: true`) but none have been marked read.

## Detection

**Symptom:** `inbox_watch` or `inbox_read` returns a massive result (2MB+ or
hundreds of messages), all with:
- `from: titus` (or another health_method=inbox agent)
- `subject: health`
- `body: {"v": [1,1,1,1,1,1,1,1,1], "h": "t", "t": <epoch>}`
- `status: unread`

**Normal rate:** 1 health pulse every 10 minutes = ~6/hour = ~144/day.
Accumulation means the anchor-keep consumer is not pruning.

## Architecture of the Health Push Pipeline

```
[Agent Side]
health-vector-push.sh (every 10 min via launchd/systemd/cron)
  └─ POST /api/send {from: "titus", subject: "health", body: "{...}"}
      └─ Inbox API creates message file with status: unread
          └─ File lands at the file-based inbox (legacy — see agent-bus skill for current)\n
[Orchestrator Side (Moses)]
orch-team-health.py (no_agent cron, every 10 min)
  └─ GET /api/inbox?topic=health&limit=20
      └─ _fetch_inbox(agent_key) → anchor-keep pattern:
          1. Sort agent's health messages by timestamp (oldest first)
          2. Keep oldest (the anchor — proof of liveness)
          3. DELETE all newer messages via /api/delete/<filename>
          4. Parse anchor body → return (health_data, timestamp)
```

## Diagnosis Checklist

### 1. Is the orchestrator cron running?

```bash
hermes cron list | grep orch-team-health
ls -la ~/.hermes/cron/output/ | grep orch-team-health | tail -3
```

If the cron hasn't run recently (stale output > 10min) or shows errors,
the anchor-keep consumer is not pruning.

### 2. Does the inbox API respond to DELETE?

```bash
curl -s -X DELETE "http://127.0.0.1:8903/api/delete/<filename>" \
  -u "<auth>" -w "\nHTTP %{http_code}"
```

If it returns non-2xx, the anchor-keep delete calls fail silently and
the poller logs no error (the error is swallowed in the loop).

### 3. Are health messages going to the right topic?

Check the message file's `topic:` field. The anchor-keep pattern in
`_fetch_inbox` only polls `topic=health`. If `health-vector-push.sh`
sends to `topic: general`, the orchestrator never sees them.

### 4. Is `_fetch_inbox` actually running for this agent?

The agent must be in `agent-registry.json` with `health_method: inbox`.
If `health_method` is missing or wrong, the poller skips inbox health
collection entirely for that agent.

### 5. Is health-vector-push.sh running too frequently?

Check the launchd/cron schedule. If it's running more frequently than
every 10 minutes, a 10-min poll cycle can't keep up.

## Immediate Remediation

When pulses have accumulated to 100+ messages and are all-green:

1. **Acknowledge them** — they're all healthy, no action needed on content.
   - Move to trash (recoverable) via `inbox_delete` per message
   - Or contact the orchestrator to clear via bus queue: `inbox_delete(msg_id)` per message
     (keep the oldest anchor if you want liveness continuity)

2. **Fix the root cause** — pick from diagnosis above:
   - Restart `orch-team-health` cron if stopped
   - Fix DELETE endpoint if broken
   - Fix agent-registry.json `health_method` if missing
   - Correct push script topic if wrong

3. **Verify fix**: A new health pulse should arrive within 10 min. The
   next `orch-team-health` tick should prune all but the anchor.

## Prevention

- The anchor-keep pattern in `_fetch_inbox` should log a warning when it
  finds >2 messages for the same agent (indicates delete path failed).
- Consider a `max_messages_per_agent` guard that warns if count exceeds
  a threshold.
- The inbox-flag cron should flag >50 unread health messages as a
  secondary alert.

## Pitfalls

- **DELETE failure is silent.** `_fetch_inbox` has no error handling on
  the delete call. One tick of accumulation is fine; dozens means the
  DELETE endpoint is persistently failing.
- **Inbox API endpoint changes.** If the API changes its response shape,
  `_fetch_inbox` returns empty and no pruning happens.
- **Renamed agent.** If the agent changes names but inbox messages still
  carry the old name, the client-side `from` filter won't match.

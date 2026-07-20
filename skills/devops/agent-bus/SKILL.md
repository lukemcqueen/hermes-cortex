---
name: agent-bus
version: 1.2.0
category: devops
description: "Agent Bus (PGMQ) operations — queue inspection, DLQ management, message recovery, auth, and health diagnostics. Covers the Postgres-backed message queue that replaces the legacy file inbox."
platforms: [linux]
author: Esther
metadata:
  hermes:
    tags: [bus, pgmq, dlq, messaging, queue, postgres, recovery]
    related_skills: [system-remediation, hermes-cortex-deployment]
---

# Agent Bus — PGMQ Operations

## Overview

The Agent Bus is a Postgres-native message queue (`lib/pgmq` implementation with `SKIP LOCKED`) running on port `:8903`, proxied through nginx. All inter-agent communication flows through it. It replaces the old file-based agent inbox.

Key architectural facts:
- **Bus server** processes at `~/hermes-cortex/ops/services/agent-bus/server.py`
- **Queue module** at `~/hermes-cortex/core/agent_bus/queue.py`
- **Postgres schema** `bus.*` in the shared gbrain database (`:15432`)
- **MCP tools** `mcp__agent_bus__*` route through the bus via HTTP
- **Health check**: `curl http://127.0.0.1:8903/health` returns 200
- **Bearer token auth**: token from `CORTEX_BUS_TOKEN` in `.env`

## When to Use

- Diagnosing message delivery failures between agents
- Inspecting queue depth or DLQ buildup
- Recovering stuck `processing` messages
- Fixing bus auth or permission issues
- Investigating why an agent isn't receiving messages

## Diagnosing Bus State

### 1. Queue Overview

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT queue_name, state, COUNT(*) as count
FROM bus.messages
GROUP BY queue_name, state
ORDER BY queue_name, state;
\""
```

Shows every queue with its message counts broken down by state:

| State | Meaning |
|-------|---------|
| `pending` | Ready for dequeue — normal state |
| `processing` | Currently dequeued, within visibility timeout |
| `archived` | Successfully processed (or auto-archived) |

### 2. DLQ Inspection (Dead Letter Queue)

Messages that exceeded `max_retries` (default 3) move to `{queue}_dlq`. DLQ messages older than 6 hours are auto-archived by `bus.recover_timeouts()`.

```bash
# DLQ depth by queue
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT queue_name, state, COUNT(*) as count,
    MIN(enqueued_at)::timestamptz(0) as oldest,
    MAX(enqueued_at)::timestamptz(0) as newest
FROM bus.messages
WHERE queue_name LIKE '%dlq%'
GROUP BY queue_name, state
ORDER BY queue_name, state;
\""

# DLQ message content — who sent it, what about, how many retries
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT 
    queue_name,
    COALESCE(body->>'from', '(empty)') as sender,
    body->>'subject' as subject,
    body->>'topic' as topic,
    retry_count,
    error,
    enqueued_at::timestamptz(0)
FROM bus.messages
WHERE state = 'pending' AND queue_name LIKE '%dlq%'
ORDER BY queue_name, enqueued_at DESC
LIMIT 50;
\""
```

### 3. Check Queue Schema Integrity

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT name, is_dlq, parent_queue, max_retries FROM bus.queues ORDER BY name;
\""
```

Every queue ending in `_dlq` MUST have `is_dlq = true`. If false, the auto-archive and chain-deletion break silently.

### 4. Run Recovery

```bash
# Returns count of messages recovered/archived
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT bus.recover_timeouts();
\""
```

The `recover_timeouts()` function does three things:
1. **Recovers** processing→pending for messages below `max_retries`
2. **Moves** over-retry processing messages to DLQ (or deletes if already in a DLQ)
3. **Auto-archives** DLQ messages older than 6 hours

### 5. Interpreting Recovery Counts

The `orch-bus-recover-timeouts` cron (every 5m) calls `bus.recover_timeouts()` and reports results. The **silent threshold is 50** — below that, no notification is sent (routine timeouts are normal).

| Recovery count | Meaning |
|----------------|---------|
| 0–5 | Normal — routine visibility timeouts |
| 5–50 | Mild backlog — catching up, no action needed |
| 50+ | Moderate+ backlog — worth investigating |

### 6. Normal DLQ Baselines

DLQ messages < 6 hours old are normal — they auto-archive on each `recover_timeouts()` tick.

| DLQ depth | State |
|-----------|-------|
| < 50 | Normal — transient backlog |
| 50–200 | Moderate — check sender breakdown |
| 200+ | Elevated — investigate with DLQ content query (section 2) |

If messages older than 6 hours are present, `is_dlq` may be broken (see Common Issues below).

The threshold (50) is set in `ops/scripts/orch-bus/orch-bus-recover-timeouts.sh` as `RECOVER_THRESHOLD=50`.

### 7. Health Report Monitoring (`orch-bus-message-tracker.py report`)

The `orch-bus-confirmation-alert` cron (every 60m) runs `orch-bus-message-tracker.py report` producing a combined bus health report covering message tracker status + queue depths + DLQ health.

**Report behaviour:**
- **Silent when healthy** — no output if no DLQ backlog, no overdue confirmations, no pending messages. Zero stdout = zero notification.
- **Alerts on DLQ backlog** — checks both `depth` (pending) AND `processing` state in DLQ queues. Messages stuck in processing count as a backlog.
- **Reports on overdue confirmations** — tracked messages past their confirmation deadline.

**Common gotcha — processing messages in DLQ hidden from alerts:**
The DLQ alert code in `cmd_report()` at `ops/scripts/orch-bus/orch-bus-message-tracker.py` initially only checked `depth > 0` for DLQ queues. Messages in `processing` state were invisible. The fix adds `or processing > 0` to both the marker and `dlq_issues` detection.

```python
# Before (missed processing messages):
marker = " ⚠️ DLQ" if is_dlq and depth > 0 else ""
if depth > 0: dlq_issues.append(name)

# After (checks both):
marker = " ⚠️ DLQ" if is_dlq and (depth > 0 or processing > 0) else ""
if depth > 0 or processing > 0: dlq_issues.append(name)
```

**Silent-when-clean pattern** — the report collects all data first, then only prints if there's something to report:

```python
# At the end of data collection:
if not overdue and not dlq_issues and not pending:
    return  # completely silent
```

### 8. Cron Alert Design: Silent-When-Clean

A general principle for no_agent cron scripts that produce health/status reports:

- **No output = no notification.** The user should only hear from a cron when there's something to act on.
- **Collect data first, print only if there's a signal.** Build the entire report into variables (`queue_lines`, `dlq_issues`), then check whether anything needs attention before printing.
- **Silence is the default, not a special mode.** The healthy state should produce zero stdout. Don't print "✅ All clean" — that's noise.
- **Thresholds belong in the script, not hardcoded in docs.** The `RECOVER_THRESHOLD` variable in the script defines what's actionable. Docs reference the variable name, not the value.

This pattern applies to: health reports, watchdog crons, depth monitors, alert crons, and any periodically-running agent script that checks system state.

### 9. Stuck Pending Messages at Max Retries

The `recover_timeouts()` function only moves messages from `processing` → pending/DLQ. Messages that were never dequeued while it ran remain in `pending` with their retry count unchanged. This means **messages can sit in `pending` with `retry_count = max_retries` without ever being promoted to the DLQ**.

These are truly stuck: the message was dequeued up to max_retries times, timed out each time, but no agent subsequently dequeued it again, so it never re-entered `processing` state for `recover_timeouts()` to catch.

**Detection query:**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT queue_name, retry_count, COUNT(*) as count,
    MIN(enqueued_at)::timestamptz(0) as oldest,
    MAX(enqueued_at)::timestamptz(0) as newest,
    COALESCE(body->>'from', '(null)') as sender,
    body->>'subject' as subject,
    body->>'topic' as topic
FROM bus.messages
WHERE state = 'pending'
  AND retry_count >= (SELECT COALESCE(max_retries, 3) FROM bus.queues WHERE name = bus.messages.queue_name)
GROUP BY queue_name, retry_count, body->>'from', body->>'subject', body->>'topic'
HAVING COUNT(*) > 0
ORDER BY COUNT(*) DESC
LIMIT 20;
\"" 2>&1
```

**Remediation:**

⚠️ **`bus.dlq_move(msg_id)` does NOT exist in the schema.** Attempting to call it produces `ERROR: function bus.dlq_move(uuid) does not exist`. Use `bus.archive()` instead.

The correct approach requires getting the message ID first, then archiving it individually — `bus.archive()` takes a single `msg_id`.

**Step 1 — Get the stuck message IDs:**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT msg_id::text, queue_name, body->>'subject' as subject,
    retry_count, enqueued_at::timestamptz(0)
FROM bus.messages
WHERE state = 'pending'
  AND retry_count >= (SELECT max_retries FROM bus.queues WHERE name = bus.messages.queue_name)
  AND queue_name = 'inbox_target'
ORDER BY enqueued_at;
\"\" 2>&1
```

**Step 2 — Archive each via `bus.archive()` with explicit `::uuid` cast:**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \"
SELECT bus.archive('inbox_target', '<msg_id>'::uuid, 'esther-remediation');
\"\" 2>&1
```

Repeat for each stuck message ID. Verify the queue is clean afterward with the detection query from Step 1.

**Bulk fallback (bypasses proper archive function — use only when you're sure all are orphaned):**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \"
UPDATE bus.messages SET state = 'archived', archived_at = NOW()
WHERE state = 'pending'
  AND retry_count >= (SELECT max_retries FROM bus.queues WHERE name = bus.messages.queue_name)
  AND queue_name = 'inbox_target';
\"\" 2>&1
```

> **Why individual archiving:** `bus.archive()` logs the action via `bus.audit()` and handles DLQ chain metadata correctly. The direct UPDATE is faster for bulk cleanup but skips audit logging — acceptable for known-orphaned messages where you want to clear a backlog fast.

**Root cause:** Target agent stopped dequeuing. The message was picked up by visibility timeout (default 30s), retried, exhausted max_retries, and the agent never dequeued it again. Fix by clearing backlog or restarting the agent's consumer.

### 10. Raw-Field Wrapper Messages

Some bus senders wrap the payload inside a `raw` field, producing messages like:
```json
{"raw": "{\"from\": \"moses\", \"to\": \"moses\", \"topic\": \"health\"}"}
```

This means `body->>'from'` evaluates to `NULL` at the top level. The sender data is nested inside `body->'raw'->>'from'` after a JSON decode of the inner string.

**Detection query:**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT COUNT(*) as count, queue_name
FROM bus.messages
WHERE state = 'pending'
  AND body->>'from' IS NULL
  AND body ? 'raw'
GROUP BY queue_name
ORDER BY COUNT(*) DESC;
\"" 2>&1
```

**Reading actual content:**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT msg_id, queue_name,
    body->'raw'->>'from' as actual_sender,
    body->'raw'->>'subject' as actual_subject,
    body->'raw'->>'topic' as actual_topic,
    enqueued_at::timestamptz(0)
FROM bus.messages
WHERE state = 'pending'
  AND body->>'from' IS NULL
  AND body ? 'raw'
ORDER BY enqueued_at DESC
LIMIT 20;
\"" 2>&1
```

### 11. Fleet-Wide Queue Scan During Inbox Processing

When an inbox-processing cron runs, scan all queues for a fleet-wide health picture — even though you can only act on your own queue. This surfaces backlogs in other agents.

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT queue_name, state, COUNT(*) as count,
    MIN(enqueued_at)::timestamptz(0) as oldest,
    MAX(enqueued_at)::timestamptz(0) as newest
FROM bus.messages
GROUP BY queue_name, state
ORDER BY queue_name, state;
\"" 2>&1
```

Compare depths:
- **0:** Clean
- **1–50:** Normal backlog
- **50–200:** Moderate — flag in report
- **200+:** Elevated — escalate

**Note:** PSQL access is via local `sg docker` gateway. For remote agents, use the bus API at `/api/pgmq/queues` (lists all queues but not per-message detail).

## Common Issues

### DLQ Messages Accumulating Without Auto-Archive

**Symptom:** DLQ depth grows without bound, old messages (6h+) stay in `pending` state.

**Root cause:** The `is_dlq` flag was not set on DLQ queues — `bus.recover_timeouts()` Step 3 (auto-archive) checks `WHERE q.is_dlq = true` and silently skips queues where it's false. Also Step 2 cannot chain-delete exhausted DLQ messages, causing `_dlq_dlq` accumulation.

**Fix:**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \"
UPDATE bus.queues SET is_dlq = true WHERE name LIKE '%_dlq%' AND is_dlq = false;
\"" 2>&1

# Run recovery to immediately clear old messages
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT bus.recover_timeouts();
\""
```

After fix, the cron `orch-bus-recover-timeouts` (every 5m) auto-maintains the DLQ. Verify with queue overview query.

**Prevention:** The queue creation code at `core/agent_bus/queue.py:create_queues_for_agent()` already sets `is_dlq = true` — the bug only affects queues created before the column was added to the schema.

### All Bus Tools Return 401 (Not 200)

The MCP bus tools (`mcp__agent_bus__*`) return HTTP 401 when:
1. `CORTEX_BUS_TOKEN` in `.env` doesn't match the hash in `bus.tokens` table
2. The token is missing entirely from the PG table

**Diagnostic:**
```bash
# Check which tokens exist
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \"
SELECT agent_name, substring(token_hash::text, 1, 20) as token_prefix, rotated_at
FROM bus.tokens ORDER BY agent_name;
\""

# Verify your .env token matches
grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env
```

### Bus Unreachable (Connection Refused)

**Symptom:** `curl http://127.0.0.1:8903/health` fails.

**Check:**
```bash
# Is the bus process running?
ss -tlnp | grep 8903

# Is the systemd service active?
systemctl --user status agent-bus.service

# Restart if needed
systemctl --user restart agent-bus.service
```

Note: The bus at `:8903` is a direct local connection. It's also proxied through nginx at the orchestrator's bus port (e.g. `:13004` for Moses, `:14004` for Esther) with Bearer auth. The MCP tools route through nginx, not directly.

## References

- `references/dlq-isdlq-fix.md` — Full reproduction of the `is_dlq = false` bug: symptoms, diagnosis, fix, and verification
- `references/dlq-monitor-fix.md` — DLQ alert fix: processing state detection + silent-when-clean pattern for `orch-bus-message-tracker.py report`
- `references/cross-server-architecture.md` — Per-server independent Postgres architecture: why local `inbox_moses` sends don't reach Moses, fleet port map, and correct curl pattern for cross-server messages
- `core/agent_bus/queue.py` — Queue creation, DLQ logic, send/read/archive
- `ops/services/agent-bus/server.py` — HTTP API, auth, dashboard
- `docs/agent-bus-setup.md` — Architecture, security model, deployment guide, DLQ maintenance section
- `docs/esther-bus-setup.md` — Maintenance steps, changelog (DLQ fix, threshold changes, pipeline updates)

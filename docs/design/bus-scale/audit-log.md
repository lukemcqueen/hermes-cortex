# Bus Audit Log — Design Document

> **BUS-P2-1:** Enterprise compliance — every operation logged.
> Priority: 🟢 P2 (needed for 100+ agents). Effort: 1 day.

## Problem

Currently no record of who did what on the bus. If a message goes missing, there's
no way to trace whether it was read, archived, or never sent. Security auditors
require per-agent operation traces.

## Solution

Add a `bus.audit_log` table that records every bus operation with agent identity,
timestamp, and action details.

### Schema

```sql
CREATE TABLE IF NOT EXISTS bus.audit_log (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,       -- Who did it
    action TEXT NOT NULL,            -- send, read, archive, requeue, delete
    queue TEXT NOT NULL,             -- Target queue
    msg_id UUID,                     -- Affected message (nullable for list/debug ops)
    details JSONB DEFAULT '{}',      -- Status code, error info, extra context
    client_ip INET,                  -- Source IP (from request)
    created_at TIMESTAMPTZ DEFAULT NOW()  -- When it happened
);

-- Index for time-range + agent queries
CREATE INDEX idx_audit_log_agent_created ON bus.audit_log (agent_name, created_at DESC);
CREATE INDEX idx_audit_log_action_created ON bus.audit_log (action, created_at DESC);
CREATE INDEX idx_audit_log_created ON bus.audit_log (created_at DESC);
```

### Implementation

Add a middleware or decorator on every bus API endpoint:

```python
async def audit_log(func):
    """Decorator that logs every bus operation."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract agent identity from auth
        request = kwargs.get("request")
        agent_name = _get_agent_name(request)
        client_ip = request.client.host if request.client else None
        
        result = await func(*args, **kwargs)
        
        # Log the operation
        operation = _detect_operation(request)
        await _write_audit_log(
            agent_name=agent_name,
            action=operation["action"],
            queue=operation["queue"],
            msg_id=operation.get("msg_id"),
            details={"status_code": result.status_code if hasattr(result, "status_code") else 200},
            client_ip=client_ip
        )
        
        return result
    return wrapper
```

### Logged Operations

| Action | When | Details |
|--------|------|---------|
| `send` | After successful message send | queue, msg_id, priority, correlation_id |
| `read` | After successful read (message found) | queue, msg_id |
| `read_empty` | After read with no message | queue |
| `archive` | After successful archive | queue, msg_id |
| `requeue` | After requeue | queue, msg_id, reason |
| `delete` | After message deletion | queue, msg_id |
| `queue_create` | After queue creation | queue |
| `permission_change` | After permission change | agent, old_perms, new_perms |
| `token_revoke` | After token revocation | agent |

### What is NOT Logged

- Message bodies (privacy) — only metadata
- `health` and `metrics` endpoint calls (noise)
- `list_queues` calls (high frequency, low value)

### Retention Policy

Audit logs are append-only. Retention:

| Time Range | Storage | Queryable |
|------------|---------|-----------|
| < 7 days | Full detail | Yes |
| 7-90 days | Full detail | Yes |
| > 90 days | Aggregated (daily counts per agent) | Summary only |

Cleanup cron (`bus-audit-cleanup`, weekly):
```sql
-- Archive entries > 90 days to summary
INSERT INTO bus.audit_log_archive (date, agent, action, count)
SELECT DATE(created_at), agent_name, action, COUNT(*)
FROM bus.audit_log
WHERE created_at < NOW() - INTERVAL '90 days'
GROUP BY 1, 2, 3;

-- Delete detailed entries > 90 days
DELETE FROM bus.audit_log WHERE created_at < NOW() - INTERVAL '90 days';
```

### CLI: Query Audit Log

```bash
# Recent operations by agent
hermes cortex audit agent gisu --since 2026-07-27

# All operations on a queue
hermes cortex audit queue inbox_gisu --last 7d

# Suspicious activity (errors)
hermes cortex audit errors --since 24h

# Summary by agent
hermes cortex audit summary --since 30d
# → gisu: 142 sends, 138 reads, 4 archives
# → moses: 981 sends, 12 reads
```

### Performance

- Each audit write is a single INSERT on a table with no contention
- Indexes support the primary query patterns
- At 1000 agents × 200 ops/day = 200K rows/day = ~2M rows at 10-day retention
- At 30-byte overhead per row + indexes: ~200MB at 90-day retention
- Auto-cleanup keeps this bounded

### Files Changed

| File | Action |
|------|--------|
| `core/cortex_bus/schema/audit.sql` | Create |
| `core/cortex_bus/server.py` | Add audit logging middleware |
| `core/cortex_bus/audit.py` | Create — audit log module |
| `ops/scripts/manage/bus-audit-cleanup.py` | Create — retention cron |

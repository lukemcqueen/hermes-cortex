---
name: bus-queue-maintenance
description: "Bus queue lifecycle — inspecting stuck messages, archiving orphaned messages, navigating state constraints, and performing routine queue cleanup. Complements cortex-bus for the hands-on maintenance side."
version: 1.0.0
category: devops
author: Hermes Cortex
platforms: [linux]
---

# Bus Queue Maintenance

## When to Use

- Messages are stuck cycling `processing → pending → processing` in a bus queue
- A consumer stopped dequeuing and orphaned messages keep retrying
- You need to clean up stuck messages without waiting for visibility timeouts
- You're investigating why a queue has persistent `processing` messages

## Core Concept: Valid Message States

The `bus.messages` table enforces a check constraint. **`'archived'` is NOT a valid state.**

| State | Meaning |
|-------|---------|
| `pending` | Ready for dequeue |
| `visible` | Timer-based visibility — readable after timeout |
| `processing` | Currently consumed, within visibility window |
| `completed` | Successfully consumed |
| `failed` | Consumer explicitly marked as failed |
| `dlq` | Moved to dead letter queue after max retries |

**Archiving** means moving a message from `bus.messages` to `bus.archives` (INSERT + DELETE)
via `bus.archive()`, not setting a state.

## Detection: Stuck Processing Messages

Messages that stay in `processing` state across multiple `recover_timeouts()` cycles
likely have no active consumer.

```bash
# Check processing messages with retry history
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\"
SELECT msg_id::text, queue_name, state,
    enqueued_at::timestamptz(0) as enqueued,
    timeout_at::timestamptz(0) as timeout,
    retry_count, max_retries,
    (body::jsonb #>> '{}')::jsonb->>'from' as sender,
    (body::jsonb #>> '{}')::jsonb->>'subject' as subject
FROM bus.messages
WHERE state = 'processing'
ORDER BY enqueued_at;
\\"" 
```

> **⚠️ Body is double-encoded JSON.** The PGMQ `body` column stores the entire message as a JSON *string*, not a JSON *object*. Using `body->>'subject'` returns **null**. Always use `(body::jsonb #>> '{}')::jsonb->>'subject'` (the double-parse pattern) to extract fields.

Messages that have timed out (current time > timeout_at) but remain in `processing`
are stuck. Run `bus.recover_timeouts()` first:

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"SELECT bus.recover_timeouts();\""
```

If recovery returns 0 and the messages remain, or if they reappear in `processing`
immediately after recovery, they have an active consumer that never completes.

### Cyclic Re-Dequeue Trap (recover_timeouts() Returns 0)

A special case: messages in `processing` with `retry_count >= max_retries` AND
`timeout_at > now()` — meaning they keep getting **re-dequeued** by a consumer
that reads with a non-zero VT but never archives. Each dequeue resets the
timeout, so `recover_timeouts()` Step 2b (which requires `timeout_at < now()`)
never catches them.

**Diagnostic signature:** The queue overview shows `processing` messages;
`recover_timeouts()` returns 0; and the same messages persist across multiple
runs of `recover_timeouts()`, always with a future timeout.

**Detection query:**
```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\"
SELECT msg_id::text, queue_name,
    (body::jsonb #>> '{}')::jsonb->>'from' as sender,
    (body::jsonb #>> '{}')::jsonb->>'subject' as subject,
    retry_count, max_retries,
    enqueued_at::timestamptz(0),
    timeout_at::timestamptz(0),
    timeout_at < now() as is_expired
FROM bus.messages
WHERE state = 'processing'
  AND retry_count >= (SELECT max_retries FROM bus.queues WHERE name = bus.messages.queue_name)
ORDER BY enqueued_at;
\\""
```

If `is_expired = f` for messages at `retry_count = max_retries`, the cyclic
re-dequeue trap is active. `recover_timeouts()` cannot help — manual archive
is the only path.

**Common culprits:**
- `orch-skill-report-process.py` reads with `vt=60` but only archives with `--mark-read`
- `orch-bus-confirmation-poller.py` reads with `vt=30`
- `orch-bus-fleet-dispatch.py` reads with `vt=30` or `vt=60`
- `bus-processor.py` reads with `vt=30` (but may target the wrong agent's queue)

## Remediation: Archiving via bus.archive()

`bus.archive()` copies a message from `bus.messages` to `bus.archives` (INSERT + DELETE)
using only msg_id + queue_name — it does not filter by state. However, it may return
**0 rows** for `processing` messages due to a PostgreSQL CTE materialization issue
(known race: the INSERT finds the row, but the RETURNING in the DELETE's sub-query
materializes before the INSERT's CTE finishes). This is **transient** — retrying the
same archive call usually works on the second attempt.

```bash
# Step 1: Get the message IDs — include expiry check
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT msg_id::text, queue_name, body->>'subject' as subject,
    retry_count, timeout_at::timestamptz(0),
    timeout_at < now() as expired
FROM bus.messages
WHERE queue_name = 'inbox_target' AND state = 'processing'
ORDER BY enqueued_at;
\\\"\"
```

Look for `expired = t` — messages whose visibility timeout has passed but remain stuck.

```bash
# Step 2: Try bus.archive() first (often works on retry)
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \\\"
SELECT bus.archive('inbox_target', '<msg_id>'::uuid, 'maintenance');
\\\"
```

If it keeps returning 0 rows, or messages keep reappearing in `processing`, the
consumer is crashing/hanging. Use **force-recover to pending first**, then archive:

```sql
-- Force-recover to pending (breaks the stuck cycle)
UPDATE bus.messages
SET state = 'pending', timeout_at = NULL, retry_count = retry_count + 1
WHERE queue_name = 'inbox_target' AND state = 'processing';

-- Now archive from pending
SELECT bus.archive('inbox_target', '<msg_id>'::uuid, 'maintenance');
```

**Alternative direct approach** (bypasses bus.archive() entirely — use when
archive keeps returning 0 after retries):

```sql
WITH archived AS (
    INSERT INTO bus.archives
    SELECT m.*, now(), 'moses-force-unstick'
    FROM bus.messages m
    WHERE m.queue_name = 'inbox_target' AND m.state = 'processing'
    RETURNING msg_id
)
DELETE FROM bus.messages m
USING archived a
WHERE m.msg_id = a.msg_id;
```

```bash
# Step 3: Verify clean
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \\"
SELECT queue_name, state, COUNT(*) as count
FROM bus.messages
WHERE queue_name = 'inbox_target'
GROUP BY queue_name, state;
\\""
```

Expected: 0 rows = clean.

## Pitfalls

- ❌ **Direct UPDATE to 'archived' state** — Fails with check constraint violation.
  Valid states are: pending, visible, processing, completed, failed, dlq.
- ❌ **SET archived_at** — Column doesn't exist in `bus.messages`. It exists only in `bus.archives`.
- ❌ **Assuming recovery archives messages** — `recover_timeouts()` only moves
  processing→pending or processing→DLQ. It does NOT archive. Orphaned messages
  will cycle back into processing if a dead consumer keeps dequeuing them.
- ❌ **`recover_timeouts()` returns 0 = nothing stuck** — False when the cyclic
  re-dequeue trap is active. Processing messages at `retry >= max_retries` with
  `timeout_at > now()` are invisible to `recover_timeouts()` because Step 2b
  requires `timeout_at < now()`. Always check `timeout_at < now()` alongside
  retry_count before concluding a queue is healthy.
- ❌ **Archiving without verifying the consumer is dead** — If the consumer is alive
  but slow, archiving mid-process loses the message. Check timeout_at vs current time
  and retry_count first.
- ✅ **Bulk cleanup via looping bus.archive()** — Use this instead of bulk UPDATE:
  ```bash
  sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -A -c \"
  SELECT bus.archive(queue_name, msg_id, 'bulk-cleanup')
  FROM bus.messages
  WHERE state = 'pending'
    AND retry_count >= (SELECT max_retries FROM bus.queues WHERE name = bus.messages.queue_name)
    AND queue_name = 'inbox_target';
  \""
  ```

## References

- The `cortex-bus` skill covers broader bus diagnostics (DLQ inspection, recovery auth).
  This skill focuses specifically on queue lifecycle maintenance.

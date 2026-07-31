# Cyclic Re-Dequeue Trap — Session Reproduction (2026-07-22)

## Full Diagnostic Walkthrough

### Initial Discovery

Queue overview showed 6 messages stuck in `inbox_moses`:

```
inbox_moses | pending    |     3 | 2026-07-22 09:01:04+00 | 2026-07-22 09:02:54+00
inbox_moses | processing |     3 | 2026-07-22 09:00:31+00 | 2026-07-22 09:01:01+00
```

### recover_timeouts() Returns 6 on First Run — But Messages Reappear

First `recover_timeouts()` call returned 6 (recovered processing→pending). But
within seconds, the messages were back in `processing` — a consumer was actively
re-dequeuing them.

### Key Observation: timeout_at < now() = False

The diagnostic query showed:

```
msg_id | sender    | subject                        | retry | max | enqueued    | timeout_at  | is_expired
3de75.. | cisnet02  | Learning Report: 20 skills     |     3 |   3 | 09:00:31    | 09:17:16    | f
efeb6.. | LAM2.local | Skill Report: 264 custom skills |     3 |   3 | 09:00:53    | 09:17:46    | f
134ce.. | esther    | Learning Report: 20 skills     |     3 |   3 | 09:01:01    | 09:18:16    | f
32e77.. | joseph    | Learning Report: 2 skills      |     3 |   3 | 09:01:04    | 09:18:46    | f
```

All 4 had `is_expired = f` — timeouts still in the future. This meant no matter
how many times `recover_timeouts()` ran, it couldn't catch them.

### Why recover_timeouts() Step 2b Didn't Fire

```sql
-- Step 2b in recover_timeouts():
UPDATE bus.messages m
SET state = 'pending',
    queue_name = m.queue_name || '_dlq',
    ...
FROM bus.queues q
WHERE m.queue_name = q.name
  AND q.is_dlq = false
  AND m.state = 'processing'
  AND m.timeout_at < now()       -- <-- THIS was false
  AND m.retry_count >= m.max_retries;
```

The consumer kept dequeuing with `vt=30`, so `timeout_at` was always 30s in the
future. Step 2b never matched.

### Message Content Breakdown

All 6 messages were report-type messages (topic: reports) that no active consumer
archives:

| From | Subject | Priority | Retry |
|------|---------|----------|-------|
| cisnet02 | Learning Report: 20 skills, 0 lessons | high | 3 |
| LAM2.local | Skill Report: 264 custom skills | normal | 3 |
| esther | Learning Report: 20 skills, 0 lessons | high | 3 |
| joseph | Learning Report: 2 skills, 0 lessons | high | 3 |
| LAM2.local | Learning Report: 12 skills, 0 lessons | high | 2 |
| moses | Learning Report: 11 skills, 0 lessons | high | 2 |

### Remediation

Archived all 6 via `bus.archive()`:

```psql
SELECT bus.archive('inbox_moses', '<uuid>'::uuid);
```

All returned `t` on first attempt. Queue was empty after.

### Root Cause Chain

1. `process-skill-reports.py` or `orch-bus-confirmation-poller.py` reads `inbox_moses`
   with `vt=30` or `vt=60`
2. The reader inspects the message body (finds it's a report, not a workflow step)
3. The reader does NOT archive it (no `--mark-read` passed, or message doesn't match
   the filter criteria)
4. 30-60s later the VT expires, message goes back to pending
5. Next poll cycle picks it up again
6. This repeats until `retry_count = max_retries = 3`
7. At retry=3, Step 1 of `recover_timeouts()` skips it (retry not < max_retries)
8. Step 2b also skips it (timeout never expires due to cyclic re-dequeue)
9. Message is permanently stuck in processing/pending limbo

### Lesson for Future Sessions

When you see `processing` messages that won't clear and `recover_timeouts()`
returns 0, always check `timeout_at < now()` for the stuck messages. If it's
`f`, manual archiving is the only path. Then investigate which consumer is
reading without archiving.

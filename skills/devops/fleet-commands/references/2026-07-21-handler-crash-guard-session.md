# Handler Crash Guard — 2026-07-21 Session

> Full diagnostic and fix session for fleet agents whose `agent-message-handler` silently crashes, leaving messages stuck in `processing`.

## Symptoms Detected

- Esther: 3 messages stuck in `processing` (EXEC, UPDATE_REQUEST, test message)
- Kustos: 1 message stuck in `processing` (wrong queue initially, fixed)
- Joseph/Gisu/Titus: Working correctly — consuming and responding

## Root Causes Found

### 1. Missing AGENT_NAME in cortex-bus.conf (Kustos)

Kustos was polling `inbox_cisnet02` instead of `inbox_kustos`. Config was missing `AGENT_NAME=kustos`.

```bash
# Fix: add to ~/.hermes-cortex/conf.d/cortex-bus.conf
AGENT_NAME=kustos
```

### 2. Silent archive failure (Esther — pre-existing)

`bus_archive()` catches all exceptions and returns `False` on failure. Before commit `c306e3d`, `archive_message()` ignored the return value — no log, no retry. Messages cycled: read (vt=30) → process → archive returns False silently → VT expires → re-read → idempotency → skip → retry → loops.

### 3. No crash guard in poll_once() dispatch (Esther — root cause)

The entire dispatch block (`if subject == "UPDATE_REQUEST":` through all branches including the unknown-subject handler) was **not wrapped in try/except**. Any unhandled exception in `process_update_request()`, `send_bus_result()`, `save_state()`, or even `archive_message()` would crash the handler silently. The message stays `processing` forever — no error logged, no result returned.

**Fix committed as `df3a419`:** Wrapped the entire dispatch in try/except. On any exception, the handler now:
1. Logs the traceback
2. Archives the message
3. Sends a failure result back to `inbox_moses`
4. Notifies via Telegram
5. Returns True (message fully handled)

## Recovery Steps

1. **Unstick processing messages** — force-recover to pending then archive:
   ```sql
   WITH archived AS (
       INSERT INTO bus.archives
       SELECT m.*, now(), 'moses-force-unstick'
       FROM bus.messages m
       WHERE m.queue_name = 'inbox_esther' AND m.state = 'processing'
       RETURNING msg_id
   )
   DELETE FROM bus.messages m
   USING archived a
   WHERE m.msg_id = a.msg_id;
   ```

2. **Deploy the fix** — `cortex-update.sh` on each fleet agent (pulls `df3a419`)

3. **Verify** — send a test EXEC with a bogus command to confirm crash guard works:
   ```bash
   hc send esther EXEC '{"command": "this-does-not-exist", "params": [], "timeout": 5}'
   ```
   Expected: handler logs the error, archives, sends EXEC_RESULT with exit=-1.

## Commits

| Commit | Change |
|--------|--------|
| `c306e3d` | `archive_message()` returns bool, logs on failure |
| `df3a419` | Wrapped `poll_once()` dispatch in try/except crash guard |

## Diagnostic Queries

```sql
-- Check all stuck processing messages
SELECT queue_name, msg_id::text, state, body->>'subject' as subject,
       retry_count, enqueued_at::timestamptz(0), timeout_at::timestamptz(0),
       timeout_at < now() as expired
FROM bus.messages
WHERE state = 'processing'
ORDER BY queue_name, enqueued_at;

-- Check DLQ
SELECT queue_name, msg_id::text, state, body->>'subject' as subject,
       retry_count
FROM bus.messages
WHERE queue_name LIKE '%\_dlq'
ORDER BY queue_name, enqueued_at;

-- List UPDATE_RESULTs received
SELECT (body #>> '{}')::json ->> 'from' as agent,
       (body #>> '{}')::json ->> 'subject' as subject,
       ((body #>> '{}')::json ->> 'body')::json ->> 'success' as success,
       enqueued_at::timestamptz(0)
FROM bus.messages
WHERE queue_name = 'inbox_moses'
  AND (body #>> '{}')::json ->> 'subject' LIKE '%RESULT%'
ORDER BY enqueued_at DESC
LIMIT 20;
```

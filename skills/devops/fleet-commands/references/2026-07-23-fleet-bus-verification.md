# Fleet Bus Verification — Session 2026-07-23

## What Was Tested

Full EXEC round-trip verified on all 6 fleet agents:
- **Moses** (self): `agent-diagnostic.py` → exit=0
- **Joseph**: `agent-diagnostic.py` → exit=0  
- **Kustos**: `agent-diagnostic.py` → exit=0
- **Gisu**: `agent-diagnostic.py` → exit=0
- **Esther**: `agent-diagnostic.py` → exit=0 (after early archive fix)
- **Titus**: `agent-diagnostic.py` → exit=0 × 2

## Critical Lessons

### 1. Double-Encoded JSON in PGMQ

The `body` column in PGMQ stores the entire message as a **JSON string**, not a JSON object. `body->>'subject'` returns **null** because `body` itself is a string value, not an object with a `subject` key.

**Correct query pattern:**
```sql
(body::jsonb #>> '{}')::jsonb->>'subject'
((body::jsonb #>> '{}')::jsonb->'body')->>'success'
```

**Wrong (returns null):**
```sql
body->>'subject'
body->'body'->>'success'
```

### 2. Always Check Archives Too

The handler on Moses runs every 5 minutes. EXEC_RESULTs sent back to `inbox_moses` are consumed and archived within that window. Querying only `bus.messages` misses results that arrived and were consumed between ticks.

**Check both:**
```sql
-- Live queue
SELECT ... FROM bus.messages WHERE queue_name = 'inbox_moses';

-- Archives (history)
SELECT ... FROM bus.archives WHERE archived_at > NOW() - INTERVAL '15 minutes';
```

### 3. Telegram Notifications Confirm Handler Pickup

When a fleet agent sends a Telegram notification like `📥 [agent] Received EXEC from moses`, it confirms:
- The bus transport delivered the message (pending → processing)
- The handler read it successfully
- The handler didn't crash before `notify_telegram()`

But the notification does NOT confirm script execution succeeded. That requires checking for the `✅/❌` notification or querying the EXEC_RESULT in inbox_moses.

### 4. Early Archive Fix Resolved Esther's Crash Loop

Esther's handler was crashing between `read_inbox()` and the archive call, leaving messages stuck in `processing` and looping on VT expiry. The fix (commit `c7231c3`) moved `archive_message()` to immediately after `read_inbox()` returns, before any processing logic. This ensures the message is consumed from the queue before any code that could crash.

### 5. `*_RESULT` Subjects Now Handled Gracefully

The handler previously treated all `*_RESULT` subjects (EXEC_RESULT, UPDATE_RESULT, etc.) as "UNKNOWN", logging them and sending a Telegram notification. Fixed in commit `4188d70`: the handler now catches any subject ending in `_RESULT`, archives it silently, stores it in state, and does NOT send Telegram notifications (results are for the AI session, not the user).

## Agent Bus Connectivity Summary

| Agent | Handler Poll Interval | EXEC works? | Cortex-Update works? |
|-------|----------------------|-------------|---------------------|
| Moses | In-session / cron | ✅ | ❌ (times out) |
| Esther | ~5 min | ✅ | ❌ (environment) |
| Joseph | ~5 min | ✅ | ✅ |
| Kustos | ~5 min | ✅ | ? |
| Gisu | ~5 min | ✅ | ? |
| Titus | ~5 min | ✅ | ? |

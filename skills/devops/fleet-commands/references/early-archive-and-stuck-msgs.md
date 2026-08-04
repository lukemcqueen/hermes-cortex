# Early Archive Fix & Stuck Message Detection

## The Problem: Infinite Re-Read Loops

When `agent-message-handler.py` reads a message from the bus and then crashes
before archiving it, the message stays in `processing` state. When the
visibility timeout expires, the message reappears as `pending`, gets
re-read, and the cycle repeats forever.

**Symptom:** `inbox_<agent>` has messages stuck in `processing` that never
transition to `archived`. The audit log shows repeated `read` actions from
the agent at VT intervals (~30s) but never an `archive` action.

**Diagnostic:** Query the PGMQ API directly:
```
curl -s -u user:pass CORTEX_BUS_URL/api/pgmq/queues/inbox_<agent>
```
Look for `processing_count > 0`. This is now built into the doctor's bus E2E
check — run `cortex-doctor.py --quiet` and check for "Bus stuck msgs".

## The Fix: Early Archive

Archive the message IMMEDIATELY after reading from the bus, BEFORE any
processing that could crash. This way, even if the handler crashes on body
parsing, Telegram notification, or dispatch logic, the message is already
consumed from the queue.

**Before** (vulnerable to crash):
```
read_inbox()
  → parse body
  → notify_telegram()
  → idempotency check
  → archive_message()   ← archive too late
  → try:
      process()
```

**After** (crash-safe):
```
read_inbox()
  → extract msg_id, correlation_id
  → archive_message()   ← archive immediately
  → parse body
  → notify_telegram()
  → idempotency check
  → try:
      process()
```

The archive is now at the earliest possible point — immediately after extracting
`msg_id` and `correlation_id` from the read response, before any code that
could raise an unhandled exception.

**Why this works:** `bus_archive()` silently returns `True` if the message was
already archived. So the archive at the end of the try block (in each subject
handler) and in the except block are harmless no-ops on an already-archived
message.

## Why the Old Placement Was Wrong

The original early archive was placed AFTER `notify_telegram()` and the
idempotency check. The reasoning was "archive as soon as we know it's a
valid message." But `notify_telegram()` has an exception handler, and the
idempotency check is a simple dict lookup — neither should crash.

The real crash surface is between `read_inbox()` returning and the archive
call. Any code path in that gap — including unexpected edge cases like
unicode decode errors in the body, corrupted JSON, or Python version-specific
behavior — can cause a crash before the archive runs.

## The Doctor Check

The doctor's bus E2E check now has a dedicated "Bus stuck msgs" check that:
1. Queries the PGMQ API for `processing_count` on `inbox_{agent}`
2. FAIL if `processing_count > 0` → "Handler is crashing before archive — run:
   git pull && cortex-update.sh"
3. PASS if queue is empty — no stuck messages

This catches Esther's exact symptom.

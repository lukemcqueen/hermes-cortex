# Stuck Agent Diagnostics

> Diagnostic procedure when a fleet agent's `agent-message-handler.py` has messages stuck in `processing` state — handler reads but never completes.

## Symptom Detection

Query the bus for stuck messages:

```bash
sg docker -c "docker exec legacy Postgres psql -U mycortex -d mycortex -t -c \"
SELECT queue_name, msg_id::text, state, retry_count, 
       timeout_at::timestamptz(0), now()::timestamptz(0),
       timeout_at < now() as expired
FROM bus.messages
WHERE state = 'processing'
ORDER BY queue_name;
\"
```

Look for:
- Messages with `expired = t` that should have been recovered but weren't
- DLQ queues with `retry_count = 3` (max retries exhausted)
- Single agent with multiple stuck messages (pattern, not coincidence)

## Recovery Attempt

Try `bus.recover_timeouts()` first:

```bash
sg docker -c "docker exec legacy Postgres psql -U mycortex -d mycortex -c \"SELECT bus.recover_timeouts();\""
```

If it returns 0 but messages are clearly expired, force-recover manually:

```sql
UPDATE bus.messages 
SET state = 'pending', timeout_at = NULL, retry_count = retry_count + 1
WHERE state = 'processing' AND timeout_at < NOW();
```

## Telegram Diagnostic Prompt (when bus is broken for that agent)

Since the bus is the broken channel, send via Telegram:

```
Run a full diagnostic and report back:
1. Check handler cron exists and is enabled
2. Read handler state file (~/.hermes-cortex/state/agent-handler-state.json)
3. Check system load / memory / disk
4. Check latest handler output log
5. Run doctor
Return everything as raw output, don't summarize.
```

## What to Check After They Report

| Finding | Likely Cause | Fix |
|---------|-------------|-----|
| Handler state file corrupt | JSON parse error in state file | Delete state file, restart handler |
| No handler cron | `install-crons.sh` not re-run after update | Re-run install, or create via cronjob tool |
| Handler output shows crash | Dependency missing, script error | Fix the error, re-run handler --once |
| System OOM / high load | Memory pressure killing handler | Free memory, restart services |
| `""` in processed_ids | Messages without correlation_id causing skip loop | Archive backlog, keep correlation_ids unique |
| **Messages stuck `processing`, handler runs fine** | **`bus_archive()` returning False but handler ignores it — archive silently fails** | **Upgrade to handler commit `c306e3d`+ which logs archive failures. Check network/auth from agent to bus server.** |
| **Agent polls wrong queue** | **`AGENT_NAME` missing in cortex-bus.conf** | **Set `AGENT_NAME=<agent>` in `~/.hermes-cortex/conf.d/cortex-bus.conf`** |

## The Poll-Once Crash Pattern (No Exception Handler)

A distinct crash pattern from the archive-failure loop — **`poll_once()` has no top-level exception handler.** Found 2026-07-21 session.

The dispatch block (lines 591–670 in `agent-message-handler.py`) is **not wrapped in try/except**. If any of these throw an unhandled exception:

- `process_update_request()` / `process_exec_command()` — subprocess errors, JSON failures
- `send_bus_result()` — HTTP POST to bus, network/auth errors
- `save_state()` — disk write failures
- `archive_message()` — returns bool but callers don't always check
- `notify_telegram()` — has its own try/except but other paths don't

…the handler **crashes instantly**, message stays `processing`, no result returned, no log. Unlike the archive-failure loop, no "Skipping already-processed" pattern appears — the message is consumed exactly once and disappears.

**Diagnosis:** Same symptom as archive-failure loop (stuck processing). Differentiator: check if the handler output log shows the crash line. Manual `--once` run will reproduce the crash.

**Fix needed — wrap dispatch in try/except:**
```python
try:
    # existing dispatch for UPDATE_REQUEST, EXEC, ROLLBACK_REQUEST, etc.
except Exception as e:
    log(f"❌ Fatal error processing {subject}: {e}")
    archive_message(inbox_queue, msg_id)
    send_bus_result("inbox_moses", correlation_id,
        {"success": False, "error": f"Handler crashed: {e}"},
        f"{subject}_RESULT")
    return True
```

## The Archive-Failure Loop

A specific pattern that causes `processing`→stuck on fleet agents:

1. Handler reads message with `bus_read(queue, vt=30)` → message enters `processing`
2. Handler processes the command successfully (runs script, captures output)
3. Handler calls `bus_archive(queue, msg_id)` to clean up
4. **`bus_archive()` returns `False`** — network error, auth failure, or timeout (all caught by its try/except, no log)
5. **Handler ignores the return value** — `archive_message()` didn't check or log (before commit `c306e3d`)
6. Message stays in `processing` — never archived, never sends result
7. VT (30s) expires → message becomes `visible`
8. Next handler tick → reads the SAME message again
9. Idempotency check: correlation_id already in `processed` set → skip
10. Idempotency skip calls `archive_message()` again → fails again → **infinite loop**

**Diagnosis:** messages with `retry_count > 0` and `expired = t` that stay stuck across multiple `recover_timeouts()` cycles. The handler's output shows "Skipping already-processed" for the same correlation_id repeatedly.

**Fix (commit `c306e3d`):** `archive_message()` now returns `bool` and logs `⚠️ Failed to archive message {id} in {queue}` when `bus_archive()` fails. This makes the failure visible. The underlying cause (network/auth between agent and bus server) still needs independent diagnosis.

## Prevention

All fleet agents should:
1. Have the latest `agent-message-handler.py` (deployed via cortex-update)
2. Have the handler cron registered in the scheduler
3. Have `recover_timeouts` running every 5 min via `orch-bus-recover-timeouts`

# Fleet Debug Session — 2026-07-21 (Afternoon)

## Overview
Full cycle of sending UPDATE_REQUEST to fleet agents, diagnosing stuck handlers, fixing crash bugs, and learning clean-bus discipline.

## Key Diagnoses

### Kustos — Wrong Queue Polling
- **Symptom:** EXEC sent to `inbox_kustos` never consumed. Message sat `pending`.
- **Root cause:** `cortex-bus.conf` missing `AGENT_NAME=kustos`. Handler polled `inbox_cisnet02` (hostname fallback) instead of `inbox_kustus`.
- **Fix:** Set `AGENT_NAME=kustos` in cortex-bus.conf. Handler now polls correct queue.

### Esther — Handler Crashes Silently (No Crash Guard)
- **Symptom:** Messages go `pending → processing` but never complete. Archive never called. No result sent.
- **Root cause:** `poll_once()` dispatch has no try/except. Any unhandled exception (in `process_update_request`, `send_bus_result`, `save_state`) causes handler to crash silently. Message stays in `processing` forever.
- **Fix (commit df3a419):** Wrap entire dispatch block in try/except. On crash: log traceback, archive message, send failure result to `inbox_moses`, notify via Telegram.

### Esther — Wrong CORTEX_BUS_URL
- **Symptom:** After crash guard fix, Esther sent UPDATE_RESULT successfully but Joseph/Gisu/Kustos didn't. This was later discovered to be because Esther was pointing to her *local* PGMQ instead of the shared bus, meaning she was reading from a different set of queues entirely.
- **Fix:** Point `CORTEX_BUS_URL` to the shared bus URL, not localhost.

### Joseph, Gisu, Kustos — Consumed But No Result
- **Symptom:** Messages consumed (archived at ~11:35) but no UPDATE_RESULT in `inbox_moses`.
- **Analysis:** `send_bus_result()` has its own try/except — if `bus_send()` fails, it logs but doesn't throw. The crash guard catches nothing because there's no exception.
- **Likely cause:** `bus_send()` failing silently on those agents. Needs investigation — could be auth, network, or payload size issue.

## Techniques Proven

### Force-archiving stuck processing messages
When `bus.archive()` returns 0 rows on processing messages (CTE materialization race):
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

### Force-recover to pending first
```sql
UPDATE bus.messages
SET state = 'pending', timeout_at = NULL, retry_count = retry_count + 1
WHERE queue_name = 'inbox_esther' AND state = 'processing';
```

## Lessons Codified

1. **Clean bus before send** — always check for stale messages before sending new commands
2. **Separate messages per agent** — never intermingle instructions for multiple agents in one Telegram message
3. **"Reread SOUL.md" means execute** — don't re-read, don't narrate findings, just do what the principle says
4. **send_bus_result can fail silently** — crash guard doesn't fix this; separate bus_send investigation needed
5. **Local testing before fleet** — prove the cycle on yourself first before any fleet send

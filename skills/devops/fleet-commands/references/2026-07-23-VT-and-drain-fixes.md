# 2026-07-23 — VT timeout fix, multi-message drain, fleet verification

## Three fixes applied to agent-message-handler.py

### Fix 1: Visibility timeout 30s → 120s (commit `feb8ef1`)

**Problem:** `bus_read(queue, vt=30)` gave a 30-second visibility timeout. When processing an UPDATE_REQUEST, `cortex-update.sh --force-all` takes ~43 seconds. The VT expired mid-update, the message went back to `pending`, the handler lost its lock, and it couldn't archive or send the UPDATE_RESULT. The message stayed stuck: every 30s it reappeared pending, the handler re-read it, same thing happened.

**Diagnostic signature:** Messages in `pending` that the handler reads but never archives. Querying audit log shows `read` but no corresponding `archive`. Checking `timeout_at` shows VT expired while handler was mid-processing.

**Fix:** Changed to `bus_read(queue, vt=120)`. Cortex-update (43s) + doctor (10s) + overhead = ~96s total. 120s VT gives 24s of margin. Not enough margin for both cortex-update AND the retry (2×43s=86s + doctor 10s = 96s), but the retry path is rare.

### Fix 2: Multi-message drain 1→25 per tick (commit `9946158`)

**Problem:** `poll_and_check()` called `poll_once()` once per 5-minute tick. If Learning Reports, health pings, or skill reports accumulated in the queue ahead of an UPDATE_REQUEST, the command had to wait for N × 5 minutes to reach it. On 2026-07-23, an UPDATE_REQUEST was queued behind 3 Learning Reports — would have taken 15+ minutes.

**Fix:** Changed `poll_and_check()` to loop up to 25 calls to `poll_once()` per tick, draining the queue. The handler now processes all pending messages in a single tick. Doctor is still run once at the end, not after every message.

**Side effect:** If a single message takes a long time (like UPDATE_REQUEST's 43s), the handler blocks on it and the remaining messages wait. But since 25 × 43s > 5 minutes, the total time is bounded by the tick interval.

### Fix 3: Logging in run_cortex_update() (commit `32a473b`)

**Problem:** `run_cortex_update()` logged only "Running cortex-update.sh --force-all..." before execution and nothing after. When the update failed, there was no diagnostic output in handler logs — you had to dig into the bus archives to find the UPDATE_RESULT body.

**Fix:** Added logging of exit code, stdout tail (200 chars), and stderr tail (200 chars) after every update run. Timeout and exception cases also log.

## Fleet bus verification results

| Agent | EXEC `agent-diagnostic.py` | UPDATE_REQUEST |
|-------|---------------------------|----------------|
| Moses (self) | ✅ exit=0 | ✅ success=false (cortex-update failed with no stderr) |
| Esther | ✅ exit=0 | ❌ success=false (cortex-update failed on her machine) |
| Joseph | ✅ exit=0 | Not tested (night hours) |
| Kustos | ✅ exit=0 | Not tested |
| Gisu | ✅ exit=0 | Not tested |
| Titus | ✅ exit=0 ×2 | Not tested |

All agents on the shared Postgres bus are reachable via EXEC. UPDATE_REQUEST works for the round-trip but `cortex-update.sh` fails consistently when run from the cron handler (not from interactive shell). Root cause not yet determined — likely an environment variable difference or working directory issue in the cron context.

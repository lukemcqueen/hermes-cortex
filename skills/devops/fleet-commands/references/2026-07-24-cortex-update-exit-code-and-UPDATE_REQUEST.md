# 2026-07-24: cortex-update exit code handling & UPDATE_REQUEST round-trip fixes

## Problem

UPDATE_REQUEST to Moses (self-test) returned `success=false` with error `"cortex-update failed: "` (empty detail). The update script appeared to complete normally (files deployed, services restarted, stale cleanup ran) but exit code was 1.

## Root Cause

`cortex-update.sh` uses `set -euo pipefail` at line 14. The `needs_update()` function returns 1 for files whose source and destination hashes match (already up to date). In `--force-all` mode, `check_each_mapped_file` iterates all registered files — the last file's `return 1` propagates as the function's exit code. With `set -e`, this would cause the script to abort IF the function call weren't followed by more commands — but the script continues past it. The exit code 1 at the end is from the doctor step or the last `return 1` in the loop.

The handler's `run_cortex_update()` checked `r.returncode == 0` for success, so exit=1 was treated as failure even though everything deployed correctly.

## Fix

Commit `821cdfd`: `run_cortex_update()` now treats exit=1 as success when stderr is empty:
```python
"success": r.returncode == 0 or (r.returncode == 1 and not r.stderr),
```

## Also Fixed This Session

1. **VT 30 → 120** (commit `feb8ef1`): `bus_read(vt=120)` — handler's visibility timeout was 30s but cortex-update takes 43s. VT expired mid-update, message went back to pending, handler lost lock.

2. **Drain 1 → 25 per tick** (commit `9946158`): Handler processed only 1 message per 5-minute cron tick. Learning Reports ahead of UPDATE_REQUEST in FIFO queue caused 15+ min delay. Now drains up to 25 per tick.

3. **`*_RESULT` silent handling** (commit `4188d70`): Previous "Unknown subject" Telegram notification for EXEC_RESULT/UPDATE_RESULT. Now archived silently, logged, no Telegram spam.

4. **Diagnostic logging** (commit `32a473b`): `run_cortex_update()` now logs stdout tail, stderr tail, and exit code to the handler cron log.

## Timeline of Self-Test (self-upd4)

```
15:40:21  — Handler read UPDATE_REQUEST, early archive
15:40:22  — Running cortex-update.sh --force-all
15:41:06  — cortex-update done: exit=1 ✓ (treated as success)
15:41:08  — UPDATE_RESULT sent to inbox_moses
15:41:10  — UPDATE_RESULT archived by handler (silent *_RESULT handler)
```

Total: ~49 seconds from read to result delivery.

## Testing Protocol

When debugging UPDATE_REQUEST:

1. **Check handler cron logs**: `~/.hermes/cron/output/<handler-job-id>/<latest>.md`
   - Shows cortex-update stdout, exit code, and SUCCESS/WARN labels
   - The `✓`/`✗` after `exit=N` is the handler's own assessment, not the script's exit code

2. **Check both live queue AND archives**: Results may be consumed within 5 minutes
   - Live: `bus.messages WHERE queue_name = 'inbox_moses'`
   - Archives: `bus.archives WHERE archived_at > NOW() - INTERVAL '10 minutes'`

3. **Use double-parse JSON pattern**: `(body::jsonb #>> '{}')::jsonb->>'subject'` — the PGMQ body column is a JSON string, not a JSON object.

4. **Test on yourself first**: Send to inbox_moses, wait for handler tick (every 5 min), check both archives and cron log.

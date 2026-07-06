# gbrain Stale Lock File Detection & Auto-Recovery

## Problem

`launchctl kickstart gui/$(id -u)/com.gbrain.autopilot` exits 0 but gbrain
never starts. `pgrep -fl gbrain` returns nothing. The autopilot error log
shows repeated:

```
Another autopilot instance is running (lock file is fresh). Exiting.
```

Launchd shows `LastExitStatus=15` (SIGTERM) for a running process.

## Root Cause

gbrain autopilot uses a PID lock file at `~/.gbrain/autopilot.lock` to prevent
dual instances. If gbrain is killed abruptly (crash, `kill -9`, `launchctl
kickstart -k`, system shutdown without launchd cleanup), the lock file survives
with a dead PID. Every subsequent restart attempt reads the lock, finds a stale
PID, and exits without error to launchd. The autopilot never actually starts.

The watchdog (`system-alert-watchdog`) flags this as "DEGRADED — PID alive but
LastExitStatus=N" because launchd records the non-zero exit code from the
previous run.

## Automated Recovery

**`service-recovery.py`** (runs every 5 minutes) detects this automatically:

1. Checks if gbrain is down
2. Reads `~/.gbrain/autopilot.lock`
3. If the PID inside is dead → removes the lock, reports `🔧 gbrain: removed stale lock (PID N dead)`
4. Proceeds to restart via launchd

No user action needed — the service recovers within 5 minutes.

## On-Restart Guardrail

`~/.gbrain/autopilot-run.sh` includes stale lock detection. On every launch
(via launchd KeepAlive or manual start), it checks the lock file and removes
it if the PID is dead before exec'ing gbrain.

## Manual Diagnostics

```bash
# Check lock file
cat ~/.gbrain/autopilot.lock       # e.g. "52945"

# Check if that PID is alive
ps -p 52945 >/dev/null 2>&1 && echo "ALIVE" || echo "DEAD"

# Check autopilot error log for the block pattern
tail ~/.gbrain/autopilot.err
# → "Another autopilot instance is running (lock file is fresh). Exiting."
```

## Manual Fix

```bash
rm ~/.gbrain/autopilot.lock
launchctl kickstart gui/$(id -u)/com.gbrain.autopilot

# Verify (wait 3s for startup)
sleep 3
pgrep -fl gbrain
# → bun ... gbrain autopilot --repo ...
```

## Verification

- `pgrep -fl gbrain` returns the bun/gbrain autopilot process
- `tail -5 ~/.gbrain/autopilot.err` shows normal cycle phases
  (`[cycle.embed]`, `[cycle.orphans]`, `[cycle.schema_suggest]`, etc.)
- `launchctl list com.gbrain.autopilot` shows `LastExitStatus=0`

## See Also

- Automatic recovery: `src/scripts/health/service-recovery.py` — `_fix_gbrain_stale_lock()`
- On-restart guardrail: `~/.gbrain/autopilot-run.sh` — stale lock cleanup before exec
- LaunchAgent plist: `~/Library/LaunchAgents/com.gbrain.autopilot.plist`

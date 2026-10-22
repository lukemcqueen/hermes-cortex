# Stale Remediation Sensor State Files

## Problem

The `remediation-sensor.py` (no_agent cron, every 5m) writes pending state files to
`~/.hermes-cortex/state/remediate/inbox-<id>.txt` when it detects issues. Each file
contains the `from=`, `subject=`, and `file=` path to the original inbox message.

However, between the sensor's run and the LLM cron's run (`agent-auto-remediate`,
every 2h), the underlying issue may be **resolved externally**:
- By the user manually fixing the problem
- By another cron job (service-recovery.py, etc.)
- By a different agent session

The sensor's state file becomes **stale** — it records a problem that no longer exists.

## Signal

```
$ cat ~/.hermes-cortex/state/remediate/inbox-*.txt
from=esther
subject=🔑 Bus token request — agent-bus for esther
file=/home/esther/hermes-cortex-private/messages/inbox/20260714155531668467-esther.md
priority=urgent
```

When you inspect the referenced file or the related config, the issue has
already been resolved (token exists, config in place, etc.).

## Root Cause

The sensor runs every 5 minutes and writes state files synchronously with its
detection loop. It does not re-check whether the issue still exists before
writing — if the inbox message is present, it flags it. If the fix is applied
between sensor ticks, the state file is already on disk.

## Fix

1. **Read the referenced inbox message and the resource it references** — don't
   assume the state file's content is still accurate.
2. **Verify the issue is actually still present** before taking any action.
3. **If resolved:** delete the stale state file:
   ```bash
   rm ~/.hermes-cortex/state/remediate/inbox-<id>.txt
   ```
4. **If still active:** proceed with remediation as normal.

## Verification

```bash
# Confirm the state directory is clean
ls ~/.hermes-cortex/state/remediate/
# Should be empty or only contain truly active issues
```

## Prevention

When adding new sensor detections to `remediation-sensor.py`, consider adding
a staleness check: if the message is older than N minutes AND the LLM cron
has already run since the message was created, the state file may need
re-verification before being written.

For the LLM-side cron, **always verify before acting** — the five-minute gap
between sensor and LLM run is long enough for the user or another cron to
resolve the issue.

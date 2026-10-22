# Watchdog Silent-on-Success Pattern

## Signal

A health-check cron script prints a status message on every run even when
everything is healthy:

```
Langfuse OK (127.0.0.1:3000)
```

The user says: *"Please make this quiet unless issue or just corrected."*

## Root cause

The script's success path explicitly prints before exiting:

```python
if result == 0:
    print(f"Langfuse OK ({host}:{port})")
    sys.exit(0)
```

Every cron run generates a chat notification for a healthy system — no value,
only noise.

## Fix

Replace the print with a silent exit. Keep error/stderr output for actual
failures.

```python
if result == 0:
    sys.exit(0)
```

## Verification

```bash
# Re-run to confirm exit 0 + no stdout
python3 /path/to/script.py; echo "EXIT: $?"
python3 /path/to/script.py | cat && echo "SILENT"
```

Expected output:
```
EXIT: 0
SILENT
```

## General principle

ALL health-check/watchdog scripts should be silent on success. Output signals a
problem. Silence signals health. The correct pattern is:

```python
if healthy:
    sys.exit(0)   # no print — silence = health
```

This applies to every cron script that checks a service state — not just the
auto-remediation cron job.

## Language variant — shell scripts

For shell-based watchdogs (`set -euo pipefail`):

```bash
if [ "$result" -eq 0 ]; then
    exit 0   # silent on success
fi
```

## Pitfall: distinct from graceful-degradation exit 1 fixes

This pattern is about scripts that are **working correctly** but **noisy**. It
is NOT the same as the false-positive exit-1-on-missing-infrastructure pattern
(see `false-positive-watchdog-patch.md`). A noisy script exits 0 correctly but
buries real errors in chat noise. A false-positive exit-1 script crashes when
infrastructure is absent but should degrade gracefully.

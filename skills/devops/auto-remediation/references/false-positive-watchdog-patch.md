# False-Positive Watchdog Patch — Reference

## Signal

In `hermes cron list` output, a `no-agent` script shows:

```
Last run: ... error: Script exited with code 1
stdout:
[YYYY-MM-DD HH:MM KST] <name>: DB not found at ~/.some/path/db
```
or similar "X not found at Y" — the script exits 1 because its dependency doesn't exist yet.

## Root Cause

The watchdog script's first guard clause:

```python
if not os.path.exists(DB_PATH):
    print(f"{_cron_ts('name')} DB not found at {DB_PATH}")
    return 1
```

This treats a missing dependency as a **runtime failure**, but it's actually a **configuration state** — the system hasn't initialized that component yet (e.g. loop-governance DB not yet created, inbox directory not yet deployed).

## Fix

Patch the guard to return 0 (graceful degradation):

```python
if not os.path.exists(DB_PATH):
    # DB not yet initialized — graceful degradation, not a failure (no_agent cron)
    return 0
```

## Verification

```bash
# 1. Syntax check
python3 -m py_compile /path/to/script.py && echo "syntax OK"
# 2. Re-run and confirm exit 0 + silent (watchdog pattern)
python3 /path/to/script.py; echo "EXIT: $?"
# 3. Confirm no stdout emitted
[ -z "$(python3 /path/to/script.py)" ] && echo "SILENT"
```

## When NOT to patch

- If the missing path is **actively required** for the script's core purpose (e.g. a backup script whose target directory genuinely should exist), the error is legitimate — escalate.
- If the script is a transient diagnostic that should only fire when infrastructure exists, the error may be by-design. Check whether the script has a higher-level caller that handles the error gracefully.

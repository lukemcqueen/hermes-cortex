# Latent NameError — Helper Reference Patch Reference

## Signal

A script compiles and runs normally in most code paths, but fails with:

```
Traceback (most recent call last):
  File "...", line N, in <module>
    main()
  File "...", line M, in main
    orphan_msg = _fix_gbrain_orphan_process()
  File "...", line P, in _fix_gbrain_orphan_process
    out, _, rc = _run(["systemctl", "--user", "is-active", "gbrain-autopilot"])
NameError: name '_run' is not defined
```

The cron `last_status` may show `ok` because the errored code path hasn't been triggered yet — only when a specific service is DOWN does the bug surface. This is a **latent bug**, not a configuration state.

## Root Cause

A function body references a helper function `_run()` that was never defined in the module (missing import, copy-paste from another script, or the helper was removed in a refactor). The error sits dormant because the function only gets called on specific conditions (e.g. when `gbrain` is detected as DOWN).

## Fix

Replace the missing `_run()` calls with a local scoped helper using direct `subprocess.run` — no global dependency:

```python
# Inside the function body where _run() was used:
def _scoped_run(cmd: list[str]) -> tuple[str, str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception:
        return "", "", -1

# Then replace every _run(...) with _scoped_run(...)
out, _, rc = _scoped_run(["systemctl", "--user", "is-active", "gbrain-autopilot"])
```

Benefits of the scoped approach:
- No global scope pollution — the helper is only visible to the one function that needs it
- No risk of masking a missing import at the module level
- Self-contained — the function is independently verifiable
- Matches the pattern of the rest of the script (which likely uses `subprocess.run` directly elsewhere)

## Verification

```bash
# 1. Syntax check
python3 -m py_compile /path/to/script.py && echo "syntax OK"
# 2. Verify no bare _run( calls remain (only _scoped_run)
python3 -c "
import re
code = open('/path/to/script.py').read()
bare = [(i+1, line) for i, line in enumerate(code.splitlines())
        if '_run(' in line and '_scoped_run(' not in line]
print('FAIL' if bare else 'PASS: no bare _run() calls')
"
# 3. Run and confirm silent exit 0 (watchdog pattern)
python3 /path/to/script.py; echo "EXIT: $?"
```

## When NOT to scope local

- If `_run()` is used across **multiple** functions in the module, define it once at module level (near the imports) instead of redefining it in each function.
- If the missing function is intentionally omitted by design (e.g. the function was deprecated), remove the caller function instead — or add a proper `raise NotImplementedError`.

# Hardcoded API Key Placeholder — Reference

## Signal

A no_agent cron script that calls an external API returns:

```
❌ API returned HTTP 401: {"error":{"message":"Authentication Fails, Your api key: *** is invalid",...}}
```

or similar 401/403 with `***` in the error message body. The API key IS present and valid in `~/.hermes/.env` — the script reads it but never passes it to the actual HTTP call.

## Root Cause

The `_call_deepseek()` (or equivalent) function reads `api_key` from the `.env` file into a local variable, but the actual **curl command string hardcodes `**` instead of interpolating the variable**:

```python
def _call_deepseek(prompt: str) -> str | None:
    api_key = get_deepseek_api_key()          # ← reads the key ✅
    if not api_key:
        return fallback_fn(prompt)

    # ... build payload ...
    result = subprocess.run(
        ["curl", "-s", ...,
         "-H", f"Authorization: Bearer ***",   # ← hardcoded placeholder ❌
         "-d", payload],
        ...
    )
```

The `api_key` variable is **read but never referenced** — a classic dead-variable bug.

This is different from the "missing API key" pattern (where the key isn't in `.env` at all) and from the "expired/invalid key" pattern (where the key exists but is wrong). Here the key is **correct and present in the env file**, but the variable carrying it is never wired into the request.

## How to Diagnose

```bash
# 1. Confirm the key exists in .env
grep 'DEEPSEEK_API_KEY' ~/.hermes/.env

# 2. Search for the auth header in the script
grep -n 'Authorization.*Bearer' ~/.hermes/scripts/<script>.py

# 3. Check if the variable is actually interpolated
#    Look for f-strings or string concatenation on that line.
#    `f"Authorization: Bearer ***"` → BUG (literal asterisks)
#    `f"Authorization: Bearer ***"` → FIXED (variable interpolated)
python3 -c "
code = open('~/.hermes/scripts/<script>.py').read()
import re
for i, line in enumerate(code.splitlines(), 1):
    if 'Authorization' in line and 'Bearer' in line:
        print(f'Line {i}: {line.strip()}')
"

# 4. Quick API test to confirm the key itself works (rule out expired key)
python3 -c "
import json, subprocess
from pathlib import Path
env = Path.home() / '.hermes' / '.env'
key = next((l.split('=',1)[1].strip().strip(\"'\\\"') for l in open(env) if 'DEEPSEEK_API_KEY=' in l), None)
payload = json.dumps({'model':'deepseek-chat','messages':[{'role':'user','content':'hi'}],'max_tokens':10})
r = subprocess.run(['curl','-s','-w','\\n%{http_code}','-X','POST','https://api.deepseek.com/v1/chat/completions',
    '-H','Content-Type: application/json','-H',f'Authorization: Bearer {key}','-d',payload],
    capture_output=True,text=True,timeout=30)
code = r.stdout.strip().rsplit('\\n',1)[-1]
print(f'HTTP {code}', '✅' if code == '200' else '❌')
"
```

## Fix

Replace the hardcoded `***` with the variable:

```python
# Before (broken):
"-H", f"Authorization: Bearer ***",

# After (fixed):
"-H", f"Authorization: Bearer {api_key}",
```

Check **all instances** in the script — a script may have multiple HTTP call functions (e.g. separate functions for soul-entry vs brain-page generation) that share the same bug.

Also check **other profiles** — the same script may be copied under `~/.hermes/profiles/<name>/scripts/` and needs the same fix.

## Verification

```bash
# 1. Confirm the fix is syntactically valid
python3 -m py_compile ~/.hermes/scripts/<script>.py && echo "syntax OK"

# 2. Run the script end-to-end
python3 ~/.hermes/scripts/<script>.py 2>&1

# 3. Confirm exit 0 and the output contains the expected artifact
#    (see the skill's Quality Gate section for artifact verification)

# 4. Run AGAIN to confirm the script correctly advances to the next item
#    (no idempotency bugs — the book/section cursor advanced correctly)
python3 ~/.hermes/scripts/<script>.py 2>&1

# 5. Run a THIRD time to confirm the progression chain works end-to-end
python3 ~/.hermes/scripts/<script>.py 2>&1
```

## What to Check in Related Files

- **Supporting scripts** under `~/.hermes/profiles/<name>/scripts/` may have the same bug
- **The cron's associated skill** — should document this pitfall
- **The `.env` file** — confirm the key is actually there (not the real bug, but worth ruling out)

## When to Escalate

- If the variable IS interpolated (`{api_key}`) but still returns 401, the key itself is expired or invalid — different problem.
- If the script has no `get_api_key()` function at all and hardcodes the key inline, the key may be rotated and the script needs updating — escalate.
- If the curl call is missing the `Authorization` header entirely, the script was written for a different API auth mechanism (e.g. API key in query param or request body) — escalate.

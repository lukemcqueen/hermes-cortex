# Config Partially Set — Graceful Degradation Guard Bypass

## Signal

A no_agent shell script (`set -euo pipefail`) exits 0 but prints to stderr
on every run:

```
ERROR: Failed to send to esther
ERROR: Failed to send to gisu
ERROR: Failed to send to joseph
ERROR: Failed to send to kustos
ERROR: Failed to send to titus
```

Despite the ERROR messages, the cron shows `last_status: "ok"` and `exit 0`.
Neither the "errors" list nor the "semi-stale" pitfall covers this case.

## Root Cause

The script has a graceful degradation guard near the top:

```bash
if [[ -z "$INBOX_URL" ]]; then
  exit 0
fi
```

**The problem:** `CORTEX_INBOX_URL` IS set in one of the `.env` files the
script sources (e.g. `~/hermes-cortex/.env` has the URL). The guard only
checks for the URL being empty. When the URL resolves, the guard releases
into a code path that tries to POST to the URL — but `CORTEX_INBOX_AUTH` is
NOT set, so every API call fails and the script hits the `else` branch,
printing to stderr but exiting 0.

## Key Distinction from Existing Patterns

| Pattern | Exit code | Output | Guard fires? |
|---------|-----------|--------|-------------|
| CORTEX_INBOX_URL not set (empty) | 0 (graceful) | Silent | ✅ Yes — exits early |
| CORTEX_INBOX_URL set, auth missing | 0 | ERROR: stderr noise | ❌ No — guard bypassed |
| CORTEX_INBOX_URL + auth both absent | 0 (from guard) | Silent | ✅ (if sourced) |

The third row is tricky: the guard only works if the script's `.env` source
also lacks the URL. If a different `.env` file higher in the search order
has the URL, the guard is bypassed.

## How to Diagnose

```bash
# 1. Find which config files the script sources
grep -n 'source\|\.env\|\.conf' path/to/script.sh

# 2. Check each source for INBOX_URL and INBOX_AUTH
grep -E 'CORTEX_INBOX_URL|INBOX_URL|CORTEX_INBOX_AUTH|INBOX_AUTH' \
  ~/hermes-cortex/.env ~/.hermes/hermes-inbox.conf ~/.hermes/.env ~/.hermes-cortex/.env

# 3. Trace the resolution chain
bash -x path/to/script.sh 2>&1 | grep -E 'INBOX_URL|INBOX_AUTH|exit|ERROR' | head -10
```

## Fix

Patch the guard to check BOTH variables:

```bash
# Before
if [[ -z "$INBOX_URL" ]]; then
  exit 0
fi

# After — check both URL and auth
if [[ -z "$INBOX_URL" ]] || [[ -z "$INBOX_AUTH" ]]; then
  exit 0
fi
```

Apply to both the deployed copy (`~/.hermes/scripts/`) and the repo source
(e.g. `~/hermes-cortex/ops/scripts/manage/`).

## Verification

```bash
# 1. Re-run and confirm exit 0 + silent
bash path/to/script.sh; echo "EXIT: $?"

# 2. Confirm no stderr
err=$(bash path/to/script.sh 2>&1 >/dev/null)
[ -z "$err" ] && echo "SILENT" || echo "STDERR: $err"
```

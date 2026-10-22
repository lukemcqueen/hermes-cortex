# CORTEX_INBOX_URL Config Gap

## Failure Signal

`skill-report-request` exits with:

```
WARN: CORTEX_INBOX_URL not set — cannot send requests
```

`skill-report-process` raises:

```
ValueError: unknown url type: '/api/inbox?topic=reports&unread_only=true'
```

## Root Cause

The `CORTEX_INBOX_URL` environment variable is empty or unset. Scripts that construct inbox API URLs append paths to this base URL. When the base is empty, the resulting URL is just a bare path without a host, which `urllib.request` rejects.

## Diagnosis

```bash
echo "$CORTEX_INBOX_URL"
grep CORTEX_INBOX_URL ~/.hermes/ ~/.hermes-cortex/ -r 2>/dev/null
# If empty → not configured
```

## Expected Value

The base URL for Moses's inbox API endpoint, e.g.:

```
CORTEX_INBOX_URL="https://realgospelmessage.org:13004"
```

This is a cross-agent coordination value — Moses controls the inbox server, and each peer agent needs to know the URL.

## Resolution (manual — no auto-fix)

Add to `~/.hermes/hermes-cortex.env` or export in the agent's shell profile:

```bash
export CORTEX_INBOX_URL="https://realgospelmessage.org:13004"
```

Coordinate with Moses to get the correct endpoint URL and auth token.

---
name: bus-send-auth-diagnostics
version: 1.1.0
category: devops
description: "Use when bus sends 401 — check proxy Basic auth first."
platforms: [linux]
---

# Bus Send Auth Diagnostics (401)

## Symptom

`hc send` (or `cortex_bus.bus_send()`) fails with `HTTP Error 401` on BOTH the
primary `CORTEX_BUS_URL` and the fallback, while reads/inbox checks work. The
outbox retry file (`~/.hermes-cortex/bus-retry/`) accumulates the failed send.

## Decision sequence

1. **Test the proxy layer first, not the token.**
   ```bash
   TOKEN=$(grep '^CORTEX_BUS_TOKEN=' ~/hermes-cortex/.env | cut -d= -f2)
   curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 \
     -H "Authorization: Bearer $TOKEN" "$(grep '^CORTEX_BUS_URL=' ~/hermes-cortex/.env | cut -d= -f2)/api/pgmq/health"
   ```
   Bearer → 401 means the nginx proxy in front of the bus validates **Basic
   auth (htpasswd identity)** and ignores the shared Bearer token. Do NOT sync
   or compare `CORTEX_BUS_TOKEN` across hosts — that is not what the proxy
   checks; don't burn a cycle on it.

2. **Check the auth key in `cortex-bus.conf`.** The Bearer→Basic cascade in
   `cortex_bus.py` fires only when `CORTEX_BASIC_AUTH` (or `CORTEX_BUS_AUTH`)
   is set. A host whose env lacks the key sends Bearer-only forever. Compare
   env KEY NAMES (not values) with the bus host:
   ```bash
   diff <(grep -o '^[A-Z_]*=' ~/hermes-cortex/.env | sort) \
        <(ssh -o BatchMode=yes <bus-host> 'grep -o "^[A-Z_]*=" ~/hermes-cortex/.env' | sort)
   ```
   Missing `CORTEX_BASIC_AUTH` on the sending host is the usual root cause.

3. **Copy the Basic creds from the bus host's `.env`** (never print them —
   pipe directly via ssh into a python one-liner that rewrites the local env;
   back up `.env` first). Verify with:
   ```bash
   AUTH=$(grep '^CORTEX_BASIC_AUTH=' ~/hermes-cortex/.env | cut -d= -f2- | tr -d '"')
   curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 -u "$AUTH" "$BUS_URL/api/pgmq/health"
   ```
   404 (not 401) = auth passed, path is wrong — proceed.

4. **A 400 that names an identity is SUCCESS at the auth layer.** After Basic
   passes, a POST may return:
   `from '<agent>' does not match authenticated agent '<user>'`
   The bus server validates the envelope `from` field against the htpasswd
   identity the proxy authenticated. Until a per-agent htpasswd entry exists on
   the bus host, the sending host cannot claim its own identity over the HTTP
   path. Never work around this by sending `from: <other agent>` — that is a
   forgeable identity and a governance violation.

5. **Read the 401's response BODY and EVERY retry attempt before concluding
   auth is broken — a reported "401" can be a masked validation error.** The
   outbox/retry loop surfaces only the LAST error. Hook the HTTP layer to log
   each attempt (URL, auth scheme, error body):
   ```python
   # sitecustomize-style hook
   import urllib.request, urllib.error, sys
   _orig = urllib.request.urlopen
   def logged(req, *a, **k):
       try:
           return _orig(req, *a, **k)
       except urllib.error.HTTPError as e:
           print("ERR", e.code, getattr(e, 'url', ''), e.read()[:150], file=sys.stderr)
           raise
   urllib.request.urlopen = logged
   ```
   Interpretation:
   - nginx HTML body (`<center>401 Authorization Required</center>`) = rejected
     at the proxy — Basic auth missing/wrong. Steps 2-3 apply.
   - app JSON body (`{"detail": ...}`) = auth PASSED; the bus rejected the
     payload. Fix what the detail names (subject format, `from` mismatch,
     `priority` type) — do NOT rotate credentials.
   - **A 400 on the Basic-retry attempt after a 401 proves auth was never
     broken.** Known sender poison: a sender hardcoding `priority: "normal"`
     (string) fails validation (bus requires int 0-100) on every send, and the
     reported "401" is just the final retry's error.

6. **After fixing a sender, clear the poisoned outbox.** Failed sends queue to
   `~/.hermes-cortex/bus-retry/*.json` and the retry-sweep cron re-fails them
   forever — clearing the outbox is part of the fix, not optional cleanup:
   ```bash
   rm -f ~/.hermes-cortex/bus-retry/*.json
   ```

## Working alternative (while HTTP identity is unresolved)

The `inbox_send` MCP client authenticates **server-side** with its own agent
identity and delivers immediately to any queue. A working MCP send + failing
`hc send` is the signature of the auth-layer problem above, not a bus outage —
dispatch via MCP, verify on the authoritative bus (double-parse pattern), and
fix the htpasswd separately.

## Verification on the authoritative bus

The sending host's local Postgres may be a stale reports mirror. Always verify
queue/archive state via ssh to the bus host. Avoid nested-quote SQL over ssh:
pipe the SQL through stdin instead:

```bash
ssh -o BatchMode=yes <bus-host> 'sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A"' <<'SQL'
SELECT queue_name, state, (body::jsonb #>> '{}')::jsonb->>'subject' AS subj
FROM bus.messages WHERE queue_name LIKE 'inbox_%' ORDER BY enqueued_at DESC LIMIT 15;
SQL
```
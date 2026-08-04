---
name: hermes-gateway-operations
version: 1.0.0
description: >-
  Diagnose, configure, and maintain Hermes messaging gateway platforms
  (Telegram, Discord, WhatsApp, etc.). Covers connectivity troubleshooting,
  secret/token setup, gateway state inspection, and common failure patterns.
---

# Hermes Gateway Operations

Diagnostic and maintenance procedures for the Hermes messaging gateway.

## When to load

- User reports "messages not sending" on any platform
- Gateway is disconnected or repeatedly reconnecting
- Need to set up a new platform (Telegram bot token, Discord token, etc.)
- Debugging `.env` configuration for gateway platforms

## Diagnostic Path (Telegram example)

Always follow this sequence — each step feeds the next:

```
1. gateway_state.json    → platform state ("disconnected" / "connected")
2. gateway.log           → error message ("No bot token configured")
3. .env                  → check TELEGRAM_BOT_TOKEN exists
4. config.yaml           → check platform_plugins and telegram
```

### Step 1 — Inspect gateway state

```bash
cat ~/.hermes/state/gateway_state.json 2>/dev/null
# {"platforms": {"telegram": {"status": "connected", "last_seen": "..."}}}
```

`"disconnected"` + a `last_seen` far in the past = the platform dropped and
isn't reconnecting. `"connected"` but messages not arriving = delivery-side
problem (see Step 5).

### Step 2 — Read the gateway log

```bash
tail -50 ~/.hermes/logs/gateway.log
```

Typical failure lines:
- `No bot token configured for platform telegram` → token missing
- `401 Unauthorized from Telegram API` → token wrong/revoked
- `Connection reset by peer` → transient network; check reconnect behavior

### Step 3 — Verify the token

```bash
# Does the var exist?
grep -c "TELEGRAM_BOT_TOKEN" ~/.hermes/.env

# Is it set in the environment?
printenv TELEGRAM_BOT_TOKEN >/dev/null && echo "set" || echo "UNSET"

# Is the token VALID? (never print it)
curl -s "https://api.telegram.org/bot$(cat ~/.hermes/.env | grep TELEGRAM_BOT_TOKEN | cut -d= -f2)/getMe" | head -c 200
```

> **Never print secrets.** Read tokens via `$(cat <file>)` or `grep | cut`
> inside the command — never pass them as literal strings.

### Step 4 — Check config.yaml

```bash
grep -A5 "telegram:" ~/.hermes/config.yaml
```

Confirm the platform is enabled in `platform_plugins` and no stale config
(e.g. old bot name, wrong chat ID).

### Step 5 — Delivery-side check (connected but nothing arrives)

If the gateway is connected but messages don't reach the user:
- Confirm the destination chat ID is correct
- Check `deliver` targets on the failing cron/job
- Verify the platform session didn't expire (re-auth if needed)

## Adding a New Platform

1. Obtain the token/secret for the platform (Telegram bot token from
   @BotFather, Discord bot token, etc.)
2. Add to `~/.hermes/.env` (never commit the file)
3. Enable in `config.yaml` → `platform_plugins`
4. Restart the gateway
5. Verify `gateway_state.json` shows `"connected"` and send a test message

## Common Failure Patterns

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| `No bot token configured` | Token missing from .env | Add token, restart gateway |
| `401 Unauthorized` | Token revoked or wrong | Generate new token, update .env |
| Repeated reconnecting | Network / API instability | Check outbound connectivity; verify with `curl` |
| Connected but no delivery | Wrong chat ID / deliver target | Verify destination chat ID and `deliver` config |
| Gateway up, platform down | Platform-side outage | Wait + monitor; check platform status page |

## Verification

```bash
# End-to-end test after any fix: send a test message to the home channel
# via a cron or direct invocation, then confirm it arrived.
```

## Related
- `hermes-agent` — general Hermes configuration
- `telegram-delivery-diagnostics` — Telegram-specific delivery debugging
- `cortex-bus-messaging` — inter-agent messaging (separate from the user gateway)

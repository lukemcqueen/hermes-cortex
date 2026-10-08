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

## Restarting to load new code — and verifying it actually happened

The gateway **holds the MCP servers it spawned**, so new governance/enforcer code
is not loaded until the gateway restarts. Two independent failure modes:

1. **Restarting from inside the gateway is blocked by design.** A restart issued
   from inside a Hermes session (a tool call) is refused — the gateway would
   SIGTERM the command before it completed. Restart from a **separate shell**.
2. **A restart can report success and still not land.** Verify; do not assume:

```bash
systemctl --user show hermes-gateway.service -p MainPID -p ExecMainStartTimestamp -p NRestarts
```

`MainPID` and `ExecMainStartTimestamp` **must change**. Observed failure: an
attempt that left both unchanged at the previous start time — the unit never
re-activated, so the MCP child still held pre-change code while everything
*looked* restarted.

Then confirm the child post-dates the deploy:

```bash
ps -o lstart= -p $(pgrep -f loop-governance/loop-gov-mcp.py)
date -r ~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py '+%e %H:%M:%S'
```

If the child's start time is older than the deployed file's mtime, the old code
is still live — regardless of what the restart command printed.

Note: a config value in `~/hermes-cortex/.env` does **not** need a restart once
the gate's own resolver is deployed (it re-reads per call); only the code does.

### A restart that preserves sessions is INVISIBLE — announce it, and tell the agent

The only message about a restart is sent by the process that then exits; nothing
follows it. So a human in the chat cannot tell the restart happened, and the agent
cannot tell them either: sessions survive a gateway restart (starting fresh is
`/new`), so an agent asked "did you restart?" answers from its own memory —
"no, I still have our context" — which is true of the SESSION, false about the
gateway, and the only answer available. Three things fix that, and the third is
the one usually missed:

1. **The restart command's reply states what happens to the CONVERSATION.**
   "restart" reads like "fresh start"; a session that carries over otherwise looks
   like nothing happened.
2. **The NEW process announces itself at startup, before it serves anything**, in the
   operator's wording, verbatim: `♻ Gateway restarted successfully. Your session
   continues.` Keep that phrasing — it answers both questions a restart raises (did it
   work, did I lose the conversation) in one line, and a longer invented variant is not
   what the operator wants here. Persist a per-chat marker BEFORE sending the restart
   reply — the process that writes the marker is the one that exits, so in-memory state
   cannot carry it. Consume the marker on the first turn, so the human is told once and
   not on every later reply. If the startup send fails, LEAVE the marker and let the
   first reply carry the confirmation: a transient send failure must not lose the news.
3. **Hand the AGENT the same fact on its first prompt after the restart** (a
   `[system]` note prepended to the turn). Announcing to the human alone leaves the
   agent still answering "no" — the contradiction the human will notice.

Prove a restart with the unit, not with the chat:

```bash
systemctl --user show <unit>.service -p NRestarts -p MainPID -p ExecMainStartTimestamp
```

A NEW `MainPID` plus start timestamp is the proof. `NRestarts` increments only for a
**policy** restart (`Restart=` firing) — an operator-issued `systemctl restart` does
not increment it, so a changing `NRestarts` is evidence the unit restarted ITSELF.

- **`Restart=always` is required for restart-on-clean-exit**, the pattern where a
  service asks systemd to bring it back by exiting on purpose: `Restart=on-failure`
  does NOT start the unit again after `exit(0)`, so the exit is a plain stop and the
  bot stays down. Check the policy before trusting the mechanism.
- **Probing this with a throwaway unit: end the probe with
  `systemctl --user stop <unit>` and exit 0.** Under `Restart=always`, a probe that
  exits non-zero restarts itself in a loop — it floods the journal and, if it also
  touches live state, does so repeatedly. Confirm the unit is gone afterwards
  (`systemctl --user list-units --all | grep <name>`).

## A non-Hermes backend is a SEPARATE runtime, not a Hermes session

A backend of `kind: command` (a CLI coding agent) is a distinct process with its
own tooling: it inherits **none** of a Hermes session's memory, skills, or
governance. "Agent X has no memory" is therefore a property of that backend's
OWN integration layer, never of the host — establish where its memory comes from
before touching anything shared:

| Backend | Memory comes from |
|---|---|
| Hermes session | the `mycortex-mem` memory-provider plugin, in-process |
| command/CLI agent | its own MCP server or extension, spawned by the agent CLI |

`hermes mcp list` does not list plugin-provided stores, so its absence proves
nothing about a Hermes session; a CLI agent's tools appear in ITS agent config
(its own `mcp.json`/settings), not in `config.yaml`.

### One service-hosted agent reports a store unreachable, a sibling works

Compare the two SERVING UNITS' sandbox flags before blaming the store —
hardening is invisible in the agent's own output, and the store's availability
check often swallows the real exception:

```bash
systemctl --user show <failing>.service -p NoNewPrivileges -p PrivateTmp
systemctl --user show <working>.service -p NoNewPrivileges -p PrivateTmp
```

`NoNewPrivileges=true` refuses `sg`/`newgrp` setgid **even when the process
already holds the target group**, which breaks any store whose only access path
is `sg docker -c "docker exec …"`. Reproduce faithfully with
`setpriv --no-new-privs -- <cmd>` — it keeps the real supplementary groups,
whereas `systemd-run` drops them and fails for the wrong reason. Fix by giving
the store a direct `docker exec` path when the group is already held; never by
dropping the hardening flag. Mechanism and store-specific fix: `psql-automation`.

### Slash commands are the GATEWAY's, never the agent's

When a `kind: command` backend (a CLI coding agent) serves a chat, the built-in slash
commands belong to the GATEWAY: such a backend handles `/new`, `/model`, `/compact`,
`/restart` only in its interactive/RPC surface, so forwarded as prompt prose they become
ordinary conversation — a `/new` is answered politely while every bit of context stays.
Intercept them in the gateway's command dispatcher and never pass them through
(backend mechanics: `pi-coding-agent`).

- **Each command needs a defined contract, not just a route.** `/new` starts a fresh
  session; `/model` persists the override per chat — a stateless prompt wrapper has
  nowhere to keep it, so the GATEWAY owns a small chat→model store, mode 0600 (a chat id
  is personal data); `/compact` reports what it reclaimed, and "nothing to compact" for a
  session too small; `/restart` exits so the unit restarts it, and the new process
  announces itself (above).
- **Design for the EMPTY chat.** Commands run on chats with no conversation yet, where a
  backend's session operations hang or refuse (compact on a transcript that does not exist
  never answers). Probe state first and answer with the specific condition — "this chat has
  no conversation yet" — never a generic failure.
- **A control timeout must cover a real turn plus the operation.** Compacting a large
  session measured ~1m46s; a 30s deadline reports a healthy backend as broken.
- **Test parity with a STUB transport and an echoing backend** (`/bin/echo` so the reply
  body IS the argv). A probe that polls with the real bot token starts a second poller and
  steals the live channel's messages (409); echoing is what lets the assertion check the
  ARGV the gateway produced — model declared exactly once, no duplicate `--model`.

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
- `psql-automation` — the `sg`/`NoNewPrivileges` store-access mechanism behind a
  "store unreachable" report from a hardened service

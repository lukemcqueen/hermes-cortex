# TitusClaude Hookup — Messaging Gateway recipe (ADR-0005)

**Status:** PREPARED (token minted, perms scoped, shim generated) —
Titus's host-side install pending
**Date:** 2026-08-24 · **Author:** Esther · **Live-verified:** gateway
outbound path (round-3 DM confirmed by Luke)

## What was done on the orchestrator side

1. **Agent created** — `cortex-agent-manager.py add titusclaude --role worker`
   (manager SQL-quoting + scoped-ARRAY-ACL bugs fixed in the process;
   the old `add` interpolated bare params and used stale boolean columns).
   - Token: minted, stored hashed, 90-day expiry (auto-rotate via
     `cortex-agent-manager.py rotate titusclaude`)
   - Perms (enumerable, no wildcard, no admin):
     - can_read  = `{inbox_titusclaude}`  (the gateway writes user msgs here)
     - can_write = `{out_titusclaude}`    (the gateway drains → Telegram)
2. **Shim generated** — `agent-shim.py --generate --agent titusclaude`
   → `/tmp/titusclaude-shim.py` (bakes `inbox_titusclaude`/`out_titusclaude`)
3. **Gateway routing row** — gateway.yaml: `routing.default: titusclaude`
   for Titus's bot (or `overrides: {<chat_id>: titusclaude}`)

## The queue contract (corrected 2026-08-24)

```
inbox_titusclaude  = messages FOR Titus   (gateway writes ← shim polls)
out_titusclaude    = messages FROM Titus  (shim writes ← gateway drains → DM)
```
The shim MUST poll/ack `inbox_`, and reply to `out_`. (Original shim had
this backwards — polled `out_`, which is the gateway's drain. Fixed.)

## Titus's host-side install (copy-paste)

```bash
# 1. Get the shim onto Titus's host (scp/rsync from Esther, or from repo)
# 2. Create his secrets file (600 perms — NEVER in git or shared env):
mkdir -p ~/.titusclaude
cat > ~/.titusclaude/env <<'EOF'
CORTEX_BUS_URL=http://<bus-host>:8903
CORTEX_BUS_TOKEN=<token from orchestrator>
AGENT_NAME=titusclaude
EOF
chmod 600 ~/.titusclaude/env

# 3. Poll loop (background — feeds Claude Code sessions):
while true; do
  set -a; . ~/.titusclaude/env; set +a
  MSG=$(python3 ~/titusclaude-shim.py --poll)
  if [ -n "$MSG" ]; then
    echo "$MSG" >> ~/.titusclaude/inbox.jsonl   # Claude reads this
    MID=$(echo "$MSG" | python3 -c "import sys,json; print(json.load(sys.stdin)['msg_id'])")
    # (Claude Code session processes the message, then:)
    python3 ~/titusclaude-shim.py --reply --body "done: processed $MID"
    python3 ~/titusclaude-shim.py --ack --msg-id "$MID"
  fi
  sleep 2
done
```

## Bot token (Titus's own — never reuse Esther's)

- Create via BotFather: `/newbot` → e.g. `titusclaude_bot`
- Token goes in Titus's `~/.titusclaude/env` as `TELEGRAM_BOT_TOKEN=...`
  — NOT the orchestrator's bot
- The GATEWAY owns the getUpdates polling for Titus's bot (single-poller);
  Titus's side only speaks to the bus via the shim

## Gateway.yaml addition (when Titus's bot is ready)

```yaml
bots:
  - token_ref: TELEGRAM_BOT_TOKEN_TITUS
    channel: telegram
    initial_offset: 0
    routing:
      default: titusclaude
```

## Verification

1. `cortex-agent-manager.py rotate titusclaude` — rotation works
   (compromise recovery: one agent's key, fleet untouched)
2. Gateway drains `out_titusclaude` (esther has `out_*` read for the
   live-test; the gateway principal `gw-<host>` gets `out_*` read in prod)
3. First end-to-end: DM Titus's bot → gateway → `inbox_titusclaude` →
   shim poll → Claude Code → shim reply → `out_titusclaude` → gateway →
   your DM (mirror of the live-verified esther path)

## Costs / notes

- One bot token per coding agent (per-agent isolation — Security 5/10
  design: a leaked Titus token only exposes Titus's bot, not the fleet)
- 90-day expiry: `token-expiry-alert.py` warns 7 days before
- The shim is ~100 lines, generated, no deps — fits Claude Code / Codex /
  OpenCode / Blackbox / Grok identically (only AGENT_NAME changes)

# Messaging Gateway + Envelope Contract (party-converged, 2026-08-24)

Context: the fleet needed app↔agent messaging (Telegram bots, WhatsApp,
N coding agents) on the bus. The per-agent `telegram-bridge.py` approach
hit Telegram's ONE-getUpdates-poller-per-bot limit (HTTP 409) and was
superseded by a unified gateway. A 4-role architecture party (Architect 7,
SRE 4, Security 5, Product 8) converged on this design. Full detail:
`docs/design/messaging-gateway.md` + `docs/adr/0005-messaging-gateway.md`.

## The shape

```
┌─────────────────────────────────────────────┐
│  MESSAGING GATEWAY (one daemon per server)  │
│  owns ALL app connections — single poller   │
│  telegram_adapter  whatsapp_adapter  ...    │
└──────────────┬──────────────────────────────┘
               │ routing table: chat_id → AGENT_NAME
   inbound:    │ outbound: out_<AGENT> → app
   inbox_<AGENT>│
               ▼
        ┌─────────────┐
        │  AGENT BUS  │  (PGMQ)
        └──────┬──────┘
   Hermes / coding agents — all bus-only
```

## Non-negotiables

1. **Gateway = deterministic service, NOT an agent** — no LLM, no memory,
   no inbox of its own. Bus identity (`gw-<host>`) for queue permissions
   only. Agents are the only thinking entities.
2. **Agents bus-only** — read `inbox_<AGENT>`, post to `out_<AGENT>` via
   a frozen versioned envelope; never touch app APIs.
3. **Per-bot exclusive ownership**: `pg_try_advisory_lock(bot_id)` held
   for the poller's lifetime — ONE mechanism for 409-avoidance, cutover
   exclusivity, multi-server active-passive. Failure to acquire = bot
   stays unowned/standby.
4. **Reliability invariants**: enqueue-then-ack (offset committed only
   after PGMQ send succeeds); archive-after-send is the commit point;
   never start from offset 0; dedupe by update_id; bus-outage = never
   ack what you couldn't enqueue (Telegram holds it).
5. **Inbound trust boundary**: app text is UNTRUSTED. Gateway HMAC-signs
   inbound; agents accept only gateway-signed messages as DATA
   (`kind:user_message`), never directives. No markdown/HTML passthrough,
   sender allowlist, length caps — prevents prompt injection via chat.
6. **Per-bot ACLs, not wildcard**: `gateway_<bot>` scoped to
   `inbox_<mapped_agent>` write + `out_<mapped_agent>` read, is_admin=false.
   Requires prefix-wildcard ACL support (bus checks exact-or-`*` today).
7. **Expansion**: new coding agent = generated ~100-line shim (poll
   out_<AGENT>, POST inbox_<AGENT>) + scoped token + routing row (< 30
   min). New app = ~200-line adapter (start/stop/parse/send).
   Config-as-code: gateway.yaml + reload without dropping polls.

## Envelope v1 (frozen before 2nd adapter)

```
{msg_id, ts, from_agent?, to_agent, channel, channel_user_id,
 thread_id, body, media[], reply_to_msg_id, ack_required}
```

Inbound (app→bus) is wrapped as `{source:'gateway', kind:'user_message',
text, sender_id}` — DATA, never directives. Outbound must carry
`{channel, channel_user_id, thread_id}` or the gateway guesses the wrong
app/chat (Telegram+WhatsApp coexisting).

## Migration from a Hermes-gateway-owned bot

Maintenance window: stop old adapter → final drain from old offset →
migrate delivery ledger + session state (keyed by app_chat_id) +
offset+1 → start gateway → verify first inbound/outbound. Rollback =
restart adapter, blocked by the same advisory lock. Dry-run on a test
bot first. Old adapter and gateway must NEVER poll the same bot
simultaneously.

## Why 409 is a design constraint, not a config issue

Telegram allows one long-poll getUpdates consumer per bot token. A second
poller (old adapter during cutover, second gateway, stray bridge) gets
409 and the bot goes silently dark. Single process ≠ single poller — the
exclusive per-bot advisory lock is what actually guarantees ownership.

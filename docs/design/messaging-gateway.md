# Design: Unified Messaging Gateway (multi-agent harness)

**Status:** DESIGNED — architecture party complete (4 roles, grounded)
**Date:** 2026-08-24 · **Author:** Esther · **Owner:** Luke (architecture call)
**Party scores:** Architect 7/10 · SRE 4/10 · Security 5/10 · Product 8/10

## Why

The per-agent `telegram-bridge.py` hit the fundamental limit: Telegram
allows **one getUpdates poller per bot** (409). The correct shape is ONE
gateway daemon owning ALL messaging transports, with agents bus-only. This
is the key to a true multi-agent harness: multi coding agents + multi
messaging apps on one fabric. (Luke, verbatim: "this is key to having a
true multi-agent harness".)

## Architecture (party-converged)

```
┌─────────────────────────────────────────────────────────┐
│  MESSAGING GATEWAY — one daemon per server              │
│  gateway-as-SERVICE (deterministic plumbing, NO brain)  │
│                                                         │
│  TransportAdapters (one interface):                     │
│    telegram_adapter  whatsapp_adapter  ...(next)        │
│    start/stop/parse/send/health                         │
│  Routing table (gateway.yaml):                          │
│    chat_id/number → AGENT_NAME (default fallback)       │
│  Per-bot advisory locks (pg_try_advisory_lock)          │
│  Enqueue-then-ack, archive-after-send, SentLedger dedup │
└──────────────┬──────────────────────────────────────────┘
               │ inbound: app → canonical envelope →
               │   POST /api/pgmq/send → inbox_<AGENT>
               │ outbound: out_<AGENT> → adapter.send
               ▼
        ┌─────────────┐
        │  AGENT BUS  │  (PGMQ — exists)
        └──────┬──────┘
   ┌───────────┼───────────┐
   ▼           ▼           ▼
 Hermes     coding      future
 agents     agents      agents
 (bus MCP)  (shim)     (same fabric)
```

## Party decisions (converged — these are the design)

1. **Gateway = service, NOT agent** (Product 8/10, decisive): deterministic
   plumbing (poll/translate/route/send) with zero judgment. A brain adds
   model-call failure modes to the critical path. It gets bus identity
   (`gw-<host>` principal) for queue permissions ONLY — no LLM, no memory,
   no inbox of its own. **Agents are the only thinking entities.**
2. **Envelope contract v1 (gateway-enforced, frozen before 2nd adapter):**
   `{msg_id, ts, from_agent?, to_agent, channel, channel_user_id, thread_id,
   body, media[], reply_to_msg_id, ack_required}`. Any producer/consumer
   speaking HTTP POST/GET on inbox_<AGENT>/out_<AGENT> works — Hermes,
   Codex, Claude Code, future — no gateway changes. Gateway validates at
   both boundaries, DLQs malformed.
3. **Inbound trust boundary** (Security 5/10): app text is UNTRUSTED.
   Gateway HMAC-signs inbound; agents accept only gateway-signed messages
   as DATA not directives: `{source:'gateway', kind:'user_message', text,
   sender_id}`. No markdown/HTML passthrough, no chat-text-to-command,
   per-agent sender allowlist, message length caps.
4. **Per-bot ACLs, not wildcard** (Security + Architect): one principal per
   bot `gateway_<bot>` with `can_write:[inbox_<mapped_agent>]`,
   `can_read:[out_<mapped_agent>]`, is_admin=false, no '*'. Requires adding
   inbox_*/out_* prefix matching to server.py (~3 lines) — verified gap.
   Audit + scope down existing '*' holders.
5. **Per-bot exclusive ownership** (SRE 4/10): `pg_try_advisory_lock(key=
   bot_id hash)` held for the poller's lifetime. Solves 409, migration
   exclusivity, AND multi-server active-passive in ONE mechanism. Failure
   to acquire = bot stays unowned/standby.
6. **Reliability invariants** (SRE): enqueue-then-ack (offset in Postgres
   only after PGMQ send succeeds); archive-after-send is the commit point;
   never first-run from offset 0; dedupe by update_id before enqueue;
   bus outage = never ack what you couldn't enqueue (Telegram holds it),
   optional SQLite WAL spool; per-bot SentLedger retained.
7. **Monitoring contract**: heartbeat table (≤5s, staleness alert);
   per-bot status rows (last poll, last error, 401/403/409 counters —
   401×N = dead token); queue depth AND oldest-message-age per queue
   (age not count); silent-when-clean alert cron.
8. **Coding-agent shim** (Product): coding agents can't speak PGMQ
   natively — ONE generated/standard ~100-line shim (poll out_<AGENT>,
   POST inbox_<AGENT>; agent name = queue name), mint per-agent scoped
   token, add routing-table row. Target: new coding agent < 30 min, no
   gateway restart beyond config reload.
9. **Adapter contract**: register in gateway.yaml as {channel, app_id,
   credential_ref, handler: parse→envelope, send(envelope)}. Routing
   lives in the gateway's table, never in the adapter. WhatsApp adapter
   ≈ 200 lines + credentials, zero agent-side changes.
10. **Config-as-code**: gateway.yaml declaring bots, adapters, routing,
    per-agent tokens; `gateway reload` applies without dropping polls —
    N-bots/N-agents = data change, not code change.
11. **Hermes gateway migration** (SRE cutover): maintenance window —
    stop old adapter → final drain from old offset → migrate delivery
    ledger + session state (keyed by app_chat_id) + offset+1 → start
    gateway → verify first inbound/outbound. Rollback = restart adapter,
    blocked by the same advisory lock. Dry-run on a test bot; shadow-run
    gateway on a new bot pre-cutover.

## MVP slice (Product's ordering)

1. 1 Telegram bot under gateway + 1 Hermes agent + 1 coding agent, both
   bus-only; envelope schema + validation; routing table with default
   fallback
2. Second Telegram bot
3. WhatsApp adapter
4. Group/thread routing
5. Media & attachments
6. Ack/read receipts
7. Multi-server gateway federation

## Security posture (Security's mitigations)

- Per-bot worker process isolation (each holds only its own token; parent
  holds only an encryption key); secrets encrypted at rest (systemd-creds
  /age, 0600), decrypted in memory, never plaintext .env
- Egress-restrict gateway host to messaging APIs + bus only; no persistent
  chat history
- Rotation: incident mode = revoke-first (deactivate → update configs →
  verify old→401 → look up identity by token_hash → sync peers → scrub →
  audit_log window); planned mode = configs-first. Bot tokens rotate
  per-bot — one bot's leak stays one bot
- Detection: alert unknown sender IDs, volume spikes, new principals;
  daily diff of bus.permissions (wildcard/admin creep)

## Facts grounded in (verified by party)

- Bus: PGMQ; per-agent tokens (90-day, rotate); per-queue perms with '*'
  (NO prefix wildcards — server.py verified); moses admin; API
  send/read/archive/requeue/depth; recover_timeouts() redelivers
  un-archived processing messages
- telegram-bridge.py: interim, hit 409, has SentLedger + durable offsets
  + --outbound-only (the seed of this design)
- Hermes Telegram adapter: deep polling (41 getUpdates refs), delivery
  ledger, session state — the migration risk

## Deliverables (next)

- [ ] ADR: messaging gateway (framework decision — public)
- [ ] gateway.yaml schema + envelope v1 spec
- [ ] server.py prefix-wildcard ACL change (~3 lines) + tests
- [ ] msg-gateway.py daemon (MVP slice)
- [ ] standard coding-agent shim generator
- [ ] Hermes adapter cutover plan + test-bot dry-run

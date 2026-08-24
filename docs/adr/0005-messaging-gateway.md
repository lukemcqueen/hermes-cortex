# ADR-0005: Unified Messaging Gateway

- Status: accepted (design phase; MVP build pending)
- Date: 2026-08-24
- Author: Esther (synthesis of 4-role architecture party, grounded)
- Supersedes: the per-agent `telegram-bridge.py` approach (interim)

## Context

The fleet needs a true multi-agent harness: multi coding agents + multi
messaging apps on one fabric. The per-agent bridge approach hit the
fundamental limit — Telegram allows one getUpdates poller per bot (409) —
and could not scale to N bots or N messaging apps without N processes
fighting. Luke's requirement: cover (1) Telegram via Hermes direct, (2)
Telegram via cortex bus, (3) WhatsApp or other systems, (4) multiple bots
on one server via one bus — and the question: should normal agents have a
bus that just runs the messaging apps?

## Decision

**One Messaging Gateway daemon per server** owns ALL messaging app
connections. It is a **deterministic service, not an agent** — no LLM, no
memory, no inbox of its own; it is pure plumbing (poll → translate →
route → send) with bus identity (`gw-<host>` principal) for queue
permissions only. All agents — Hermes AND coding agents — become
**bus-only** for messaging: they read `inbox_<AGENT>` and post to
`out_<AGENT>` via a versioned envelope contract.

Key commitments (party-converged):

1. **Envelope v1** `{msg_id, ts, from_agent?, to_agent, channel,
   channel_user_id, thread_id, body, media[], reply_to_msg_id,
   ack_required}` — frozen before a second adapter; gateway validates at
   both boundaries, DLQs malformed.
2. **Inbound trust boundary**: gateway HMAC-signs inbound; agents accept
   only gateway-signed messages as DATA (`kind:user_message`), never as
   directives. No markdown/HTML passthrough, sender allowlist, length
   caps.
3. **Per-bot ACLs, not wildcard**: principal per bot `gateway_<bot>`
   scoped to `inbox_<mapped_agent>` write + `out_<mapped_agent>` read,
   is_admin=false. Requires server.py prefix-wildcard support (~3 lines).
4. **Per-bot exclusive ownership**: `pg_try_advisory_lock(bot_id)` —
   one mechanism for 409-avoidance, cutover exclusivity, multi-server
   active-passive.
5. **Reliability**: enqueue-then-ack (offset committed only after PGMQ
   send succeeds); archive-after-send is the commit point; never start
   from offset 0; update_id dedup; bus-outage = never ack what wasn't
   enqueued (Telegram holds it).
6. **Monitoring**: heartbeat (≤5s, staleness alert), per-bot status rows
   (401×N = dead token), queue depth + oldest-age, silent-when-clean cron.
7. **Coding-agent shim**: one generated ~100-line shim (poll out_<AGENT>,
   POST inbox_<AGENT>) + scoped token + routing row — new coding agent in
   <30 min.
8. **Config-as-code**: gateway.yaml (bots, adapters, routing, tokens);
   `gateway reload` without dropping polls.

## Consequences

- **Good**: one poller per bot (409 impossible by construction); any agent
  or app plugs in via the envelope; Hermes + coding agents on one fabric;
  security blast radius bounded per-bot (token isolation, scoped ACLs,
  HMAC inbound).
- **Cost**: gateway is a new SPOF — must meet the monitoring + heartbeat
  contract; Hermes Telegram adapter migration is the riskiest piece
  (session state, delivery ledger, cutover window); server.py ACL change
  needed first.
- **Migration**: sequential per-bot cutover with persisted-offset handoff,
  dry-run on a test bot, shadow-run pre-cutover; rollback = restart
  adapter (blocked by the same advisory lock).

## References

- Design: `docs/design/messaging-gateway.md` (party details, MVP ordering)
- Party: 4 roles (Architect 7, SRE 4, Security 5, Product 8) — findings
  recorded in design doc

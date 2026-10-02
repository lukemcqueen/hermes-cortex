# The gateway reply path — how it works, why it was broken, and what is left

**Status:** the transport-level reply leg is PROVEN working (a signed envelope written to
`out_<agent>` is drained by the gateway and delivered to Telegram, with a Telegram
`message_id` as the receipt). The **agent-side producer is not yet wired**, so a real turn
still has no answer written. That is the remaining piece — spec below.

## The path (ADR-0005, unchanged)

```
human → Telegram → gateway.transport.parse → envelope
      → HermesBackend.dispatch → bus: inbox_<agent>        (the message's `body` payload)
      → agent handles it
      → agent writes a reply envelope → bus: out_<agent>
      → gateway.poll_replies → transport.send → Telegram → human
```

Nothing in the gateway needs changing to support this: `poll_replies()` was always written
for it. Four separate faults prevented it from ever working, and **all four were silent** —
no error surfaced anywhere, which is why every unit test passed while no message moved.

## The four faults (all fixed; see tests/test_gateway_bus_shapes.py)

1. **Write schema.** The gateway sent the ADR-0005 envelope *as* the bus message. The bus
   has its own schema and rejects it:
   `400 unknown envelope field(s): ack_required, channel, channel_user_id, from_agent,
   media, msg_id, reply_to_msg_id, thread_id, to_agent, ts`.
   **Every dispatch was a 400** — no human message ever reached an agent. Now the signed
   envelope travels inside the message's `body`, with `from` = the authenticated agent and
   an UPPER_CASE subject. (`from` must match the token's agent: the bus refuses
   `from 'gateway' does not match authenticated agent '…'`.)

2. **Read shape.** `bus_read()` returns the WHOLE bus message under the key `body` —
   `{"subject": …, "body": {<envelope>}, "from": …, "to": …}` — so validating `msg["body"]`
   failed and `poll_replies()` **archived the reply as malformed**. `_extract_envelope()`
   now unwraps a bus-schema message and still accepts a bare envelope.

3. **Provisioning.** No agent had ANY `out_*` grant, so no `out_*` queue existed anywhere
   and writing one was a 403 (`does not have write access to queue 'out_<agent>'`). The
   convention was designed (ADR-0005 §4) but never provisioned. Fixed on the bus host:
   the queue was created and the agent granted read+write on it. The bus server also
   honours prefix patterns (`out_*`, `inbox_*`) per ADR-0005 §4, conservatively: only
   patterns an admin explicitly granted, and a bare `*` keeps its single meaning.

4. **Endpoint asymmetry.** The library has a primary URL and a fallback URL, and it fails
   over **silently**. A stale Bearer token was 401ing at the reverse proxy on the primary,
   so writes landed on the *fallback* bus while the gateway read the *primary* — a written
   reply and a reading gateway could never meet. The dead token has been removed from the
   env so Basic (the credential the proxy accepts) is used and both sides use the primary.
   Remaining recommendation: make the failover LOUD (log which endpoint served a write) —
   a silent failover between two bus instances is a data-loss shape.

## What is left: the agent-side producer

Something must write the reply envelope to `out_<agent>`. Two supported routes:

- **`ops/scripts/agent-shim.py` (ADR-0005 §8)** — the designed shim: poll `inbox_<agent>`,
  hand the message to the agent, `reply()` → `out_<agent>`, `ack()` after handling. It
  already implements the queue contract for external coding agents; for the Hermes agent it
  needs the "hand the message to the agent" step wired.
- **A `reply` tool on the agent-bus MCP** (`mcp-servers/cortex-bus-mcp.py`) — the agent
  itself answers deliberately: `inbox_reply(text, origin_msg_id)` reads the origin message
  (which carries `channel`, `channel_user_id`, `thread_id`, `reply_to_msg_id`), builds the
  reply envelope from that routing, and sends it to `out_<agent>`. This is the smaller,
  more honest integration for an LLM agent that already has the inbox tools, and it keeps
  the routing decision in the gateway's envelope rather than in the agent's prompt.

Either way the reply envelope's routing fields must come from the ORIGIN envelope — the
gateway is the only component that knows where a message came from.

## Verification standard for this path

Unit tests cannot catch these faults: every one of them was a *wire* mismatch that the
fakes happily accept. The path is verified by:

1. a Telegram `message_id` receipt for a message written to `out_<agent>` (done), and
2. a live turn on a **second bot token** — never the live bot — because one poller per bot
   is a hard invariant (a second `getUpdates` consumer drops the live channel).

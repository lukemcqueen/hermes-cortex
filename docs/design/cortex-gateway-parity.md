# cortex-gateway ↔ hermes-gateway: functional parity matrix

**Question (Luke, 2026-10-02):** can Telegram move from `hermes-gateway` to
`cortex-gateway` without losing functionality?

**Directive (Luke, 2026-10-02): "build feature parity, and once we are confident, then
cut over."** So this file is a *progress bar*, not a judgement: parity is built in
slices, each slice is executed by the committed test, and the cutover happens only when
the gap register below is empty.

**Verdict: TRANSPORT SLICE AT PARITY (slice 1, shipped) — DAEMON SLICE STILL OPEN.**
The design doc's original CR1 parity claim was against **`ops/scripts/msg-gateway.py`**
(HC's own precursor), never against Hermes's platform adapter:

| | incumbent | target |
|---|---|---|
| code | `hermes-agent/plugins/platforms/telegram/adapter.py` (~1400 lines) | `ops/scripts/cortex_gateway/transport.py` + `daemon.py` (~700 lines after slice 1) |
| shape | full platform adapter inside the agent process | transport + dispatch seam, agent out-of-process |

## Matrix

Evidence: `T` = asserted by the committed test (executed), `C` = code path cited.

### Closed by slice 1 (transport, shipped)

| Capability | incumbent | target | Evidence |
|---|---|---|---|
| Media inbound (photo/document/voice/video) | ✅ | ✅ `media[]` with `kind`/`file_id`/`size`, caption preserved | T |
| Caption-only message | ✅ | ✅ `text or caption` (was: dropped entirely) | T |
| Reply/quote inbound | ✅ | ✅ `reply_to_msg_id` from `reply_to_message` | T |
| Edited messages | ✅ | ✅ re-dispatched, `tg_kind="edited"` | T |
| Reactions | ✅ | ✅ forwarded as `[reaction: …]`, `tg_kind="reaction"` | T |
| Inline callbacks (data) | ✅ | ✅ forwarded as `[callback: …]`, `tg_kind="callback"` | T |
| Long message outbound | ✅ splits | ✅ `chunk_body()` — provably loss-free (`''.join(chunks) == body`) | T |
| Media outbound | ✅ | ✅ `sendPhoto`/`sendDocument` from `envelope.media` | T |
| Formatting | ✅ rich | ✅ `parse_mode` (envelope → `TELEGRAM_PARSE_MODE`), invalid mode ignored, rejected formatting retried as plain text | T |
| Retry/backoff + 429 | ✅ | ✅ `_api` retries transient failures (4 attempts, exponential, honours `retry_after`) | T, C |
| Polling conflict | ✅ stall/reconnect | ⚠️ classified as `PollingConflict` | T — **handling belongs to the daemon slice** |
| API base missing | env-required | ✅ **fails closed** (was: empty base → invalid URL on every call) | T |

### Open — daemon slice (the gap register)

These are asserted as *today's* behavior in the test, so implementing any of them FAILS
the test and forces this matrix to be updated:

| Capability | incumbent | target | Why it matters |
|---|---|---|---|
| **Slash commands (`/stop`, `/status`, `/model`)** | ✅ gateway-level dispatch | ❌ text becomes the prompt body | **material** — no in-band way to interrupt a runaway turn from Telegram |
| **Busy/interrupt while a turn runs** | ✅ two-level guard | ❌ single dispatch, no queue, no interrupt | material for long jobs |
| **Inline keyboards (button approvals)** | ✅ | ❌ callbacks forwarded, but nothing renders buttons | the approval flow is unreachable from Telegram |
| Typing indicator / drafts / streaming edits | ✅ | ❌ | cosmetic, but it is UX parity |
| Forum/DM topic anchors + topic bindings | ✅ thread kwargs, reply anchors, prune | ⚠️ raw `message_thread_id` passes through | DM topics behave differently |
| DM pairing flow | ✅ pairing code | ❌ unknown senders refused (fail-closed) | behaviour difference, not a security loss |
| Multi-platform (Discord/Slack/… 20+) | ✅ | ❌ Telegram only | accepted by design (anti-bloat) |
| Polling stall detection / reconnect loop | ✅ | ⚠️ error classified, daemon must act | **material** |

### Where the target wins (unchanged)

Agent **out-of-process** (survives a gateway restart, unlike the in-process loop);
**swappable agent backend** (pi = CR5, orthogonal — it changes *who answers*, not what the
transport can carry); **HMAC-signed envelopes** with a fail-closed secret.

## Cutover gate

Confidence is defined, not felt. Cut over when **all four** hold:

1. The gap register is empty — no `DAEMON SLICE` entries left in the parity test.
2. One live end-to-end turn through the cortex gateway on a **second** bot token (never
   the live bot: one poller per bot, or `getUpdates` conflicts and the live channel drops).
3. The three material risks are covered by a test each (interrupt, polling recovery,
   chunking ✓ already covered).
4. Rollback is a single documented step (restore the hermes-gateway unit).

## Evidence

- Capability test (executed): `tests/test_cortex_gateway_parity_matrix.py` — golden updates
  → the target's real `parse()`/`send()`, gap register printed each run.
- Fixtures: `tests/fixtures/telegram-golden-updates.json` (synthetic ids/dates — real chat
  ids are personal identifiers and 10-digit unix timestamps read as phone numbers).
- Gateway suites (executed): **111 passed** (106 pre-existing + 5 new).
- Incumbent: `hermes-agent/plugins/platforms/telegram/adapter.py`.
- Target: `hermes-cortex/ops/scripts/cortex_gateway/{transport,daemon}.py`;
  design `docs/design/cortex-gateway.md` (CR1–CR4 ✅, CR5 pi pending).

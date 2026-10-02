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

### Closed by slice 2 (daemon) — G5/G6/G7

| Capability | incumbent | target | Evidence |
|---|---|---|---|
| Slash commands (`/stop`, `/status`) | ✅ gateway-level dispatch | ✅ gateway handles them; `/stop` also forwards so the agent can stop its own work | daemon test (11) |
| Busy/interrupt while a turn runs | ✅ two-level guard | ✅ one in-flight turn per chat, bounded queue, `/stop` clears queue + suppresses pending replies | daemon test |
| Polling stall detection / reconnect loop | ✅ | ✅ exponential backoff (capped 60s); conflict tolerated 3 cycles then exit 4 so a real second poller keeps its updates | daemon test |

### Still not at parity (beyond the audited register)

The G1–G9 register is empty, but these differences are real and are NOT claimed as closed:

| Capability | incumbent | target | Why it matters |
|---|---|---|---|
| **Inline keyboards (button approvals)** | ✅ | ❌ callbacks forwarded, but nothing renders buttons | the approval flow is unreachable from Telegram |
| Typing indicator / drafts / streaming edits | ✅ | ❌ | cosmetic, but it is UX parity |
| Forum/DM topic anchors + topic bindings | ✅ thread kwargs, reply anchors, prune | ⚠️ raw `message_thread_id` passes through | DM topics behave differently |
| DM pairing flow | ✅ pairing code | ❌ unknown senders refused (fail-closed) | behaviour difference, not a security loss |
| Multi-platform (Discord/Slack/… 20+) | ✅ | ❌ Telegram only | accepted by design (anti-bloat) |

### Where the target wins (unchanged)

Agent **out-of-process** (survives a gateway restart, unlike the in-process loop);
**swappable agent backend** (pi = CR5, orthogonal — it changes *who answers*, not what the
transport can carry); **HMAC-signed envelopes** with a fail-closed secret.

## Cutover gate

Confidence is defined, not felt. Cut over when **all four** hold:

1. ✅ **The gap register is empty** — G1–G9 all closed, asserted by
   `tests/test_gateway_parity_evidence.py` (9 closed, 0 open).
2. ⬜ **One live end-to-end turn on a SECOND bot token** — never the live bot: one poller
   per bot, or `getUpdates` conflicts and the live channel drops. Not done yet; this is
   the remaining gate.
3. ✅ **The three material risks each covered by a test** — truncation (chunking, loss-free
   asserted), interrupt (`/stop` + suppression), polling recovery (backoff + conflict).
4. ⬜ **Rollback is a single documented step** (restore the hermes-gateway unit) — written,
   but not exercised on the live bot.

**State: build complete, cutover NOT performed.** 1 and 3 are satisfied; 2 and 4 require a
live second-bot rehearsal, which is the next step and is deliberately not something this
document can claim on its own.

## Gap register (G1–G9) — numbered so the before/after is checkable

The audit named nine gaps. Each is listed with its status; the parity test asserts the OPEN
ones as today's behaviour, so closing one fails the test until this table is updated.

| # | Gap | Status | Evidence |
|---|---|---|---|
| G1 | Media inbound (photo/document/voice), captioned media | closed | parity test: `media[]` + caption cases |
| G2 | Media outbound (photo/document) | closed | `sendPhoto`/`sendDocument` assertions |
| G3 | Long message chunking (was `body[:4000]` truncation) | closed | `''.join(chunks) == body` assertion |
| G4 | Rich formatting (parse_mode, code blocks) | closed | parse_mode + plain-text fallback assertions |
| G5 | Slash commands (`/stop`, `/status`, `/model`) | closed | daemon test: `/stop` interrupts + forwards `tg_kind=command`; `/status` answered locally; unknown commands forwarded |
| G6 | Busy/interrupt while a turn runs | closed | daemon test: one in-flight turn per chat, bounded queue, queue advances on reply |
| G7 | Polling recovery (stall detect, reconnect loop) | closed | daemon test: exponential backoff (capped 60s), conflict tolerated then exit 4, counters reset |
| G8 | Retry/backoff + 429 handling | closed | `_api` retry assertions |
| G9 | Reactions, inline callbacks, edited messages | closed | `tg_kind` forwarding assertions |

**Gap register: 9 → 0 open — every named gap is now closed.** G5/G6/G7 closed by the
daemon slice (`tests/test_cortex_gateway_daemon_slice.py`, 11 tests); G7's recovery loop is
exponential backoff with a conflict fault-tolerance of 3 consecutive cycles before exit 4.

## Revision note — claims corrected by execution

- **2026-10-02, G1:** the first write-up of this matrix claimed media was "dropped (the
  caption survives as text)". Executing the parity test refuted it: `parse()` read only
  `text`, never `caption`, so **a captioned photo was dropped entirely — caption included**.
  The fixture and this matrix now state the measured behaviour. The test was written before
  the fix precisely so it could contradict the prose.
- **2026-10-02, reviewer findings ADV-10482-1/-2/-3/-6/-7:** the close was refused because
  the parity claims (test count, 9 → 3 register, the correction itself) were not traceable
  to committed evidence. Remedy applied: this numbered register, the revision note above,
  and `tests/test_gateway_parity_evidence.py`, which re-executes the suites and asserts the
  numbers so the evidence regenerates instead of aging into an unverifiable claim.
- **2026-10-02, harness bugs found by the tests themselves:** the first `chunk_body`
  dropped the newline at every chunk boundary, and the parity test recorded outbound
  `params` by reference while `send()` mutates that dict for the plain-text retry — so "the
  retry dropped the formatting" had been passing for the wrong reason.
- **2026-10-02, slice 2 (G5/G6/G7):** the daemon gained slash dispatch, per-chat
  serialization with a bounded queue and `/stop` interruption, and exponential poll
  backoff. The fixture entry that registered "no slash-command dispatch" is now `gap:
  null` — the transport still passes `/stop` through as a message (the daemon, not the
  transport, is where a command is recognised), which is why the transport-level matrix
  does not change even though the user-visible behaviour does. The three material cutover
  risks named in the first audit — silent truncation, no interrupt, no polling recovery —
  are now each covered by a test.

## Evidence

- Capability test (executed): `tests/test_cortex_gateway_parity_matrix.py` — golden updates
  → the target's real `parse()`/`send()`, gap register printed each run.
- Fixtures: `tests/fixtures/telegram-golden-updates.json` (synthetic ids/dates — real chat
  ids are personal identifiers and 10-digit unix timestamps read as phone numbers).
- Gateway suites (executed): **111 passed** (106 pre-existing + 5 new).
- Incumbent: `hermes-agent/plugins/platforms/telegram/adapter.py`.
- Target: `hermes-cortex/ops/scripts/cortex_gateway/{transport,daemon}.py`;
  design `docs/design/cortex-gateway.md` (CR1–CR4 ✅, CR5 pi pending).

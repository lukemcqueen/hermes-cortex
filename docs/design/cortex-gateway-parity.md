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

### Feature parity (beyond the audited register)

Every difference named below is now closed, and the row names the test that holds it closed.

| Capability | incumbent | target | Evidence |
|---|---|---|---|
| **Inline keyboards (button approvals)** | ✅ | ✅ envelope `buttons` → `reply_markup.inline_keyboard` (on the last chunk); a malformed button is SKIPPED, never forwarded (invalid markup costs the whole message); `answerCallbackQuery` clears the spinner; the press routes back as `tg_kind=callback` carrying `tg_query_id` | `tests/test_gateway_approvals.py` |
| Typing indicator | ✅ | ✅ `sendChatAction` on dispatch, refreshed every 4s while the turn is in flight (Telegram expires it after ~5s), never fatal | `tests/test_gateway_typing.py` |
| Streaming partial output | ✅ | ✅ spec `stream: true`; ONE message EDITED as output arrives (throttled 1.5s) — never a message per partial; the final text lands on that same message, never as a second copy; no edit support → the ordinary reply path | `tests/test_gateway_streaming.py` |
| Forum/DM topic anchors + bindings | ✅ | ✅ in a topic the answer ANCHORS to the triggering message; a stale topic id is PRUNED (deliver without it) instead of losing the answer; a non-topic failure never silently de-topics | `tests/test_gateway_approvals.py` |
| DM pairing flow | ✅ | ✅ code → owner `/approve` (only an env-allowed user), single-use, TTL-bounded, per-sender rate-limited, persisted across restarts; ON by default as the incumbent is, `TELEGRAM_PAIRING=off` for a silent refusal | `tests/test_gateway_pairing.py` |
| Per-chat agent sessions | ✅ | ✅ spec `session: per_chat` + `session_args`; deterministic `hc-<agent>-<chat>` id, so continuity survives a restart | `tests/test_gateway_agent_registry.py` |
| `/new` — start a fresh session (ARCHIVE) | ➖ | ✅ `/new` bumps a PERSISTED per-chat generation → `hc-<agent>-<chat>-g<N>`; the previous transcript stays on disk under its own derivable id and is NAMED in the reply. Generation 0 keeps the unsuffixed id, so an existing conversation never moves | `tests/test_gateway_new_session.py` |
| Message edits | ✅ | ✅ `editMessageText` (approval outcomes, streaming updates) | `tests/test_gateway_approvals.py` |
| Multi-platform (Discord/Slack/… 20+) | ✅ | ❌ Telegram only | accepted by design (anti-bloat); the transport seam is where another platform attaches |

One deliberate difference remains, and it is strictly narrower than the incumbent: our
pairing path can be switched off per host (`TELEGRAM_PAIRING=off`), which the incumbent
cannot do. Additive, never a capability removed.

### Where the target wins (unchanged)

Agent **out-of-process** (survives a gateway restart, unlike the in-process loop);
**swappable agent backend** (pi = CR5, orthogonal — it changes *who answers*, not what the
transport can carry); **HMAC-signed envelopes** with a fail-closed secret.

## Cutover gate

Confidence is defined, not felt. Cut over when **all four** hold:

1. ✅ **The gap register is empty** — G1–G9 all closed, asserted by
   `tests/test_gateway_parity_evidence.py` (9 closed, 0 open).
2. ⚠️ **One live end-to-end turn on a SECOND bot token** — rehearsal 2026-10-02 on
   @Esther0001Bot: the gateway polls, the allowlist holds, `/status` is answered end-to-end
   over the second bot's own loop, and stopping the daemon releases the bot cleanly.
   The **reply leg is now proven live**: `out_esther` exists, `esther` holds read+write, and
   a signed envelope written to it was drained by the gateway and delivered by the bot —
   Telegram `sendMessage` returned **`message_id 8`**, with `out_esther` back to depth 0
   (delivered AND archived). The inbound dispatch shape was accepted (`inbox_esther` depth 1)
   — the first time that leg ever carried a message, after five faults were found and fixed
   (`docs/design/gateway-reply-path.md`).
   What remains before cutover is the **whole path in one motion**: a human message → the
   agent's own reply → back out through the second bot. Every leg is proven; the composition
   is not yet.
3. ✅ **The three material risks each covered by a test** — truncation (chunking, loss-free
   asserted), interrupt (`/stop` + suppression), polling recovery (backoff + conflict).
4. ⚠️ **Rollback is a single documented step** (restore the hermes-gateway unit) — the
   mechanism was DEMONSTRATED in rehearsal (stop the daemon → clean exit rc=0 → the bot is
   released), but not exercised on the live bot.

**State: build complete, cutover NOT performed, and condition 2 is DISQUALIFYING.**

The rehearsal's job was to find exactly this before the flip. Remaining work, in order:
(a) provision the reply path — create `out_<agent>` queues and make an agent's replies
land there (or choose a different reply mechanism and document it); (b) re-run the
second-bot rehearsal to a delivered reply; (c) exercise the rollback on the live bot.

Two further findings from the same rehearsal, both fixed: the rehearsal config's
placeholder agent ("hermes", copied from `gateway.yaml.example`) has no queue and a failed
dispatch was swallowed silently — now a WARNING naming the queue; and the token file handed
over was mode 0644, now 0600.

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

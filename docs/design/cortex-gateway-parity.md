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
| `/model <name>` — switch the model for THIS chat | ✅ (session-scoped) | ✅ gateway-level: a PERSISTED per-chat override (`models.py`) published on the envelope as `model_override` and substituted into the backend's `model_args` (`--model {model}`), so the NEXT turn really runs the new model. No argument reports the chat's model and the default; `/model reset` returns to the default. Optional validation: a spec may declare `check_model`, and a name the agent rejects is refused instead of stored | `tests/test_gateway_slash_parity.py` |
| `/compact` — compact this chat's context | ✅ (in-process agent) | ✅ gateway-level through the backend's DECLARED control command (`commands.compact`): pi's `/compact` lives in pi's RPC mode, so `pi_control.py` drives it and prints one line the gateway relays (measured: 69,980 → 20,267 tokens on a 71-message session, ~1m46s). rc=2 (not declared) and rc=3 (could not run) are reported distinctly, never as success | `tests/test_gateway_slash_parity.py` |
| `/restart` — reload the gateway | ✅ | ✅ gateway-level: reply, then exit; the unit is `Restart=always`, so systemd brings it back (no privileges needed under `NoNewPrivileges=true`). REFUSED with a message when the daemon is not systemd-supervised — unsupervised, exiting is a kill. **Observable afterwards** (2026-10-08): the new process announces itself at startup — "♻ Gateway restarted successfully. Your session continues." — and the AGENT is told the same fact on its first prompt, because the session deliberately survives and an agent asked "did you restart?" otherwise answers "no" | `tests/test_gateway_slash_parity.py` |
| Message edits | ✅ | ✅ `editMessageText` (approval outcomes, streaming updates) | `tests/test_gateway_approvals.py` |
| Multi-platform (Discord/Slack/… 20+) | ✅ | ❌ Telegram only | accepted by design (anti-bloat); the transport seam is where another platform attaches |

One deliberate difference remains, and it is strictly narrower than the incumbent: our
pairing path can be switched off per host (`TELEGRAM_PAIRING=off`), which the incumbent
cannot do. Additive, never a capability removed.

### Where the target wins (unchanged)

Agent **out-of-process** (survives a gateway restart, unlike the in-process loop);
**swappable agent backend** (pi = CR5, orthogonal — it changes *who answers*, not what the
transport can carry); **HMAC-signed envelopes** with a fail-closed secret.

### CR5 — the pi backend, measured live on the second bot (2026-10-07)

pi plugs into the backend seam as `kind: command` with **no gateway code change** (config
only: `ops/scripts/gateway-pi.example.yaml`). Running it on @Esther0001Bot exposed four
ways a *synchronous* backend loses replies, three of them silent. All four are fixed and
each is held closed by a named test.

| # | Defect | Why it was invisible | Fix | Held by |
|---|---|---|---|---|
| P1 | `output: last_line` truncated every multi-line answer to its final line | the reply arrived, so nothing looked broken — only part of it did | `output: raw` — pi's stdout is EXACTLY the assistant answer, verified with a plain turn AND a turn that used pi's bash tool; the extension's `CORTEX_RESUME` line and tool chatter go to its log/stderr, never stdout | `ops/scripts/gateway-pi.example.yaml`, `test_output_shape_is_declared_not_guessed` |
| P2 | **A silent turn wedged the chat permanently.** One turn with no reply left the chat "in flight" forever, so every later message queued behind a turn that could never complete and the agent went silent for good | the daemon read a `None` reply as "async, still waiting" — true for hermes (bus), false for a CLI agent, and nothing let it tell them apart | the backend DECLARES it: `async_replies` on each shipped backend (hermes True, command False — declared ON the class, since `CommandBackend` satisfies the seam structurally rather than by subclassing). A sync `None` finishes the turn and frees the chat | `test_daemon_a_silent_sync_turn_does_not_wedge_the_chat`, `…an_async_silent_turn_keeps_the_chat_busy…`, `…a_queued_sync_turn_that_answers_nothing_still_frees_the_chat`, `test_every_shipped_backend_DECLARES_its_reply_mode` |
| P3 | A turn that could not RUN was **silent** — a pi timeout produced no message at all, indistinguishable from a dead gateway | the failure existed only as a `log.warning` | the turn returns a reply naming the reason (`timed out after 300s` / `could not run …` / `exited N with no output`) through the ordinary reply path; a clean turn with no output stays silent | `test_a_failed_turn_reaches_the_human_instead_of_going_quiet` |
| P4 | A long pi turn showed **no typing prompt at all** | `_refresh_typing()` runs once per poll cycle, and a sync backend blocks the cycle for the whole turn (minutes) while Telegram expires the action in ~5s — the async hermes backend returns immediately and kept it | `_TypingKeeper` thread refreshes the indicator for in-flight turns independently of the loop; every call stays best-effort | `test_the_typing_keeper_refreshes_while_the_loop_is_blocked_in_a_turn` |

Two further defects the same pass found and fixed, both pre-existing and both in the
synchronous path:

- **`_run_streaming` ignored `timeout_s` while reading.** It read with `for line in
  stream` and applied the timeout only to the closing `wait()`, so a streaming agent that
  held its pipe open (a hung turn) was never bounded — the gateway blocked on it
  indefinitely. The read is now bounded by a `select()` deadline, and a partial answer is
  delivered WITH the failure note so it cannot pass for a complete one
  (`test_a_partial_answer_from_a_failed_turn_is_marked_not_silently_truncated`).
- **`timeout_s: 0` did not fail closed.** `int(raw or default)` turned an explicit `0`
  into `300`, so `validate()`'s "must be positive" never fired — a fail-open in the field
  that decides when a turn is reported as timed out
  (`test_a_non_positive_timeout_is_refused_not_silently_defaulted`).

Still a genuine asymmetry with the incumbent, named rather than hidden: a synchronous
backend **blocks the poll loop** for the length of its turn, so other chats are polled only
between turns (the hermes backend returns immediately). The typing keeper and the per-chat
queue soften it; making sync turns concurrent is the next slice, not a claim about this one.

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

- **2026-10-07, CR5 (pi):** running the pi backend on the second bot produced the four
  defects in the CR5 table above — a truncated reply (`output: last_line`), a chat wedged
  forever by one silent turn, a failed turn that was silent, and no typing prompt during a
  long turn — plus two pre-existing faults in the synchronous path (an unbounded streaming
  read, and `timeout_s: 0` silently defaulting). Fixed with tests named in the table; the
  blocking-turn asymmetry is recorded as still open.

- **2026-10-08, CR5 addendum — slash-command parity for a CLI agent.** The four commands a
  human actually reaches for on a coding-agent bot were verified against the pi backend, and
  NONE could work as forwarded text: pi handles its built-in slash commands **only in the
  interactive/RPC surfaces** (pi's own `docs/rpc-commands.md`: "Built-in TUI commands … would
  not execute if sent via prompt"), so `/model x`, `/compact` and `/restart` arrived as four
  characters of conversation. `/new` already had a gateway handler; `/model`, `/compact` and
  `/restart` did not. The gap was measured against the DEPLOYED package before the change —
  no `models` module, no `_handle_model`/`_handle_compact`/`_handle_restart` on `Gateway`,
  and `model_args` rejected as an unknown spec key — and each is now held closed by
  `tests/test_gateway_slash_parity.py` (32 tests), which drives the REAL gateway and the REAL
  `CommandBackend` (the agent's command is `/bin/echo`, so the reply body IS the argv built).

  Two design consequences worth naming:

  - **The model is declared exactly once.** `/model` can only override a model the argv does
    not hardcode, so the model moved out of `command` into `model_args` — and a spec that has
    both is refused at STARTUP, because two `--model` flags make the switch a silent no-op
    (the failure mode this field removes). `tests/test_cortex_gateway_daemon_slice.py`'s
    "unknown command is forwarded" case used `/model gpt-5` as its example; it now uses a
    genuinely unknown command, because `/model` is handled.
  - **A control command is declared, not coded.** `/compact` needs pi's RPC mode, so the
    spec names an argv template (`commands.compact` → `pi_control.py`) and the gateway runs
    it and relays stdout. No pi flag name appears in gateway code, and a backend that
    declares nothing answers "not supported" instead of silently doing nothing.
  - **`/restart` is refused when unsupervised.** Exiting IS the restart under
    `Restart=always`; without systemd the same exit is a kill, so the handler checks
    `INVOCATION_ID`/`JOURNAL_STREAM` first and says so instead of taking the bot down.

  Verified live on the second bot (@Esther0001Bot) host: `/status`, `/new`, `/model`
  (switch + reset + a rejected name), `/compact` and `/restart` each exercised end-to-end
  through the running systemd unit — see `docs/evidence/gateway-slash-parity-2026-10-08.txt`.
  13/13 checks, run twice on the deployed tree.

  That live run also earned its keep by finding a REAL defect in `/compact`, which is
  exactly what a checked-only-in-unit-tests suite would have missed:

  - **pi's RPC `compact` never answers for a session whose transcript does not exist
    yet** (`get_state` on the same id answers in ~1.2s and creates it). A chat that has
    just used `/new`, or whose first turn has not run, is that case. The adapter now
    reads the state first and answers "this chat has no conversation yet" instead of
    asking blind.
  - **With its MCP servers connected, pi's RPC startup wedged ~40% of control calls**
    — process alive, silent, no stderr, for the whole deadline. Measured on the trigger
    sequence: 4 fast / 2 hangs with MCP, 8/8 answered at ~1.2s with `--no-mcp`. A
    control call (`compact`, `state`) uses no MCP tool, so the servers are pure risk;
    the adapter passes `--no-mcp` and starts pi in its own process group so a timeout
    reaps pi AND its children.

  Both are held by `tests/test_gateway_slash_parity.py`.

- **2026-10-08, same day — "/restart gave no indication it happened".** Reported after a
  restart that HAD happened: systemd restarted the unit (NRestarts=1, new MainPID), but
  the only message about it was sent by the process that then exited, and the
  conversation deliberately continued. Asked "did you restart?", the AGENT answered
  "No, I didn't restart. I still have our conversation context…" — true of the session,
  false about the gateway, and the only answer the human could get. Three changes, and
  the third is the one worth keeping: `/restart`'s reply states what happens to the
  conversation ("restart" reads like "fresh start" and this is not one); the new process
  announces itself at startup, before polling, with the operator's wording ("♻ Gateway
  restarted successfully. Your session continues.") so a chat need not speak first to
  learn the gateway is back; and the agent is handed the same fact on its first prompt
  after the restart (the marker outlives the announcement, and is consumed by that turn,
  so the human is not told twice). If the startup send fails, the marker survives and the
  first reply carries the confirmation — the news is never lost to a failed send.
  Evidence: `docs/evidence/gateway-restart-visibility-2026-10-08.txt` (live proof on a
  scratch systemd unit running the deployed code: start 1 = the real handler; start 2 =
  the announcement, then a real pi turn whose prompt carries the system note).

## Evidence

- Capability test (executed): `tests/test_cortex_gateway_parity_matrix.py` — golden updates
  → the target's real `parse()`/`send()`, gap register printed each run.
- Fixtures: `tests/fixtures/telegram-golden-updates.json` (synthetic ids/dates — real chat
  ids are personal identifiers and 10-digit unix timestamps read as phone numbers).
- Gateway suites (executed): **111 passed** (106 pre-existing + 5 new).
- Incumbent: `hermes-agent/plugins/platforms/telegram/adapter.py`.
- Target: `hermes-cortex/ops/scripts/cortex_gateway/{transport,daemon}.py`;
  design `docs/design/cortex-gateway.md` (CR1–CR4 ✅, CR5 pi pending).

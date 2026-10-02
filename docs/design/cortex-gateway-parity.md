# cortex-gateway ↔ hermes-gateway: functional parity matrix

**Question (Luke, 2026-10-02):** can Telegram move from `hermes-gateway` to
`cortex-gateway` without losing functionality?

**Verdict: NOT full functional parity — and that was never claimed.** The design doc's
CR1 parity claim is against **`ops/scripts/msg-gateway.py`** (HC's own precursor), not
against Hermes's platform adapter. The two are different bars:

| | incumbent | target |
|---|---|---|
| code | `hermes-agent/plugins/platforms/telegram/adapter.py` (~1400 lines) | `ops/scripts/cortex_gateway/transport.py` + `daemon.py` (~400 lines) |
| shape | full platform adapter inside the agent process | transport + dispatch seam, agent out-of-process |

`docs/design/cortex-gateway.md` states the target's own rule: "no re-implemented Hermes
agent loop", "nothing else". So the gap is intentional in shape — what matters is naming
exactly what a cutover drops, and deciding each one deliberately.

## Matrix

Evidence column: `T` = asserted by the committed test below (executed), `C` = code path
cited, `-` = absent.

| Capability | incumbent | target | Evidence | Cutover verdict |
|---|---|---|---|---|
| Plain text inbound → agent | ✅ | ✅ | T | equivalent |
| Sender allowlist | ✅ env + callback auth + pairing | ✅ `TELEGRAM_ALLOWED_USERS`, fail-closed | T, C(`daemon._turn`) | equivalent (target has NO pairing flow: unknown senders are refused, not paired) |
| Text outbound | ✅ | ✅ | T | equivalent |
| Reply/quote | ✅ | ✅ if envelope carries `reply_to_msg_id` | C(`transport.send`) | equivalent for agent-initiated replies |
| **Media (photo/document/voice) inbound** | ✅ | ❌ `media: []` always; a captioned photo is dropped ENTIRELY (`parse` reads only `text`, never `caption`) | T | **GAP — dropped silently** |
| **Media outbound** | ✅ | ❌ text-only | T | **GAP — agents cannot send images/files** |
| **Long message chunking** | ✅ splits | ❌ `body[:4000]` truncation | T | **GAP — silent data loss on long replies** |
| **Rich formatting (markdown/HTML, code blocks)** | ✅ rich rendering, desktop crash/CJK workarounds | ❌ plain text | T | **GAP** |
| **Slash commands (/stop, /status, /model)** | ✅ gateway-level dispatch | ❌ text becomes the prompt body | T | **GAP — no way to interrupt a runaway turn from Telegram** |
| **Busy/interrupt (queue while agent runs)** | ✅ two-level guard | ❌ single dispatch, no interrupt | C | **GAP** |
| **Polling recovery (stall detect, conflict, reconnect)** | ✅ `_PollingStallError`, `_wait_for_reconnection` | ❌ raises `RuntimeError` on `!ok` | C | **GAP — one bad poll can kill the loop** |
| **Retry/backoff + 429 handling** | ✅ error classification | ❌ no retry | C | **GAP** |
| Forum topics / DM topics | ✅ thread kwargs, reply anchors, binding prune | ⚠️ passes `message_thread_id` only | C | partial |
| Typing indicator / drafts / streaming edits | ✅ | ❌ | C | GAP (cosmetic) |
| Reactions, inline callbacks, edits | ✅ | ❌ (non-`message` updates → `None`) | T | GAP |
| Multi-platform (Discord/Slack/… 20+) | ✅ | ❌ Telegram only (anti-bloat by design) | C | accepted by design |
| Agent out-of-process (survives gateway restart) | ❌ in-process | ✅ | C | **target wins** |
| Swappable agent backend (pi/steadfaste) | ❌ | ✅ seam; pi = CR5 pending | C | **target wins** |
| HMAC-signed envelopes between gateway and agent | ❌ in-process | ✅ `GATEWAY_SECRET`, fail-closed | T(`test_cortex_gateway_key_guard`) | **target wins** |

## What this means for the cutover

The target is better where it was designed to be (out-of-process, swappable backend,
signed envelopes) and thinner in platform features that Hermes's adapter accumulated over
a long time. Three of the gaps are not cosmetic:

1. **Silent truncation at 4000 chars** — a long agent reply loses its tail with no error.
2. **No `/stop`-equivalent** — with the agent out-of-process there is currently no
   in-band way to interrupt a turn from Telegram.
3. **No polling recovery/backoff** — the incumbent treats a polling conflict or a network
   blip as a recoverable state; the target raises.

Recommendation: treat "adapter feature parity" as its own slice (call it CR5a) before the
Telegram cutover, OR cut over accepting the three named losses above. The pi backend
(CR5) is orthogonal — it changes *who answers*, not what the transport can carry.

## Evidence

- Committed capability test: `tests/test_cortex_gateway_parity_matrix.py` (golden Telegram
  updates → the target's actual envelope/`send` behavior; each GAP above is asserted as
  today's behavior so an improvement FAILS the test and forces this matrix to be updated).
- Fixtures: `tests/fixtures/telegram-golden-updates.json`.
- Existing suite (executed): `tests/test_cortex_gateway_*.py`,
  `test_telegram_bridge*.py`, `test_msg_gateway.py`, `test_gateway_envelope.py`,
  `test_telegram_notify_unit.py` — **106 passed**.
- Incumbent: `hermes-agent/plugins/platforms/telegram/adapter.py`.
- Target: `hermes-cortex/ops/scripts/cortex_gateway/{transport,daemon}.py`;
  design `docs/design/cortex-gateway.md` (CR1–CR4 ✅, CR5 pi pending).

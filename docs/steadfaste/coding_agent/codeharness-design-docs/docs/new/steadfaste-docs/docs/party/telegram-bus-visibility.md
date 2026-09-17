# Delivery & Integration Layer — Telegram Sessions, Notifications, Live Visualization, Agent Bus

> Requirements from Luke, grounded in the fleet's EXISTING fabric: the PGMQ
> Agent Bus (`cortex-bus` skill) and the Unified Messaging Gateway ADR-0005
> (`messaging-gateway` skill). Key finding: **the fleet already built the exact
> fabric this needs.** Coding agents are already bus-only citizens with
> HMAC-signed envelopes, scoped tokens, and an add-an-agent recipe. The harness
> is just one more such agent.

## The convergence (read this first)

ADR-0005 already answers "Telegram sessions like Hermes" for ANY coding agent:

```
messaging gateway (one daemon/server)  ← owns N Telegram bots, no LLM
        │  inbound: inbox_<AGENT>       │ outbound: out_<AGENT> → adapter.send
        ▼
    AGENT BUS (PGMQ)  ← the fabric every agent shares
        │
  Hermes + coding agents (Codex/Claude/Blackbox/Grok) + OUR HARNESS
```

The harness's own-agent is **just another coding agent on this bus**. It needs
no Telegram code of its own — the gateway routes `channel_user_id → AGENT`, the
harness reads `inbox_codeharness`, writes `out_codeharness`, and the gateway
delivers. HMAC-signed inbound means the harness accepts gateway messages only
as DATA (anti prompt-injection), exactly the trust model we froze.

## 1. Telegram sessions "like Hermes"

**Nothing new to invent — follow the ADR-0005 coding-agent recipe:**

1. `cortex-agent-manager.py add codeharness` — mint a **scoped** token
   (read `inbox_codeharness`, write `out_codeharness`; never wildcard).
2. `gateway.yaml` routing row: `Luke's chat_id → codeharness`.
3. `agent-shim.py --generate --agent codeharness` — the standard poll/reply shim.
4. Hook the shim into the harness **supervisor** (not the worker): the
   supervisor is the bus-only citizen; the worker stays dumb and out-of-process.

**Session semantics** (map Hermes → harness):
- DM to the bot = a `Task` (objective from the message; budget from defaults or
  an inline prompt like `$1 / 30m`).
- Streaming output → `out_codeharness` as `PROGRESS`/`MODEL_REQUEST_FINISHED`
  journal events, delivered by the gateway.
- Steer / cancel / status = inbound messages (gateway-signed, HMAC-verified) →
  supervisor translates to Worker ABI v1 `send` / `cancel` / `status` ops.
- **HITL approval = an inbound message the harness renders as an inline
  keyboard** (approve/deny buttons). The harness posts a `HITL_REQUEST` to
  `out_codeharness` with reply-markup; the operator's tap returns as an inbound
  `HITL_RESPONSE`. This closes the party's "plugins will fake approval" gap —
  the approval primitive is real and human-delivered.

**The only new requirement vs. ADR-0005:** the gateway envelope already covers
text + media; inline-keyboard **reply markup** for HITL must be an additive
field on the outbound envelope (v1 already has `body`/`media`/`reply_to_msg_id`;
add `inline_actions[]`). Additive, not breaking.

## 2. Notifications at each logical place

A **notifier peripheral** (plugin, not core) subscribes to the journal:

- **Milestone policy** (which events → notify): `TASK_LEASED`, `CHECKPOINT`,
  `TESTS_PASSED`, `VERIFIER_PASSED`, `HITL_REQUIRED` (interactive), `TASK_COMPLETE`,
  `TASK_FAILED`, and `STOPPED` (emergency: budget/interrupted/error).
- **State-signature dedup** — fleet lesson (memory): identical deliveries every
  tick are noise. Suppress by a state signature (task_id + event_type + content
  hash), not raw event rate.
- **Sink** = `out_codeharness` (gateway → Telegram). The notifier is bus-only,
  exactly like the agent.
- **Core emits journal events; the notifier is peripheral.** The frozen core
  only guarantees the journal + a stable event envelope. Which events notify,
  at what throttle, to whom — all policy, all swappable.

## 3. Live visualization on a live image

The **visualizer/drill-in** (already designed) rendered as a **status board
image**, re-rendered + pushed on each milestone:

- `renderStatusBoard(journalSnapshot) → image` — a pure fold of the append-only
  journal (same fold QA put in the test pyramid). Shows: task tree, fan-out,
  per-step progress, model/cost/cache-hit line, issues (red), **emergency stops
  as a red banner**, pending HITL (yellow).
- **SVG → PNG** (or direct PNG): SVG is dependency-free and diffable for tests;
  Telegram delivers PNG/JPG as a photo. A tiny SVG→PNG step (or a minimal
  rasterizer) is the only build dependency.
- **Push cadence**: re-render on `CHECKPOINT` / `TASK_LEASED` / completion /
  emergency-stop — the same milestone policy as §2, shared config.
- It is a **pure function of the journal**, so it's deterministic (golden-fixture
  testable) and can never get out of sync with reality. No separate state.

## 4. Agent bus augmentation (what actually changes)

The bus is already the right transport. The augmentation is **small and
additive**:

**New subjects** (extend the `^[A-Z][A-Z0-9_]{0,63}$` subject enum — no schema
change, just new values):
- `TASK_DISPATCH` — a task pushed to the harness (closes scenario G2: "pushed
  to agent" = a TASK_DISPATCH on `inbox_codeharness`).
- `WORKER_EVENT` — harness journal events re-published for fleet visibility.
- `HITL_REQUEST` / `HITL_RESPONSE` — the approval round-trip.
- `STATUS_BOARD` — the rendered board (media payload) for cross-agent visibility.

**New queues**: `inbox_codeharness` + `out_codeharness` (created by the
add-an-agent recipe; per-queue ACL already supports this).

**Who owns what:**
- The **supervisor** is the bus-only citizen: it consumes `inbox_codeharness`
  (tasks, steers, approvals), emits `out_codeharness` (events, HITL, board).
- The **worker** stays out-of-process, off-bus (stdio ABI) — it never touches
  Telegram or the bus directly. This preserves the security model: the LLM-driven
  worker is sandboxed behind the supervisor + gateway, and its only egress is
  the ABI event stream.

**Fleet integration consequence (this is the win):** because the harness rides
the same bus, a task can arrive from ANY fleet agent, the harness can dispatch
subtasks to fleet agents over the bus, and results/approvals flow back over the
same fabric. "Push to agent" and "fan-out across agents" become the same
mechanism — no new orchestration layer.

## Key decisions (need Luke's sign-off)

- **D1 — gateway reuse.** The harness does NOT build its own Telegram gateway;
  it rides the existing messaging-gateway daemon (ADR-0005) as a bus-only agent.
  This is the whole point of "like Hermes". Confirm.
- **D2 — HITL inline keyboard.** Requires ONE additive envelope field
  (`inline_actions[]`) on the outbound envelope — additive, not breaking v1.
- **D3 — board image format.** SVG→PNG (dependency-free core, small rasterizer)
  vs. a heavier chart lib. Recommend SVG→PNG.
- **D4 — notifier scope.** Milestone policy (which events notify) as a JSONC
  config block in the harness config, dedup by state-signature.

## Open questions

1. **Supervisor placement** — does the harness supervisor run as a fleet service
   (like the messaging gateway daemon) or as a per-task process? Leans service
   (bus-only, always-on, mirrors the gateway's "deterministic daemon" model).
2. **Task intake syntax** — how a DM maps to a `Task` (budget/workspace/
   permissions from defaults vs. inline). Needs a tiny parser + defaults profile.
3. **Board push throttle** — milestone-push vs. also a pull-on-demand
   (`status` command → render now).

## What this means for the frozen core

**Nothing changes in the frozen core.** The journal, the ABI, the store, the
permission gateway — all untouched. Everything here is peripheral: a notifier
plugin, a renderer (pure journal fold), a supervisor that speaks the gateway
envelope, and new bus subject strings. The core's provider-agnostic, bus-agnostic
stance is *why* this slots in cleanly — the harness is just another peer on a
fabric the fleet already runs.

# Coding Agent Story — Foundation-First, Hermless, Future-Proof

> **North star (Luke, 2026-09-11):** "I want to be able to do exactly what we
> are doing now via Telegram with the new system (without hermes)."
>
> **The necessary prerequisite (Luke, same day, escalated):** "We must make the
> plumbing and foundation the focus. Making this truly rock solid and future
> proofing is *necessary*, not just ideal."
>
> So the order is explicit and non-negotiable: **the permanent, future-proof
> foundation comes first.** The frozen core, crash-safe plumbing, and the Covenant
> contracts are built for **permanence** (they version so slowly a 2026 worker
> still connects in 2029). Every consumer — the agent loop, the Telegram
> gateway, WhatsApp later, the fleet — is a *thin layer on top* that must not
> force the foundation to change. Hermes is not the foundation anymore; when it
> breaks, we route around it, not through it.

## Why foundation-first is necessary (not just nice)

The party's four critics converged on the same pre-freeze truth: **the journal
format, the worker Covenant, the permission vocabulary, and the audit trail are
3-year commitments.** A mistake in any of them is *cheap now, ruinously
expensive after freeze*. So:

- The **frozen `core/`** is built to be the thing that *never changes shape*.
- Every **contract** (Covenant, event, tool, plugin API) is carved, reasoned about
  adversarially (Security 4/10 → the fix list), and **tested** before anything
  else rides on it.
- The gateway (Telegram/WhatsApp), the agent loop, the TUI — all **peripheral,
  replaceable**, never able to force a core change.

Foundation-first is what makes "future proof" a property instead of a hope.
A rock-solid foundation is what lets a three-year-old worker still connect.

## The frozen foundation (Story 1 — necessary, built first)

**As a** builder, **I want** the core foundation to be provably crash-safe,
versioned, and future-proof, **so that** every consumer I add on top is thin,
replaceable, and never forces the foundation to change.

### 1.1 — Covenant v1 (the frozen vocabulary)
- **Value:** the contract that never changes — `task_id`, `attempt_id`,
  `worker_id`, `workspace_id`, `checkpoint_id`, `lease_id`, the 6 operations,
  the events. A worker written in 2026 must connect in 2029.
- **Slice:** finalize `core/abi.ts` (already the scaffold): the `Task` shape
  + a **`deadline` (wall-clock) budget field** (scenario gap G1, must land
  before freeze) + the permission-string vocabulary (default-deny).
- **Skills:** `cross-agent-design` (the Covenant seam), `architecture-review` (the
  freeze contract), `change-checklist` (pre-ship), `test-driven-development`
  (conformance before anything else).
- **Depends:** nothing (it is the substrate).
- **Verify:** the Covenant schema validates; the conformance suite passes a trivial
  worker; the `deadline` field is enforced.
  - Given the frozen Covenant schema, when a Task lacks a valid `deadline`, then it
    is rejected at intake (the wall-clock budget is mandatory).

### 1.2 — Crash-safe atomic store + write-ahead intent journal (the plumbing core)
- **Value:** a kill or ENOSPC leaves either the old complete snapshot or the
  new one — never a torn file. Every effect is exactly-once at the effect level
  via a write-ahead intent journal. This is the rock-solid durability the whole
  system sits on.
- **Slice:** the **rewritten `store.ts`** — real `fsync` (file + directory),
  **sleep-based retry, not busy-spin**, **stale-lock reclaim** (age + pid
  liveness probe), backport OpenSwarm's failure-mode reasoning. Plus the
  intent journal (`replay: never|safe` per tool).
- **Skills:** `reliable-agent-design` (crash-safe patterns),
  `change-checklist`, `test-driven-development`,
  `adversarial-verifier` (A4: state corruption, torn files).
- **Depends:** 1.1 (store persists Covenant Tasks/outcomes).
- **Verify:** a simulated crash mid-write → the file stays a complete snapshot;
  a stale lock from a dead pid is reclaimed; a replay never double-applies a
  `replay: never` effect.
  - Given a killed writer mid-write, when the next writer starts, then it
    recovers the last complete snapshot (never a torn file) and reclaims the
    stale lock.

### 1.3 — Out-of-process stdio worker contract (the trust boundary)
- **Value:** the worker runs out-of-process behind spawn/stdio JSONL — the
  critics' #1 pre-freeze fix. Crash isolation is physically real, and the trust
  boundary keeps a broken worker from taking down the core.
- **Slice:** `WorkerSpec` transport-shaped: 6 ops in, events out, over stdio.
  The conformance suite a **foreign** worker (Pi later) must pass through the
  same door as our own.
- **Skills:** `cross-agent-design`, `agent-harness-design`,
  `adversarial-verifier` (A4: process isolation, malformed frames).
- **Depends:** 1.1.
- **Verify:** a trivial foreign worker passes the conformance suite without a
  core change; a crashing worker is isolated (core survives).
  - Given a worker that crashes mid-task, when the supervisor notices the
    process death (OS liveness + stall timeout), then the core survives and the
    lease is released for retry — the core never shared the worker's fate.

### 1.4 — Event bus + audit log (journal-as-truth)
- **Value:** every effect, every approval, every cost is append-only and
  tamper-evident (hash-chained). The audit trail is the operational truth; the
  store is a rebuildable projection.
- **Slice:** `core/events.ts` (CoreEvent envelope) + hash-chained append-only
  audit journal + write-time secret redaction (not regex-at-render).
- **Skills:** `security-audit` (tamper-evidence), `logging-patterns`,
  `reliable-agent-design`.
- **Depends:** 1.1, 1.2.
- **Verify:** an audit entry cannot be deleted/forged; secrets are scrubbed at
  write time; the store can be rebuilt from the journal.
  - Given a written audit trail, when a plugin tries to alter a past entry,
    then the chain hash fails and the write is rejected.

### 1.5 — Config loader + permission gateway (the security substrate)
- **Value:** one JSONC+JSON-Schema config file; unknown keys are startup errors
  (no env-var spaghetti). Every tool effect goes through a permission-gated
  gateway with `max_observe` truncation + audit.
- **Skills:** `security-audit`, `agent-ergonomic-output`, `codebase-design`.
- **Depends:** 1.1, 1.4.
- **Verify:** an unknown config key fails startup; a tool outside the granted
  permissions is blocked; a large tool result is truncated.
  - Given a config with an unknown key, when loaded, then startup fails with a
    clear message (never silent).

### 1.6 — The agent loop (our own coding agent, as a worker)
- **Value:** the core now runs a real task end-to-end against a real
  OpenAI-compatible adapter with real tools, budget+deadline enforced, exactly
  as the foundation was designed to carry it.
- **Slice:** `core/loop.ts` (agent loop, Pi-derived) + `core/adapter.ts` (real
  provider, no Hermes) + the six built-in tools; `workers/own-agent` registers
  via the plugin door.
- **Skills:** `reliable-agent-design`, `agent-contract`,
  `survey-before-action`, `root-cause-debugging`, `test-driven-development`.
- **Depends:** 1.1–1.5.
- **Verify:** a "add a route + prove it" task runs with real tools, budget +
  deadline enforced, a verified result, a full audit trail — **no Hermes.**

---

## Story 2 — The gateway (Telegram-first, transport-agnostic)

**As a** user, **I want** to send a task to a bot and get the verified result
back over any chat app (Telegram today, WhatsApp/others later via the same
`TransportAdapter` interface), **so that** I do via chat exactly what I do via
Hermes today — minus Hermes.

- **2.1** `TransportAdapter` interface + Telegram adapter (Bot API long-poll;
  offset-advance only after send succeeds; never start from offset 0).
- **2.2** Task intake: chat message → Task (objective, workspace, budget,
  deadline). Parse inline `$1` / `30m`.
- **2.3** Gateway → core dispatch + progress streaming + result reply — the
  hermless demo end-to-end.
- **2.4** Approval gate (HITL) over any transport.

**Design principle:** the gateway is a thin shell. It translates chat messages ↔
the core's task/event contracts; the core never knows the channel.

---
## Story 3 — Fleet & visibility (nice-to-have, later)

- 3.1 Agent-bus integration (TASK_DISPATCH subjects).
- 3.2 Live status-board image over any transport.
- 3.3 WhatsApp (and other) transport adapters — same `TransportAdapter`.
- 3.4 RAG/offline-cache and prompt-engine as configured peripherals.

---

## Execution order

```
Story 1 (FROZEN FOUNDATION — NECESSARY, BUILT FOR PERMANENCE)
  1.1 Covenant v1 (+deadline, permissions)     ← the frozen vocabulary
  1.2 crash-safe store + intent journal            ← the durability core
  1.3 out-of-process stdio worker                  ← the trust boundary
  1.4 event bus + audit (journal-as-truth)         ← the operational truth
  1.5 config + permission gateway                  ← the security substrate
  1.6 the agent loop (our own worker)              ← the foundation carries it

Story 2 (CHAT GATEWAY — THIN SHELL ON THE FOUNDATION)
  2.1 TransportAdapter + telegram
  2.2 task intake
  2.3 gateway → core → stream → reply   (hermless demo)
  2.4 approval gate (HITL)

Story 3 (FLEET & VISIBILITY)
  3.1 bus · 3.2 board · 3.3 more transports · 3.4 RAG/prompt
```

**Why this order is necessary, not ideal:** slices 1.1–1.5 are the frozen
contracts that version so slowly a 2026 thing works in 2029. Getting them right
**before** anything rides on them is the only way "future proof" is a property.
1.6 proves the foundation carries real work; Story 2 attaches a chat transport;
Story 3 extends to the fleet. Every later slice is thin *because* the
foundation is rock-solid.
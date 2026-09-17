# steadfaste

> **Boring, stable, agentic.** A coding-agent foundation that can sit unchanged
> for a year and keep working — a future-proof core you can hand to a 2026
> worker in 2029.

## North star (Luke, 2026-09-11)

> **Mission-critical AI work.** Engineered extremely well, but simple to use,
> configure, understand, and modify — for humans. Four governing words:
> **dependable, visible, enterprise-governed.**

And the companion goals, unchanged:

> Do exactly what we do today via Telegram with the new system — **without
> Hermes.** When Hermes breaks, we route around it, not through it.
>
> An excellent UI **for normal people (non-coders)**, familiar / minimal
> training (not at the expense of genuinely better UX).

## The stack (settled — Rust core + TypeScript modifiable layer)

```
┌─────────────────────────────────────────────────────┐
│ Rust core  (frozen, memory-safe, one static bin)    │
│ ──────────────────────────────────────────────────  │
│ store · audit · event bus · config · supervisor     │
│ worker dispatch · permission gateway                 │
│ a black box that "just works and has worked" —       │
│ engineered so expertly it rarely needs touching.     │
│ Agents maintain it if necessary; enterprise trusts   │
│ it. Versions so slow a 2026 worker still connects.   │
└───────────────────────┬─────────────────────────────┘
                        │ Covenant v1 (JSON over stdio)
                        ▼
┌─────────────────────────────────────────────────────┐
│ TypeScript modifiable layer                          │
│ ──────────────────────────────────────────────────  │
│ agent worker (loop, tools, adapters) — out-of-       │
│   process, spawned by the core                       │
│ the web UI for normal people (React)                 │
│ swappable messaging / models / skills / context      │
│ one language, one toolchain, one seam for humans     │
└─────────────────────────────────────────────────────┘
```

- **Rust = the frozen core** (the "Linux kernel"): store, audit log, event bus,
  config validation, supervisor, permission gateway. Memory-safe, one static
  binary, no runtime churn. This is where the 3-year freeze and performance
  live. It is a **black box that "just works and has worked"** — not a thing
  every user reads.
- **TypeScript = the modifiable layer**: the agent worker (loop, tools,
  adapters), the **web UI for normal people** (React), and the swappable
  messaging / models / skills / context. **One language, one toolchain** on
  everything a human or agent customizes — which is what makes it simple-first
  for the people who DO touch it.
- **The Covenant v1 (JSON-over-stdio) is the seam.** Rust spawns a TS worker
  over the exact out-of-process contract. "Rust core ↔ TS worker" *is* the
  trust boundary.
- **Postgres is the default DB, behind a swappable port** (a typed DB
  interface; SQLite and other backends plug in without a core change).

## Platform & UI

- **Postgres** (default, swappable) — durable, ACID, audit, roles. The
  crash-safety + exactly-once + tamper-evidence work lives here, not in a
  hand-rolled store.
- **Ubuntu LTS** — the safe, boring, enterprise OS base.
- **Cross-platform** — unix / macOS / Windows (per-platform binaries).
- **Non-coder web UI** — a familiar web/chat surface normal people open in a
  browser; admin-customizable.

## Design principles

1. **Future-proof core.** `core/` versions so slowly a 2026 thing works in
   2029. Frozen by directory-name and CI-grepped: it never imports from a
   worker/tool/plugin.
2. **Rock-solid plumbing.** Durability/atomicity/exactly-once live in Postgres
   (intent-journal table keyed by `attempt_id`); hash-chained append-only audit
   (journal-as-truth); no busy-spins.
3. **Simple for humans — and for non-coders.** One validated config file
   (unknown key = startup error, no env-var spaghetti). The 90% works with zero
   config; the 10% is a swappable peripheral (worker/messaging/model/db/UI).
4. **Swappable everything.** Messaging, models, skills, context, DB, UI —
   ports-and-adapters across the surface, each easily seen/changed.
5. **The agent is a plugin.** Our own coding agent is one worker; Pi/OpenSwarm
   plug in through the same Covenant with zero core change.
6. **Set-and-forget.** No auto-updates; pinned versions; immutable workers;
   one-way promotion (develop → soak → candidate → 30-day fleet → stable).
7. **Enterprise-governed.** Governance, traceability, reduced risk — approvals,
   audit, no bypasses, reproducible builds.

## The frozen Covenant (Covenant v1) — the whole vocabulary

A `Task` in (objective, workspace, permissions, budget incl. wall-clock
deadline), 11 worker events out, 6 worker operations. The core never knows what
a "Pi session" or "Hermes session" is — only `task_id`, `attempt_id`,
`worker_id`, `workspace_id`, `checkpoint_id`, `lease_id`.

## Layout

```
steadfaste/
  core/            # Rust — the frozen runtime (store, audit, bus, config,
                   #          supervisor, gateway, Covenant types)
  worker/          # TypeScript — the agent-worker (loop, tools, adapters),
                   #   spawned over stdio by the core
  web/             # TypeScript — the non-coder web UI (React)
  gateway/         # TypeScript — transport-agnostic (Telegram first)
  docs/            # the full design (party, briefs, story, decisions)
  test/            # the test tree (Rust tests + TS tests + the Covenant
                   #   conformance suite a foreign worker must pass)
```

## Status

Foundation-first. Language decision **settled**: Rust core + TypeScript
modifiable layer + Postgres + Ubuntu LTS + cross-platform + non-coder web UI.
Slice 1.2 (durable store) becomes **Postgres-backed tables + intent-journal
table with `attempt_id` exactly-once**, proven by the same contract the
TypeScript prototype validated. Next: the Rust core skeleton + Covenant v1 +
conformance suite.

**Docs home:** [`docs/story/coding-agent-story.md`](docs/story/coding-agent-story.md)
(execution order), [`docs/party/decision.md`](docs/party/decision.md) and
[`docs/party/lang-decision.md`](docs/party/lang-decision.md) (decisions).
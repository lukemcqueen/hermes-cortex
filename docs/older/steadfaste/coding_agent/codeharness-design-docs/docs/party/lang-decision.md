# Language / DB / UI Decision — Language Party Synthesis (deepseek pro)

> Elicit + architecture party, reviewers pinned to **deepseek-v4-pro**
> (OpenRouter). Inputs: `docs/party/language-brief.md`, `decision.md`,
> `story/coding-agent-story.md`, `README.md`, plus mid-review steers (Postgres,
> Ubuntu LTS, mission-critical north star, cross-platform, non-coder UI,
> swappable-everything, familiarity/minimal-training).

## The independent verdicts (consensus — they disagree only in degree)

| Role | Verdict | Why |
|------|---------|-----|
| **Architect** | **Unified TypeScript** 6.95 > Rust+Python 6.60 | the web-GUI-for-normal-people constraint *forces* TS into the stack anyway → Rust+Python becomes **three languages** for one maintainer; cross-platform + runtime-free binary favor a single toolchain |
| **Performance** | Rust's speed is **not load-bearing** (2/10); **all-Python async 9/10** | **99%+ of wall-clock is I/O-bound** (LLM API, tool subprocess, Postgres WAL/fsync) → language-agnostic. The few CPU bursts (hash, JSON) are microseconds. **Postgres killed Rust's only perf-adjacent justification** (the hand-rolled store's fsync/WAL is now Postgres's job) |
| **DX / Human-Simplicity** | **Python wins** (8-9/10); Rust core 3/10 | Rust's dependability (memory-safe, exhaustive) **hurts human governability** — a tired solo maintainer in 2029 cannot independently audit/fix/verify async Rust; "trust the compiler" is not enterprise governance |

## The sharpest tension (all three hit it)

> **Rust protects the system but makes it opaque to the person who must govern
> it.** For *depends-on/visible/enterprise-governed* + a **single human
> maintainer**, the human's ability to read, prove, and fix the core is itself a
> governance requirement. A Rust core the human can't read is a black box in the
> most critical layer.

## What the mission-critical / cross-platform reframes did

1. **Postgres** (default) absorbs durability/atomicity/tamper-evidence — the old
   strongest pro-Rust argument. Slice 1.2 becomes **Postgres tables + an
   intent-journal table with `attempt_id` exactly-once**, not a custom store.
   Custom file store **rejected** (the prototype's own busy-spin/fsync/stale-lock
   bugs prove hand-rolling durability is exactly what you don't want).
2. **Swappable DB** partially re-opens the concern (SQLite has no GRANT, so
   enforcement returns to typed port contracts) — but the resolution is a
   **typed DB port**, not Rust.
3. **Cross-platform + web UI** kills all-Python *and* Ubuntu-only packaging;
   **swappable-everything + non-coder UI + minimal-training** confirm the target:
   a **backend daemon + familiar web/chat UI** (chat panel, task view, approval
   prompts) — which is TS-ecosystem-native.

## Recommendation

**Unified TypeScript** — one language for the core daemon, the worker (out-of-process
over stdio), and the React web UI. Postgres behind a swappable DB port (default).
Shipped as per-platform binaries (Bun compile / Node SEA) for cross-platform
double-click simplicity. This is the least-toolchain, best-enterprise-governance,
most human-readable outcome.

- **Worker is still out-of-process** (the critics' #1 pre-freeze fix) — the seam
  is JSON-over-stdio, unchanged.
- **The "agent is a plugin" principle stands** — own-agent is one worker; Pi/
  OpenSwarm plug in via the same ABI.
- **"Blazing fast" is satisfied** by async + native libs (asyncpg/orjson/argon2),
  not by a slow-to-maintain core.

## The ONE thing that would flip it to Rust

> If a **reproducible, runtime-free binary that provably sits unchanged 3 years
> AND where 'no bypasses' must be a compiler/enforcement guarantee** is a hard
> requirement (Node/Bun churn unacceptable), then promote **only the thin
> ~3–5k-LOC core** to Rust, keeping TS/Python as disposable peripherals.

That is Luke's call — it hinges on whether "runtime-free frozen binary" matters
more than "one language the human can read." Default here: **TypeScript** single
language, Rust only as the narrow-core escalation.

## Standing constraints (locked, not re-litigated)

- Postgres = default DB (swappable); Ubuntu LTS = enterprise OS; cross-platform
  (unix/macos/windows); non-coder excellent web UI; swappable everything;
  mission-critical → dependable/visible/enterprise-governed, then
  simple-for-humans, with familiarity/minimal-training (below genuinely-better UX).

---

## FINAL DECISION (2026-09-11, Luke) — SETTLED

After the black-box-core reframe, the DX critique of Rust is dissolved: the core
is **not** for people to read — it is a black box that "just works and has
worked," engineered so expertly it rarely needs touching. Agents maintain it if
necessary; enterprises never need to. That restores Rust as the frozen core on
its own terms (performance, memory-safety, static binary, 3-year freeze,
compiler-enforced no-bypass).

**Chosen stack:**
- **Rust = frozen core** (store, audit, bus, config, supervisor, permission
  gateway) — the black box that just works; the performance + 3-year-freeze
  layer.
- **TypeScript = the modifiable layer** — agent worker (out-of-process stdio),
  the non-coder web UI (React), and the swappable messaging/models/skills/
  context. One language, one toolchain on everything a human or agent touches.
- **Postgres** default DB behind a swappable typed port; durability/atomicity/
  exactly-once/tamper-evidence live in Postgres (intent-journal table keyed by
  `attempt_id`).
- **Ubuntu LTS** enterprise base; **cross-platform** (unix/macos/windows);
  **non-coder web UI**; **swappable everything**.
- **Python dropped** — it added a second customize-layer language, the worst
  cross-platform distribution story, and weaker contract governance, with no
  ecosystem edge that outweighs those for a harness.

Rationale recorded in `lang-architect.md`, `lang-performance.md`, `lang-dx.md`. The
TS-vs-Python depth: TS is decisively better on single-language customizability,
cross-platform double-click install, and type-safe swappable contracts; Python
loses those and its AI-ecosystem edge doesn't move the needle for a harness.
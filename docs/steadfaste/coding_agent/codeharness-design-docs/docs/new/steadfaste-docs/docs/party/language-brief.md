# Language Decision Brief — Rust core + Python worker

> Subject of an elicit + architecture party (reviewers = deepseek pro).
> The question: **are Rust (frozen core) + Python (agent-worker) the right
> language split for steadfaste?** Decide before committing the foundation.

## Context (already decided / not re-litigating)

- **steadfaste**: a future-proof, hermless coding-agent foundation. It must
  version so slowly a 2026 worker connects in 2029.
- **North star (Luke):** "Engineered extremely well, but simple to use,
  configure, understand, and modify — for humans."
- **Foundation-first:** store, audit, event bus, config, supervisor, permission
  gateway are built for permanence and proven before any gateway/demo.
- **The ABI** (Worker ABI v1: Task in, 11 events, 6 ops) is the frozen seam.
  Out-of-process stdio is the trust boundary (the critics' #1 pre-freeze fix).
- **Companion goal:** do via Telegram what we do via Hermes today — without
  Hermes.
- Design docs live in `docs/party/decision.md`, `docs/story/coding-agent-story.md`.

## The proposed split (IN REVIEW)

```
Rust core (frozen, memory-safe, one static binary)
  store · audit · event bus · config · supervisor · permission gateway
  ────────────────────────  Worker ABI v1 (JSON over stdio)  ─────────
Python worker + gateway (readable, I/O-bound, ergonomic)
  agent loop · tools · adapters · templates · Telegram/WhatsApp transports
```

**Rationale given:** the core benefits from Rust (memory safety, static binary,
3-year freeze, blazing fast); the worker is I/O-bound (LLM + tool exec) where
Rust's speed adds little but Python's readability and agent ecosystem help
"simple for humans."

## Decision axes (each role must weigh these honestly)

1. **Performance** — where does steadfaste actually spend time? Is the hot path
   really in the store/audit/bus (Rust's win), or in the LLM loop + tool exec
   (I/O-bound, language-agnostic)? Is a Python core "good enough" for a 1-2
   person harness, or is Rust's speed genuinely load-bearing?
2. **Stability / future-proof** — does Rust genuinely deliver the 3-year-freeze
   promise better than a pinned Python? Compile-time type safety vs. runtime;
   static-bin reproducibility vs. interpreter + pinned deps; the cost of
   touching Rust to a maintainer.
3. **Simplicity for humans** — for THIS owner (read/understand/modify), is a
   Python worker + Rust core *more* or *less* simple than all-Python or the
   original all-TypeScript? Where is the seam's cognitive cost?
4. **Ecosystem fit** — the agent ecosystem (loop patterns, tools, adapters) is
   rich in Python; is Rust net-adding or net-subtracting for the *agent*
   layers? For the core layers, does Rust buy enough to justify a second
   toolchain?
5. **The seam itself** — JSON-over-stdio between Rust and Python is a real
   process boundary. Is that the right boundary (crash isolation, versioning)
   or an avoidable hop? Could a single language do both cleanly?
6. **Operational cost** — two toolchains, two build systems, two dep trees,
   two security surfaces. Is that a feature (isolation) or a tax (drift)?

## Alternatives to weigh honestly (NOT strawmen)

- **All-Python core + worker:** one language, maximum simplicity for humans;
  give up Rust's static-bin guarantees; performance from libraries.
- **All-Rust core + worker:** one language, maximum performance/stability;
  give up Python's agent ecosystem + ergonomics; higher authoring cost.
- **Rust core + Python worker (the proposal):** the split; best-of-both om
  paper, but two toolchains.
- **Rust core now, PyO3/Native bindings:** Rust core called from Python in-
  process (no stdio hop) — keeps one process; loses process-level crash
  isolation.
- **Keep TypeScript prototype** (what we had): already proven; but "blazing
  fast" steer says otherwise.

## What the party must produce

For the **Recommended** option: score (1-10) on each axis, the weighted total,
the showstoppers (anything that would make the choice wrong), the mitigations,
the cost estimate (dev effort, infra, maintenance), and the answer to the
north-star test: *is this simpler for a human to use/read/modify/configure than
the alternatives?* If the recommendation is a different split, say so plainly —
the point is to decide before the foundation is committed to Rust.
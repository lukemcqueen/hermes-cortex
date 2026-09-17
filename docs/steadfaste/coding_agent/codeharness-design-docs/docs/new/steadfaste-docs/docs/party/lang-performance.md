# Performance — Language Decision Analysis

> Role: PERFORMANCE. Honest, trace-driven, no cheerleading.
> Updated for the owner's steer: **the database is Postgres** (default), which
> changes what the "store" layer IS. Also: **Ubuntu LTS** is the OS baseline.

## OS baseline: Ubuntu LTS

steadfaste targets **Ubuntu LTS** (safe, boring, enterprise-first — apt-installable
Postgres, systemd units, a known glibc target, 5-year support). This is
performance-neutral: the perf story is language + DB + I/O, not the distro.
Assembly and reproducibility are tracked against the Ubuntu LTS glibc baseline;
no packaging surprises expected. Recorded for reproducibility, not revisited.

## The real hot path (trace a coding-agent run)

A single turn in the agent loop:

```
Worker receives task → assemble prompt → LLM API call (stream tokens)
→ parse tool call → spawn subprocess → wait for tool output
→ read/edit file → emit TOOL_CALL_FINISHED → core persists journal entry
→ core appends audit record → loop back
```

The "core persists journal entry" and "append audit record" steps are the only
ones that touch the Rust side — and, under the Postgres steer, they are now
database round-trips, not hand-rolled file writes.

## Per-layer cost analysis

| Layer | What happens | Bound? | Language matters? |
|-------|-------------|--------|-------------------|
| **LLM API call + stream** | HTTP POST, SSE token stream over TLS | **Network I/O** (~100ms–30s; median ~2–5s/turn) | **No.** Rust and Python both sit in `select()`/`poll()` on a socket. |
| **Tool subprocess exec** | `fork`/`exec`, child runs bash/node/python, writes stdout | **Process spawn + child I/O** (~10ms–500ms for simple tools, minutes for heavy ones) | **No.** OS-level. `asyncio.create_subprocess_exec` is a thin wrapper over `fork`/`exec`. |
| **File read/edit** | `open()`/`read()`/`write()` on workspace files | **Disk I/O** (10µs–10ms on NVMe) | **No.** Same syscalls. Python file I/O is C-backed. |
| **Journal / audit persist** | **Postgres `INSERT` + `COMMIT`** (WAL write + fsync inside Postgres) | **DB round-trip** (0.1–1ms local over unix socket/TCP; 1–10ms remote) | **No.** Client sends SQL over a socket and awaits the reply. Durability is Postgres's job. |
| **Audit hash chain** | SHA-256 of the record + prior hash (~1KB buffer) | **CPU** (transient) | **Barely.** `hashlib.sha256()` is C-backed. ~1µs/entry. The difference vs Rust is ~0.7µs, dwarfed by the DB round-trip that brackets it. |
| **ABI serialize/deserialize** | JSON for 6 ops, 11 events, each <2KB | **CPU** (transient) | **No.** `json`/`orjson` does 2KB in single-digit µs, between I/O waits. |
| **Config load** | Parse JSONC at startup | **CPU** (one-time, <1ms) | **No.** Startup, not runtime. |
| **Permission gateway** | Hash-set allowlist lookup | **CPU** (µs) | **No.** O(1) lookup in Python. |
| **Event bus / queue dispatch** | PGMQ-style queue: a Postgres `INSERT` + `SELECT ... FOR UPDATE SKIP LOCKED` | **DB round-trip** | **No.** Postgres does the work; both languages await it. |

## The verdict in one table

```
                     Time spent     Language-agnostic?    Rust wins here?
LLM API call          85–99%         Yes (network)          No
Tool subprocess        1–10%         Yes (process I/O)      No
File I/O              <1%            Yes (disk)             No
Postgres round-trips  <1%            Yes (network + WAL)    No
Audit hash            <<0.01%        Mostly (C-backed)      ~0.7µs saved
JSON serialize        <<0.01%        Mostly (C-backed)      ~2µs saved
Everything else       <<0.01%        —                      Noise
```

The hot path is **99%+ I/O-bound**. The CPU-bound operations (hash, JSON,
dispatch) run on data so small they complete in microseconds even in pure
Python, and in practice Python delegates them to C (`hashlib`, `json`/`orjson`).
Rust shaves single-digit microseconds off operations already dwarfed by the
multi-second LLM round-trip and the multi-millisecond Postgres commit.

## Postgres re-trace — what the steer changes

The original proposal justified Rust partly on a **hand-rolled atomic file
store**: real `fsync`, stale-lock reclaim, busy-spin-free locking, exactly-once
via a write-ahead intent journal. That is the one place Rust's low-level
control could conceivably matter — and it was also the one place the source
already had correctness bugs (`src/store.ts` busy-spin lock, missing `fsync`
despite the doc comment claiming it; decision.md pre-freeze fix #2).

**Postgres deletes that entire problem.** The system-of-record (journal, audit,
tasks, PGMQ-style queues) becomes a durable, atomic, crash-safe database that
already solved `fsync`, WAL, locking, and exactly-once semantics 25 years ago.
The Rust "store" shrinks to a **SQL client**: serialize a row, `INSERT`, await
the `COMMIT`. That is:

- **Network + WAL bound, not CPU bound.** The client language is irrelevant to
  the latency — it is waiting on a socket and on Postgres's own fsync.
- **Driver-bound, not language-bound.** `asyncpg` (Python) is a C-accelerated
  binary-protocol driver routinely benchmarked among the fastest Postgres
  drivers available, full stop. `tokio-postgres`/`sqlx` (Rust) are comparably
  fast. At a 1-2 person harness's round-trip rates, the client-side difference
  is microseconds against a multi-millisecond DB round-trip. Both are "fast
  enough"; neither wins.
- **The durability/atomicity argument for Rust evaporates.** Rust no longer
  hand-rolls `fsync` or locking; Postgres owns it. There is no Rust file-store
  left to "earn its keep" on performance grounds.

The "blazing fast" ask, correctly located, is now about **the agent loop +
tool exec + the DB driver** — three things where the language is immaterial to
the wall-clock latency. The performance budget is being spent in Postgres (C)
and the async driver, both of which are equally fast under Rust or Python.

## Scoring: performance as a load-bearing concern (1–10)

| Option | Score | Why |
|--------|-------|-----|
| **Rust core + Python worker (proposal)** | **2/10** | With Postgres as system-of-record, the Rust core's only performance story — the hand-rolled atomic store — is gone. Rust becomes a Postgres client on the non-critical path. Performance is not the reason to choose this split; stability and the 3-year freeze are. |
| **All-Python** | **9/10** | Python + `asyncio` + `asyncpg`/`orjson`/`hashlib` handles every operation at speeds where I/O (LLM socket, subprocess, Postgres round-trip) dominates by 3–4 orders of magnitude. `asyncpg` is as fast as any Rust driver. The GIL is irrelevant: the worker spends 99% of its time in `await` on sockets/subprocesses/DB, all of which release the GIL. Genuinely "fast enough" with margin for any scale this harness will see. |
| **All-Rust** | **2/10** | Performance is not load-bearing here. You'd pay Rust's authoring cost for microsecond wins on a seconds-scale, DB-round-trip-dominated pipeline. The only defensible Rust argument is stability/future-proofing, not speed. |
| **Rust core + PyO3 in-process** | **2/10** | Eliminates the stdio hop (µs saved) but loses crash isolation — the #1 pre-freeze fix from Security/SRE/QA. Not worth it on performance grounds. |

## Blunt assessment

**For the actual coding-agent workload — with or without Postgres — Rust's
performance buys essentially nothing.** The entire hot path is I/O-bound: the
LLM socket dominates, tool subprocesses and Postgres round-trips bracket it,
and the few CPU-bound operations in the core are C-backed in Python and run on
data so small that language overhead is noise. With Postgres as the
system-of-record, the case is *stronger*, not weaker: durability, atomicity,
and exactly-once semantics are now Postgres's proven domain, and the
application language is just a client awaiting a socket. A Python `asyncio`
core — `asyncpg` for the DB, `orjson` for serialization, `hashlib` for audit
chaining — is indistinguishable from Rust in end-to-end latency for any number
of users this harness will ever serve. Ubuntu LTS as the OS baseline is neutral
to this conclusion.

## One-paragraph verdict

**Rust's performance is not genuinely load-bearing for this workload, and the
Postgres steer makes that conclusion firmer, not weaker.** The coding-agent hot
path spends 99%+ of wall-clock time waiting on network sockets (LLM API calls),
subprocess I/O (tool exec), and Postgres round-trips — all language-agnostic.
The Rust core's remaining operations are tiny CPU-bound tasks (single-digit
microseconds) that sit between multi-second and multi-millisecond I/O waits,
and its one performance-adjacent justification — the hand-rolled atomic file
store — is now dissolved into Postgres, which owns durability and atomicity in
C regardless of what the client is written in. Python + `asyncio` + `asyncpg` +
`orjson` + `hashlib` delivers "fast enough" with enormous headroom; the
"blazing fast" ask is satisfied by Postgres and the async driver, not by the
application language. If Rust is the right choice for steadfaste, the argument
must rest entirely on stability, the 3-year freeze, compile-time guarantees,
and the static binary — not on performance.
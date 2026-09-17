# DX / Human-Simplicity — Language Split Review

> Role: is the proposed **Rust core + Python worker over JSON-stdio** simpler
> for **one human maintainer** to use, configure, understand, and modify?
> Judge: a tired person, under time pressure, in 2029, who must read and
> modify essentially every important line. That is the real user, not the
> 2026 author at peak energy.

> **North star refined (owner steer):** this is **mission-critical AI work.**
> Governing words, in order: **dependable** (no silent failure), **visible**
> (audit/traceability), **enterprise-governed** (roles, approvals, reproducible
> builds, no bypass) — *then* simple-for-humans. Simplicity is real but
> subordinate. The DX question becomes: which choice yields a system a single
> careful human can **depend on, see, and govern** over 3 years?

> **Other constraints folded in:**
> - **Database is Postgres** — durability/atomicity/WAL/crash-recovery are
>   now Postgres's job, not the core language's. This removes the strongest
>   Rust justification (hand-written crash-safe store).
> - **Platform is Ubuntu LTS** — apt, systemd, known paths, 5-year support.
>   Omarchy-on-Arch is out of scope. Postgres is a well-managed dependency.

---

## The governing lens

Every claim below is tested against three questions, in order:

1. **Dependability:** does this choice prevent silent failure in production?
2. **Visibility:** can a single human SEE what happened — trace, audit, prove?
3. **Governability:** can a single human GOVERN the system — fix, modify,
   verify correctness, prevent bypass — when tired and under pressure?

"Simple to read" is the fourth test, not the first. But it feeds into all
three: you cannot govern what you cannot read.

---

## Re-examined: Rust's dependability wins (real, but narrower than claimed)

The north-star refinement forces an honest accounting of what Rust actually
buys for mission-critical work — not the sales pitch, the reality:

**Real wins:**

- **Memory safety in the supervisor.** A supervisor that spawns worker
  processes, manages leases, and detects stalls must never have a
  use-after-free, data race, or buffer overflow. A memory bug in the
  supervisor is a *silent failure to detect worker death* — catastrophic for
  a mission-critical agent harness. Rust eliminates this class of bug at
  compile time. This is a genuine dependability win.
- **No `AttributeError` / `NoneType` / `TypeError` in production.** Every
  field access, every method call, every match arm is checked at compile
  time. Python's runtime errors are *visible* (tracebacks) but they are still
  failures — and in an async supervisor managing leases, a traceback that
  wasn't caught is a silent stall. Rust's exhaustiveness checking (`match`
  arms, `Option`/`Result` handling) prevents the "forgot to handle this case"
  failure that dominates Python production bugs.
- **Reproducible, self-contained builds.** `cargo build --release` produces
  a single static binary with no runtime interpreter dependency. Docker +
  pinned Python achieves the same reproducibility, but the artifact chain is
  longer (base image, venv, deps, lockfile). The Rust binary is a simpler,
  more auditable artifact.

**Honest limits:**

- **Logic bugs dominate, and Rust does not prevent them.** The pre-freeze
  fixes in `decision.md` — busy-spin lock loop, missing `fsync`, stale lock
  deadlock, conflicting worker contracts, missing adapter — are all *design
  and logic errors*. Rust's type system catches none of them. The
  dependability that matters most for this system is *design* dependability,
  and a language cannot enforce design.
- **Compile-time safety does not equal runtime safety — the store was the
  bridge.** The original Rust argument was "memory-safe language + hand-rolled
  crash-safe store = dependable core." Postgres now owns the store. The Rust
  core's remaining surface (supervisor, gateway, bus, config) is ordinary
  application logic — safer in Rust than Python, yes, but the gap is *much*
  narrower than it was when the core owned fsync and WAL.
- **Async Rust is its own dependability risk.** Tokio + `Send`/`Sync` bounds +
  async traits is expert territory. A tired human can introduce a deadlock or
  a silent task cancellation in async Rust just as easily as in async Python
  — and the debugging experience is worse (no REPL, slow compiles, opaque
  error messages).

---

## The honest tension: Rust protects the system, but may undermine the human's ability to govern it

This is the core of the refined DX analysis:

| Property | Rust | Python (strict) |
|----------|------|-----------------|
| **Dependability** — prevents silent runtime errors | ✅ Compile-time exhaustiveness, memory safety | ⚠️ Runtime errors possible; mypy + strict mode + exhaustive tests narrow the gap |
| **Dependability** — prevents memory bugs in supervisor | ✅ Eliminated at compile time | ⚠️ CPython is memory-safe by design (no manual allocation); subprocess management is battle-tested |
| **Visibility** — audit trail, traceability | ✅ Same design (hash-chained journal, event bus) works in any language | ✅ Same design works |
| **Visibility** — can a human READ and verify every line? | ❌ Async Rust with tokio + traits + lifetimes is genuinely hard to audit | ✅ Tracebacks, REPL, line-by-line readability |
| **Governability** — can a human FIX it when broken? | ❌ Slow compiles, borrow-checker fights, expert-only debugging | ✅ Edit-and-run, quick diagnose-fix-verify loop |
| **Governability** — can a human PROVE correctness independently? | ⚠️ Trust the compiler; but complex async code is hard to reason about even for experts | ✅ Readable code + exhaustive tests = independently verifiable |
| **Governability** — prevents bypass of permission/approval gates | ✅ Type-system enforcement possible (make it impossible to call a tool without going through the gate) | ⚠️ Runtime enforcement (decorators, middleware); discipline required, but auditable |
| **Enterprise** — reproducible builds | ✅ Single static binary | ✅ Docker + pinned deps + hashed lockfile |
| **Enterprise** — no silent failure detection | ✅ Exhaustive match, no forgotten arms | ⚠️ Requires discipline; linters (ruff, mypy) help |

**The sharpest tension:** Rust's type system *prevents* bypass of the
permission gateway at compile time — a genuine governance win. But if a
single human cannot independently audit the gateway code because it's async
Rust with generic traits, the governance win is hollow: you are *trusting*
the compiler instead of *verifying* the code. Enterprise governance requires
the human to govern, not just the machine.

---

## Postgres + Ubuntu LTS amplify the Python argument for governability

With Postgres handling durability and Ubuntu LTS handling platform stability:

- **The most dangerous code is gone.** No hand-written WAL, no custom fsync
  discipline, no stale-lock reclaim. The remaining core (supervisor, gateway,
  bus, config) is safety-important but not *durability-critical* — a bug in
  the supervisor may cause a stall, not data corruption. The dependability gap
  between Rust and Python narrows further when the data integrity layer is
  Postgres.
- **The human already manages Postgres on Ubuntu LTS.** The operational
  surface is familiar: `apt`, `systemctl`, `psql`, `pg_dump`. Adding one more
  database is a configuration line, not a new discipline. The "always-on
  dependency" that would be scary on a raw binary is routine on Ubuntu LTS.
- **SQLite is simpler than Postgres for a single host**, but if the fleet
  standard is Postgres, the operational familiarity wins. Either way, the
  store is not code the human writes — and that is the single biggest
  dependability win in the whole architecture.

---

## Scores — re-weighted for mission-critical

| Option | Dependable | Visible | Governable | Simple for human | **Composite verdict** |
|--------|-----------|---------|------------|------------------|----------------------|
| (a) Rust core | **6/10** (memory safety + exhaustiveness real; async complexity undercuts) | **4/10** (audit trail is design, not language; code is hard to read) | **3/10** (hard to fix, hard to verify independently) | **3/10** | **Loses on governability — the human cannot independently verify the most critical code** |
| (b) Python worker + core (strict) | **5/10** (runtime errors possible; mypy + exhaustive tests narrow the gap; Postgres owns durability) | **8/10** (readable, REPL-able, tracebacks, line-by-line audit) | **8/10** (edit-and-run, quick fix loop, independently verifiable) | **8/10** | **Wins on governability — the human CAN depend on, see, and govern every line** |
| (c) Two toolchains + JSON-stdio seam | **4/10** (process boundary adds failure modes; two surfaces to secure) | **3/10** (split logs, split mental models, cross-boundary tracing) | **2/10** (two builds, two deps, frozen seam taxes every change) | **3/10** | **Loses on all four — the seam is a dependability risk AND a governance failure** |
| (d) One language | **5/10** (same as chosen language) | **9/10** (one model, one debug surface) | **9/10** (one build, one dep tree, no boundary to debug) | **9/10** | **Max visibility + governability; dependability depends on language chosen** |

**The composite verdict:** Rust adds real dependability for the supervisor
layer (memory safety, exhaustive match) but at the cost of human governability
— and for a single maintainer of a mission-critical system, the ability to
independently verify, fix, and govern every line is itself a dependability
property. **The worst outcome is a Rust core the human cannot audit — that is
a governance failure, not a dependability win.**

---

## The sharpest mission-critical trap

**A Rust core that the maintainer cannot read is a black box in the most
critical layer — and "trust the compiler" is not enterprise governance.**

Enterprise governance means: the human can prove the system is correct. In
Python with strict mypy, exhaustive tests, and readable async code, a tired
human in 2029 can read the supervisor, trace a lease-expiry path, verify the
permission gate has no bypass, and fix a bug in 15 minutes. In async Rust with
tokio, `Send`/`Sync` bounds, and generic traits, the same human may spend an
hour just getting the code to compile — and may never be confident they
understand the full correctness picture.

The dependability Rust offers is real, but it is *compiler-mediated*
dependability — the human trusts the machine. Python's dependability must be
*discipline-mediated* — the human verifies the design through tests, types,
and readability. For a single maintainer who must govern the entire system
alone, discipline-mediated dependability is the surer bet, because the human
remains in the loop.

If the team were 5 engineers with a Rust expert on call, the calculus flips:
Rust's compiler-mediated guarantees are a force multiplier. For one person,
they are a barrier.

---

## Verdict

**For a mission-critical system governed by a single human over 3 years:
Python (strict) + Postgres + Ubuntu LTS is the dependability win, not Rust.**

The store is Postgres — durability, atomicity, and crash recovery are solved.
The platform is Ubuntu LTS — apt, systemd, known paths, no surprises. What
remains is a supervisor, a permission gateway, an event bus, and a config
loader — ordinary application logic that must be *correct* and *auditable*.

Rust adds real compile-time guarantees: memory safety, exhaustive match, no
forgotten error paths. But those guarantees come at the cost of the human's
ability to independently verify, fix, and govern the system — and for a single
maintainer, that trade-off loses. The dependability that matters for
mission-critical AI work is not "the compiler says it's correct" — it is "I
can read every line, understand every path, fix every bug, and prove to myself
that the system is right." Python + strict mypy + exhaustive tests + Postgres
delivers that. Rust + one tired human in 2029 does not.

**The human-win is one language (Python, strict), one mental model, one build,
Postgres for durability, on Ubuntu LTS for platform stability.** Start there.
If — and only if — a real production incident proves that Python's runtime
errors are causing mission-critical silent failures that mypy and tests cannot
catch, then extract the supervisor and gateway into a Rust sidecar. The seam
is the last thing to add, not the first.
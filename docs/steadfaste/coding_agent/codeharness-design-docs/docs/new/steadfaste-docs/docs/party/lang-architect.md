# Language Architect — steadfaste language-split evaluation (v3, final)

> Role: **ARCHITECT**. Question: is **Rust core + Python worker** the right split,
> or is all-Python / all-Rust / PyO3 / keep-TypeScript better?
>
> **North star (final, 2026-09-11):** mission-critical AI work. Four governing words:
> **dependable, visible, enterprise-governed** — *then* simple-for-humans. "Simple" is the
> aimed-for surface, **subordinate** to exactly-once/crash-safe/no-silent-failure,
> tamper-evident traceability, and who-did-what/no-bypass governance.
>
> **Binding constraints (stacked):** foundation freezes 3 years · **cross-platform**
> (unix/macOS/windows, not Ubuntu-only) · **swappable-everything** (ports-and-adapters
> across TUI/messaging/models/skills/context/**DBs** — Postgres is the *default port*, not a
> hard dependency) · **excellent web GUI for normal (non-coder) people**, where **familiarity /
> minimal training is a first-class value but ranked below genuinely better UX** · single
> maintainer who reads and modifies it all.

---

## 0. Four constraints that moved the answer — and how far

### 0.1 The web GUI forces TypeScript into the stack — regardless of the backend

The primary human surface is now an **excellent web app for non-coders**, opened in a
browser. That UI is React, and React is TypeScript. **This is the single most consequential
change**, because it means the "one language" simplicity that all-Python offered in earlier
passes is **gone**: the system now contains TypeScript no matter what you do with the core
and worker. It also quietly revives keep-TypeScript from "the incumbent we're throwing away"
to "the language the primary new surface must be written in anyway."

### 0.2 Familiarity shapes *what* the UI is — a chat app + task view + approval prompts

The refined north star specifies the UI as **familiar web/chat patterns**: a chat panel, a
project/task view, and clear approval prompts — the three surfaces normal people already know
from Slack/Telegram/Asana/Jira. Nothing bespoke, no new paradigms; familiarity yields only
where a genuinely better UX clearly wins. This **confirms and hardens the browser + daemon
shape**: a backend serving a localhost HTTP+SSE web app is precisely the architecture that
lets the UI *feel like apps people already know* while the dependable core stays invisible.
It also kills any remaining argument for a bespoke terminal TUI as the primary surface — the
TUI becomes a *secondary, swappable, developer-only* surface.

### 0.3 Cross-platform + normal-people distribution → the *deploy artifact* matters, and Python is the worst at it

"Excellent UI for normal people" on Windows/macOS/Linux means a person double-clicks **one
self-contained thing**. That reframes packaging:

- **Rust** is best-in-class: `cargo build --release --target …` yields one runtime-free
  binary per OS (linux-gnu, apple-darwin, windows-msvc). No interpreter, no install.
- **TypeScript** is close second via **Bun `--compile`** or **Node SEA** (single executable
  applications) — a single binary, though the runtime is bundled rather than absent, and the
  tooling is younger than cargo's.
- **Python** is the **worst**: shipping a Python agent to a non-coder on three OSes means
  either requiring Python + `pip` (a non-starter for normal people) or `PyInstaller`/`uv`-frozen
  bundles, which are brittle the moment native deps (pydantic-core, etc.) enter the tree.

The earlier "Ubuntu LTS makes the runtime boring" point is now **demoted**: boring one-OS is
replaced by "must self-contain on three OSes." That is a distribution problem, and it is the
axis on which the language choice now bites hardest.

### 0.4 Swappable-everything → the frozen **ports** (typed contracts) are the product

Postgres becoming a *port* (swappable down to SQLite) rather than a hard dependency has a
subtle, important effect on the durability argument. In the Postgres-only pass, I said
"Postgres absorbs durability/roles/GRANT, so the language barely matters." With a **swappable
DB**, you can no longer *rely* on Postgres's roles and row-level security to carry governance
— a SQLite fallback has no GRANT at all. So the enforcement of "who did what, no bypasses"
must live **in the app's port contracts**, which must be **typed and frozen**. That partially
**re-opens** the case for compile-time-enforced ports — the one place Rust (and TypeScript)
genuinely beat Python.

### 0.5 The hot path is still I/O + now Postgres; performance remains off the table

Nothing in these constraints changes the fact that the LLM loop, tool exec, and DB are where
time goes — language-agnostic. **Performance is still not a reason to choose a language here.**
Rust's remaining justification is entirely dependability/governance, not speed.

---

## 1. Weights (unchanged shape from v2, new sub-factors named)

| Axis | Weight | Mission-critical justification |
|---|---|---|
| Stability / future-proof | **25%** | dependable (freeze, ACID, typed frozen ports) + visible (tamper-evidence) + governed (reproducible) |
| Operational cost | **20%** | enterprise-governed + **cross-platform distribution** + swappable-DB port complexity |
| Seam / crash-isolation | **15%** | dependable: exactly-once, crash-safe, the trust boundary |
| Ecosystem fit | **15%** | adapter richness (models/messaging/skills) + **React UI ecosystem + familiar web patterns** |
| Simplicity for humans | **15%** | still material — one human reads/audits *everything* — but subordinate |
| Performance | **10%** | I/O-bound + Postgres absorbs the store path |

---

## 2. The five options, scored (all constraints in)

Scores 1–10. Every option assumes: **Postgres default behind a swappable DB port**, worker
**out-of-process over stdio** (except PyO3), and a **familiar React/TS web UI** as the primary
surface.

### A. Rust core + Python worker (+ TS web UI) — *the proposal*

| Axis | Score | Why |
|---|---|---|
| Performance | 7 | core is fast; irrelevant (I/O + Postgres) |
| Stability / future-proof | 9 | memory-safe supervisor/gateway; **Rust traits = compile-time-frozen ports**; cleanest cross-platform single binary |
| Simplicity for humans | 3 | **three languages** (Rust + Python + TS), three build systems, three dep trees — for one maintainer |
| Ecosystem fit | 7 | thin Rust core (few deps) + rich Python adapters + React UI |
| Seam / crash-isolation | 9 | Rust spawns Python over stdio; memory-safe both sides; DB a third isolated process |
| Operational cost | 4 | three toolchains + cross-compile matrix + swappable-DB port surface |
| **Weighted total** | **6.60** | |

**Biggest architectural risk:** three languages for one maintainer. The web UI *added* TS on
top of the Rust+Python pair, so the split is no longer "two toolchains" but **three mental
models + three build systems**, and the frozen port vocabulary must be kept identical across
Rust types, Python dicts, *and* TS types — three places to drift into a silent protocol
failure. The very seam built for dependability is now triplicated.

### B. All-Python (core + worker + TS web UI) — demoted, not by logic but by distribution

| Axis | Score | Why |
|---|---|---|
| Performance | 5 | good enough; I/O + Postgres |
| Stability / future-proof | 6 | Postgres + process boundary carry durability/audit; but no static binary, duck-typed ports |
| Simplicity for humans | 7 | two languages (Python + TS); one backend mental model |
| Ecosystem fit | 9 | best agent/adapter ecosystem + React UI |
| Seam / crash-isolation | 8 | real OS isolation; Python memory-safe |
| Operational cost | 5 | one backend toolchain, but **Python cross-platform distribution to non-coders is the worst of the three** |
| **Weighted total** | **6.55** | |

**Biggest architectural risk:** the shipping problem, not the code. A Python backend that must
be double-clicked by a non-programmer on Windows/macOS/Linux either forces a brittle frozen
bundle or silently assumes a technical user. The two-language simplicity win is real, but it
is **surrendered at the install step** — which is precisely the step "excellent for normal
people" targets.

### C. All-Rust (core + worker + TS web UI)

| Axis | Score | Why |
|---|---|---|
| Performance | 10 | everywhere fast; everywhere irrelevant |
| Stability / future-proof | 10 | the most typed, most reproducible, most memory-safe |
| Simplicity for humans | 2 | borrow checker + compile latency on the churny agent/adapter layer |
| Ecosystem fit | 4 | thin Rust agent/adapter ecosystem |
| Seam / crash-isolation | 9 | memory-safe both sides |
| Operational cost | 5 | one language but slow iteration + cross-compile |
| **Weighted total** | **6.55** | |

**Biggest architectural risk:** swappable-everything makes the *adapter* layer (models,
messaging, skills, context) the fast-moving, plural surface — and Rust taxes exactly that
layer. You buy governance on the frozen ports by throttling the part of the system that
actually *exercises* the dependability guarantees in production.

### D. Rust core + PyO3/native binding (in-process)

| Axis | Score | Why |
|---|---|---|
| Performance | 8 | native, no stdio hop |
| Stability / future-proof | 7 | Rust core, but FFI boundary + **per-platform native wheels** (now three of them) |
| Simplicity for humans | 3 | FFI + PyO3 type conversions + TS UI = three languages *and* an FFI seam |
| Ecosystem fit | 6 | both, awkwardly glued |
| Seam / crash-isolation | 3 | **in-process = shared fate**; a panic/native fault kills both |
| Operational cost | 3 | two toolchains + three-platform wheel matrix + build step per deploy |
| **Weighted total** | **4.95** | |

**Biggest architectural risk:** it destroys crash isolation (the party's #1 fix) *and* it is
the worst option for cross-platform packaging (native wheels on three OSes). The FFI seam is
more fragile to freeze than JSON-over-stdio. Worst of both worlds, and the new cross-platform
constraint makes it strictly worse than in v2.

### E. Keep TypeScript (core + worker + web UI — **one language end-to-end**)

| Axis | Score | Why |
|---|---|---|
| Performance | 6 | Bun/V8 fine; still I/O + Postgres |
| Stability / future-proof | 6 | **TS structural types enforce frozen ports**; Bun `--compile`/Node SEA give single binaries; but 3-year Node/Bun runtime churn |
| Simplicity for humans | 9 | **one language for one maintainer**, from core to worker to UI |
| Ecosystem fit | 7 | React is best-in-class for the familiar web UI; agent ecosystem thinner than Python but LLM+tools are HTTP+subprocess, which TS does fine |
| Seam / crash-isolation | 8 | JS memory-safe; stdio process isolation |
| Operational cost | 6 | one toolchain; npm/bundler churn is the tax, mitigated by Bun + lockfile + Docker |
| **Weighted total** | **6.95** | |

**Biggest architectural risk:** runtime churn over 3 years — the thing Luke steered away from.
Node/Bun version drift and the npm ecosystem's velocity are the one place a TS core can fail
the "sit unchanged for a year" test that a Rust binary passes by construction.

---

## 3. The honest reading

Ranked by weighted total, all five constraints stacked:

| Rank | Option | Total | One-sentence reality |
|---|---|---|---|
| 1 | **Keep TypeScript (unified)** | 6.95 | the UI already forces TS; making the core+worker TS too is the simplest dependable path |
| 2 | Rust core + Python worker (+TS UI) | 6.60 | strongest artifact, but now **three** languages for one person |
| 3 | All-Python (+TS UI) | 6.55 | best agent ecosystem, worst "normal-person installs it" story |
| 4 | All-Rust (+TS UI) | 6.55 | most governed, taxes the churny adapter layer |
| 5 | PyO3/native | 4.95 | loses crash isolation *and* loses cross-platform |

The field has **compressed into a near-tie** at the top, and the compression is itself the
finding: the constraints (web UI, cross-platform, swappable-everything, familiar UI) pull in
different directions that nearly cancel. The web UI pushes toward TypeScript (it's forced in
anyway); cross-platform pushes *away* from Python (worst distribution) and *toward* Rust or
Bun-compiled TS (single binary); swappable-everything pushes toward typed frozen ports (Rust
or TS over Python); familiarity locks in the browser+chat shape (which is TS-native). The net
is that **all-Python, which led v1/v2, is now dead on install ergonomics**, and the real race
is **TypeScript-unified vs a thin Rust core**.

---

## 4. The owner's questions, answered directly

**Does Rust still buy as much?** No — *less*, then partially *more again*. Postgres (as the
default) absorbs durability/atomicity/tamper-evidence into battle-tested C, leaving Rust with
a thin core. But **swappable-DB** partially re-opens it: when the DB can degrade to SQLite,
you cannot rely on Postgres's GRANT/roles for governance, so the enforcement returns to your
port contracts — and *typed* contracts (Rust traits, or TS types) are the only thing that
makes "no bypasses" a compile error rather than a skipped test. So Rust's one remaining edge
survives, but it is narrow: compile-time no-bypass + the cleanest reproducible single binary.

**Does slice 1.2 (store/journal) change?** Yes, materially. The "crash-safe atomic store +
write-ahead intent journal" becomes **Postgres-backed behind a DB port**: store = tables
(tasks/attempts/checkpoints/leases) with WAL durability; intent journal = a table with a
`replay: never|safe` column and exactly-once via a unique `attempt_id`; audit ledger =
append-only, hash-chained, write-time redaction. "Store is a rebuildable projection" is
*cleaner* in SQL. SQLite is demoted to **ephemeral worker-local scratch only**, never
system-of-record — and it *must* be a supported port (not an afterthought) because swappable-
DB is now a stated requirement.

**Postgres vs SQLite vs custom file store?** Postgres is correct for the default — it is the
only option that *natively* serves "enterprise-governed" (ACID + WAL + roles/GRANT + RLS +
PGMQ + replication), and it's already the fleet's reality. SQLite is good dependability but
weak governance (no roles/GRANT — "who did what" has no DB enforcement). Custom file store is
**rejected** outright: the prototype's own store bugs (busy-spin, missing fsync, stale-lock
deadlock) prove that hand-rolling WAL/fsync/hash-chain is the most load-bearing and most
error-prone code, and re-deriving it in Rust only changes the *language* of your bugs.

**Does the web/React GUI change the language calculus?** Yes — fundamentally. It forces
TypeScript into the stack no matter what, which (a) destroys all-Python's "one language"
argument, (b) revives keep-TypeScript, and (c) turns the Rust+Python split into a *three*-
language system. It also makes the deployment artifact the decisive operational question, and
on that axis Python loses and Rust/Bun-TS win.

**Does cross-platform + non-coder UI push toward web-server + browser?** Yes, and that is the
right call — it is the only write-once-run-anywhere UI model, and it correctly makes the
backend a small localhost HTTP+SSE daemon serving a static React bundle. The terminal TUI is
demoted to a *secondary, swappable, developer-only* surface.

**Does familiarity/minimal-training change the shape?** It confirms it. A chat panel + task/
project view + explicit approval prompts are all standard web patterns that map directly onto
a React front-end over a daemon — so familiarity strengthens the browser+daemon shape *and*
strengthens the TypeScript case, because the familiar patterns the UI must feel like are
themselves TS-ecosystem-native. The only place familiarity yields is where a genuinely better
UX clearly wins (e.g. a purpose-built approval/deny flow over a raw chat echo); that is a
UI-level decision, not a language one.

---

## 5. Verdict

The Rust-core + Python-worker split is **now more defensible than it was and simultaneously
more over-engineered** — and the two are the same sentence. Cross-platform distribution and
typed frozen ports are the strongest arguments anyone has yet made *for* a Rust core, and both
land squarely in the mission-critical north star. But the web GUI — which must feel like apps
normal people already know, and is therefore TypeScript-native — forces TypeScript into the
stack anyway, which turns the split from "two toolchains for one maintainer" into **three
languages, three build systems, three dep trees, and a triplicated port vocabulary** — for one
person whose spec has changed five times during this review alone. For a single maintainer
building a dependable, visible, governed foundation whose primary surface is a familiar
browser app, I recommend **a unified TypeScript system — core daemon, worker, and React web UI
in one language, the worker out-of-process over stdio, Postgres (via a swappable DB port) as
the default system of record, shipped as per-platform single binaries via Bun compile or Node
SEA, presenting a chat panel + task/project view + explicit approval prompts** — because
TypeScript's structural types give you compile-time-frozen ports and default-deny enforcement
nearly as strong as Rust's, at one language instead of three, and Postgres plus the process
boundary do the heavy lifting on durability and crash isolation. **The one risk that flips my
answer to a Rust core:** if a *reproducible, runtime-free, single-binary artifact that provably
sits unchanged for three years* is a hard requirement — i.e. the maintainer judges Node/Bun's
runtime churn unacceptable for the 3-year freeze and "no bypasses" must be a compiler guarantee
rather than a typed-but-erasable TypeScript guarantee — then promote the thin, frozen core
(ports + supervisor + permission gateway + audit + web server, ~3–5k LOC) to Rust, accept the
third language, and treat the TS UI and Python worker as disposable peripherals. That is a
defensible call; it is not the one I would make for one human who must read and audit the whole
system.

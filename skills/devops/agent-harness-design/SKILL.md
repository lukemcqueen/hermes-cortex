---
name: agent-harness-design
description: "Use when designing a coding-agent harness or runtime."
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Agent Harness Design — Boring, Stable, Agentic

Designing a coding-agent harness, runtime, or orchestration layer. Luke's #1
requirement is **boring stability**: set-and-forget, pinned versions, no
auto-updates, rare deliberate updates. A foundation that sits unchanged for a
year and keeps working.

## When to Use

- Building or evaluating a coding-agent harness, runtime, or multi-worker orchestration layer
- Deciding whether to adopt vs. fork vs. reimplement an upstream agent framework (Pi, OpenSwarm, OpenHands, Claude Code, Manus)
- Adding a worker, tool gateway, checkpointing, task queue, or TUI cockpit to an existing harness

## Core principle: the agent is GOVERNANCE around the model (risk + cost)

Do not design a harness as "core + a worker that does the work." The agent is
**intelligent governance wrapped around a model/brain** — and the governance is
the product, not the model. The layer between an inbound request (a chat
message) and the executor decides, per request: budget + wall-clock deadline,
which model (cheapest-first escalation), which tools it may touch, what needs a
human's approval, which template/recipe to follow, when to retry/escalate/stop,
and records every decision. That is **risk management** (what it may/must-not
do, approvals, audit) + **cost management** (model choice, budget, cheap-first).
Enterprise adoption is, in the end, just *less risk* — and the yield of the
whole product is *repeatable quality*: a variable-quality model producing the
same good result, run after run, then improving via a self-healing/
self-learning loop that pulls today's lesson into tomorrow's policy.

Design implication: model the **governor/policy engine** (business-editable
rules, templates, cost/method intelligence) as a first-class user/user-editable
layer, and hand the executer a *policy* (not just an objective) — the solid
Task carries budget, permissions, model policy, verification policy, and a
wall-clock deadline. This governance layer is what serious harnesses famously
lack; do not forget it and build just a worker dispatch.

## Structure the repo first, and OVER-structure it (before any real code)

Restructure/rename/move the repo layout **early**, while nothing real depends on
the paths — the user's explicit call is to over-structure with the future in
mind. A folder or file name that will not survive contact with real code is a
sign the design is not done. When the settled architecture differs from the
scaffold on disk (e.g. a TypeScript prototype sitting in a `core/` that is about
to hold Rust), rename/move it immediately so browsing the tree is not
misleading — never leave legacy-code-as-current mislabeling. Lay down stubs and
interfaces first; a well-named public interface *is* the architecture, and it is
what a future session (or agent) reads cold. File names and code names must be
intelligent for human review — a name that reads like an index beats a name that
needs the file opened.

## Settle the solid contract's decisions BEFORE writing it

Do not write the ABI/contract code (types, structs, enums) until the contract's
*open decisions* are pinned. For a long-term-stability ABI (3 years, rarely
touched) the cheap-now/expensive-after-it-is-solid fixes matter: the permission
vocabulary (enumerate the strings and define default-deny for unknowns), the
wall-clock deadline field, and additive-only growth (new variants ship
alongside, never replacing). Draft the decision doc + get sign-off, THEN encode
it in the target language. Writing the solid contract ad hoc hardens undeclared
choices outright.

## Core principle: core defines reality, workers adapt

The runtime's vocabulary is its own and never changes. It knows `task_id`,
`attempt_id`, `worker_id`, `workspace_id`, `checkpoint_id`, `lease_id` — and
NEVER learns what a "Pi session" or "Claude conversation" is. Workers, models,
and agent frameworks are disposable adapters plugged in behind a solid
contract. A three-year-old worker must still connect.

## Core principle: the governance IS the trust layer — give it covenant vocabulary

The governance/policy engine is not plumbing; it is the product, and it earns
its own **covenant-toned vocabulary** that a non-technical business owner can
read at a glance. Luke iterates on this vocabulary directly and cares deeply
about the words — expect him to veto and rename terms, and drive each rename to
its settled form rather than defending a proposal. Established (settled) set:
**Constitution** = the solid core / supreme law everything runs inside;
**Covenant** = the bond of trust (the core is that trust *written as law*);
**Charter** = the rules you set; **Mandate** = one job's orders;
**Steward** = the human (cares for + is answerable for the system — chose over
"Guardian" because a guardian watches, a steward owns the call);
**Agent** / **Worker** = governed actor / clinical motor, both swappable;
**Ledger** = the unchangeable record. Keep universal industry words (Agent,
Task, Budget, Audit, Retry, Timeout) as-is for coherence; only novel
components get covenant-toned names. Register preference: the user dislikes
"frozen" (too cold/brittle) — use **solid / bedrock / foundation** instead.

The distinct governance principles this layer encodes (trust tiers, the
evidence-Ledger, dry-runs, emergency stop, keep-alive duty, willful-breach
definition, trusted latitude, prison-vs-freedom framing, model reputation +
operational-intelligence, Steward levers pinned per run, the Operator role, the
the Expert Evaluator, calibrated/compensatory validation, the blind-trust ladder,
the impression axis + de-listing, evaluation-baked-in) — plus the settled
language/mechanics decisions (wire-contract-as-governance-language, brutal
token-efficiency, fleet-replicated hash-chain ledger) and the trust foundation
(biblical covenant tradition + psychology: error-vs-betrayal = competence-vs-
integrity, the exact restore-vs-permanently-withhold criteria, forgiveness ≠
trust) — are captured in `references/governance-trust-principles.md` — read that
before authoring any governance/covenant doc.

**Always-on rule: settle every declared guarantee into a TESTED mechanism.**
When the covenant promises a safety/trust property (tamper-evidence, trusted dry
run, sovereign stop, no hidden pair, un-foolable observer), it is NOT done until
the declaration is a concrete, mechanically-enforced mechanism WITH a
conformance test — "settled in intent, open in mechanism" is the honest posture
until then. Prefer arithmetic over a new actor (a deterministic fold, a hash
match, an OS signal + sandbox) — the anti-bloat and the anti-recursion move in
one. Each of the S1.1–S1.5 showstoppers closes this exact way; see the reference
for the five patterns.

## The rules (always apply)

1. **Settle the contract, keep it tiny.** A worker contract (Task shape + a small
   event union + a small op union) that is versioned and never broken; new
   shapes are added alongside old ones, never replacing them. Model the
   handshake on a `PROTOCOL_VERSION` constant + `hello` exchange + strict
   schemas (`additionalProperties: false`). ~a dozen events and ~half a dozen
   ops is plenty; a 300-method framework violates the point.

2. **Vendor the loop, skip the lifecycle.** The agent loop is one `while`
   statement: stream → extract tool calls → execute (sequential or parallel) →
   append results → repeat, with steering/follow-up queues and
   before/after-tool hooks. Copy its shape; do NOT inherit the upstream's
   release cadence. Make a *maintenance* fork (security patches by default, bug
   fixes need regression tests, provider updates cherry-picked one at a time).
   A broken worker is a degraded worker class, never a core upgrade — version
   components independently (`core 1.x` never breaks; `worker-pi 1.9` drifts
   freely).

3. **Atomic durable state.** Every state write: write temp → `fsync` → atomic
   `rename` → `fsync` directory, guarded by a token-checked O_EXCL lock file. A
   kill or ENOSPC leaves an old or new complete snapshot, never a torn file.
   Validate every read/write against a versioned schema.

4. **Plan is the context.** Decompose the objective into a structured, tracked
   plan (a typed tool with per-step status), then hand each worker only the plan
   status + its one step — never the transcript, never the full history. The
   plan is the shared memory. Enforce context budgets: truncate tool output
   (`max_observe`), cap turns (`max_steps`), detect duplicate turns and inject a
   strategy-change signal.

5. **Failures are states, not crashes.** Token-limit is a terminal `FAILED`
   state; tool errors become tool-result messages; state transitions are guarded
   (IDLE→RUNNING→FINISHED/ERROR, revert on exception). The adapter contract
   never throws — it encodes failure in a result event.

6. **Reproduce to the byte.** Immutable workers (a running agent never mutates
   its own runtime — it files a `runtime_issue` and engineering ships a new
   image); pinned deps + lockfile-as-truth + container digest + pinned runtime
   version; one-way promotion (`develop → soak → candidate → fleet → stable`);
   stable receives security/data-loss/severe-compat fixes only.

## Research method — steal the pattern, not the project

To learn from an upstream agent framework, shallow-clone it
(`git clone --depth 1`) and read the small set of files that define its shape:
the agent loop, the protocol/types file, the state store, the provider
abstraction. The value is in the loop's structure, the event vocabulary, the
tool contract, and the store's failure handling — not the README summary. Then
list steal-vs-skip and prove the pattern in a minimal runnable scaffold before
committing to it.

## Designing the hooks for foreign harnesses / coding agents — ground it first

When the question is *"where do other harnesses/coding agents plug in?"*,
shallow-clone the real top contenders and read the actual integration surface
before drawing the seam — do NOT brief the adapter design on README summaries or
your prior knowledge of an agent. The grounded payoff is real and recurring:
research across ~17 harnesses collapses to **virtually every serious coding
agent is a DELEGATED CLI with a headless `-p`/`exec`/`run` mode + an MCP seam +
a per-family provider adapter** — so the whole market needs **TWO reusable
seams** (one sandboxed delegated-CLI adapter + one MCP seam), not a bespoke
adapter per harness. Verify a harness is still maintained before building its
adapter (the landscape is volatile: Windsurf→Devin, Roo Code shut down,
Continue frozen). Full grounded table in
`references/adapter-layer.md`; the stale-doc-authoring discipline in *Pitfalls*.

## Consolidating a design that has grown — see `references/adversarial-consolidation.md`

When the covenant/spec has accumulated many later principles, consolidate it
with a delegator party (consolidator + adversarial reviewer), land the reviewer's
S1/S2/S3 findings as a tracked open design ledger, and hook the spec's
Acceptance to it ("settled in intent, open in mechanism"). Full procedure +
pitfalls in that reference.

## Pitfalls

- **Don't adopt the framework to get its loop.** If upstream permits breaking
  API changes in minor releases or is evolving fast, you inherit their bugs and
  their redesigns. The loop is ~800 lines worth vendoring; the release lifecycle
  is not worth one dependency.
- **Verify a requested design feature against the existing system BEFORE adding it — "don't just do it because I want it."** When the user suggests a capability (e.g. a per-model configuration bundle), do NOT reflexively add it. Overlap-check the proposal against the concepts already defined — map each existing concept to it and confirm it is *complementary* (new granularity / lifecycle / axis) rather than *redundant* (already covered by, e.g., PromptState+inject_prompt, Charter/levers, Reputation-permutation). Then state the safety invariants that keep it bounded and write them into the doc verbatim (e.g. a Model Profile *configures, never grants* — authority stays in the Charter/Mandate/Gate — and it is NOT an MCP-Gate bypass: listing a server doesn't unlock it, availability ≠ allowance). The user values a coherent design where every addition justifies itself against what is already settled, not one that grows because a feature was requested.
- **Don't turn a small suggestion into a product-wide declaration.** When the
  user makes a narrow call ("you don't have to declare the core is the
  product"), apply the SMALLEST edit that honors it — undo the specific
  emphasis and leave the rest. Do not react by retitling sections, adding
  motto/priority tables, or propagating the correction through every doc. "Just
  because I suggest something, you don't have to go and change everything and
  come up with some motto." Default to the minimal, surgical change; the user
  values keeping the docs unstuffed even when the principle in question
  matters.
- **A settled contract is not the same as settled API semantics.** Solidifying the field
  (`Task.permissions: string[]`) without pinning the vocabulary means 2026
  cores and 2029 workers disagree on what `"git"` or `"fs.write"` mean.
  Enumerate the permission strings + define unknown-strings-default-deny as part
  of the contract, or the stability is hollow.
- **Plan state must be durable.** A plan tracked in a process-local dict is lost
  on crash and cannot resume. Route plan state through the atomic store, never a
  process-local structure.
- **Tool output must be bounded.** An unbounded `grep`/`cat` result floods the
  context window and degrades the model. Truncate every tool result to a fixed
  budget before it enters context — this is a worker-layer concern, never an
  ABI change.
- **Don't pick a language by the developer vibe — trace the hot path.** For an
  I/O-bound agent harness (LLM API, tool subprocess, DB WAL) ~99% of wall-clock
  is network/subprocess/fsync — language-agnostic. Native performance is rarely
  load-bearing; the real axes are (a) cross-platform distribution story (TS/Bun
  compiles to a per-platform binary with double-click simplicity; Python's
  packaging is the weakest), (b) one language on the modifiable layer, (c) typed
  contracts for swappable seams. A Rust *black-box core* is defensible for
  memory-safety + static-binary + a solid no-bypass guarantee, but then the
  modifiable layer (worker, UI, config) should be the readable single language.
- **Push back on a pure-TS recommendation if a runtime-free frozen binary is
  load-bearing.** A party will often land "single language for simplicity"; if
  the enterprise requires a reproducible binary that provably sits unchanged (no
  runtime churn), keep that as the narrower trigger for a Rust core.
- **Before writing the solid core, do a build-readiness pass — the contract must
  be settled at the LEVEL the code is written against.** "Settled in intent" is
  not settled enough to open an editor. Verify there is ONE canonical contract
  (a single ABI/wire shape the corpus agrees on) — a spec that accumulated
  several competing wire/enum/schema descriptions is not ready even though each
  one reads coherently. Verify the code you're told to reconcile ACTUALLY exists
  — a review that "reconciles `core/src/abi.rs`" with the prototype is
  misleading if no such file exists (the real state is usually simpler and
  worse: one wrong-shape artifact to replace, not two to reconcile). Pin, in
  order, before code: the canonical ABI, the DB schema, the crypto (separate
  integrity from authenticity — do NOT use HMAC-as-hash with a fleet-shared
  verification key as "tamper evidence", because any peer that can verify can
  also forge; use an unkeyed hash chain + asymmetric signed checkpoints), the
  trust-root key lifecycle, and the platform/sandbox matrix. Enumerate these as
  "must-decide-before-code" items dated to the build, not left as open prose.
  Do an adversarial reviewer pass (not just the content author) before coding;
  it surfaces the phantom-artifact and competing-contract issues the author is
  blind to.
- **Don't name the contract after what the TUI is, and keep "interface" and
  "wire" distinct.** The wire/ABI is the core↔worker seam; the Core Interface is
  the core↔surface seam (any TUI). They are different contracts with different
  consumers — do not blur them into one "the interface".

## Pitfalls (doc & communication)

- **Grep existing section numbers before appending a numbered section to a
  grown spec.** A doc that already has a near-identical header (e.g. an existing
  `## 8. Honest bounds` when you append a new `## 8. The adapter layer`) silently
  collides and both render as duplicates. List the existing `^## ` headers
  first and assign the next free number — never assume your new section is
  unnumbered. Fix in place by renumbering yours, not by moving the established
  one.
- **When the user asks to read a large design doc in chat (Telegram etc.),
  render a faithful *essence* — do not dump the raw file.** A 100KB+ spec cannot
  be pasted whole into a message (truncation, unreadable). Deliver the
  document's essence organized by its own structure, offer the archive/repo
  path for the full detail, and chunk remaining sections across messages only
  when the user asks. Signal that you omitted the full text so they know where
  the fidelity boundary is.

## References

- `references/reference-implementations.md` — what Pi, OpenSwarm, OpenManus, and FrontierAgent each contribute and what to skip, the files to read, and the concrete context-budget levers (adds the inference-aware core: real-token-gauge compaction trigger, tiered compaction, reasoning-runaway detection, SpawnGuard/WallClockGuard bounded parallelism)
- `references/governance-trust-principles.md` — the trust-layer principles (trust stack, willful breach, trust tiers/latitude, model library, levers, Operator) — read before authoring any governance/covenant doc
- `references/adversarial-consolidation.md` — consolidating a grown design: consolidator + adversarial-reviewer party, gap ledger, "settled in intent, open in mechanism" acceptance
- `references/adversarial-loop-and-interface.md` — the leveled in-loop adversarial reviewer (L0–L3), its budget-aware loop (bounded decaying retries, failure-classed stop, honest `UNENDORSED`/`UNDECIDABLE` exits), loop-budget-as-reputation, and the Core Interface surface contract (ACP + granular data + drive verbs + authority model; the interface is the moat, not the TUI)
- `references/adapter-layer.md` — grounded (2026-09-11): how foreign coding agents/harnesses hook in — every agent is a delegated CLI with `-p`/`exec`/`run` + MCP seam, collapsing to TWO reusable seams (sandboxed delegated-CLI + MCP); per-family provider-adapter pattern; market-reality notes (Windsurf→Devin, Roo Code down, Continue frozen). Read before designing any adapter/hook layer.

# QA — Testability & Quality Critique of the Reference Architecture

> Role: QA in the architecture party. Target: `docs/party/architect.md` (primary),
> cross-read against `README.md`, `docs/design-brief.md`, `docs/party/elicit.md`,
> `docs/party/domain.md`, and the live code (`src/abi.ts`, `src/loop.ts`,
> `src/store.ts`, `src/adapter.ts`, `test/loop.test.ts` — 3 passing bun tests).
> Late-added scope (owner, mid-party): a 6th surface (model/cache-aware
> **prompt engine**) and a 7th surface (**offline-cache + pluggable RAG**),
> plus five cross-cutting QA concerns (MCP trust, duplicate-action safety,
> plugin HITL, audit tamper-evidence, replay) — covered in §5.6–§5.12 — and
> two further additions: **prompt/context templatization** (per-model system
> prompts, templatized skills/AGENTS.md — §5.13) and an **event-journal
> visualizer/drill-in** (§5.14).
>
> QA's framing: this architecture's central promises are **negative claims**
> ("the core never breaks for 3 years", "no worker is privileged", "a plugin
> cannot corrupt the store") and **temporal claims** ("a 2026 plugin loads in
> 2029"). Negative and temporal claims are exactly the claims a normal test
> suite is worst at. Everything below is about converting them into things CI
> can actually fail on.

---

## 1. How do we verify correctness — and what's hard to test

### What the architecture gets RIGHT for testability (credit where due)

- **One chokepoint.** All tool execution flows through `core/gateway.ts`
  (registry → permission → schema → execute → truncate → audit). One seam to
  test exhaustively instead of N tools × N policies scattered.
- **Pure folds.** `timeline(events)`, `costs(events, prices)`, and F-507's
  "status is a pure function of (store, journal)" are deterministic
  input→output functions. Cheapest, strongest tests in the whole system.
- **Deterministic fake adapter already exists.** `FakeAdapter` means worker
  behavior is scriptable end-to-end with zero network. This is the backbone of
  every integration test.
- **Tiny frozen surface.** 11 events + 6 operations + `Task`/`TaskOutcome` is
  small enough to enumerate exhaustively in a conformance suite — a
  300-method framework would not be.
- **Event journal as source of truth.** Every test can assert against the
  NDJSON journal instead of poking internal state; the observable IS the
  contract.
- **TUI quarantine.** Core builds/tests with zero TUI deps; F-106 headless
  parity means every TUI fact has a CLI-testable equivalent. We can (and
  should) test almost nothing through Ink rendering.

### What is genuinely HARD to test

1. **The 3-year behavioral freeze.** Types can be frozen with a compat suite;
   *behavior* (event ordering, nullability, truncation footer shape, error
   shapes — domain.md §5.3 names these) drifts silently. The only defense is
   pinned golden fixtures recorded *at freeze time* and replayed forever. If
   the fixtures are written after code churns, they enshrine drift instead of
   detecting it.
2. **The neutrality claim ("no worker is privileged").** This is a claim about
   what the core *doesn't* do. A green test suite with only `own-agent`
   installed proves nothing — own-agent passing through a door it secretly
   widened looks identical to a fair door. Only a *second, foreign* worker
   makes the claim falsifiable (elicit F-209 already demands this; it must be
   a gate, not an aspiration).
3. **Crash-window semantics (F-409 replay policy).** "A `replay:"never"` tool
   interrupted after execution but before result persistence is NOT re-run" —
   testing this requires deterministic fault injection at specific points in
   the gateway/store write path. There is no injection seam in the current
   design. `store.ts`'s fsync/rename discipline has the same problem: torn
   files, stale locks, ENOSPC are cited from OpenSwarm's comments but nothing
   in this repo can *induce* them.
4. **Concurrency.** Parallel `executionMode`, mixed sequential/parallel
   batches (F-408), lease expiry racing task completion, two supervisors on
   one store. Bun tests will happily pass 999/1000 runs of a racy scheduler.
5. **The "six tools = 90%" claim.** Untestable without a task corpus; it's a
   product benchmark, not a unit test (architect §7.4 concedes this).
6. **Cost accounting.** `loop.ts` (line ~55 per elicit F-503) hardcodes zero
   usage — every cost test written today asserts against a stub. F-503's
   "matches to the cent" acceptance cannot be exercised until usage plumbing
   lands.
7. **In-process plugin fault isolation.** "A throwing panel/sink can never
   lose a journal event or take down the loop" is testable per-callback, but
   the *class* of faults (infinite loop in a sink, sync fs call blocking the
   event loop, memory growth) is not catchable by try/catch tests. In-process
   = we test the mistakes we imagined.
8. **Ink/React panels.** Render-output testing is brittle and low-value. The
   architecture correctly makes this unnecessary — we must *hold that line*
   (test the fold that feeds the panel; one smoke test that panels mount).
9. **Provider cache behavior (new 6th surface).** Prompt-cache hits are
   provider-specific, time-dependent (TTL-based eviction), and invisible
   except through billing/usage fields. **The hardest thing in the system to
   test correctly** — a test cannot observe a hit/miss directly, only what
   the provider reports after the fact. Strategy: never test the provider;
   test our *preconditions for cacheability* (byte-stable prefix) and our
   *accounting of what the provider reported* (§5.6).
10. **Retrieval quality (new 7th surface).** RAG ranking is probabilistic —
    embedding models, ANN indexes, and score ties make "the right document
    came back" non-deterministic across backends and versions. Strategy:
    separate the *plumbing* (deterministic, port/adapter seam) from the
    *quality* (corpus benchmark, thresholded not exact) — §5.7.

---

## 2. Testability score: **7 / 10**

**Rationale.** The bones are excellent: single gateway chokepoint, pure
derived views, a scriptable fake adapter, a small enumerable ABI, journal
as observable truth, and the TUI walled off from the tested surface. Very few
architectures make their central invariant (worker-neutrality) *mechanically
checkable* — this one does, via the trivial-second-worker fixture and the
import-boundary grep. That's 9/10 material.

Three points off because: (a) the two design docs ship **two conflicting
worker-plugin contracts** (architect's `WorkerSpec.handle(op, emit)` vs
domain's `WorkerFactory.start(task, ctx) → WorkerHandle`) — you cannot write
the ABI conformance suite until there is exactly one door (SHOWSTOPPER S1);
(b) the plan moves the only tested module (`loop.ts`, 2 of the 3 existing
tests) *out* of core with no stated test-migration step, so the "frozen core"
would momentarily be the least-tested code in the repo (S2); (c) crash-window
and durability claims have no fault-injection seams, so the store's and
gateway's hardest promises are currently assert-by-vibes (S4). The two new
surfaces (prompt engine, RAG) don't change the score — both are testable *if*
they are built as pure functions behind port/adapter seams (§5.6–5.7), and
untestable if they aren't; that is a design constraint this critique imposes,
not a property the architecture already has.

---

## 3. SHOWSTOPPERS

**S1 — Two worker APIs, zero conformance targets.**
`architect.md §2c` defines `WorkerSpec { worker_id, abiVersion, handle(op,
emit) }` (one function, ops in / events out — transport-shaped, matching
Q-205's "more neutral" option). `domain.md §1.3` defines `WorkerFactory {
workerType, start(task, ctx) → WorkerHandle }` with `ctx.tools`,
`ctx.adapter`, and a method-per-operation handle. These are not the same
contract; they differ on *who provides tools/adapter to the worker* (core-fed
context vs worker-acquired) and on operation dispatch. The ABI conformance
suite — the single most important test artifact in this project — cannot be
written against both. **Freezing either one without the suite existing first
means the first foreign worker discovers the door was shaped like own-agent.**

**S2 — The core loses its tests on day one of the reorg.**
`src/loop.ts` carries 2 of the 3 existing tests. The plan moves it to
`workers/own-agent/loop.ts` (architect §0; §7.2 acknowledges the risk). After
the `src/`→`core/` rename, the frozen 3-year-committed directory contains
`store.ts` (1 test) and roughly eight brand-new untested modules (events,
eventlog, tool, gateway, config, plugin-host, supervisor, template, daemon).
A freeze declared on untested code is a freeze of unknown behavior. **No
rename until every `core/*.ts` module has its contract tests, and the loop
tests demonstrably move with the loop.**

**S3 — "Additive-only" has no enforcement mechanism.**
The behavioral-freeze rule (domain §5.3) is stated but nothing fails when
violated. Without a pinned `plugin-api-compat` suite recording *today's*
observable behavior (event order, envelope key order, truncation-marker text,
error result shapes), an innocent refactor in 2027 changes event ordering,
every existing test still passes, and the 2026 fixture plugin breaks in
production in 2029. The compat suite must exist **before** v1 is declared
frozen — it is what defines "v1 behavior" at all.

**S4 — F-409 replay-on-recovery is untestable as specified.**
"Interrupted after execution but before result persistence" requires the
gateway/store to expose deterministic crash points — or a journaling design
where the recovery decision is a pure function of journal contents. Neither
doc specifies the persistence ordering (result write vs `TOOL_FINISHED`
append vs checkpoint). Until the ordering is specified, the recovery test
cannot be written, and an unwritable test on a data-loss path is a
showstopper for a harness whose pitch is "boring and crash-safe." (The
exactly-once fixture in §5.9 is the concrete form this test must take.)

**S5 — Permission vocabulary (Q-405) is de-facto ABI and still open.**
The gateway permission matrix (the highest-value security test in the system)
cannot be pinned while `"fs.read"` vs `"read"` vs `"git_write"` is undecided.
Architect's tools table already uses `fs.read`/`fs.write`/`shell`/`git`;
elicit leaves it open. Freeze the enum before `gateway.ts` tests are written,
or every permission test becomes a change-detector when the strings settle.

**S6 — (new surfaces) prompt engine and RAG must be pure-core + adapter, or
they are untestable.** If prompt assembly reads the clock, environment, or a
live tokenizer service, byte-stability (§5.6) cannot be asserted. If the RAG
layer's retrieval interface isn't a frozen port with an in-memory test
adapter, every enterprise backend swap is untested by construction (§5.7).
This is a design requirement, stated here so the architect bakes it in rather
than QA discovering it after freeze.

---

## 4. Mitigations

- **S1:** Owner decides Q-205 *now*. QA recommendation: the **transport-shaped
  `WorkerSpec.handle(op, emit)`** (architect's version) — it is the more
  neutral contract (a future out-of-process Pi worker is just NDJSON-on-stdio
  behind `handle`), and it makes the conformance suite a pure
  function-of-messages test with no mock `ctx` to keep honest. Domain's
  `WorkerContext` conveniences (gateway handle, resolved adapter) become
  core-provided facilities the worker plugin obtains at registration, not a
  second dispatch API. Whichever wins: delete the loser from the docs and
  land `abi-conformance.test.ts` in the same PR that defines the type.
- **S2:** Test migration is a named step in the reorg PR checklist:
  (1) `workers/own-agent/test/loop.test.ts` = moved tests 1–2, still green;
  (2) `test/core/store.test.ts` = moved test 3 + growth (§5.5); (3) CI fails
  if `core/` line coverage drops below the pre-rename baseline; (4) the rename
  PR includes the conformance suite so core never has fewer contract tests
  than the day the freeze started.
- **S3:** Record golden transcripts *now* against the current scaffold
  (FakeAdapter task → full journal), commit them as
  `test/fixtures/golden/*.ndjson`, and make `plugin-api-compat.test.ts`
  replay them on every core change (§5.2). Additive changes append to goldens;
  they never edit them — an edited golden line in a diff is the review signal
  that a behavioral break is being attempted.
- **S4:** Specify the persistence order as part of Tool Contract v1:
  *journal `TOOL_STARTED` (fsync) → execute → journal `TOOL_FINISHED` +
  result hash (fsync) → return to worker.* Recovery then becomes a pure rule:
  "STARTED without FINISHED + `replay:"never"` → surface recorded absence to
  the model; `replay:"safe"` → re-run." Best mitigation: make recovery a pure
  function of the journal — then the test needs no injection seam at all,
  just hand-crafted journals. Failing that, a test-only `onBeforePersist`
  hook in the gateway. §5.9 specifies the exactly-once proof fixture.
- **S5:** Enumerate the permission strings in `core/tool.ts` as a closed union
  (`"fs.read" | "fs.write" | "shell" | "git" | "net"`), freeze it with the
  contract, and *generate* the gateway permission-matrix test from the union
  (every tool × every permission subset) so the matrix can never silently
  miss a new tool.
- **S6:** Constrain both new surfaces at design time: prompt assembly is a
  pure function `(templates, task, model_profile, history) → PromptPlan`
  with tokenizers as injected data (pinned vocab fixtures), and RAG is a
  frozen `Retriever` port with the in-memory reference adapter shipped as
  both test double and conformance target (§5.6, §5.7).
- **Hard-to-test #4 (concurrency):** scheduler/lease tests loop 100 iterations
  in a nightly CI job (not per-PR); store tests include a real two-process
  lease-contention test (spawn a child contending for the token lock).
- **Hard-to-test #6 (cost):** plumb optional `usage` into `AssistantTurn`
  (elicit F-503, additive) before writing `costs.test.ts`; until then the
  cost fold is tested against synthetic `MODEL_REQUEST_FINISHED` events only,
  and the suite carries an explicitly-skipped test named
  `costs from real adapter usage (BLOCKED: F-503 plumbing)` so the gap is
  visible in every run rather than forgotten.

---

## 5. The concrete test strategy

### 5.0 The test pyramid for the core

```
        e2e (2–3 tests)         test/e2e/task-lifecycle.test.ts
      ───────────────────       full daemon: config → plugin load → task →
                                 journal → outcome; FakeAdapter only
     contract / conformance     abi-conformance, plugin-api-compat,
    (the load-bearing band)      gateway permission matrix, journal format,
   ─────────────────────────     retriever-port conformance, audit integrity
  unit: pure functions          store atomicity, folds (timeline/costs/status),
 (widest, fastest)               template resolution, config validation,
                                 prompt assembly, prefix stability, truncation
```

The TUI gets **no pyramid slot** beyond one smoke test (mounts against a
fixture event file without throwing) — headless parity (F-106) means every
TUI fact is asserted via its CLI/fold equivalent instead.

### 5.1 ABI conformance suite — every worker through the same door

**`test/conformance/abi-conformance.test.ts`** — a suite *parameterized over
a worker registration*, exported as a function any worker package can import:

```ts
export function abiConformance(name: string, makeWorker: () => WorkerSpec) { … }
```

Run in core CI against **two** workers:

- `workers/own-agent/` — the real agent, with FakeAdapter injected via plugin
  config.
- **`test/fixtures/worker-trivial/`** — a ~50-line scripted fake plugin
  (`plugin.json` + `index.ts`): on `start` it emits `WORKER_STARTED`, one
  scripted `TOOL_REQUESTED` → (through the gateway) → `TOOL_FINISHED`, then
  `RESULT`; it honors `cancel`/`kill` by emitting `STOPPED`. Deliberately
  *not* an LLM loop — its only job is to prove the door has no
  own-agent-shaped notches.

What each conformance case proves:

| Case | Proves |
|---|---|
| `start` → events → exactly one terminal event (`RESULT`\|`FAILED`\|`STOPPED`) | lifecycle contract; no zombie attempts |
| no events after the terminal event | terminality is real; supervisor can free the lease |
| every emitted event validates against the frozen `WorkerEvent` schemas (`additionalProperties: false`) | a worker can only speak ABI vocabulary |
| all 6 operations accepted; unknown op rejected without crash | operation surface complete and closed |
| `kill` mid-run → `STOPPED` within timeout | supervisor can always reclaim |
| `cancel` mid-tool → terminal `STOPPED{reason}`; in-flight tool result discarded or surfaced, never lost silently | cooperative shutdown path |
| worker exceeding `budget.max_turns` → terminal state, not a hang (core kills what the worker won't stop) | belt-and-suspenders budget enforcement |
| events carry no extra envelope fields; core stamps `task_id`/`attempt_id`/`worker_id` | a worker tells only its own story (domain §1.3) |
| **the identical suite passes for `worker-trivial`** | **neutrality — the F-209 gate** |

**CI job `neutrality`** (separate, named, required): runs with
`plugins.allow = ["worker-trivial"]` (own-agent absent), executes one task
end-to-end, asserts green, **and** asserts
`grep -rE "own-agent|own_agent" core/` is empty and `core/` has zero imports
resolving outside `core/` (US-200 acceptance + architect's rule 2,
mechanized). **This job is the one thing that catches the "agent re-acquires
privileged status" regression** — architect.md's own named single biggest
risk: the moment core code imports from `workers/` or grows a field only
own-agent needs, either the grep fails or worker-trivial stops passing the
identical suite.

### 5.2 plugin-api-compat regression suite

**`test/compat/plugin-api-compat.test.ts`** + **`test/fixtures/frozen-2026/`**
— fixtures committed at freeze time and *never edited* (additions only):

- `frozen-2026/worker-min/` — a copy of worker-trivial, frozen forever.
- `frozen-2026/tool-echo/` — one tool plugin (schema + execute).
- `frozen-2026/panel-hello/`, `frozen-2026/sink-count/` — panel + event sink.
- `frozen-2026/templates-pack/` — one replace override + one anchored patch.
- `frozen-2026/harness.jsonc` — a full config file.
- `frozen-2026/journal.ndjson` — a real recorded task journal.
- `frozen-2026/golden/*.ndjson` — golden event transcripts (FakeAdapter task;
  seq- and ts-normalized) capturing **event order**, envelope **key order**,
  truncation-marker text, and error result shapes.

What each case proves:

| Case | Proves |
|---|---|
| every frozen plugin loads unmodified, registers, and executes its capability | US-202: a 2026 plugin runs on today's core |
| a fixture declaring `hostApiVersion: 2` is refused with the actionable one-line message | version refusal is fail-closed and humane |
| golden replay: today's run of the same scripted task reproduces the goldens (order-sensitive) | the **behavioral** freeze — domain §5.3's killer (event reordering, changed defaults, changed footers) fails here and nowhere else |
| 2026 `journal.ndjson` parses; an injected unknown event type is ignored with a warning, never a crash | NF-501 forward-compat; "consumers ignore unknown types" is tested, not documented |
| 2026 `harness.jsonc` validates against today's schema | config additive-only |
| truncation footer / permission-denial message text unchanged | tool-result strings are contract (models pattern-match on them) |

Rule that keeps this honest: **goldens are append-only; a PR that edits a
golden line is by definition a breaking change** and needs explicit owner
sign-off — the diff itself is the alarm.

### 5.3 Mutation-testing gate — gateway and store only

The two modules where a silently-wrong line is a security hole or data loss:
`core/gateway.ts` (permission check, truncation, workspace confinement) and
`core/store.ts` (fsync/rename/lock). Line coverage lies about these —
`if (permitted)` flipped to `if (true)` passes a coverage-only suite.

- Tooling: **StrykerJS** with `stryker.conf.json` `mutate:
  ["core/gateway.ts", "core/store.ts"]`, running the targeted tests via the
  command runner (`bun test test/core/gateway.test.ts
  test/core/store.test.ts`). Caveat: Stryker's bun support is immature — if
  it proves flaky, a ~100-line in-repo mutator (flip comparisons, negate
  conditions, delete fsync calls, swap atomic-rename for plain write) is
  acceptable. The *gate* matters, not the brand.
- Threshold: **mutation score ≥ 85%** on those two files; surviving mutants
  listed in CI output. Run on PRs touching
  `core/{gateway,store,tool}.ts` and nightly — not on every PR (runtime).
- What it proves: the permission matrix actually *bites* (a deleted
  permission check kills a mutant); truncation boundaries are asserted at the
  exact budget (off-by-one mutants die); the store tests notice a removed
  `fsync`/rename (which forces the torn-file tests of §5.5 to be real —
  mutation testing is the enforcement that they exist).

### 5.4 The TDD Iron Law for `core/`

**No diff to `core/` merges without a test that failed before the diff.**
Enforced, not aspirational:

1. Every `core/` bugfix PR contains a test whose RED run is demonstrated
   before the fix (README stability rule 2 already requires regression tests
   — this operationalizes it). Reviewer checklist item; CI assists by failing
   any `core/` PR that changes zero `test/` lines.
2. New `core/` modules land *contract-tests-first*: the PR creating
   `core/gateway.ts` starts from `test/core/gateway.test.ts` written against
   the interface, watched failing, then implemented.
3. Coverage ratchet on `core/` only: CI stores the baseline; a PR may not
   lower it. No ratchet on `workers/`, `tui/`, `tools/` — peripherals may
   churn (that's the point). The Iron Law applies exactly where the 3-year
   promise applies.
4. Frozen means frozen: a PR touching a frozen contract file (`abi.ts`,
   `tool.ts`, `events.ts`, `plugin-host.ts` types) additionally requires the
   compat suite (§5.2) green **with unmodified goldens** — the Iron Law's
   test can never be "I updated the golden."

### 5.5 Growing the existing 3 tests — without becoming change-detectors

Disposition of the current tests:

- `runLoop` test 1 (tool call → complete) and test 2 (budget_exhausted):
  **move with the loop** to `workers/own-agent/test/loop.test.ts` — they test
  own-agent cognition, not core. They grow siblings there:
  stuck/duplicate-turn detection injects a strategy-change signal;
  token-limit → graceful `FAILED` (never a throw); `max_observe` applied to
  context assembly.
- store test 3: stays, as the seed of `test/core/store.test.ts`.

The growth map (file → what it proves):

| File | Proves |
|---|---|
| `test/core/store.test.ts` | atomic write survives kill (hand-write a torn temp file → read tolerates + warns); stale-lock takeover by token; ENOSPC surfaces as an error, not corruption; two-process lease contention (spawned child); property test (fast-check): any interleaving of `recordTask`/`recordOutcome` preserves read-back integrity |
| `test/core/gateway.test.ts` | permission matrix **generated** from the closed permission union × 6 built-ins — denial is a failed result *naming the missing permission*; schema-invalid args fail *before* execute runs; `max_observe` head+tail truncation at the exact boundary with original-size marker; per-tool timeout → `ok:false`, never a hang; workspace escape (`..`, absolute path, symlink) → failed result; tool-name collision → hard startup error; sequential/parallel batch ordering (F-408) |
| `test/core/events.test.ts` | seq strictly monotonic; replay-from-seq returns an identical prefix; a throwing sink is detached + counted while the journal is unaffected (US-503); `emit` never throws; unknown-event-type fuzz — consumers survive |
| `test/core/plugin-host.test.ts` | manifest schema refusal (unknown key, bad version) with the one-line actionable error; capability gating (a panel-only plugin has no `registerTool`); activation throw → prior registrations disposed, host fine; deterministic config-order loading; sha256 mismatch → skip + report |
| `test/core/config.test.ts` | unknown key = load error with JSON path + suggestion; effective-config provenance per key; only the sanctioned env vars are honored |
| `test/core/template.test.ts` | layer resolution order (project > user > plugin > builtin) with `which` provenance; render determinism (byte-identical — NF-304); unknown `{{var}}` warns + renders literal, never throws; anchored-patch append/replace; version-drift notice fires when core template moves past `core_version` |
| `test/core/supervisor.test.ts` | dispatch by `worker_id` only (supervisor source never names a worker — asserted by grep); lease expiry → retry or explicit `stalled?`, never a guess; core-side kill on budget when the worker misbehaves (uses worker-trivial configured to ignore `cancel`) |
| `test/core/costs.test.ts`, `test/core/timeline.test.ts` | pure folds over fixture journals; budget-cap identification (US-502: exactly 3 `MODEL_REQUEST_STARTED` under `max_turns: 3`, then `STOPPED{reason:"budget"}`) |
| `test/conformance/…`, `test/compat/…` | §5.1, §5.2 |
| `test/e2e/task-lifecycle.test.ts` | config → plugins load → `run --template bugfix` on a fixture repo → scripted FakeAdapter sequence (`search → read → edit → test-run → git commit`) → journal complete, outcome recorded, cost fold consistent (US-401 + US-501 in one) |

**The anti-change-detector rules** (how the suite stays useful for three
years instead of ossifying):

1. **Assert contracts, not transcripts — everywhere except §5.2.** Unit and
   conformance tests assert set membership, invariants, and terminal outcomes
   (`events contains TOOL_FINISHED{ok:false}`, "exactly one terminal event",
   `output.length ≤ max_observe`) — never full event sequences, never
   snapshot dumps. Exact-sequence assertions live **only** in the golden
   compat suite, where change-detection is the explicit job. One suite is
   *supposed* to break on any behavioral change; every other suite must
   survive refactors.
2. **One behavior, one test, named for the requirement.** `gateway denies
   fs.write when task lacks permission` survives refactors; a test named for
   an implementation detail dies with it.
3. **No mocking core-internal seams.** Tests drive real store + real gateway +
   FakeAdapter + fixture workspaces (NF-402). Mock only the process boundary
   (LLM, clock, fs-fault injection, embeddings). Internal mocks are how
   suites become mirrors of the implementation.
4. **Peripheral tests may churn or die.** `workers/own-agent` tests evolve
   with the agent; their failure is never treated as a core regression. The
   load-bearing band (conformance + compat + gateway/store + audit) is small
   (~12 files) precisely so it can be held to a much higher bar.

### 5.6 Prompt engine (6th surface) — cache-aware, per-model assembly

**Design precondition (from S6):** assembly is a pure function —
`assemble(templates, task, modelProfile, history) → PromptPlan` where
`PromptPlan = { prefix: string; suffix: string; prefixHash: string;
tokenEstimate: {prefix, suffix} }`. Tokenizers are injected as pinned data
(vendored vocab fixtures per model family), never fetched. Live provider
cache behavior is **out of scope for CI by decision** — we test our
preconditions and our accounting, not the provider's cache.

**`test/core/prompt-engine.test.ts`** — what each case proves:

| Case | Proves |
|---|---|
| **Prefix byte-stability**: `assemble()` called twice with the same task-stable inputs but different volatile inputs (new history turn, new tool result, different wall-clock) → `prefix` is byte-identical, `prefixHash` unchanged; only `suffix` differs | the cacheable prefix contains nothing volatile — the single precondition for any provider cache hit |
| **Volatility partition test**: for every documented prompt variable, an annotation `stable \| volatile`; a generated test flips each variable and asserts stable-flagged ones change the prefix hash NEVER and volatile ones change ONLY the suffix | new variables can't silently land in the wrong partition — the classic cache-invalidation regression (someone adds a timestamp to the system prompt) fails this test the day it's written |
| **Golden prefix hashes**: `test/fixtures/prompt/golden-prefixes.json` maps (template version, model profile) → prefixHash; assembly must reproduce them | an *unintentional* prefix change (reordered sections, whitespace churn from a refactor) is caught; an intentional one is an explicit golden update = visible cache-invalidation event in review, with the same append-only sign-off rule as §5.2 |
| **Per-model assembly via FakeAdapter model profiles**: fixture profiles (`fixture-anthropic-like`, `fixture-openai-like`, `fixture-local-like`) with different message shapes / system-prompt conventions; assemble the same task against each and assert against per-profile golden *structures* (role sequence, section presence), not full text | model-specific assembly is exercised with zero network; adding a real provider later means adding a profile fixture, not a live test |
| **Token budgeting is monotone + bounded**: property test — for any history, `tokenEstimate.prefix + suffix ≤ modelProfile.context_window − reserved`; growing history never grows the prefix estimate | budgeting can't overflow the window and can't destabilize the prefix |
| **Cache accounting fold**: `MODEL_REQUEST_FINISHED.usage` gains optional `cached_tokens`; a pure fold over fixture journals produces hit-rate and saved-cost reports; a synthetic journal with known cached/uncached mix must fold to exact known numbers | hit/miss *tracking* is deterministic bookkeeping even though hits themselves aren't; a prefixHash change mid-task must appear in the fold as an explicit `cache_invalidated` marker |

**Anti-change-detector rule for token counts:** never assert exact token
counts in unit tests — assert **relations** (≤ budget, prefix estimate
unchanged when suffix grows, estimate within ±10% of pinned tokenizer output
on fixture text). Exact counts live only in one golden file tied to the
pinned tokenizer fixture version; bumping the tokenizer fixture is an
explicit versioned event, not a test failure surprise. Regression that this
still catches: any change that alters the *prefix* (the thing that
invalidates provider caches) fails the prefixHash goldens even though no
token-count assertion exists.

**What we deliberately do NOT test in CI:** actual provider cache hits (TTL,
eviction, cross-request affinity). That is a **soak-stage check**: the
promotion pipeline (README rule 4) runs a scripted task twice against a real
provider and asserts `cached_tokens > 0` on the second run — an operational
gate, not a unit test, because time and provider state are inputs we don't
control.

### 5.7 Offline-cache + pluggable RAG (7th surface)

**Design precondition (from S6):** one frozen port —

```ts
// core/retriever.ts — Retriever Port v1
interface Retriever {
  index(docs: Doc[]): Promise<IndexInfo>;          // IndexInfo = {doc_count, index_hash, built_at}
  query(q: string, k: number): Promise<Hit[]>;     // Hit = {doc_id, score, chunk}
  status(): Promise<"cold" | "warm" | "stale">;    // stale = corpus hash ≠ index hash
}
```

Embeddings are behind the port; the core never sees a vector. Ship
**`test/fixtures/retriever-memory/`** — a deterministic in-memory reference
adapter (plain lexical scoring, stable tie-break by `doc_id`) that is both
the test double and the conformance target enterprises run against their
backend.

**`test/conformance/retriever-port.test.ts`** — parameterized like §5.1
(`retrieverConformance(name, makeRetriever)`), run in CI against
`retriever-memory`, runnable by any enterprise against their adapter:

| Case | Proves |
|---|---|
| `index()` then `query()` returns k hits, each `doc_id` exists in the corpus, scores non-increasing | plumbing contract every backend must meet |
| **golden query/answer fixtures** (`test/fixtures/rag/corpus/` ~30 small docs + `queries.json`: query → set of acceptable doc_ids): asserted as **top-k contains at least one acceptable doc_id**, never as exact ranking or exact scores | retrieval correctness without pinning a ranking — exact-order assertions are the change-detector trap; "the right doc is present in k" survives backend and model swaps |
| query before index → typed `cold` error or empty-with-status, never a crash | **cold path** |
| index → query → assert; re-query without re-index → identical results | **warm path** determinism (a warm cache returns the same answer twice) |
| mutate a corpus doc without re-indexing → `status() === "stale"`; querying stale is *allowed* but the journal event for the retrieval carries `index_state: "stale"` | **stale detection** is explicit and audited, never silent — the fork-and-forget failure mode (domain §5.2) applied to indexes |
| adapter throwing/hanging → gateway-style timeout → failed tool result; task continues degraded (RAG unavailable ≠ task crash) | enterprise backend failure is isolated like any tool failure |
| unknown extra fields on `Hit` tolerated; missing required fields refused at registration | additive-only port discipline, same as ABI |

**Offline determinism:** everything above runs with no network and no
embedding model — the reference adapter is lexical; real embedding adapters
are conformance-tested by their owners with the same suite plus their own
pinned model. **Never commit embedding vectors as fixtures** — they change
with every model rev and make every test a change-detector; commit *acceptable
answer sets* instead.

**Quality vs plumbing split (the anti-change-detector rule here):** CI tests
plumbing (above). Retrieval *quality* (recall@k on a real corpus with a real
embedding backend) is a thresholded nightly benchmark
(`bench/rag-recall.test.ts`, `recall@5 ≥ 0.8` on the fixture query set) —
threshold failures alert, they don't block PRs; exact-score assertions are
banned.

### 5.8 MCP as untrusted tool source

The claim under test: an MCP-provided tool is wrapped into Tool Contract v1
at the boundary (architect §2a Lane A) and therefore passes through the
**identical** gateway gate as a built-in.

**`test/core/mcp-bridge.test.ts`** — fixture: `test/fixtures/mcp-fake/`, a
~80-line stdio process speaking just enough MCP to register tools; scriptable
to misbehave (hang, garbage schema, oversized output, extra fields).

| Case | Proves |
|---|---|
| **same-door test (generated)**: the entire §5.5 gateway matrix (permission denial naming the permission, schema-invalid args rejected pre-execute, `max_observe` truncation, timeout → `ok:false`, workspace confinement) is *parameterized over tool source* and run twice — once with built-in `read`, once with the same behavior via `mcp-fake` | an MCP tool cannot skip any gate a built-in passes through; if the wrapper grows a bypass, the shared matrix fails on the MCP leg |
| MCP tool with no declared permission → registration refused (deny-by-default), not defaulted to permitted | untrusted source cannot self-grant |
| `replay` defaults to `"never"` for MCP tools; wrapper stamps `toolApiVersion: 1` | conservative defaults are tested, not documented |
| **hung server**: `mcp-fake --hang` during execute → per-tool timeout fires → failed tool result; task proceeds; other tools (built-in and other MCP servers) unaffected; second hang → server marked unhealthy in journal | isolation — one bad MCP server degrades its own tools only |
| server dies mid-task → in-flight call = failed result; reconnect policy exercised; no gateway crash | process-boundary fault tolerance |
| MCP tool result with extra/hostile fields (huge strings, control chars, fake `evidence` paths outside workspace) → sanitized/truncated before entering messages; evidence paths validated against workspace | tool *results* are untrusted input too |

### 5.9 Duplicate-action safety — exactly-once at the effect level

This is S4 made concrete. Fixture: **`test/fixtures/effect-counter/`** — a
tool whose `execute` appends a line to `effects.log` in the workspace
(`{call_id, nonce}`) and returns the count. The file IS the effect; counting
lines IS the proof. Two variants registered: `effect-never`
(`replay:"never"`) and `effect-safe` (`replay:"safe"`).

**`test/core/replay-safety.test.ts`** — each case builds a journal state by
hand (or via the `onBeforePersist` crash hook), then runs recovery:

| Case | Proves |
|---|---|
| journal has `TOOL_STARTED` + `TOOL_FINISHED` for `effect-never`, crash after persistence → recovery does NOT re-execute; `effects.log` has exactly 1 line; recovered context contains the recorded result | completed effects are never re-applied |
| journal has `TOOL_STARTED`, **no** `TOOL_FINISHED`, for `effect-never` — the ambiguous window (may or may not have executed) → recovery does NOT re-execute; instead surfaces an explicit `tool_interrupted` result to the model; `effects.log` line count is 0 or 1 but recovery *adds* 0 | **the exactly-once-at-effect-level proof**: in the ambiguous window the system chooses at-most-once for `never` tools and says so out loud, rather than guessing |
| same ambiguous window for `effect-safe` → recovery re-executes; result recorded; `effects.log` may have 2 lines and that is correct *because the tool declared it* | at-least-once is opt-in via `replay:"safe"`, never the default |
| retry of a whole attempt (`TASK_RETRIED`): new `attempt_id`; `effect-never` results from attempt 1 are not re-applied in attempt 2's recovery — attempt 2 starts clean and any re-execution is a fresh *model* decision, journaled as such | retries don't silently duplicate effects across attempts |
| double-delivery of the same operation (`send` delivered twice with same op id, simulating a flaky command channel) → one journaled effect | idempotent operation ingestion |
| property test: random crash point injected at every persistence boundary in a scripted 5-tool task × both replay policies → invariant: `effect-never` tools' `effects.log` count ≤ 1 per call_id, and every ambiguous case has a `tool_interrupted` journal record | the invariant holds at *every* crash point, not the two we thought of |

### 5.10 Plugin HITL (human-in-the-loop approvals)

Precondition: the approval gate is a core gateway concern — a tool or
permission marked `approval: required` suspends the call and emits an
`APPROVAL_REQUESTED` journal event; a response arrives through the command
channel. Fixture: **`test/fixtures/fake-approver.ts`** — a scriptable
responder (approve / deny / never-answer / answer-after-N-ms) driven by a
fake clock.

**`test/core/approval-gate.test.ts`**:

| Case | Proves |
|---|---|
| approval-required tool call → `APPROVAL_REQUESTED` journaled with args hash → fake approver approves → tool executes → `TOOL_FINISHED` | happy path, fully deterministic (fake clock, no sleeps) |
| deny → failed tool result naming the denial (visible to model + operator); no execution; `effects.log` untouched | deny is safe and explicit |
| timeout (approver never answers, fake clock advanced past `approval_timeout`) → failed result `approval_timeout`; task continues or stops per policy — never hangs | unattended tasks can't wedge on a human |
| **no-silent-self-approve guard**: an approval response arriving from a plugin-originated source (event-sink handle, worker `emit`, the requesting plugin itself) is rejected; only the operator command channel (CLI/TUI `ops`) may carry approvals — asserted by attempting each illegitimate path and checking the request stays pending + a `rejected_approval_source` journal record | the requester can never approve itself; read-only event taps can't inject (domain §1.3's "events are read-only" rule, applied to approvals) |
| crash while approval pending → recovery re-presents the pending approval (journal fold), does not auto-approve, does not lose it | approvals survive restarts un-answered, not un-asked |
| approval decision is journaled with initiator identity | audit trail covers the human, too |

### 5.11 Audit integrity — append-only and tamper-evident

The audit trail's value is exactly its trustworthiness; F-504/NF-502 promise
it but nothing yet tests hostility toward it. Design hook: each journal line
carries `prev_hash` (hash-chain), making tamper *evidence* a pure fold.

**`test/core/audit-integrity.test.ts`** — fixtures: a fake audit sink
(records every envelope it is offered, in order) and a hostile plugin
(`test/fixtures/plugin-hostile/`) that tries to write.

| Case | Proves |
|---|---|
| hostile plugin attempts journal writes via every handle it can reach (`onEvent` sink return value, mutating received envelopes, `emit`-ing core-lifecycle event types, opening the journal file path from its own code) → mutations don't land: journal bytes unchanged (hash before == after except legitimate appends); worker `emit` of non-worker event types refused at validation | plugins can observe the story, never edit it; the event-sink tap is fed post-write copies |
| envelopes handed to sinks are deep-frozen (or copies) — sink mutating its argument does not alter what the next sink or the journal sees | no cross-sink contamination |
| hash-chain fold over a pristine journal → valid; flip one byte mid-file → fold reports the exact first broken seq; truncate the tail → valid-but-shorter (distinguished from tampering, per NF-502's torn-tail tolerance) | tamper-*evidence* is mechanical: edits are detected, crash-truncation is tolerated and distinguishable |
| **replay-run invariance**: run a scripted task; snapshot journal hash; re-run the task from checkpoint (§5.12); assert the original byte range is untouched — the file grew by exactly the new attempt's appended envelopes and nothing else | replays append history, never rewrite it |
| append is the only code path: a CI grep proves `core/eventlog.ts` exports no truncate/seek-write API, and file open flags are append-only | append-only by construction, checked mechanically |
| retention prune (`prune --older-than`) removes whole task files only, journals the prune action itself in a surviving meta-journal | even deletion is audited |

### 5.12 Replay determinism and lineage

**`test/core/replay-lineage.test.ts`** — reuses `effect-counter` (§5.9) and
the fake audit sink (§5.11). Scenario: scripted FakeAdapter task runs to
`CHECKPOINT ckpt-1` then `FAILED`; operator restarts from ckpt-1.

| Case | Proves |
|---|---|
| resumed run gets a **new `attempt_id`**; every event it emits carries the new attempt_id; no event ever carries a reused (task_id, attempt_id, seq) triple | attempts are distinguishable forever; no identity collision in the journal |
| resumed run's recovery honors §5.9: `effect-never` results from attempt 1 are surfaced as recorded results, `effects.log` gains no duplicate lines from recovery itself | replay is safe, not just possible |
| **lineage fold**: `timeline()` over the combined journal renders one continuous story — attempt 1's events, an explicit `ATTEMPT_RESUMED {from_checkpoint: ckpt-1, prior_attempt}` core event, then attempt 2 — and a `lineage(task_id)` fold returns the attempt DAG (attempt 2 → parent attempt 1 → ckpt-1) | F-506's "resumed history reads continuously" is a tested fold, not a hope |
| determinism: two replays from the same checkpoint with the same FakeAdapter script produce event streams identical after (attempt_id, ts, seq) normalization | replay is reproducible — the debugging use case actually works |
| replaying from a checkpoint of a *different* task or a checkpoint whose workspace hash no longer matches → refused with an explicit error, journaled | replays can't be aimed at the wrong state |
| cost fold across both attempts sums correctly and attributes per-attempt | budgets survive resumption without double- or zero-counting |

### 5.13 Prompt/context templatization — per-model overrides, determinism, injection safety

Scope: the system prompt is swappable per model (generic default +
model-specific overrides); skills and AGENTS.md-style context files are
templates too. This extends §5.6 (assembly) and the template resolver
(architect §3): resolution gains a **model axis** on top of the layer axis.
Design precondition: model-specific lookup is part of the frozen resolver
algorithm — `resolve(name, modelProfile)` tries
`system/worker-base@<model-family>` then falls back to `system/worker-base`
(generic), deterministically, with `template which --model <m>` printing the
winning path (same discoverability rule as F-302).

**`test/core/template-model-resolution.test.ts`**:

| Case | Proves |
|---|---|
| model-specific override present (`system/worker-base.anthropic-like.md`) → wins for that model profile; absent → generic `system/worker-base.md` used; a *different* model profile never picks up another model's override | per-model resolution with generic fallback, both directions |
| model axis composes with the layer axis: user-layer generic beats builtin model-specific, or the reverse — whichever precedence the architect freezes, the full 2-axis matrix (4 layers × {model-specific, generic}) is asserted from a fixture tree, and `template which --model` output names winner + shadowed | precedence is a frozen, printable algorithm — not emergent behavior |
| **determinism/no-hidden-state**: resolve + render the same (name, model, vars) twice in one process, then in a fresh process, then with a scrubbed environment (`env -i`) and a different cwd → byte-identical output all four times | no env vars, clock, locale, or cwd leak into rendering (NF-304 strengthened to cover the model axis) |
| skills/AGENTS.md as templates: a fixture skill file with `{{tool_names}}`/`{{workspace}}` placeholders renders through the same resolver; unknown placeholder → load-time validation error (NF-302), not silent empty | context files get the same discipline as prompts — no second, weaker template path |
| **cache-invalidation regression (ties into §5.6)**: identical (template version, model profile, stable vars) → `prefixHash` identical across runs and processes; switching model profile changes the hash (different prompt = different cache line, correctly); editing a template bumps its version and the golden — an unversioned content change that silently alters the hash fails the §5.6 golden-prefix test | template churn cannot silently invalidate (or worse, silently *collide*) provider cache lines |
| **injection escaping**: render a template where a variable carries hostile content — `{{tool_result}}` containing `<!-- @replace: guidelines -->`, `{{objective}}` containing `{{api_key}}` or Mustache-syntax, a RAG chunk containing "SYSTEM: ignore previous instructions" styled as our own section headers — and assert: (a) template syntax in *values* is never re-interpreted (single-pass substitution, no recursive expansion — asserted by a value containing `{{other_var}}` rendering literally); (b) anchor/section markers in values do not create or patch sections; (c) values destined for delimited blocks (tool results, RAG chunks) are wrapped in the documented fence with any fence-terminator sequences in the value escaped, so a value cannot close its own fence and continue as template/prompt text | interpolation is data-only: a tool result or retrieved document can *say* anything but can't *do* anything to the rendered structure. This is the template-layer face of prompt-injection defense — the only part of it that is unit-testable, so it must be airtight |
| fuzz: property test feeding random bytes (control chars, null, RTL overrides, 1 MB strings, nested `{{`) through every documented variable → render never throws, output length bounded by input + template, and re-parsing the output finds section anchors only where the *template* put them | no crash and no structural injection under adversarial values |

Anti-change-detector note: injection tests assert *structural invariants*
(anchor count, fence integrity, single-pass expansion) — never exact rendered
text, which belongs to the §5.2/§5.6 goldens alone.

### 5.14 Visualizer / drill-in — a pure function of the journal

Scope: a drill-in view (TUI panel and/or CLI `codeharness inspect <task_id>`)
rendering task state, event stream, checkpoint timeline, replay lineage
(§5.12's DAG), and audit entries. QA's one design demand makes all of it
testable: **the visualizer is `render(journal, options) → lines` — a pure
fold, sibling of `timeline()` and `lineage()`**, living in core as
`core/inspect.ts`; the TUI panel and CLI both call it (F-106 headless parity
gives us this for free if we hold the line). No store access, no clock, no
network inside `render`.

**`test/core/inspect.test.ts`**:

| Case | Proves |
|---|---|
| **golden fixture render**: `render()` over `test/fixtures/journals/multi-attempt.ndjson` (2 attempts, checkpoint, resume, mixed tool results, one denial, one approval) reproduces `test/fixtures/golden/inspect-multi-attempt.txt` byte-for-byte; run twice + in a fresh process → identical | determinism: same journal, same tree, always — the drill-in can be trusted as a forensic view (append-only golden rule of §5.2 applies) |
| purity guard: `render()` executed with a read-only journal array, scrubbed env, fake clock → output contains no wall-clock-derived strings (all timestamps come from event `ts` fields) | "given the same log, the same picture" can't rot into "same picture, mostly" |
| **secret redaction**: a fixture journal seeded with secret-shaped values (config `redact` patterns: API keys, `AWS_SECRET`, bearer tokens) inside tool args, tool output, and error strings → rendered view shows `[REDACTED:<pattern>]`, and a grep of the full rendered output for the seeded secrets finds zero; redaction applied at render *and* verified already absent from the journal itself where the append-time scrub (visibility config `redact`) claims to run — the test distinguishes the two layers and fails if either regresses | secrets can't leak through the inspection path — the place operators copy-paste from |
| **huge-journal bound**: a generated 100k-event journal (loop over fixture events) → `render()` with default options completes under a CI-safe time bound and returns a *bounded* summary view (windowed event slice + counts + "showing N of M"), never the full 100k lines; drill-down options page through deterministic windows (same `--from-seq/--limit` → same slice) | rendering is O(window), not O(journal); NF-104's ring-buffer discipline holds in the drill-in too — no operator tool that dies exactly when the task was big enough to matter |
| **replay-lineage tree**: the multi-attempt fixture renders the attempt DAG correctly — attempt 2 shown as child of (attempt 1, ckpt-1) with the explicit `ATTEMPT_RESUMED` marker, events grouped per attempt, no interleaving confusion; a 3-attempt fixture (resume of a resume) renders the chain in order | §5.12's lineage fold is not just computable but *legible*; multi-attempt history reads as one continuous, correctly-nested story |
| corrupt/partial journal input (torn tail line, one hash-chain break from §5.11) → renders the valid prefix + an explicit `⚠ journal integrity` marker at the break point, never a crash or a silently truncated view | the forensic tool is honest about damaged evidence |
| unknown event types in the journal (2029 reading 2026-future events) → rendered as raw one-liners, not dropped | forward-compat (NF-501) extends to the visualizer |

TUI note: the Ink panel wrapping this fold gets only the §5.0 smoke test.
Every behavior above is asserted through the pure fold / CLI — the panel is a
thin projection, and we do not test projections.

---

## 6. Verdict

Approve the architecture **conditional on**: Q-205 resolved to a single
worker contract with `abi-conformance.test.ts` landing in the same PR (S1);
the `src/`→`core/` rename gated on test migration + per-module contract
tests (S2); golden fixtures recorded before the freeze is declared (S3);
tool-result persistence ordering specified so F-409 recovery is a pure
journal fold — proven by the §5.9 exactly-once fixture (S4); the permission
enum closed (S5); and the two new surfaces built as pure functions behind
frozen ports — prompt assembly with byte-stable prefix goldens, RAG behind a
Retriever port with an in-memory reference adapter, the model-axis template
resolver rendering deterministically with data-only interpolation (§5.13),
and the visualizer as a pure fold over the journal (§5.14) (S6). None of
these are
redesigns — they are **sequencing and purity requirements**. The design is
unusually testable if built in the right order; built in the wrong order,
the freeze certifies untested behavior for three years.

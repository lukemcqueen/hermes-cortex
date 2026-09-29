---
version: 1.0.0
name: steadfaste-design
category: software-development
description: steadfaste design-doc and governance-cycle work.
---

# steadfaste — architecture & design-doc work

## When this applies
Any change to the steadfaste architecture (repo `~/steadfaste`): covenant/spec docs, design mechanism docs, grounded research reviews, the governance cycles that gate them, and the **build execution** of the frozen spec (`docs/design/build-tasks.md` → the BUILD/CHECK split). This is the fleet owner's (Luke) product: **settle the design before building** — the design docs are the deliverable, not code. Core = the Constitution (unamendable Rust core) + Covenant (bond of trust); Agent/Worker/harnesses/gateways are all swappable behind it.

## Standing preferences (Luke)
- **Settle design first, thoroughly.** "Take your time, no rush to build." Build only after a design looks bulletproof. Ground every claim in primary sources (read real docs/repos; mark UNKNOWN rather than guess).
- **DESIGN-FIRST GATE: "research X for the interface" means write a design doc, NOT code.** Even when the request mentions an interface/API, and even if you already have a RED test written — the deliverable is a thorough design doc unless Luke explicitly says implement/build. If you catch yourself writing implementation files for a design request, delete them and write the doc. Luke has corrected this mid-task; a half-built implementation is wasted work, the design was the ask.
- **"Research X" = consult the expert model directly (DeepSeek Pro via OpenRouter), not vendor-doc browsing.** When Luke names a model/provider as the research source, prompt it via the OpenRouter API with the concrete design question — crawling the vendor's docs site is the wrong path. Ground the doc in what the consult returned, marking UNKNOWN what the consult could not confirm.
- **Every new subsystem design doc must state explicitly: (1) its relationship to the Ledger — which stream it is, what it must never touch, the wall between it and the single writer; and (2) its scale-ladder placement — zero-config at 1 agent, inert-until-needed heavy paths, per-tier operator steps.** Luke checks these first; a doc missing them reads as unreviewed.
- **When Luke interjects a mid-task correction, pivot immediately after the current tool result** — do not push the interrupted path to completion first. Corrections arrive as narrow one-line messages and each narrows the deliverable (design-only, organize with the corpus, must not interfere with the Ledger); the interrupted path's remaining work is now waste.
- **Keep the core pure/focused.** Design an *interface* when it serves the product's GTM (enterprise deal-opener); DEFER adapters/transports/implementation until a client or deal demands it (anti-bloat). Never let external policy/adapter become an authority over the Law.
- **Current vs historical separated.** Current docs live in `spec/` + `docs/design/` + `docs/research/`; stale/one-off artifacts move to `docs/historical/`. Keep every doc listed in `docs/README.md` map.
- **Anti-bloat test for any new surface:** "is this needed to govern well, or is it a client wanting to be pretty / a feature that loses the core?" The latter is out of scope.
- **Verify-before-add, even on the user's own idea:** when Luke proposes adding a capability, do NOT fold it in just because he asked. First overlap-check it against the settled concepts (a per-model bundle vs PromptState/inject-prompt vs Charter/levers vs the reputation permutation — complementary, not redundant), state the overlap analysis, then add it with the invariants that keep it safe. Show the verification was done, not just that you complied ("don't just do it because i want it... verify this makes sense with our system").
- **Judge "do we need hermes-cortex concept X here?" by comparing topologies, not by presence:** bus/brain existed in hermes because it is a FLEET of autonomous agents with independent state; steadfaste is ONE accountable core + swappable isolated workers + the Ledger as single truth. A capability whose purpose the opposite topology already serves (coordination → the single-writer Ledger; knowledge → Ledger + Model Reputation Library) is a DELIBERATE EXCLUSION, and the exclusion is recorded as a reasoned decision, not an omission.
- **Scale ladder governs scope:** features are sized so "easy at 1 agent" needs zero config, and heavy machinery (mTLS, consensus, PgBouncer, sharded writer) is REJECTED for small scale with the exact tier+trigger to reconsider. The 1000-agent path must be an EXTENSION of the 1-agent path, never a rewrite.

## Procedure (every design change)
1. Open a governance cycle: `begin_change`.
2. Write/append the design doc (see doc-writing pitfalls).
3. If the doc is one the docs map lists, add it to the `docs/README.md` map row.
4. Commit with a message that states: the design decision, the grounding/sources, and the scope line (v1-build vs designed/demand-gated vs never/anti-bloat).
5. `feedback_accept(cycle_id)` then `end_change(task_id)`.

Pitfalls in the procedure:
- **Subagent writes are ALSO governance-gated**, even into `/tmp`. Subagents must open/close their own cycles; writes are refused until they do.
- **Known MCP arg-drop**: `begin_change`/`inbox_send_task` intermittently serialize EMPTY args. Retry 2–3x max, then report the blocker — don't loop.
- Successfully draining the research fan-out does NOT close the work: synthesize findings into a doc under your own cycle before reporting.

## The grounded research "party" pattern
For "are we design-right / is it bulletproof" reviews, dispatch PARALLEL subagents via `delegate_task`, one task per DOMAIN CLUSTER, each instructed to read that domain's PRIMARY docs and return structured findings. Synthesize into a research doc under your own governance cycle.
- Use a fixed verdict vocabulary per system: **VALIDATES / BORROW / GAP-RISK**, each = a one-line finding + the mechanism, not a narrative.
- If a subagent returns only PART of its assigned set, re-dispatch the missing cluster — do not assume a partial result is complete (one fan-out returned only 1 of 3 clusters; the rest had to be re-dispatched).
- Ground in repo READMEs/official docs; mark UNKNOWN explicitly, never fabricate.
- Reuse the standard task-prompt + output schema: `references/research-party-schema.md`.

### The "frozen for years" hardening review (interface-freeze + cross-OS + adversarial sweep)
When the goal is "core/interface rock-solid and UNCHANGEABLE for years" (also: a platform that cannot be tested yet, e.g. a PC/Windows port), run a 3-DEEPSEEPRO-PASS hardening party in addition to any design review:
- **LA — frozen-interface integrity:** what breaks an additive-only interface over 3+ years. Key findings to check for: shape-freezed but MEANING-drifting fields (semantic-freeze layer — pin prose definition + invariant fixture per field, not just a type); codegen-from-schema must be the PRIMARY path (parity-testing only DETECTS drift, it does not prevent it); version-negotiation in the handshake (negotiate frame version, not just capability scope); deprecation calendar + compat matrix + wire-visible payload versioning; unknown-type-IGNORE must be scoped to telemetry (must-understand content rides `kind`, never the ignorable channel).
- **LB — cross-OS forward-design:** decide the interface amends NOW for the untestable OS so the port cannot break the frozen contract later. The decisive mechanism: a **`platform_caps` capability declaration** on both handshakes (freeze/kill/egress_revoke/containment/path_style enums) so "stop" is declared per-host rather than assuming POSIX SIGSTOP (Windows has no SIGSTOP — the guarantee must read "freeze if the host can freeze, else atomic tree-kill ~500ms"). Separate DECIDE-NOW (declarations, additive) from DEFER (pure plumbing).
- **LC — adversarial final sweep:** 11-finding sweep for logic contradictions across docs (e.g. single-writer vs federation — pin ONE designated writer-core, others submit), security holes in the n-arrow cases (egress-proxy revocation must DROP ESTABLISHED connections not just update the allowlist; emergency-stop must kill pid-namespace-init or cgroup.kill, NOT process-group, or setsid/double-fork escapes; Ledger HMAC with a fleet-shared key is forgeable — use unkeyed SHA-256 chaining + Ed25519-verifiable checkpoints), and seed-pinning (use TWO seeds: a RECORDED reproducibility seed + an UNRECORDED anti-gaming CSPRNG, or colluders predict pair-review).
- Synthesize all three into one research doc with a concrete "before the freeze ships" action list. Do dependencies explicitly (HMAC fix precedes verify-from-checkpoint; two-seed precedes collusion defense).

### The scale-ladder design shape ("easy for the 1/2/10/1000-person")
When sizing a feature/architecture for adoption, structure it as a 4-rung scale ladder — produce per-rung (persona, topology, what "easy" means, the zero-config default, which gaps bite hardest), plus the complete gap-accommodation table marking each gap **BUILT-IN (v1, zero config) vs SCALE-UP-GUIDANCE (tier + concrete operator step)**, and a what-changes-per-rung (automatic vs operator-decides) summary. The honesty rule that governs it: a small deployment must never inherit heavier machinery it doesn't need, and the 1000-agent path is an EXTENSION never a rewrite — test: "if the 1-person must touch a knob to get an honest answer, or the 1000-person must rewrite to add capacity, it's broken." Performance/single-writer/consensus items marked "BUILT-IN" that are actually load-dependent are wrong-axis errors — code path may exist in v1 but lie INERT at n=1, activating on demand.

## Story & slicing the build requirements (v1 → vertical stories)

When the ask is "story and slice the requirements" (Luke, recurring — planning
the build in user-valuable slices before code), the deliverable is a vertical
story/slice plan doc under `docs/design/` (current plan:
`docs/design/story-slices.md`), cut from the BUILD-READY blueprint — NOT the
blueprint's §7 crate order presented on its own, and NOT the old
Pi-vocabulary story (`docs/historical/story/coding-agent-story.md`, superseded).

- **Slice by covenant promise, vertically.** Each story crosses Wire framing →
  Constitution → Ledger and lands as a demonstrable, user-visible governance
  outcome (a verdict, a stop, an audit, a kept promise). "Done" for a story =
  its owned conformance tests (blueprint §5) green against the real pipeline.
- **The done-map is the discipline:** every conformance test is owned by EXACTLY
  one story. Reproduce the test→story table so nothing is owned twice and
  nothing is unowned; that table is the single source of truth for "which tests
  ship with which story."
- **One deliberate horizontal substrate first.** The core is a single Rust
  binary assembled crate-by-crate, so the first story is the substrate that
  freezes and proves the two halves named "core & interface": the Wire ABI
  (one `abi.schema.json`, codegen primary, byte-parity, handshake fail-closed)
  and the Ledger (hash chain + single-writer, verify-on-read). State explicitly
  WHY it is the one non-user-valuable horizontal — it IS the core+interface;
  nothing downstream is testable honestly until the loop exists.
- **Map to §7** in a table so the vertical (stories) and horizontal (crate
  build) views agree; order stories by dependency (substrate → run →
  verification needs ride later stories).
- **Stay faithful to §6 IN-scope** plus the anti-bloat test: a slice that is
  data → a Ledger fold/view; judgment → a governed worker over the ABI;
  enforcement → a core gate; a client wanting to be pretty → a client of an
  interface, never core. Project v1.1+/v2 (surface, gateway, fleet) separately
  as DESIGN, marked not-core-blockers.
- **Per story:** As-a/so-that framing, Given/When/Then acceptance (one happy +
  one error scenario), INVEST, dependencies, and a scale note — the
  `story-decomposition` vertical-slicing discipline applied to a governed
  monolith.
- Register the new doc in `docs/README.md` CURRENT table; note it supersedes the
  historical story.

## Executing the build — the BUILD vs CHECK split

The build is a frozen-spec implementation (`docs/design/core-build-blueprint.md`)
driven top-to-bottom through `docs/design/build-tasks.md` — numbered tasks, each
tagged BUILD or CHECK, with a status column. The split is the whole discipline:

- **BUILD = mechanical shape/wiring** (a struct, an enum, a DDL). The compiler
  + a happy-path test catch the errors. **Delegate BUILD to subagents**
  (`delegate_task`), in parallel where independent, and verify their self-report
  against real `cargo test` output before trusting it (a subagent's "done" is a
  claim, not proof).
- **A subagent transcribes your spec LITERALLY — your spec's bugs become its
  bugs.** A missing `rename_all` or `skip_serializing_if` in the type spec you
  hand over is copied verbatim into the output, and the subagent will not catch
  it because it followed you faithfully. Review delegated output against the
  codebase's own wire conventions (the serde pitfalls above), not just
  diff-check it against your own prompt — the spec author and the reviewer must
  be different eyes.
- **CHECK = a security guarantee** — the conformance tests plus the
  canonicalization / tamper / stop / redaction / replay functions they prove.
  Silent-when-wrong; a weak model must never write them. **Do CHECK tasks
  yourself** (the strong model). Stop before each CHECK, commit the accumulated
  BUILD work, and report for strong-model review. Never hand a CHECK to a
  subagent.
- **Drive autonomously, top-to-bottom.** The owner should only have to say
  "continue" — not re-prompt per task. Do CHECKs yourself, delegate BUILD,
  commit each task, and report the next task to hand off.
- **Session-tail handoff, not in-session slicing.** When the next phase is a
  large build and this session is already long, stop after the survey: close
  the cycle and emit a SELF-CONTAINED handoff prompt instead — repo state
  (HEAD + green test count), what exists vs what doesn't, the task table with
  BUILD/CHECK tags, and the TDD/governance/commit rules a cold session needs.
  Hand it to the owner verbatim for a fresh session ("Don't slice yet — give
  me a prompt for another session to do it", 2026-09-23; the fresh session
  then built Story 7 end-to-end off that prompt).

**One task = one file (or one tightly-coupled pair) + one test + one RED→GREEN
cycle.** Never batch unrelated edits. After every task, `cd core && cargo test`
must be full-suite green before commit.

- **Every task — BUILD and CHECK alike, and including delegated output — closes
  with edge-case tests and an adversarial review.** This is a standing operator
  directive, not a per-task request: probe the boundaries (empty input, integer
  extremes, malformed/wrong-typed input, reordered/duplicate data) and attack the
  implementation's assumptions with a scratch probe rather than reasoning from
  memory. A finding becomes either a fix (a panic path, a lenient parse) or a
  pinned fail-closed test — never a silent acceptance. **For a typed-probability
  threshold gate (a verdict split at a LM/HI band), pin the EXACT seam values
  both sides of every threshold and the type extremes** — `LO-1`, `LO`, `HI`,
  `HI+1`, and the domain limits (`0`, `1_000_000` ppm), plus the wrong-typed
  answer failing closed. Representative middles (a confident-low, a confident-high,
  a mid value) pass while the inclusive/exclusive edge is silently wrong; a
  security gate's contract IS the seam.

**A hand-written `validate()` on a typed record must bound EVERY numeric field,
not just the ones the happy-path example exercises.** Adversarial review caught
`conf_ppm`/`score_ppm` passing at >1,000,000 while only `p_ppm` and the
distribution sums were checked — the example tested a noul and a choice, never a
score, so the score branch's bounds were never exercised. Enumerate the record's
fields in the validator and give each a bound (or a sum-to-exact rule), then write
one adversarial test per field that violates it.

**A conformance test is expected to reveal spec-vs-code divergence.** When the
test fails not because the code is missing but because the code *violates the
frozen contract* (e.g. the spec says "unknown `type` → ignore" but a derived
`Deserialize` rejects it), that is the test working. Write the test first
(RED), then apply the minimal fix that makes the *code* match the *frozen spec*
— you are implementing an already-settled rule, never re-designing, and never
weakening the assertion to make the code look correct.

**serde pitfalls — the abi/ledger/wire crates are serde-heavy; these recur:**
- `#[serde(deserialize_with = "f")]` on an `Option<T>` field **overrides the
  implicit missing-field default** — an absent field becomes a `missing field
  <x>` error. Pair it with an explicit `#[serde(default)]`, or a frame that
  legitimately omits the field regresses.
- **"Ignore unknown enum variant" (an additive registry like `EventType`) is not
  free** — a derived `Option<MyEnum>` REJECTS an unknown variant. Write a custom
  deserializer that maps unknown *strings* to `None` while still rejecting
  non-string values (the malformed-known-field case). The ignore is a *policy*
  on one field, never an `untagged` enum.
- `serde_json::Value` from a helper that returns a temporary cannot be indexed
  by reference (`golden()["kinds"].as_object()`) — E0716 "temporary dropped
  while borrowed". Bind the `Value` to a `let` first, then index.
- **Every enum needs `#[serde(rename_all = "snake_case")]`** (verbs/discriminants
  like `Kind`/`Trust`) or `SCREAMING_SNAKE_CASE` (registries like `EventType`/
  `VerificationStatus`). A missing `rename_all` serializes the PascalCase variant
  name (`Allow` not `allow`) — a silent wire-convention divergence that a
  round-trip test will NOT catch (it round-trips fine) but a golden-fixture or
  convention review will.
- **Every optional field needs its OWN `#[serde(skip_serializing_if =
  "Option::is_none")]`** — it is NOT inherited from the struct or a sibling
  field. A struct-variant field (`GateDecision::Veto.rule_id`) serializes as
  `"rule_id": null` unless annotated, violating the omit-never-null rule (LA-11).
- **"No float in hashed content" detection = `serde_json::Number::is_f64()`.**
  Probe the real parser before trusting it: `-0`, `1e2`, `1.0`, and any integer
  past `u64::MAX` all parse to `is_f64()==true` (the last becomes scientific
  notation — the exact non-deterministic form the rule exists to block);
  `u64::MAX`/`i64::MIN` stay exact `is_f64()==false`. Reject `is_f64()`
  recursively over the value, before serializing. In a *test* asserting a
  serialized record is float-free, walk the parsed JSON value checking
  `!n.is_f64()` at every number — do NOT scan the serialized string for `.`/`e`/`E`,
  because ordinary field values ("severity", "verification") contain those
  characters and trip a false positive. The string-level guarantee is also
  dependent on field names; the value-walk is not.

**Don't let `cargo fmt -p <crate>` creep the commit.** It reformats the whole
crate — including pre-existing files that were never rustfmt-clean — so
`git status` shows unrelated `M` files. Revert the files you didn't otherwise
touch (`git checkout -- …`) and keep the commit to the task's own files. To
confirm remaining fmt diffs are pre-existing rather than yours: `git stash`,
re-run `cargo fmt --check` on the clean tree, `git stash pop` — if the diff
persists without your changes, leave it alone.

## The codegen-primary build (abi-codegen)

The generator (`core/crates/abi-codegen`, lib+bin) reads a schema and emits the
SHAPE-ONLY types; two targets (`abi`, `surface`). Codegen only reproduces a
schema that carries `x-rust` metadata — wire `enum`/`properties` values alone
record neither rename_case, integer widths, nor the serde attribute set, so a
schema without `x-rust` cannot be regenerated faithfully.

- **Shape vs logic split is the whole point.** The generator emits rename_all,
  derive flags (`copy`/`eq`), field order, widths, and serde attrs — nothing
  else. Doc comments flow from the schema `description`. Logic moves OUT to
  hand-written files: `impl Default` → `*_policy.rs`, `#[cfg(test)]` modules →
  `tests/`, projection fns → `surface/src/projections.rs`. A
  `deserialize_with`/`tag`/`skip_serializing_if` attribute is WIRING the
  generator reproduces verbatim, but the function it points at
  (`frame_policy::deserialize_ignorable_type`) stays hand-written.
- **Field order lives in an explicit `x-rust.fields` array, never JSON key
  order** — `serde_json::Map` is a `BTreeMap`, which re-sorts keys and drops
  insertion order; emitting in `$defs`/`properties` order scrambles struct
  fields (a silent wire regression a round-trip test won't catch).
- **`--target` on a cargo-built tool collides with cargo's own cross-compile
  `--target` flag.** `cargo run -p abi-codegen --target surface` is swallowed
  by cargo and fails on a nonexistent target triple; use `cargo run -p
  abi-codegen -- --target surface`, and make the generator's banner/doc
  comments state the `--`-separated invocation, not the one cargo swallows.
- **Never run `cargo fmt -p <crate>` on a crate that contains GENERATED files**
  — rustfmt reformats the generated output, which then diverges from the
  generator bytes and fails the committed-match test; regenerate to restore.
  `cargo fmt -p` only the hand-written crates/files.
- **A generator is production code → it needs a test.** A bare `main.rs` bin
  trips the TDD Iron Law gate (no test target); refactor to lib+bin and expose
  `generate(schema, target)` as a lib fn so the idempotence + committed-match
  tests can call it directly.
- **Idempotence is the load-bearing guarantee** — fixed layout, ordered arrays,
  no timestamps or HashMap iteration. The committed-match test (generated
  output == committed files byte-for-byte) is the "regenerate → zero diff"
  CHECK; prove it non-vacuous by hand-editing a generated file and watching the
  test fail before trusting it.

## "Show the current design" — the component & interface accommodation map

When Luke asks to see the current design, or to make sure all components and
interfaces are accommodated, the deliverable is ONE inventory doc — not a chat
summary alone: `docs/architecture/component-interface-map.md`, plus a row in
`docs/README.md` (the only index; give it a slot in a reading path too).

- **Two tables, one row per part:** components (C1…Cn) and interfaces (I1…In).
  Every row carries: where it lives, the doc that specifies it, its status
  (SETTLED / BUILD-READY / DESIGN / DEFERRED / STANDARD / NOT-THE-PRODUCT), its
  **relationship to the Ledger**, and its **scale rung**. Make Ledger and scale
  *columns* — that is the pair Luke checks first, and a column cannot dodge them
  the way prose can.
- **State the accommodation test at the top, then apply it:** a component is
  accommodated when it has (1) a folder home, (2) a specifying doc, (3) a named
  interface into the core, (4) a Ledger rule, (5) a scale rung. An interface is
  accommodated when it has a stable envelope, one canonical schema artifact, and
  a no-bypass path through the Constitution.
- **The gaps get their own ranked table** — id, what is missing, why it matters,
  the smallest fix — each marked structural or thin. Never silently omit a part
  with no home; never pad the inventory with a part that does not exist.
- **Do NOT invent the missing design to close a gap.** A naming/structure
  question (which folder the human surface lives in) is the owner's call — name
  it, name the smallest fix, and let him settle it.
- **Close the contradiction loop in the same commit.** Surveying for the map is
  where cross-doc drift surfaces (a stale count, a README tree that disagrees
  with the designed tree and with disk); the map commit is the one that must
  leave the corpus consistent.

## Reviewing an external project's source against the design
When asked to "check <vendor/project>'s source against our core/interface," the
deliverable is a grounded research doc under the verdict vocabulary
(VALIDATES / BORROW / GAP-RISK), with every adoptable mechanism APPLIED into the
doc that owns it before the cycle closes — a finding without a home is an orphan.
1. **Triage the repo listing first** (org repos via the GitHub API): separate the
   1–2 repos that touch OUR seams (adapters, packaging, wire-like contracts)
   from apps/eval-corpora, vendored forks of other projects (no design of theirs
   to review), and unlicensed repos (excluded — nothing is taken from them).
   Record the exclusion lists so the omissions are decisions, not gaps.
2. **Read the load-bearing source modules, not READMEs** — the adapter/contract
   types, registry, policy modules, and the lifecycle/install paths. Cite by
   module path; anything not verified from source goes in an explicit UNKNOWN
   section. Closed-source parts of the vendor get no claims at all.
3. **One numbered finding per mechanism**, each with: the mechanism (quote only
   when the quote IS the rule), what it means for our design, the Ledger
   relationship, and the scale rung. A finding may be a deliberate DIVERGENCE —
   when our rule is stricter than the market's, record that we are stricter and
   why, never import the permissive branch.
4. **Apply each borrow into its owning doc in the same commit** (interface
   contract changes into the interface doc, host/capability rules into the
   blueprint, packaging acceptance bars into the gap ledger, a row into
   `docs/README.md`), and state in the review's "where each lands" table that
   nothing changed in the frozen envelope / single writer / v1 scope unless it
   truly did.
5. Split a large new doc across multiple tool calls — draft the file, then
   append sections via `patch` — rather than one oversized write.

### From BORROW findings to a story/slice plan — split v1-core vs v2-deferred FIRST

When a grounded review produces BORROW findings and Luke then says "story and
slice the gaps," the honest answer is usually **most of them are not v1-core
sliceable**, and padding the plan with fake slices is the failure shape. Before
cutting any slices:

- **Check `core-build-blueprint.md` §6** with `search_files` for what is already
  `DEFERRED v2, out of core`. Almost every borrow that touches routing / the
  model pool / the Model Reputation Library / the Evaluator-L2b-critic is
  already deferred — so it becomes a **recorded DEFERRAL with a v2 trigger**, not
  a v1 slice. The borrow note is already applied into the owning doc (step 4);
  the slice plan just names the trigger under which the v2 subsystem will pick
  it up.
- **Only an additive core change is a genuine v1 slice** — a new `EventType`
  member, a new additive field on the frozen schema. Verify against the live
  enum/schema (`core/crates/abi/src/enums.rs`, `abi.schema.json`), never
  intuition: grep the actual variant list before declaring something "additive,
  already covered." (e.g. `TOOL_LOADED` is a real add because the enum has
  `TOOL_REQUESTED/STARTED/FINISHED` but not it; an "already covered" claim is
  only safe after reading the enum.)
- **A one-BUILD/CHECK-story slice plan is a correct outcome, not a thin one.**
  State the v1-vs-deferred split in a table (finding → verdict → v1 core? →
  disposition), put the single additive slice in BUILD/CHECK form, and record
  the rest as deferrals. If a borrow reduces to "already covered by the existing
  event/field," collapse it and say so rather than inventing work.
- **A deferral whose only open question is a one-word owner decision** (e.g.
  "is event X distinct from event Y, or does the existing one suffice?") goes in
  the slice plan as a named decision point blocking its BUILD — do not silently
  pick, and do not build past it.

## Doc-writing pitfalls (these cost real time — proven)
- **Append large markdown via `write_file` to /tmp then `cat >> file`** — do NOT use `printf`/heredoc; backticks/quotes get shell-escaped and the command errors or writes garbled bytes. The same `>/tmp` + `cat >>` rule applies to APPENDING a large block to a code file: `patch`'s fuzzy matcher can grab the WRONG closing brace and corrupt the file (an MN3 append to `fold.rs` merged the new `calibration_fold` block INTO the `RefusalFold` struct and renamed an unrelated field). Recovery is `git checkout -- <file>` then re-append via `cat >>`; grep the diff after a large append confirms nothing got nested.
- **Before appending a numbered `## N.` section, grep `^## N.` in the target.** If a collision exists (an added `## 8.` collided with an existing `## 8.` this project), renumber the NEW section (8→9) AND its subsections (8.1→9.1).
- **After ANY `write_file`, re-read your own written section.** Placeholders are not auto-filled (saw a literal `"v": null — placeholder` ship), and multi-bullet prose gets mangled (dup/missing words, stray tokens). `write_file` writes bytes; it does not proofread.
- **Proofread prose for typos before commit** — misspellings such as `agentatic`, `tracable`, `"A get, not a stylistic note"` slipped through and needed a separate fix pass.
- When a patch "fix" accidentally merges/garbles an adjacent sentence, repair that sentence immediately (re-read the diff), not with an appended "UPDATE" note.

## Public README & marketing copy (the user-facing face of the repo)

Luke treats the README as **part selling the repo** — but sells *honestly and conservatively*. When asked to write or rewrite the README (or any public-facing doc), follow these standing preferences — they override generic prose instincts:

- **Be proud of the genuinely novel and good parts; do NOT oversell.** State the real facts that make it strong (stable core, swappable agents, tamper-evident evidence, enterprise governance). Cut value-judgment claims about your own quality (e.g. "Engineered extremely well" was rejected: "people will judge it for themselves"). Cut unverifiable forward-claims (e.g. "a 2026 thing works in 2029") — state the mechanism that makes it true (additive-only contract) instead. "Be conservative in statements. Do not oversell something you can't verify."
- **Strip PII and the owner's identity from public docs.** No personal names, no real IPs/identifiers. The remote repo may still carry the owner handle — that's the repo URL, not doc content, and is fine.
- **Do NOT use Luke's spoken/internal words in public copy.** Rejected outright: "boring", "non-coder", "settled", "swappable", "watched by arithmetic". "North star" is a concept you *talk about*, not a heading — use "What we build". Branded terms (Constitution, Covenant) are fine but use them SPARINGLY — only a few capitalized concepts stay memorable; when every mechanism gets a name, metaphor competes with engineering.
- **The README is not a diary.** Do not enumerate every request made this session; keep only important product info. "Stop repeating everything I request as if everyone in the world needs to hear it."
- **Teach the product in order** (this is the shape): what it is → the idea (agents replaceable, foundation not) → built for trust → architecture → why it exists → technology → enterprise governance → status. Learn concepts in sequence; don't open with several competing headlines.
- **Plain spoken prose over branded stacking.** If a block reads like a creed (titles + prometheus of internal names in bullets: Constitution/Covenant/Ledger/Gate/VERIFY), rewrite it as natural sentences that keep the facts ("Rust core, one static binary… the core handles the store, a tamper-evident ledger, config validation…").
- **Pitfall — a "wrong online version" is usually an UNPUSHED branch.** Before
  editing a README (or any doc) the user says looks wrong online, count the
  unpushed commits (`git log --oneline origin/main..main | wc -l`) and check
  `git status -sb`. Local main can be many commits ahead (this session: 76) while `origin/main` shows a stale version with old content (Python, owner name, missing citations). The on-disk copy was already correct; the real fix was PUSHING. Pushing N commits is a meaningful action — get explicit go-ahead first, then `git push origin main` and verify sync (`git status -sb` shows no ahead/behind) + confirm the remote branch via `git show origin/main:README.md`.

## Two-harness coexistence (steadfaste + hermes-cortex)

If asked "should the two harnesses play nice / can they coexist," the answer is **good neighbors, never a merged system**: steadfaste is the eventual target core, hermes-cortex is the incumbent fleet. Keep them SEPARATE (own Postgres DBs, own ports, own config/state dirs — steadfaste never touches `~/.hermes*`, hermes never steadfaste's); decide the two real seams (skills/prompts → Model Profiles mapping; the Telegram-token decision) as boundaries, not merges; coordinate state across them in ONE direction only (steadfaste's Ledger can CONSUME hermes events via an adapter — hermes's bus never drives steadfaste's core). The migration rule: nothing committed to the incumbent is unavailable to the target, and nothing the target does requires the incumbent ("route around hermes when it breaks"). A hermes-cortex agent/worker talking to steadfaste registers as a governed worker through the secure-registration flow (`references/worker-registration.md`) — it does not get process-lineage trust.

## Live-testing the governed lifecycle (verify the Wire, don't just trust unit tests)

When asked "test a sub-agent command with it" (or verifying lifecycle work), drive the REAL binary with JSONL frames — the conformance tests cover the session API, not the wire loops:

1. Build once (`cd core && cargo build`), then either:
   - **stdin path** (single shot): pipe a JSONL frame sequence to `core/target/debug/steadfaste` from a Python script (`subprocess.run([...], input=frames+"\n")`) and read the ACK frames back; or
   - **socket path** (shared session): start `core/target/debug/steadfaste --serve /tmp/steadfaste.sock &`, connect a `socket.AF_UNIX` client, send frames line-by-line, read one ACK line per frame, then `pkill -f 'steadfaste --serve'` and remove the socket when done.
2. Frame shape: `{"version":1,"kind":<lowercase snake_case verb>,"job_id":...,"seq":N,"ts":<RFC3339 UTC>,"trust":"untrusted","data":{...}}`. Kinds are the enum's snake_case names (`commission`, `started`, `progress`, `result`, `stop`, `keep_alive`, ...) — a PascalCase kind is rejected as `unknown variant` (parse error ACK, job_id empty).
3. Assert on `data.state` and `data.ledger_len`, **never on the ACK's `kind`** — the ACK frames echo a fixed label regardless of the request kind; `data.state` (Handshake → Commissioned → Running → Result) is the real lifecycle readout.
4. Always include the negative sequence — a governed system is proven by its rejections: duplicate `commission`, a `result` naming a foreign job id, heartbeat on a finished/released lease. Both listeners share ONE dispatch, so expect IDENTICAL responses per step: `kind:error` with `TransitionError` or the lease errors (`JobAlreadyLeased` on a dup commission, `NotLeaseHolder` for a foreign job's advancing frame, `LeaseReleased`/`LeaseNotFound` on a dead-lease heartbeat). Parity = identical kind + state + error on EVERY step — if the two transports ever disagree again, that is a regression of the shared-dispatch invariant: record it in the design-gaps ledger, never accommodate it in the probe. A success-only script proves nothing. An error ACK does NOT prove the state didn't move — verify from the NEXT step's observed state, never from the error alone. Even a REJECTED attempt is appended (auditable): `ledger_len` grows on a refused action, so assert `data.state`/`kind`, not that `ledger_len` stayed put. And when re-running a stored probe after a legitimate behavior change, re-derive its expectations (which frames answer, expected states) from the NEW behavior FIRST — stale hardcoded expectations make a PASS read as a FAIL and send you debugging the wrong thing.
5. **Plain heartbeats are `keep_alive`, not repeated `progress`.** Every governance kind advances the lifecycle, so a second `progress` from the same state is a TransitionError, not a no-op; `keep_alive` is the passive lease-renewal verb. Reserve `progress`/`started`/`result` for actual state transitions.
6. **Verify both wire listeners separately** — the stdin loop and the `--serve` loop are separate code paths that CAN diverge (the serve loop has lagged the stdin loop on lifecycle mapping). A green stdin run does not prove the serve path; drive both with the same frame sequence before claiming parity.
7. Cleanup: kill the serve process and remove the socket file in the same session — a stale `/tmp/steadfaste.sock` makes the next `--serve` start look successful while clients connect to a dead listener. `pkill -f 'steadfaste --serve'` from a bash tool call can SIGTERM the tool's own wrapper shell (pattern matches it) — verify with a socket `connect()` instead and clean the socket file separately.
8. **Promote a probe that must stay into a cargo integration test in the owning crate** (`core/crates/steadfaste/tests/…`): spawn the real binary with `Command::new(env!("CARGO_BIN_EXE_steadfaste")).arg("--serve")`, poll-connect the socket until it accepts (never sleep blind), give EACH test a unique socket path — tests run in parallel, and two tests deriving one path from the pid collide and fail with `ConnectionReset` mid-sequence — and clean up in `Drop` (kill + wait + remove socket). A manual Python probe explores; the committed integration test is the regression net.
9. **Grep the dispatch arms (`SessionManager::dispatch`) before trusting a documented verb.** An unmapped kind falls into the passive `_ => Ok(self.state())` arm, which ACKs it as OK while touching nothing — exactly how `keep_alive` silently stopped renewing leases while the docs called it the passive lease-renewal verb. A new verb needs an explicit match arm plus a test for the dead/unknown-lease case.

**Wire findings that touch the single-writer dispatch story get RECORDED, not patched.** When live testing surfaces a cross-listener divergence that changes the dispatch/ownership design, add a row to the findings ledger (`docs/design/design-gaps.md`, the ID | Sev | finding | status/where-it-lands table style), point the `build-tasks.md` header at it, and leave the design decision to Luke — the design-first gate applies during build too. Fix in the same cycle only the unambiguous defect (a documented verb that silently no-ops), with its conformance test. **Write each finding row from the probe transcript, not from the design intent** — cross-check the claimed mechanism against the observed step sequence (an error followed by a still-advancing state proves the mutation happened despite the error) before committing the row; a row narrated from the intended design has claimed "rejected before touching state" when the probe had just proved the opposite, and had to be rewritten before commit.

### When a recorded finding becomes a build task — unify, don't accommodate

When Luke says continue on a recorded divergence, the fix direction is **unify the dispatch, never accommodate per-transport**: two transports of one core answering the same frame differently get ONE shared dispatch function both call — per-transport patches that make observed outputs match just re-create the divergence on the next verb.

- **Gate before mutate, record the refusal.** An ownership/authorization gate runs BEFORE the state transition; the refused attempt is still appended through an append-only path (auditable), and the error names the actual failure (a dedicated `NotLeaseHolder` variant, not a reused `JobAlreadyLeased` — a wrong error name sends clients debugging the wrong thing). A gate placed after the mutation protects nothing.
- **Carve exemptions from pinned tests, not intuition.** Before adding a gate, grep the existing test suite for legitimate flows the gate would refuse (the pinned stop-after-failed → Closed client test forced the one exemption: sealing an already-terminal session is record-keeping, not work). Each exemption stays pinned by that existing test.
- **Layer the verification: unit conformance first, live probe second.** RED→GREEN the gate at the SessionManager level (state unmoved + attempt appended + the holder still lands), then re-run the live parity probe to prove the transports stayed in lockstep — the unit test proves the rule, the probe proves the wiring.

## Pitfalls that recur on the steadfaste repo
- **A shared doc-freshness hook may expect a `docs/DOCS-INDEX.md` that steadfaste does not have.** Its canonical doc map is `docs/README.md` (which IS updated). Do NOT invent a parallel `DOCS-INDEX.md` to placate the hook — that is a second source of truth and bloat. Recognize it as a mismatched hermes-cortex hook expectation and leave it (or flag scoping the hook to steadfaste's real index — the operator's call).
- **After a hardening fix, historical gap-analysis docs go stale.** If a hardening pass fixes a design gap in the live docs (e.g. Ledger HMAC → unkeyed SHA-256 + Ed25519), a *historical* gap-analysis doc that still documents the OLD design as an open gap is now partly wrong. Leave a pure historical record as-is, but flag the staleness rather than silently propagating the old design as current; update any CURRENT doc, never the historical one.
- Always confirm sync after a push with `git status -sb` (no ahead/behind) and `git show origin/main:<file>` on the shipped file.
- **Open the governance cycle BEFORE the first `terminal` call.** The lock is
  repo-scoped and the enforcer blocks `terminal` for ANY command inside
  `~/steadfaste` — even a read-only `ls`, `git status`, or `find`. `read_file`,
  `search_files`, and `skill_view` stay allowed, so survey the docs first and
  `begin_change` the moment a shell command is needed; retrying a blocked call
  never works.
- **"Exists" means "has files" — never infer from a folder name or README tree.**
  `core/` holds the Rust workspace (crates under `core/crates/`), `prototype-ts/`
  holds the TS prototype, while `worker/`, `web/`, `gateway/`, `packaging/`,
  `governance/`, `test/`, and `config/` remain EMPTY placeholder directories;
  git does not track empty dirs, so a folder in the designed tree need not be on
  disk. The build advances over time, so COUNT rather than trust this
  sentence: `for d in core worker web gateway packaging governance test config prototype-ts; do printf '%-14s %s\n' "$d" "$(find "$d" -type f | wc -l)"; done` — a component's state is the file count, not the folder existence.
- **`docs/design/build-tasks.md` lists every task TWICE — the cumulative top
  table AND the per-story section tables — and they silently diverge.** A task
  marked ✅ in the top table can still sit ⬜ in its Story section below, and
  the "Path at a glance" story-map block at the top goes stale the moment a
  released story's next marker isn't moved. The doc header's "Where we are" is
  the agreed source of truth, so before polling a task/status column from a
  section table, cross-check it against the top table + header, and when a
  build task lands, update BOTH the cumulative row and the story-section row in
  the same commit — never just one copy.
- **The `build-tasks.md` "Where we are" test-count header is hand-maintained and
  drifts.** Verify the true count with `cargo test --workspace -- --list 2>/dev/null
  | grep -cE ': test$'` — the `--list` count is authoritative; the "N passed" sum
  over-inflates it because some target shards are counted more than once. To prove
  a change is exactly +N (and catch a stale header you would otherwise propagate),
  `git stash`, run the count (BEFORE), `git stash pop`, run it again (AFTER), diff.
  Correct the number in the same commit rather than carrying a header that already
  disagrees with the suite.
- **A rejected push usually means origin/main advanced with a PEER's work — count
  AFTER the merge, never propagate either side's header count.** A mid-build
  `git pull --rebase` that lands a parallel author's commit (e.g. another agent's
  Story) will conflict on the hand-maintained count header precisely because both
  sides rewrote it. Resolve the header by MEASURING the merged tree
  (`cargo test --workspace -- --list | grep -cE ': test$'`) + the MERGED `test
  result` lines, combining BOTH bodies of work, not by taking either line's "N".
  **If the peer brought failing tests (e.g. live-API integration tests hitting a
  real provider), prove they are pre-existing before claiming green**: `git show
  <peer-commit>:<path> | md5sum` vs the merged file (byte-identical + your diff is
  confined to other crates = not yours). Then put the HONEST number + a named
  caveat ("4 pre-existing `live_jev` live-API tests fail without a valid key") in
  the header — a header that claims all green while the suite is red is a lie
  that misleads every reader. A peer's live-API failure is that peer's domain;
  document + flag it, do not silently fix it into your unrelated slice.
- **Adding a wire/surface type is now SCHEMA-FIRST, not hand-edits.** CG1–CG4
  and surface Slice 0.3 built the generator (`abi-codegen`), which is the
  primary path: `abi.schema.json` (and `surface/interface.schema.json`) carry an
  `x-rust` block per `$def` (rename_case, integer widths, field order,
  Option-ness, serde attrs) + a `description` (the semantic freeze), and the
  shape files (`abi/src/*.rs`, `surface/src/reads.rs`/`verbs.rs`) are GENERATED
  from them with a `GENERATED — DO NOT EDIT` banner. To add a type: (1) add the
  `$def` with its `x-rust`; (2) register it in `abi/tests/schema_complete.rs`
  (`WIRE_TYPES` for a Rust type, `DATA_PAYLOAD_DEFS` for a `*_data` payload);
  (3) `cargo run -p abi-codegen` (or `-- --target surface`) to regenerate;
  (4) STILL hand-update the golden/parity fixtures
  (`tests/golden/abi_parity.golden.json`, `all_event_types()`, `roundtrip_upper`)
  — the generator does NOT emit those. The committed-match + idempotence tests
  (`abi-codegen/tests/`) and the CI `git diff --exit-code` gate then enforce no
  manual divergence. Grep the variant name across `core/crates/abi/` before
  declaring an add complete — an "already covered, additive" claim is only safe
  after reading the live schema+enum.
- **Any new `$def` in `abi.schema.json` MUST be registered in `abi/tests/schema_complete.rs`
  (the CG1.2 inventory guard) or `every_schema_def_is_accounted_for` fails the suite.**
  The guard's `WIRE_TYPES` lists Rust wire types by PascalCase name
  (`Kind`, `Frame`, `ReviewVerdict`, `JudgmentData`, `JudgmentAnswer`); a `$def`
  with no Rust struct (a `*_data` payload) goes in `DATA_PAYLOAD_DEFS` keyed to a
  data-carrying `Kind`. The `$def` NAME must match the Rust type exactly: a
  `snake_case` `$def` like `judgment_data` against a `JudgmentData` struct breaks
  the guard (it looks for the PascalCase wire-type name in `WIRE_TYPES`). This
  guard is a LATER addition than the golden/parity lists — a new wire-shape commit
  must touch it too, and the enum+golden+parity list in the pitfall above is no
  longer sufficient on its own.
- **After a `git pull --rebase` that re-merges `abi.schema.json`, grep for
  DUPLICATE `$def` keys and stale cases BEFORE trusting the schema.** When a
  parallel branch/commit also edited the schema (upstream CG1.1 did), git
  auto-merges by line and can leave two `WorkerRole` defs (our `"judge"` version
  plus upstream's `primary/critic`) or one def under a stale case. JSON with
  duplicate keys parses but the LAST wins — a silent behavioral change. Fix by
  consolidating to one canonical def (the one carrying every member) and confirm
  `schema_complete.rs` still accounts for every key. Run
  `python3 -c "import json;json.load(open('core/crates/abi/abi.schema.json'))"`
  won't catch a duplicate-key collision; grep for the key count instead.
- **The pre-commit secret-leak detector flags the frozen `abi.schema.json`
  `"$schema": "https://json-schema.org/…"` line as a "non-placeholder domain".**
  That is a non-blocking false positive (it is the JSON Schema draft URI, not PII).
  Do not "fix" the URI or add an ignore — the warning is cosmetic and the commit
  lands.
- **Any design that puts model probabilities, confidence, or scores on the
  Ledger as decimals is unappendable.** `canonical_json` rejects every IEEE-754
  float (`CanonicalError::FloatRejected`, pinned by `ledger/tests/entry_hash.rs`
  + `edge_cases.rs`). Quantize at the *schema* boundary, not by the consumer:
  integer parts-per-million (`u32`, 0–1,000,000); every distribution sums to
  exactly 1,000,000 (largest-remainder residual); raw provider bytes ride by
  hash, never inline. This is what `judgment-abstraction.md` got wrong (Jev
  `noul: 0.87` could never append) and why `machine-native-substrate.md` §4.3
  quantizes to ppm.
- **The machine-native / judgment layer is owned by
  `docs/design/machine-native-substrate.md`; MN0–MN3 have SHIPPED, MN4–MN7 are the
  remaining slices.** Shipped: MN0 (`WorkerRole::Judge` in `abi/src/review.rs`,
  `judgment_data`/`JudgmentAnswer` in `abi/src/judgment.rs`,
  `EventType::JudgmentRendered`; the CG2 shape/logic split keeps `validate()` +
  `judge_commission()` in `judgment_policy.rs`), MN1 (`Constitution::judgment()
  append`), MN2 (`constitution/src/decision_class.rs` compose grammar —
  `compose(floor,a) ≥ floor`, untrusted-never-clears, undecidable-escalates),
  MN3 (`calibration_fold` in `ledger/src/fold.rs`). When asked to build the apply
  step of compose, the surface judgment reads, the autonomy dial, the judge
  adapters, or a judge baseline battery, start at §6's slice table — the design
  (invariants MN-1..MN-10, output classes, Decision Classes) is settled.
- **The concrete, tested Jev integration patterns live in
  `docs/research/ten-levels-of-jev-2026-09-30.md`** (digest of
  `disler/ten-levels-of-jev`: 30 Jev use cases in 10 levels). When asked how Jev
  integrates into steadfaste, or to wire a Jev gate/route/cheap-read, start there:
  it maps each level onto the machine-native design (what VALIDATES, what BORROWs
  — hook placement at tool_call/tool_result/turn_end, cheap file reads, parallel
  fan-out — and the deliberate divergences: weights-in-code and agent-authored
  questions are forbidden by the compose grammar / MN-3). It also records Luke's
  cost posture: Pi (`@earendil-works/pi-coding-agent`) as the coding agent + Jev
  for judgment + offline coding (`offline_code`/`qwen2.5:3b`) for generation.
- **The coding-agent model-cost routing design lives in
  `docs/design/coding-cost-routing.md`** (pi → Jev / offline / other at the
  lowest honest model cost, commissioned by the Steward over the Telegram
  gateway). When asked how coding work should route models, or to wire the pi
  harness's cost layer, start there: a three-tier resource model (T0 Jev
  judgment ~$16.80/million, T1 offline_code+qwen2.5:3b codegen at $0 marginal,
  T2 hosted workhorse, T3 hosted reasoning), a governed four-class routing
  Decision Class (BOUNDED/ROUTINE/COMPLEX/CREATIVE → cheapest capable tier, per
  MN-3 the question is the policy), five Jev judge-worker hooks in the pi loop
  (routing classifier, destructive-command gate, compaction scoring, cheap file
  reads, output screening), and monotone-toward-caution failover (never downgrade
  a tier, fail closed to the Steward on undecidable). The routing classification
  is itself a Jev `choice` — it never costs an LLM call; the verbosity tier rides
  the same routing (BOUNDED→MINIMAL … CREATIVE→FULL). The core routing module is
  BUILT (`core/crates/constitution/src/routing.rs`: `route_for_class` /
  `route_from_answers`, provider-neutral — takes `JudgmentAnswer`, never a Jev
  handle — fail-closed undecidable/unknown/missing → T3); the CR0–CR7 build
  track (one test owned once) is in `build-tasks.md`. **pi install:**
  `npm install -g @earendil-works/pi-coding-agent` — requires Node `>=22.19.0`,
  NOT Node 24 (Node 24 was only the ten-levels repo's own TS requirement, not
  pi's).
- **Neither pi nor Jev is load-bearing — both are swappable behind adapter seams
  (a standing design rule: "easy swappability and interoperability is very
  important").** A coding agent (pi) is ONE adapter behind a GENERIC
  coding-worker event interface (`on_tool_call`/`on_tool_result`/`on_turn_end`/
  `on_context_gather`/`on_output`) — the Jev hooks are defined against that
  interface, never pi's extension API; pi maps its own events onto it and is the
  reference adapter. A judgment model (Jev) is ONE provider behind the judgment
  client (`decide(class, state, questions)`), resolved from config — Jev/von/
  own-model are provider profiles (swap = base_url + api_key + model_id; tier
  gating + shadow gate unproven providers). No consumer code hard-references pi
  or Jev. Interop test: swap the harness, swap the provider — the governed
  pipeline behaves identically.
- **A record that a downstream fold/report JOINs on must carry its join key
  whenever it can reach a calibratable (outcome-bearing) state — refuse an
  unlinked record loudly, never append it as a silent orphan.** The
  `calibration_fold` in `ledger/src/fold.rs` joins each escalating judgment to the
  same job's later `ratified`/`veto` via `job_id`; if `judgment_entry` wrote
  `job_id: None`, every escalating judgment would be counted as `no_outcome`
  forever and nothing would explain the gap. So `Constitution::judgment()`
  REFUSES an escalating-but-jobless judgment (`HandleError::EscalationUnlinked`,
  nothing appended) — a loud defect with its own test (escalating+None refused,
  shadow/proceed+None ok, escalating+Some linked). General rule: when you add a
  fold or report that links records by a key, make the WRITE of that key
  fail-closed for the records the fold depends on, and give the missing-key
  error a distinct variant so the caller sees WHY, not a generic failure.
- **Verify a peer's cited docs exist on THIS checkout before propagating them.**
  A parallel agent/Opus may cite `steward-tui.md`, `baml-evaluation.md`, or a
  commit hash that live only on its own branch/worktree, not `main` — `search_files`
  for the cited path before baking it into a doc, and cite the real source
  (`core-interface.md` §7/§8 held the TUI and "judgment runs as a governed
  worker" rules here) instead of the phantom one.
- **A governance verb (stop/veto/direct) must never hard-code a `job_id`, `seq`,
  or `ts` — it targets the job the caller actually holds.** The Steward TUI's
  `stop()` shipped `job_id: "job-1"` with a fixed `seq: 1` and a constant `ts`;
  since the TUI's job counter starts at 2, the emergency stop fired at a job
  that was never commissioned. Track `current_job` + a per-job sequence in the
  client state, timestamp with a now() helper, and keep that logic in the
  crate's `lib.rs` (testable without a terminal) rather than in the interactive
  `main.rs` rendering loop. When fixing a client/TUI bug, extract the pure
  decision into the lib so it can be TDD'd; the rendering loop should only wire
  I/O and input.

## The doc-corpus shape (current vs historical) — keep it this way

The corpus is organized so a PM, a builder, and an auditor each get an ordered
reading path, and no reader has to guess what is current:

- `docs/README.md` is **the map and the ONLY index** (never create a parallel
  `DOCS-INDEX.md`): three reading paths, a `Status` on every current doc, "the
  system in one screen", and a current-vs-historical table.
- **Every current doc opens with one line:** `> **Status:** <…> **Audience:** <…> **Pairs with:** <…>`.
- `docs/design/core-build-blueprint.md` is the **BUILD-READY v1 contract** — the
  doc stories and slices are cut from (§5 conformance tests, §6 scope line, §7
  build order). `docs/design/story-slices.md` is the **current story/slice plan**
  cut from it (vertical stories, each conformance test owned once; supersedes
  `docs/historical/story/coding-agent-story.md`). `docs/design/design-gaps.md`
  is the **open/resolved ledger** and the single place that lists what must
  close before Story 1.
- **Superseded material MOVES to `docs/historical/`** with a header saying it is
  historical, what supersedes it, and which of its ids stay canonical (e.g. the
  build-readiness review's `B-S1.x` ids).
- **Fix contradictions where they live, never annotate them:** a stale verdict
  ("NOT build-ready"), a stale count (`27 truths` when §0 has 35), or a stale
  status line ("do not write code against this") misleads every future reader.
- **Recount every number from the file that owns it; never trust a summary
  line.** A doc header claimed "15 governing truths" while `spec/core-spec.md` §0
  held 35 — count the entries in the owning file
  (`awk 'NR>=<start>&&NR<=<end>' <file> | grep -cE '^[0-9]+\.'`), then grep the
  whole corpus for every other restatement of that number so they all move with it.

Pitfalls on a **docs-only commit** in this repo (both cost a wasted cycle):
- The enforcer MAY block `git commit` claiming "changes to skills/, tests/" even
  when the diff is pure markdown — when it does, load `adversarial-verifier` and
  retry once; the pre-commit gate then reports `Adversarial verify: passed on N
  file(s)`. It is not guaranteed: a clean docs commit can reach the same gate and
  pass on the first try, so do not pre-load extra skills on speculation.
- The hook prints ~11 `DOCS AUDIT … docs/DOCS-INDEX.md was not updated` warnings
  for any docs change. They are the mismatched hermes-cortex expectation (see the
  pitfall above), **not a block** — the commit lands.

## Prototype code changes (prototype-ts)
Beyond docs, the repo ships a TypeScript prototype under `prototype-ts/` (Bun, `bun test`, frozen core = `abi.ts` + `loop.ts`). Rules for code work there:

- **TDD is enforced: RED (watch the test fail) → GREEN → full suite.** Run `bun test <file>` per cycle and the full `bun test` before commit. Verify the demo still runs: `bun run prototype-ts/main.ts --fake`.
- **Config/override convention (established):** precedence chain env var → `STEADFASTE_CONFIG` JSON file → built-in default, implemented in `prototype-ts/config.ts`. NEVER let the frozen core (`loop.ts`/`abi.ts`) read config — the core takes values as explicit options; config is worker-side plumbing that assembles them. **Fail-closed validation:** unknown JSON keys and bad numbers throw at load time — a typo'd threshold silently falling back to a default means an operator believes a limit is tighter than it is.
- **Run an adversarial boundary probe against the config loader BEFORE declaring config work done** — feed every env key the pathological inputs (`""`, whitespace-only, `0x10`, `Infinity`, `NaN`, `1e300`, fractional-for-int, duplicate list entries, empty list entries) and verify each either throws naming the key or normalizes correctly. A plain `Number()` parse accepts seven kinds of garbage that silently disable a safety limit; the probe is the only way to see what the parser actually accepts.
- **Settle the edge-case matrix in the DESIGN DOC before build, not just in code.** One rule covers every row: *a value that looks set must be set* (fail-closed — reject at startup with named key) or *a component that fails must degrade, not lie* (fail-safe — drop+counter, isolate the failing sink, never block the caller). Structure as tables per layer: config values / runtime failures / core-interface cross-refs. Luke asked for this explicitly; a design that leaves edge cases to the builder's improvisation is not settled.
- **Fixed-interval retry sleeps synchronize contenders (thundering herd) — always full jitter.** Under N-way contention a fixed sleep wakes all waiters on the same boundary and the wave grows with each collision; this is a stability bug at the 1000-agent tier, invisible at n=1. Exponential backoff with FULL JITTER (uniform `[0, cap]`, cap = `min(base·2^attempt, timeout/4)`), jitter-off mode only for debugging contention patterns. File lives as a class-level test (`lock-jitter.test.ts`) asserting cap growth + bounds.
- **Export the module-private lock/wrapper function to run a live multi-writer contention probe** — a unit test can't prove "no lost updates"; a script spinning N concurrent `withLock` writers against one state file and asserting every update landed can. One `export` keyword on the wrapper is the whole cost.
- **Technology-choice reviews for this repo: vindicate-or-fix, with the reason recorded.** Structure: (1) a table of load-bearing choices each with verdict + WHY it holds (not narratives), (2) findings FIXED this cycle with mechanism + verification, (3) observations already-owned-elsewhere recorded without action. The repo's habit of naming its own ceilings (single-writer honesty, rejected bloat with triggers, inert-until-needed) makes the audit mostly vindications — that is the goal; write the doc as `docs/design/technology-choice-review.md`.
- **Validate by VALUE TYPE, not key-by-key:** shared helpers `intEnv` (whole numbers: ms durations, run counts, tier numbers), `numEnv` (decimal rates), `fracEnv` (0–1 fractions), `strEnv` (reject whitespace-only) — each with a strict base-10 decimal regex, a magnitude guard (>1e9 rejected: a 1e300 retention value silently disables rotation), and a named-key error. Run cross-field rules (e.g. otlp sink requires endpoint) AFTER key-level parsing so the error names the real mistake, not a downstream red herring.
- **Every `.env.example` key must be actually wired** in the config loader — grep the loader for each var name before committing the example file. Document each key with: what it does, the sensible range, and which design doc pins the default. Known groundings: trust-tier thresholds → core-spec §4f / design-gaps (b); baselining → baselining-scale-ladder zero-config row; validation gates → token-efficiency §4.6–4.9; pair-review rate → cross-agent-collusion; log verbosity/retention/sinks/sampling → observability-logging §5 + §10.1 (hot/warm retention and rotation cap are the §10 growth numbers).
- **NEVER `write_file` a file you are only extending (`.env.example`, append-style edits) — `write_file` REPLACES the whole file.** Draft the new section to /tmp and `cat >> file` instead; the doc-append rule exists for the same reason. After an accidental clobber, `git show HEAD:<file> > file` to restore, then append — and verify the full key count afterwards (grep -c 'STEADFASTE_').
- **Treat trust/validation thresholds as POLICY, not tuning** in analysis: they decide how much evidence trust is earned with. Deliberately NOT configurable: ABI version, tier caps (Operators ≤2), the two-seed pair-review mechanism (only the rate is a lever — schedule unpredictability is a security property). Config-request touching those = design conversation, not a knob.
- **Before blaming your change for a failing repo test, stash and run it on a clean tree** — prototype tests can be pre-broken (test-dir import paths drifted after a repo restructure). If pre-existing, fixing it belongs in the same commit (contract rule: no known issues left unfixed), noted in the message.
- **Test isolation: reset ALL `STEADFASTE_*` env vars in a `finally` after any expected-throw config test** — a leaked bad value poisons sibling test files that load config through the store, failing them mysteriously. One `resetEnv()` helper covering every `STEADFASTE_` key; `clearConfigCache()` after every env mutation (config is cached).
- **Multi-line commit messages: write the message to a file and `git commit -F <file>`.** Inline multi-line messages in a shell tool call break on quotes/apostrophes/parens and split into bogus pathspecs.
- **After a governance gate blocks `git add A B C && git commit`, verify what actually staged before re-committing — a blocked commit can SPLIT the change.** The adversarial-verify gate can refuse the commit after the add already ran (or the add rolled back); re-adding only a subset then commits a test-only commit and leaves the source uncommitted, an intermediate HEAD that fails `cargo test`. Before retrying with a subset, check `git status` and stage the WHOLE intended set so source + test + docs land as one atomic commit. If a split already happened, repair with `git reset --soft HEAD~2 && git commit -F <msg>` to squash the fragments back into one compiling HEAD.
- **Nested heredocs inside a `terminal()`/`execute_code` string break on quoting — write the script to a file first, then run it.** A Python patcher or TS probe containing `<<'EOF'` cannot be passed as an inline shell string (the inner heredoc collides with the outer string literal); `write_file('/tmp/script.py')` then `terminal('python3 /tmp/script.py')` always works. Same for any multi-line script with backticks or `${}` interpolation.
- **For outside-expert model input on a design question, consult DeepSeek Pro via OpenRouter** — recipe and pitfalls (reasoning-model token budget, empty-content trap) in `references/llm-consult-via-openrouter.md`. Treat the answer as expert input to overlap-check, never as the design itself.
- **Fetch external APIs (GitHub org listings, raw file reads) via `browser_exec`'s
  `js()` with `fetch()`, not `terminal curl`** — a shell curl of an external API
  can sit awaiting user consent and stall the session; the browser fetch returns
  the JSON in one call. Parse the JSON in the same browser_exec call (json.loads
  of the innerText). **The `fetch` must be wrapped in an async IIFE inside `js()`
  (`js("(async () => {...})()")))` — a top-level `await fetch(...)` in the
  `browser_exec` `code` block fails with `SyntaxError: 'await' outside async
  function`, because the code runs as a sync Python exec. Use
  `raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` for raw file content
  (with `await r.text()`), and the git trees API
  (`/repos/<owner>/<repo>/git/trees/HEAD?recursive=1` → `tree[].path`) for the
  file list before deciding which files to read.
- **Split any doc write that would exceed roughly 8K tokens of arguments into a
  small initial `write_file` + successive `patch` appends** — a single oversized
  write can be cut off mid-stream and silently not land; re-read the file after
  each chunk to confirm where to continue.
- **Domain-skill write gates fire per file type: first a suggestion, then a
  hard block** (`docs/*.md` → `documentation-auditing`, repo `.py` →
  `codebase-design`). Load the named skill on the FIRST warning instead of
  retrying or switching tools — the retried write is refused outright, and
  each blocked attempt burns a cycle.

## Docs archive regeneration
On request, regenerate the portable archive under a governance cycle:
`tar czf /tmp/steadfaste-docs-<YYYYmmdd-HHMM>.tar.gz spec/ docs/ README.md`, then VERIFY the expected file is present (`tar tzf … | grep <file>`), then deliver as `MEDIA:/abs/path` in Telegram. Include both the byte size and the design-doc count in the report.

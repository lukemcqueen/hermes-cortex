# Adversarial Review — The ABI Shape

> Scope: `core/src/abi.rs`, `prototype-ts/abi.ts`, and every doc that justifies
> them. Job: attack the ABI, not affirm it. Find the flaw. Bring uncertainty back.
> Question set: (1) lineage, (2) minimal/general/stable primitives + "task" vs
> "request→steps→result", (3) policy in the ABI, (4) versioning + transport —
> plus two owner doctrines: **HITL as a first-class interface** and **a
> protective layer against hostile actors inside and out**. Verdict is one
> paragraph, at the end.

---

## 0. The finding in one line

**The ABI as written froze the wrong half.** It is not "a frozen vocabulary" —
it is Pi's agent-loop re-exported as a wire protocol, with the Governor's
volatile policy struct frozen into it, while the *control-plane primitives a
governed, safe building block actually needs* — HITL (pause-for-human, human
decides/overrides/redirects), deny, taint propagation, capability-scope — are
**entirely absent**, even though the project's own `decision.md` pre-freeze fix
#7 already demands a HITL primitive. On top of that, the "frozen ABI" does not
exist as one artifact: the Rust and TypeScript copies already disagree on four
wire shapes and cannot interoperate. The shape is the single most likely source
of a 3-year break.

Everything below is evidence for that sentence.

---

## 1. Where does "task in / 11 events / 6 ops / outcome" come from?

**It is copied from a lineage without being questioned — but not the way the
docs claim.**

The lineage is real and acknowledged: `loop.ts` says "derived from Pi's
`agent-loop.ts`", `store.ts` says "borrowed from OpenSwarm's taskState/store.ts",
`manus-openmanus-notes.md` + `design-brief.md` name Pi / OpenSwarm / Manus as the
research base. So the *frame of mind* is inherited.

But the trap is subtler: **the 11 events / 6 ops vocabulary is not copied from
anywhere — it is novel, and that is the problem.** Pi has no
`WORKER_STARTED / MODEL_REQUEST_STARTED / TOOL_REQUESTED / TOOL_FINISHED …`
frozen event set. OpenManus has a state machine (`IDLE→RUNNING→FINISHED/ERROR`),
not 11 events. The 11 events are a *transcription of the agent-loop's internal
instrumentation into a wire contract*. Every one except `WORKER_STARTED`,
`RESULT`, `FAILED`, `STOPPED` is an observability event of *one specific kind of
worker*: a turn-based loop that calls a model and then tools. The ABI has
silently assumed "a worker" = "a model + tools + turns loop" — exactly Pi's
agent-loop shape.

**The demotion was cosmetic.** `architect.md` is proud of moving `loop.ts` out of
`core/` into `workers/own-agent/` so the core "never runs a loop itself." But
then the loop's *skeleton was re-promoted into the ABI* via the event
vocabulary. A worker that is not a turn-based model loop — a deterministic shell
script, a long-running service, a sub-agent orchestrator that fans out to
children, a consultant doing human-mediated review — does not map onto
`MODEL_REQUEST_STARTED`/`TOOL_FINISHED` at all. The core claims
worker-agnosticism while its frozen vocabulary describes one worker in detail.

**Consequence:** the ABI is not "the minimal contract between a core and a
worker"; it is "Pi's agent-loop, with the function names turned into event
names." We inherited the *conceptual frame* from the lineage and, by inventing a
new vocabulary to express it, baked the lineage's specific worker model in as if
it were universal. We did not question the lineage; we *renamed* it.

---

## 2. The MINIMAL, GENERAL, STABLE primitive set — is "task" even the unit?

**No. "Task" is the wrong unit. "Steps" is also the wrong unit. The primitive
unit is a "job" — an invocation — and everything else is content, not ABI.**

The parent asks: "task", or a more primitive "request → steps → result"? Neither
is primitive enough:

- **"Task"** is a *product* concept — mission-critical objective, budget,
  deadline, "done" criterion — what a Telegram user asks for. It is the
  Governor's *output* (see §3), i.e. the volatile layer.
- **"request → steps → result"** smuggles "steps" into the contract, which is a
  Manus-style *planning artifact* belonging to specific workers. The project's
  own `manus-openmanus-notes.md` is explicit that Manus-style planning "none of
  these require touching `abi.ts`" — the plan lives *behind* the worker's
  `handle()`. Putting "steps" in the ABI would re-introduce a worker-specific
  assumption, the exact error §1 names.

The defensible primitive is a **job**: an invocation with an identity, an opaque
input, and an opaque result. The ABI knows `job_id`, not "task" or "step". The
core must speak the language of:

```
core → worker:  run(job_id, input, policy-envelope) · steer · cancel · kill
worker → core:  started · progress(opaque, typed) · result(status, opaque) · failed(class) · stopped
```

That is the whole ABI: ~5 messages down, ~5 up. The 11 events collapse into
**one** `progress` message with a registered `type` and opaque `data`, where
`MODEL_REQUEST_STARTED`, `TOOL_FINISHED`, `CHECKPOINT` become *event kinds in a
schema registry* — data, not ABI. The core's cost fold, audit, and timeline
*consume* the kinds it knows; unknown kinds are routed/stored/ignored by
contract, never a protocol break.

**The one architectural move the design has not made — and the one that makes
"90% of functionality, zero customization, still true in 2029" achievable
instead of a slogan — is to separate the frame from the content.** The ABI
freezes the *frame* (envelope: who, when, which job, what kind of thing, opaque
body). The *content* (payload fields, event-kind names, their schemas) lives in
a versioned, additive, feature-detectable registry.

**The 6 ops are not minimal either.** Of `START/SEND/CANCEL/CHECKPOINT/STATUS/KILL`:

- `CHECKPOINT` (core→worker "checkpoint now") is redundant: the worker already
  *emits* checkpoint events at safe points, and checkpoint *state* lives in the
  atomic store, not the worker.
- `STATUS` is a supervisor→store query, not a worker op; it belongs in the
  core's internal API, not the wire.

The minimal op set is **start / steer / cancel / kill**. The design's own "rule:
do not grow this casually" has already been violated by two ops that don't
belong on the wire.

---

## 3. Carrying a POLICY in the ABI — part of the contract, or smuggled?

**Smuggled — and it is the single most likely source of a 3-year break.**

### (a) The ABI freezes the one thing that is *designed* to change.

`Budget`, `ModelPolicy`, `VerificationPolicy` are the **Governor's output**. And
the Governor is explicitly *the product* — the thing business users edit, the
thing the learning loop updates, the thing that evolves ("cheapest-first
escalation", "which model, which budget"). `pm-summary.md` says the risk/cost
layer "IS the product." Then `abi.rs` freezes that product's output shape for 3
years. This guarantees churn: `max_parallel`, `max_retries`, per-tool spend caps,
per-model routing tables, escalation ladders — the project's own skills
(`cron-cost-scheduling`, `llm-cost-optimization`) already demand them. Every one
is an ABI break under the current struct.

### (b) The enforcement locus is contradictory — it betrays the core's own thesis.

The ABI *sends* `budget`/`model_policy`/`verification_policy` **to the worker**
as part of its contract. That is an instruction, not an enforcement. Who stops a
worker that ignores `max_tokens` or calls a model outside `model_policy`?

- If the **worker** enforces them, the policy is advisory — a governed core
  "asking nicely," precisely what the project's own research forbids: *"the
  model can rewrite a rules file; it cannot rewrite a harness gate."*
- If the **core** enforces them (gateway meters tokens, supervisor kills at
  deadline, gateway routes the model call, permission gateway gates tools), then
  the policy does **not belong in the worker-facing payload at all** — it is
  core-owned state, enforced *below* the worker, and the worker should receive
  only the *concretized envelope it must behave within* (which model endpoint to
  call, the "done" criterion, the workspace root).

The design does both and means neither. For a governed core, the only defensible
answer is: **policy is core-owned state, referenced by id, enforced at the
gateway and supervisor; the worker receives a capability envelope, not the
policy object.** Governance lives below the model — the project's own rule — which
means the numbers the worker can't override should never be in its hands at all.

---

## 4. Versioning: what makes an ABI trustworthy for a decade? Is JSON-over-stdio right?

### Additive-only is necessary and insufficient. Capability negotiation is the missing piece.

The current strategy — "add a new type alongside the old; 3-year freeze" — is
weak for a decade, for a concrete reason: **additive-only without discovery
can't be used.** A 2029 core speaking "v1 + 47 additive fields" cannot tell
whether a 2026 worker honors field #12. So additive-only forces either (a)
lowest-common-denominator forever or (b) version pinning (which defeats the
"2026 worker works in 2029" promise).

A decade-trustworthy ABI needs a **handshake with capability lists**, not a
version integer. The worker declares which ops it accepts, which event kinds it
emits, and — per the security doctrine — its *capability-scope* (what it may do)
and its *forced-HITL* action classes. The core declares the same. Both
feature-detect. The `abiVersion: 1` integer in `WorkerSpec` is a coarse
match-or-refuse gate — it is not negotiation, and it cannot carry "I emit event
kind X but not Y" or "I require approval for action class Z".

**The two-axis rule that actually survives a decade:**

1. **The frame** (envelope + transport + lifecycle + handshake) is frozen and
   must *never* break. It increments its version only on a genuinely breaking
   change, which must be *negotiated at handshake*, never silently assumed.
2. **The content** (payload fields, event-kind names, their schemas) is a
   **registry with per-schema versioning, additive-only, never-removed** — and
   *unknown content is ignorable by contract*, written into the conformance
   suite and fuzz-tested.

This is how protobuf/gRPC, Cap'n Proto, and JSON:API achieve decade-scale
stability. The current design is trying to get it from a single frozen Rust
enum — which cannot work, because **the enum *is* the content.** A frozen enum
of 11 events freezes the telemetry; a frozen struct of `Budget` freezes the
product. The frame/registry split dissolves both.

### JSON-over-stdio: right for the frame, wrong as the schema.

Challenged honestly: **JSONL-over-stdio is the correct transport for a
building-block core.**

- **Lowest common denominator.** A Rust core, a TypeScript worker, a Python Pi
  worker, a shell-script worker — every one speaks JSONL with zero runtime
  dependency. That is exactly what "Claude worker, Pi worker, integration,
  consultant" requires. gRPC/protobuf and Cap'n Proto force a binary runtime dep
  and kill the "readable / one language seam for humans" north star.
- **Debuggable and auditable.** You can `cat` a session; an NDJSON event log is
  its own replay archive. This *serves* "visible / journal-as-truth" rather than
  fighting it.
- **Its weaknesses are irrelevant at agent rates.** No binary efficiency (an
  agent does ~1 model call/sec, not 100k msg/sec), no schema validation (bolt on
  JSON Schema, which the project already does), no in-frame streaming of huge
  payloads (tool output is truncated to `max_observe`).

So the thing to challenge is **not the JSON — it is freezing JSON-shaped
*content* as a single enum.** JSON is the encoding; the flaw is treating the
encoding's schema as the contract. JSONL-over-stdio and a frame/registry/
negotiation discipline are orthogonal — you can have both.

**Two encodings, one frame.** The design already has stdio JSONL (worker seam)
and SSE/NDJSON-over-HTTP (`GET /v1/events`). Keep both, and make explicit that
they are *two encodings of the same frame*, sharing one registry. Liveness stays
out-of-band (process death + stall timeout), as the party already decided — no
heartbeat in the ABI.

---

## 5. The concrete defect: the "frozen ABI" does not exist as one artifact

Before any of the above philosophy matters, there is a blunt, checkable finding:
**the Rust and TypeScript copies of "Worker ABI v1" already disagree, and the
Rust side is not even a stable wire format.** A foreign worker implementing
"Worker ABI v1" today would have to pick one, and would be wire-incompatible
with the other.

| Field / shape | Rust | TypeScript | Wire-compatible? |
|---|---|---|---|
| `Budget` | 4 fields, **includes `max_deadline_s`** | 3 fields, **no deadline** | **NO** — story 1.1 already flags deadline as a missing pre-freeze gap; the TS side is stale |
| `WorkerEvent` tagging | `#[serde(untagged)]` — field-sniffing, **no `type` field on the wire** | explicit `type` discriminant | **NO** |
| `TaskOutcome` | untagged enum → `{"COMPLETED":{…}}` (externally-tagged) | `{status:"completed", …}` | **NO** |
| `StopReason` | `Cancelled`/`Budget`/`Interrupted` (PascalCase) | `"cancelled"`/`"budget"`/`"interrupted"` (lowercase) | **NO** |
| `ModelPolicy.fallback` | `Vec<String>` (required) | `string[]?` (optional) | borderline |
| `WorkerOperation` | `tag="op"`, lowercase | `op: "start"…` | yes (the one that agrees) |

Two of these are not cosmetic:

1. **`#[serde(untagged)]` on `WorkerEvent` is a footgun and the opposite of a
   decade contract.** Untagged deserialization tries each variant in order and
   matches on field-name sniffing — ambiguous (`FAILED {error}` vs
   `STOPPED {reason}` vs `PROGRESS {message}` all look alike to a sniffer) and
   order-dependent. A stable wire format has an explicit discriminant. The TS
   side does it right; the Rust side does it wrong. And because it's untagged,
   a Rust core cannot even *read* a TS worker's frames (the `type` field is an
   unknown key to every variant). The two "same" ABIs are not interoperable.
2. **There is no single source of truth.** The ABI is defined twice, in two
   languages, by hand. That is a conformance *bug*, not a conformance *suite*.
   A decade promise cannot survive on a hand-synced enum in two files — it needs
   one canonical schema (JSON Schema, code-generated into Rust *and* TS) or a
   conformance test proving the two serializations are byte-identical across
   every variant.

**This is the most damning finding and the cheapest to fix now: before the
freeze, the ABI must become one schema, and the Rust/TS divergence closed.**
Sections 1–4 are design corrections; this one is a defect in what already exists.

---

## 6. Owner doctrine 1 — HITL must be a first-class interface

**The current ABI cannot express "pause for a human." At all.** There is no
`needs_human` event and no `human_decided` operation in `abi.rs`. The worker has
no way to ask for judgment, and the human has no way to interrupt a running job
with a new directive. Yet the party's own `decision.md` pre-freeze fix #7
demands: *"HITL approval primitive frozen into the ABI
(request/approve/deny/timeout) or plugins will fake approval."* The design has
already ruled HITL-in, and the "frozen" ABI shipped without it — proof the freeze
was declared before the fixes landed.

The owner doctrine is stronger than fix #7: HITL is not an approval bolt-on; it
is a *quality* property. The human must have visibility and the ability to
modify/update/override **at every point** models are flawed. That means three
first-class, frozen, negotiated verbs:

| Primitive | Direction | Meaning |
|---|---|---|
| `needs_human` | worker → core | **"Human judgment needed here."** Pauses the job; carries `reason`, `scope`, and the exact action awaiting approval. |
| `human_decided` | core → worker | **"The human decided X."** approve / deny / override / redirect. |
| `direct` | core → worker | **"A human interrupted you with a NEW directive."** Not a reply to a pending request — a mid-flight override. This is the "task interrupted by a human with a new directive" primitive. |

**The asymmetry that makes HITL unforgeable:** the *request* is strictly
worker→core (the worker can ask, and only ask), and the *decision* is strictly
core→worker. The worker **never** emits `human_decided`. The human sits behind
the core; the core relays an *authenticated* decision (operator identity + a
nonce/scope binding verified against the operator registry) down to the worker.
If `human_decided`/`direct` could be emitted by the worker, then the worker — or
injected content masquerading as the worker — could forge an approval, which is
precisely the "plugins will fake approval" failure fix #7 names. HITL is only
real if the *sender* is authenticated as a human operator, not the worker. The
verb direction enforces that at the type level.

**Why this is a building-block primitive, not a feature:** any worker (Claude,
Pi, shell script, consultant), any integration, any transport — every one must
be able to *pause and ask* and *be redirected*, because every model-driven
worker has exactly the same flaw (unreliable judgment) that HITL is the
antidote to. It is as universal as "start" and "result", and belongs in the
frozen frame for exactly that reason.

---

## 7. Owner doctrine 2 — a protective layer, native to the ABI

The ABI is the boundary hostile actors cross. The owner's requirement is that
the frozen contract carry security as a first-class interface — not bolted on,
not in a "please don't" prompt, but expressible in the wire. Four protective
primitives are missing from `abi.rs`:

### (a) Taint propagation — the prompt-injection defense.

Any untrusted input — a task from a chat user, tool output, retrieved content,
model deviance — must be **marked** at the boundary where it enters, and the
marker must **ride with the message** through the system. The frame carries an
`untrusted` field:

```
untrusted: { origin: "user"|"tool"|"retrieved"|"model", chain: string[] }
```

The rule, enforced by the core and stated in the contract: **tainted content can
be *processed*, never *trusted as instruction*.** The core refuses to treat
tainted bytes as an operator directive, a permission grant, or a policy change.
Prompt injection is exactly "untrusted content masquerading as an instruction";
taint is the machine-readable wedge that separates "operator instruction" from
"content that merely looks like one." Without it, the ABI cannot even *express*
the project's own research finding (IssueTrojanBench: the model rewrites its own
rules file) — the whole defense collapses to prose.

### (b) `deny` — a frozen refusal verb.

The core must be able to *refuse* an action at runtime: block a tool, a model
route, a plugin. Currently "deny" is an implicit gateway rejection with no wire
expression. Make it a frozen verb (`deny` core→worker, with `reason` and
`subject`), so a refusal is a *first-class, auditable, replayable event*, not a
silent drop. This is the difference between "the worker tried X and it silently
didn't happen" and "the worker tried X and the core recorded the denial."

### (c) Capability-scope — negotiated at handshake, enforced at the gateway.

At connect, the worker declares what it may do (tool classes, model routes,
network egress) and which action classes are `requires_approval`. The core
declares the same. Two consequences:

- Any action **outside the negotiated scope → `deny`**, mechanically, below the
  model.
- Any action marked `requires_approval` → the worker emits `needs_human` and
  blocks until `human_decided`. This is **forced-HITL** expressed natively: a
  risky op *cannot* proceed without a human, and the worker cannot silently skip
  the gate because the gate is the core's, not the worker's.

This replaces "send policy to the worker as a suggestion" (the §3 failure) with
"negotiate scope at connect, enforce at the gateway, express refusal as a frozen
verb." Capability-scope is the same primitive for a consultant worker ("may read
this repo, may not push") and a hostile poisoned worker ("declares scope X, tries
X+Y, gets `deny`").

### (d) Malicious-task rejection — at intake, before the worker exists.

A task must be validated against policy at the intake gate: unrecognized
objective shape, no standing from the requester, an injection-carrying
objective, a budget over policy max. Rejection is a **core-side lifecycle event**
(`job_rejected`, with a reason class) — the worker never sees the malicious task
at all. This is the difference between "the worker was handed a poisoned
objective and asked to execute it" and "the poisoned objective never reached the
worker." The worker should only ever receive validated, tainted-flagged jobs.

---

## 8. The most defensible ABI (concrete proposal)

Given all of the above — the four questions *and* the two doctrines — the
defensible shape is: **a frozen frame + a content registry + a capability
handshake**, over JSONL-stdio (worker seam) and the same frame over HTTP/SSE
(external surface). HITL and security are **frozen control-plane verbs**, not
features; telemetry is demoted to **content**.

**The frame (the only thing frozen for a decade):**

```
{ "v": 1, "kind": "op"|"event"|"handshake"|"error", "job_id": string,
  "seq": uint64, "ts": ISO-8601, "type": string,
  "untrusted": { "origin": string, "chain": string[] } | null,
  "data": object }
```

`v` is the *frame* version. `type` is a registered, independently-versioned
schema name. `data` is opaque to the frame. `untrusted` propagates taint across
every message. Unknown `type` → route/store/ignore, never break.

**Handshake (capability negotiation + scope, on connect):**

```
→ { "kind":"handshake", "role":"worker",
    "ops":["start","direct","human_decided","deny","cancel","kill"],
    "events":["started","needs_human","progress","result","failed","stopped"],
    "progress_kinds":["model.request_started","tool.finished","checkpoint", …],
    "scope": { "tools":[...], "models":[...], "network":false },
    "requires_approval":["shell","git.push","network"] }
← { "kind":"handshake", "role":"core", "ops":[…], "events":[…], "progress_kinds":[…],
    "scope":[…], "requires_approval":[…] }
```

**Ops (core→worker):** `start` · `direct` (human interrupt with new directive) ·
`human_decided` (approve/deny/override/redirect, authenticated) · `deny` ·
`cancel` · `kill`.

**Events (worker→core):** `started` · `needs_human` (pause, reason + scope) ·
`progress` (registered sub-kinds) · `result` (status + opaque result + evidence
refs) · `failed` (error + `failure_class` ∈ {context, constraint, verification,
planning, other}) · `stopped` (reason). The 11 current events become `progress`
sub-kinds — `MODEL_REQUEST_STARTED`, `TOOL_FINISHED`, `CHECKPOINT` all still
exist and drive cost/audit/timeline folds, but they are *data*, not ABI.

**The job payload (out of the ABI, into a versioned content schema):**

```
start.data = {
  objective: string,
  input: {…},              // opaque, schema-versioned
  policy_id: string,       // reference to core-owned Governor output — NOT the policy itself
  envelope: {              // the instantiated bounds the worker must behave within
    model: {provider, model},        // the one route the core chose
    done: {…},                       // the checkable "done" criterion
    workspace: string
  }
}
```

`budget`, `model_policy`, `verification_policy` are **core-owned state**
(enforced at the gateway/supervisor, below the worker), referenced by
`policy_id`, free to evolve without touching the wire.

**Why this survives a decade:** the frame never changes; the content grows
additively and is ignorable-if-unknown; peers negotiate capabilities *and
scope* instead of pinning versions; the volatile product surface (policy) is out
of the contract; the telemetry surface (event kinds) is data, not shape; and the
two owner doctrines — HITL and the protective layer — are frozen control-plane
verbs that any worker or integration can speak natively. This is the only shape
under which "a 2026 worker still connects in 2029" is a *mechanism* rather than
a hope.

---

## 9. Design consequences (cheap now, ruinous after freeze)

1. **Close the two-file divergence first.** One canonical ABI schema (JSON
   Schema), code-generated or conformance-tested against both Rust and TS.
   Replace `#[serde(untagged)]` with an explicit discriminant. A defect, not a
   design choice.
2. **Split frame from content.** Freeze only the envelope; move payload fields
   and event-kind names into a versioned, additive, ignorable registry.
3. **Remove policy from the worker payload.** `policy_id` + behavioral envelope
   in; `budget`/`model_policy`/`verification_policy` out (core-owned, enforced
   below the worker).
4. **Cut the ops from 6 to 4** (`start`/`steer`/`cancel`/`kill`) — and add the
   four HITL/security verbs (`direct`/`human_decided`/`deny`/`needs_human`).
   Net: more *control*, less *telemetry*, on the wire.
5. **Add a capability handshake** (ops + events + `scope` + `requires_approval`),
   and write "unknown content is ignorable" into the conformance suite as a fuzz
   test.
6. **Add `failure_class`** to `failed` — the research's 4-way taxonomy is a
   universal primitive every worker can emit and every core can route on.
7. **Make taint a frame field, not a content field** — it must propagate across
   every message, so it rides the envelope. Write the "tainted content is never
   trusted as instruction" rule into the conformance suite.
8. **Keep JSONL-over-stdio + SSE-over-HTTP as two encodings of one frame.** Do
   not switch to a binary/runtime-dep transport; the JSON is not the flaw, the
   frozen enum is.

---

## Verdict

The ABI is the weakest link in the keystone, and in its current form it fails
every test the project set for itself — including the two that matter most. It
is not a questioned abstraction: it inherited Pi's *conceptual frame* ("a worker
is a turn-based model+tool loop") and re-expressed that frame as a novel
11-event vocabulary, so the agent-loop that was proudly demoted out of the core
was silently re-promoted into the ABI as frozen telemetry — freezing the one
worker shape a building block must not assume, and freezing the Governor's
*volatile* output (budget/model/verification policy) while leaving the *stable*
transport frame implicit and shipping that policy to the worker as an
instruction the core claims to enforce. Worse, it is not even one thing: the
Rust and TypeScript "same" ABIs already disagree on four wire shapes, including
an `untagged` enum that cannot parse the other side's frames, so today no
foreign worker could implement "Worker ABI v1" without choosing a side. And
most decisively for the owner's doctrine, the "frozen" contract **omits the
exact control-plane primitives a governed, safe building block needs**: no
`needs_human` pause, no authenticated `human_decided`/`direct` for
human-override-with-a-new-directive, no `deny`, no taint propagation, no
capability-scope — despite the project's own `decision.md` fix #7 already
requiring HITL in the ABI, proving the freeze was declared before the fixes
landed, on the wrong half of the contract. The fix is not cosmetic: collapse
the ops to start/direct/human_decided/deny/cancel/kill, collapse the eleven
events into a `progress`-typed registry plus `needs_human`/`result`/`failed`/
`stopped`, move policy out of the payload into core-owned state referenced by
id, put taint in the frame and capability-scope in the handshake, and replace
"additive-only freeze" with a **frozen frame + versioned ignorable content +
capability/scope negotiation** over JSONL-stdio — because a decade of
dependability comes from freezing the *envelope and the control-plane verbs*
while letting the *content* evolve, and the current design has it exactly
backwards on both axes. Do not freeze this ABI. Freeze the frame, freeze the
HITL and deny/taint/scope verbs, then let everything else negotiate.

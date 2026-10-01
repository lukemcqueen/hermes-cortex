# Steadfaste — The Covenant (core specification)

> **The authoritative contract.** A covenant is a promise beyond the legal — a
> bond of **trust**. **Trust is the core of the core.** This is the frozen
> agreement between the **Constitution** and every **Agent** and **Steward** that
> joins it: the promises they make to each other so the system can be depended
> on. *Corrected by the adversarial attack*
> (`docs/design/core-under-attack.md`). Built against this number: the "one
> thing" done well.
>
> **Reader's guide (no tech needed):** a business owner should get, from the
> words alone, what each component is and how they interact. The story in one
> sentence:
>
> *You give the **Agent** a **Mandate** (one job's orders). The **Constitution** —
> the dependable core — enforces it inside the **Charter** (the rules you set:
> what it may spend, touch, and approve). When unsure, the Agent **seeks
> guidance** and a human **Steward** **ratifies** or **vetoes**. Every step is
> recorded in the **Ledger**. It holds together by a **Covenant** of trust — and
> we verify everything before we trust it.*
>
> (See `spec/covenant-vocab.md` for the full vocabulary + what stays as-is.)

> **Status:** DESIGN, post-attack — deliberately NOT yet frozen. The covenant's
> messages and schemas are the next thing to settle and test. Do not write code
> against it until the covenant is finalized and the conformance suite passes.

## 0. Governing truth (from the attack)

1. **The model is almost never the problem — the harness is.** The Constitution's
   job is to make a variable model dependable, visible, and governed — by
   keeping its promises.
2. **The Steward (human) is the only trustworthy quality signal.** Trust is
   complete only with a human: grade + mandatory post-mortem on failure +
   override on any judgment. Auto-eval is a trigger/floor/defense, never a
   training signal.
3. **Control flows one way: Steward → Constitution → Agent.** The Constitution is the
   trust boundary and the security boundary. A jailbroken model, poisoned agent,
   or hostile actor cannot break the covenant from inside.
4. **The Constitution certifies only what is provable.** It never certifies a lie;
   judgment routes to a Steward who owns the residual risk.
5. **Trust, but verify.** The Covenant is a bond of trust *and* a vow to verify:
   we trust the Agent and the model, but the Constitution still verifies every
   claimable step — a gate for determinism, a Steward for judgment, a security
   check for trust. Trust opens the door; verification checks what walked
   through. "Trust but verify" is baked in, not optional.

## 1. The Constitution (the dependable core)

A minimal, frozen center that speaks only the Covenant. Owns:

| Concern | The promise |
|---------|-------------|
| **Job lifecycle** | a job (invocation) → Mandate → execution → result, or retry/heal. Exactly-once at the effect level (Ledger of intent). It never silently vanishes. |
| **Mandate (Constitution-owned)** | the Charter's decision (budget, model, tools, approvals) is Constitution state referenced by `mandate_id`, never smuggled into the Agent. |
| **Verification** | certifies only deterministic + security gates with reproducible evidence; a five-tier status, never a bare "done". |
| **The Steward** | first-class: seek-guidance and ratify, so any Agent speaks it; the Steward is the sovereign override + anti-bad-actor gate. |
| **Protective layer** | veto-list, least-privilege, trust-taint propagation, tamper-evident Ledger, consent gates — mechanically below the model, unrewritable by it. |
| **Security** | the Constitution is the security boundary INSIDE (hostile model/plugin/poisoned corpus) and OUT (malicious input, injection, malware). |

## 2. The Covenant (the shape of the promise)

A covenant is held in language both sides can read as promises — with security
and human judgment native, and a stable "frame" around every message. NOT yet
frozen; this is the shape to finalize.

- **Frame:** `{ version, kind, job_id, seq, ts, type, trust: trusted|untrusted, data }`
  — JSONL-over-stdio.
- **What the Constitution says** (to an Agent): `commission` · `direct` (a
  Steward's new course) · `ratified` (a Steward's decision) · `veto` ·
  `cancel` · `stop`.
- **What the Agent says** (to the Constitution): `started` · `seeks_guidance` ·
  `progress` · `result` · `failed(+reason)` · `stopped`.
- **Breached** is reserved: an Agent *breaches* the covenant only on a *trust*
  violation (protective layer), never on a routine failure. Routine failure is
  `failed`, expected + retried. Distinguishing them keeps the language honest.
- **Mandate** is Constitution-owned and referenced by `mandate_id` (never carried as
  a frozen instruction).
- **Trust natives:** every inbound message is marked `trusted` or `untrusted`
  (taint); the Constitution can `veto` a capability; a capability/scope handshake
  opens a run; a seek-guidance and a ratify are unforgeable (the Agent only
  *asks*; the Constitution relays an *authenticated* Steward decision).
- **Interoperability is non-negotiable:** the Rust core (Constitution) and the TS
  Worker it wraps (as an Agent) must agree on one wire shape — a conformance
  suite proves the covenant is held; a disagreement is a build failure.

## 3. The verification contract (five-tier, honest)

The Constitution speaks one of five, never a bare "done":

| Status | Meaning | Who decides |
|--------|---------|-------------|
| `VERIFIED_BY_GATE` | a named deterministic gate ran + oracle passed + security clean | machine (provable) |
| `REJECTED_UNTRUSTED` | a security gate blocked (malware/injection/secret/veto-list) | machine (hard-block) |
| `RATIFIED` | a Steward accepted the judgment outcome (logged, overrideable) | Steward |
| `UNENDORSED` | no gate covered it — fails closed toward a Steward | Steward (default) |
| `UNDECIDABLE` | no test exists / can't prove — explicitly marked unprovable | honest declination |

## 4. The Steward — a first-class promise-holder

- The Steward can **halt / direct / override** a run at any judgment point.
- The **override is the strongest learning signal** (location-tagged "the model
  was wrong here").
- **Post-mortems on failure are mandatory and involve a Steward**; successes get
  *sampled* Steward review (or the loop loses positive evidence).
- The Steward is the one element that can tell an *attack* from an *error*.

## 5. The learning loop (out of the core, Steward-gated)

- **Self-heal** (deterministic: cost, timeout, retry, exactly-once) — core.
- **Self-learn** (model/plan/template improvement) — peripheral, human-scaled:
  lesson memory is provenance-gated (unvetted lessons inert); the Charter
  updater is a *clerk, not a judge*; it cannot edit its own trust boundary.

## 6. Acceptance (what makes the covenant "done")

It is DESIGN until:
- [ ] The Covenant's messages (operations/events/frame/trust natives) are
      finalized and the Rust core + the TS Worker (as Agent) agree on the wire
      (conformance suite passes).
- [ ] The verification contract (five-tier) is implemented; a "done" without a
      real gate + evidence is impossible.
- [ ] The Steward + protective layer are first-class (halt/override/veto/
      trust/least-privilege all work through the Covenant).
- [ ] The evidence/usage/security gaps the attack found in the tree are closed
      (no theater: verification actually runs, evidence populated, no path
      certifies untrusted output as good).

Until then the core is not built; it is being *designed with integrity*. That
is the promise that makes it a covenant.
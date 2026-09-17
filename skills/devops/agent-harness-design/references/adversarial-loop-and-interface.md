# The in-loop adversarial reviewer, its budget discipline, and the surface interface

Three net-new governance patterns for a governed agent harness, all settled via
deepseek-pro party. Keep these as the durable design; they compose the
`governance-trust-principles.md` trust stack and the Wire contract.

## The adversarial reviewer is a LEVELED mechanism in the loop, for ALL work streams

Not a fixed external judge and not a persona: **every claim meets an attempt to
break it before it is accepted** ("assume it fails until proven otherwise;
only what survives refutation is done"). It runs INSIDE the agentic loop for every
work stream. Levels, by refutation depth and cost:

| Level | Refutes | When |
|-------|---------|------|
| L0 self-check | the agent's own claim vs the standard | low-risk, routine |
| L1 gate | the provable (deterministic, recompute) | most work |
| L2 independent reviewer | maker/checker — a second agent re-derives + diffs | uncertain / judgment |
| L3 expert + human | Expert Evaluator polices the unprovable; Steward ratifies | unprovable / high-risk |

The level is chosen **automatically** (`effective_tier = min(agent, model)`, risk
class, task-type fit, provability, budget) **or by a config lever**
(`adversarial_level`). It is a doctrine + a level, NOT a new actor — it composes
the existing gate/evaluator/checker/Steward. This is what "trust but verify"
means once elevated: trust nothing until it's been attacked and survived.

## The loop must be BUDGET-AWARE — it stoops honestly, it never gambles

A loop whose only exits are pass/fail silently burns the whole run budget
re-attempting one unpassable claim. Give it its own budget discipline:

- **Bounded decaying retries.** A per-claim retry pool capped at ~2× the first
  adversarial cost; each re-attempt of the SAME claim costs less by geometric
  decay (e.g. ×0.5) to a floor; a hard ceiling (~5 retries). 10 failures cost a
  bounded total, not 10× full cost. Escalation to a higher level resets decay to
  that level's full cost (so the shared pool drains faster on expensive
  escalation — correct).
- **Failure-classed retry.** The reviewer's failure carries a class that decides
  retry: `COMPETENCE` (a fixable bug — retry, decaying) · `PROVABILITY_GAP`
  (unprovable — NEVER retry, honest-stop `UNDECIDABLE`; you cannot re-attempt
  your way to provability) · `SECURITY_BLOCK` (a covenant violation, not a retry
  — escalate to the Steward) · `OVERCLAIM` (one L3 expert pass, then a second is
  a willful flag) · `BUDGET_EXHAUSTED` (self-explanatory).
- **Level-aware escalation.** Escalate only on evidence (never twice on the same
  claim without a new fix); after a fix, DROP to L0 for a cheap re-check.
- **Continue/stop predicate every iteration** — afford-and-expected-value: "is
  another try worth the remaining pool?" (p_pass = historical fix rate /
  declining with attempts).
- **Honest exits.** The loop terminates into the five-tier statuses, never a
  silent budget death: `VERIFIED_BY_GATE` / `REJECTED_UNTRUSTED` / `RATIFIED` /
  **`UNENDORSED`** (pool exhausted / not worth it / L3 terminal / gateway cap —
  with a recorded post-mortem) / **`UNDECIDABLE`** (can't prove — honest
  declination, a deliverable in itself: "here's what we couldn't prove, why,
  human decide"). Each terminal stop records a post-mortem (what was tried, at
  what level/cost, failure class, why it stopped).
- **Separate `claim_retry` from `product_work`.** The loop may re-check or
  correct in place but CANNOT spawn a product subtask to fix underlying code —
  that is the Steward's / a parent task's call. Otherwise retry→fix→retry is an
  unbounded budget drain. Boundary test: does the fix require a tool call that
  modifies code outside the claim artifact? Yes → stop + recommend; No → retry.
- **Operator visibility.** Surface a live `CLAIM_RETRY_STATUS` (level, attempts,
  cost so far, pool, failure class, next action) as a `ledger_fold` projection so
  a stuck loop is seen, not hidden.
- **Compose with one budget ledger.** The run-level hard cap (a Constitution
  gateway meter, `total_spent + reserved ≤ hard_cap`) is the single source of
  truth; the claim pool is a sub-allocation inside its `reserved_usd`. The loop is
  the governor (this claim ≤ X); the gateway is the enforcer (the run ≤ Y). No
  duplication.

## Loop budget is a REPUTATION signal — fewer loops means smarter code

How much a model loops is a tell of judgment, not just waste. Track it as an axis
in the Model Reputation Library (a free `ledger_fold` aggregation — the data is
already recorded): average retries per claim, loop $ per task, escalation rate,
**at-first-pass rate** ("no loops = smarter code"), and the failure-class mix
(more OVERCLAIM/SECURITY = worse judgment). A first-try model is favored for
budget-sensitive work and earns a tier faster; a chronic looper is
reproval-burdened and routed away.

## The Core Interface — the surface contract is the moat, not the TUI

Strategic position (the product is the CORE + its interface, never the TUI nor
the ecosystem): expose ONE stable, versioned surface contract between the core
and ANY external front-end, so plug-and-play is real without owning every TUI.

- **Adopt the plumbing, build the semantics.** Use ACP (Agent Client Protocol —
  JSON-RPC 2.0 over stdio/WebSocket/SSE, session lifecycle, event stream,
  capability handshake) as the transport; NEVER invent a transport DSL. What is
  OURS (the moat) is the semantic vocabulary spoken over it: granular-data
  objects, governance drive verbs, and the authority model. Same discipline as
  the Wire: freeze the envelope, grow content additively.
- **Granular-data objects** (Ledger/state-derived VIEWS, never a second source
  of truth): `Session` (attribution, trust tier, levers snapshot, budget),
  `PromptState` (effective system + step prompt, per-model overrides,
  verbosity, adversarial level, context window), `StepState` (live loop: claim,
  level-in-play, retry pool, failure class, confidence), `Checkpoint`,
  `Usage`+`LedgerFold` (surfaced WITH its seq range — discrepancy = `DISCREPANT`
  alert, same rule as the Operator), `TrustState`.
- **Governance drive verbs** — each translated by the Constitution into a Wire
  verb + Ledger append, NO bypass: `commission`, `ratify`, `veto`, `direct`,
  `stop`, `resume`, `set_lever`, `inject_prompt`, `checkpoint`,
  `emit_user_message`.
- **Authority model** — capability-separated, negotiated at handshake,
  mechanically enforced by the existing gate: `observer` (read-only) ·
  `partner` (read + commission) · `steward` (full — our own TUI). One gate, two
  front doors (Worker over the Wire; TUI over the Core Interface) = no
  TUI-shaped hole through the protective layer.
- **TUI scope is deliberately good-enough-and-customizable, NOT best-in-class.**
  The core + interface is where the energy goes; a better third-party TUI on the
  interface is a win for the core, not a threat. Anti-bloat test at the TUI:
  "would a Steward govern worse if this feature didn't exist?" If no, cut it.
- **ACP = door in** (a TUI drives the core); **MCP = door out** (the agent
  reaches tools) — do not conflate; MCP is not the TUI surface.

## Overlap note

The budget-aware-loop behavior is the operationalization of the calibrated-
validation + trust-tier principles (`governance-trust-principles.md` §13) and the
leveled reviewer extends the S1-closure "arithmetic not a new actor" rule to the
loop itself. Keep this file as the loop/interface depth; keep the trust stack in
`governance-trust-principles.md`.

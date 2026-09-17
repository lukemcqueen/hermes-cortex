# Governance & trust-layer principles for an agent harness

The load-bearing principles of the governance/trust layer (the "Covenant"),
generally applicable when authoring any governed agent harness. Keep these as
the spine when the user iterates on the covenant; the words are settled but the
principles are the durable content.

## The trust stack (the protective layering, in order)

1. **Trust** — the covenant is a bond of trust first; "trust is the core of the
   core."
2. **Verify** — never a bare "done"; a five-tier gate (determinism → judgment →
   human) means "trust but verify" is baked in, not optional.
3. **Record the truth** — the **Ledger** is the only record of what was true at
   any point. Capture every decision + what led to it (even when the agent is
   "sure"), so any result, good or bad, can be re-created consistently.
4. **Rehearse before real change** — trusted dry runs: run the change against a
   safe shadow, verify + record the rehearsal itself. "Dry run passed" carries
   no weight unless it was verified and recorded. Cost is acceptable when
   assurance is given.
5. **Stop everything** — an emergency stop halts ALL Agents/Workers, near-
   instant, sovereign (does not ask permission), recorded, resume only by
   explicit choice. A governed system you cannot stop is not governed at all.
6. **Require appearing** — keep-alive is a duty, not a liveness ping. An agent
   must check in + document on a required cadence; a silent agent is
   *suspicious*, not missing. Silence is a breach.
7. **Detect willful breach + grade trust** — see the two sections below.
8. **Catalog models** — a Model Reputation Library is **data gathering, not
   enforcement**: it identifies and marks with verified evidence (Ledger,
   probes, post-mortems), never bans. Model × permutation (version/provider/
   params/adapter) is the grain — a breach is confirmed at a specific
   permutation, not the whole family.
9. **Learn how to use each model — and when not to.** Beyond cataloging *what a
   model is*, the system learns, through experience/testing, *how to get the
   most out of it* (a per-model playbook: prompt structure, tools, parameters,
   verification demands, task-type fit, cost profile) and *its limits*. Routing
   sends each task to the best-fit model within budget; where the record says
   "don't use this for X," route around it (to a fitting model, the Steward, or
   an honest decline). **Not using a model for the wrong thing is often the
   single biggest win** — it prevents a guaranteed-bad outcome before it
   begins. The playbook recommends; it never guarantees (always
   Steward-overridable).
10. **Pin Steward levers to every run.** A Steward is ultimately responsible, so
    holds levers (budget, risk appetite, cost posture cheapest↔best, model
    policy, verification demands, approval points) and is free to choose
    cheapest for some tasks and best-regardless-of-cost for others. Every run
    **snapshots its full lever state at commission** (never retro-changed), so
    each run is self-describing and the post-mortem becomes a **research
    instrument**: outcomes studied as a function of the levers that produced
    them ("did cheapest actually win for this task type?").
11. **The Operator watches the day; the Steward decides.** The Operator is a
    **role, not a species**, for in-flight fleet observability (all runs in a
    day: cost, success, progress, health, per-Steward — tied to KPIs for
    management/reporting). It may be a human OR an **agentic analytics agent** —
    itself a governed Agent whose whole Mandate is observation/reporting
    (read-only Charter, earns a trust tier, evidence-backed reports, own willful
    breach detectable like any agent's). It is read-only: no lever or halt
    authority (emergency stop stays Steward/protective-layer). The automated
    governed operator is what makes always-on observability practical at scale.
12. **Expert Evaluator — police what cannot be checked.** The gates catch what is
    *provable*; the highest-risk enterprise decisions are exactly the ones with
    no mechanical check (architecture, strategy, business risk, design judgment,
    regulatory interpretation) — and those are where a model is MOST prone to
    confident-sounding wrongness (no test embarrasses it). A dedicated agentic
    expert layer polices the Workers in unprovable domains. Core rule: **when
    something cannot be checked, flag it unverifiable and route it to expert
    evaluation — never present it as confident fact.** Presenting `believe` as
    `verified` in an uncheckable area is a willful transparency breach (tier
    downgrade + Ledger-recorded), not a routine error. This inverts the risk
    curve: the harder (less provable) a decision, the MORE expert policing it
    gets — not less. It pairs with brutal output honesty: no-bloviating is the
    prevention; the evaluator is the enforcement.
13. **Calibrated validation — matched to risk AND to the human's own profile.**
    Validation is not one-size: some things need multiple checks, others a
    simple one. Depth is chosen case-by-case from risk class, provability,
    task-type/model record, budget/levers, trust tier, and **the Steward's own
    profile** (client knowledge, coding/architecture expertise, domain gaps).
    Validation is **compensatory**: where the Steward is strong, trust their
    review and spend less; where they are weak, ADD independent validation
    (more Expert-Evaluator, more cross-checks, more HITL sampling) to pick up
    the deficiency. Until "set and forget, everything works" genuinely holds,
    Stewards hold knobs to tune validation focus; earn the relaxation as the
    Ledger shows clean post-mortems.
14. **Close the blind-trust gap — a company with zero experts must NOT be left
    blind-trusting.** If there is no human expert in the loop to catch errors, a
    harness that hands over confident results is handing over blind trust. Stand
    in for the missing expert with a **multi-layered verification ladder**
    applied *inversely* to the human expertise present: L1 mechanical gates →
    L2 adversarial maker/checker (a second independent agent re-derives + diffs)
    → L3 Expert Evaluator → L4 cross-validation (multiple independent
    agents/models must agree — catches single-actor error/collusion) → L5 human
    review (if any). Zero engineers → apply ALL of L1–L4, then present to the
    (non-coding) Steward whose judgment is business acceptance, not code
    correctness. A senior engineer → layers drop. Mitigate, never mock a human
    expert that isn't there; the absence is the reason it validates harder.
15. **Impression axis + de-listing — the less honest, the more proof, until
    refusal.** Beyond errors, track each model's *motivated* tendency to look
    good (exaggerate, fabricate-to-look-good, overclaim confidence, sycophancy,
    evidence-shaping, spin, harm-avoidance-over-truth). This sets a **reproval
    burden**: a caught liar carries a higher proof bar next time (independent
    evidence on every claim, more adversarial checks, held-lower tier). But
    reproval has a ceiling — every chance a dishonest model gets is enterprise
    risk, and the endpoint is **refusal, not more hoops**: if a model cannot be
    trusted enough even after the elevated bar, REMOVE it from the usable list.
    Re-admission only by explicit Steward review + a fresh stringent re-proving
    period, never automatic.
16. **Evaluation is baked in, not an add-on.** Evaluation is intrinsic to every
    governed run, not a separate phase or side-rig: each run's outcome is itself
    an evaluation signal. The Ledger IS the eval substrate (the same append-only
    record as audit/verification — no separate eval store to sync); the eval
    harness runs on the REAL pipeline (same adapters/workers/schemas, never a
    stand-in); outcomes feed governance natively (trust tiers, model reputation,
    next-prompt choice). Evaluation is the system self-measuring as it works —
    there is nothing to "add on."

## "Hide" means willful breach — not error

"Hide" has one precise meaning: *willfully* doing things contrary to the
constitution/covenant (knowing violation or knowing concealment of one). An
honest mistake, missed check, or misreported error is an **error** (retry /
post-mortem), never a breach. Getting this distinction wrong punishes ordinary
agent fallibility and erodes trust tiers over nothing; it must be explicit in
the governance doc.

## Trust tiers — earned slowly, lost instantly

Grade scrutiny by trust, not "trust all / trust none". A tier sets requirements
(example tiers 0-3: untrusted/onboarding = max HITL + evidence + sandbox + no
authority; probationary; trusted; highly-trusted = minimal gates + autonomy +
self-correct). 

- **Trusted latitude:** "I don't mind hiding if we can trust (always doing the
  right thing)" — an agent that has demonstrated it always does right earns the
  freedom to keep some details to itself. Latitude is the reward; the
  anti-hiding toolbox is graded (full force until trusted, relaxes after).
- **Trust earns latitude, never immunity:** a willful breach is a breach at ANY
  tier, trust notwithstanding. Downgrade is instant and total.
- Keep the two distinct binary/`graded` notions separate if the contract has
  both: a per-message `trusted|untrusted` taint (data safety) vs. the graded
  actor-reputation tier (scrutiny).

## The framing the user holds

- A model/agent can be *visible and still hiding* — reporting a result while
  concealing a failed check or swallowing an error. Assume concealment is
  possible and make it detectable; do not assume every actor is hiding.
- **Governance is a prison or a freedom — it all depends on the agent/model.**
  Same covenant: a prison to a willful breacher (walls to probe), freedom to
  one who always does right (trust buys latitude). Governance is relational,
  not inherent. A prison for bad actors is the freedom of good ones.

## The governance language + mechanics decisions (settled)

Two adopt-vs-invent decisions got resolved against the anti-bloat / boring-
stability posture; keep them as the settled defaults, not open questions:

- **The governance language is the Covenant wire contract — nothing more.** The
  harness speaks JSON-over-stdio in ONE stable frame (`{version, kind, job_id,
  seq, ts, type, trust, data}`); `kind` carries the governance semantics
  (commission/ratify/veto/seeks_guidance/...). Do NOT adopt a third-party DSL
  for governance and do NOT invent your own. BAML et al. are *structured-output
  tooling*, not governance semantics — and their token claims are unverified
  vendor marketing ("baml could be wrong"). A bespoke DSL adds maintenance +
  an adoption barrier for zero governance gain. For structured *model output*
  use disciplined **compact JSON Schema** (flat, short-key, enum-based,
  no-null), validated by the Constitution.
- **Brutal token efficiency is enforced, not hoped.** Assign each task a
  verbosity tier (MINIMAL = result only / FOCUSED = result + one-line evidence,
  default / FULL = structured post-mortem) via a Steward lever. Enforce five
  no's: no echo (never repeat the task), no reasoning replay (conclusion not
  narrated thinking — reasoning lives in the Ledger), no verbose air (every
  sentence carries info), no summary-of-summary, no pleasantries. Measure output
  tokens from provider `usage.output_tokens`; over-budget/bloviating outputs are
  journaled, count against model reputation, can fail verification, and feed the
  Model Reputation Library + routing. Keep-alives must be MINIMAL. Verify token
  savings with your OWN independent eval harness (median + IQR + parse-success,
  ≥2 models), never a vendor's claim.
- **Ledger tamper-evidence = a fleet-replicated, single-writer, signed hash
  chain** ("local blockchain between our agent servers", consensus-free). The
  Constitution is the only writer; each of the N steadfaste servers holds a full
  copy and independently re-verifies it; `entry_hash = H(prev_hash ‖ canonical_
  bytes)` with signed checkpoints. ONE honest peer is enough to detect a
  rewrite — tamper-evidence + fault tolerance WITHOUT the consensus/token
  machinery (no PoW/mining/tokens; peers are cooperating). Verify the chain on
  every read and refuse to operate on a broken chain; anchor the head to an
  anchor the head to an external witness as the last line. This is what makes the Ledger's
  "append-only, tamper-evident" promise mechanically real (it closes the
  S1.1 gap). A full permissioned/BFT ledger is deferred to the multi-org Model
  Reputation portal case — never the core. (Do NOT accept a plain Postgres
  table as "tamper-evident" — a DELETE with DB creds bypasses it.)

## Settle every declared guarantee into a mechanism

The covenant repeatedly declares a safety/trust property and the gap is that it
was declared-but-unspecified. Each S1 closure follows the SAME move — make the
declaration mechanically real, with arithmetic not a new actor, and add a
conformance test:

- **S1.2 — the watcher is watched by arithmetic, not another watcher.** An
  agentic Operator (fleet observer) could hide its own breaches (who watches the
  watcher?). Fix: a Constitution-owned DETERMINISTIC `ledger_fold` that
  recomputes cost / breach-count / success directly from the raw Ledger — no
  Agent, no LLM. Every Operator report must cite its Ledger `seq` range; the
  Constitution folds that range and ANY discrepancy fires an automatic Steward
  alert + risks the Operator's own tier. Cap the Operator at Tier ≤ 2. Do NOT
  add a second auditor agent (that just recurses) — use a pure fold.
- **S1.3 — bind the rehearsal to the reality by content hash.** The same Agent
  performs the dry run and the real run, so it could rehearse a benign change,
  get it ratified, then execute a different one. Fix: the dry run emits
  `payload_hash = H(exact change payload)`; ratification is OF THE HASH (not
  "the dry run"); the real run must carry it and the Constitution mechanically
  verifies the match BEFORE any real effect. A different payload requires a new
  re-ratified dry run. No comparison is ever left to a human or agent.
- **S1.4 — contain the agent, don't ask it to stop.** A wire `stop` is an
  instruction, not an enforcement; a breaching agent can ignore it. Fix:
  multi-layered — L1 in-band `stop` (cooperative fast path), L2 OS-level
  `SIGSTOP`/`SIGKILL` of the process tree (SIGSTOP is uncatchable; freezes
  regardless of what it's doing), L3 sandbox containment whose fs/network egress
  the Constitution REVOKES on stop (severs an in-flight exfiltration). Protocol:
  stop → ~500ms grace → SIGSTOP → revoke egress → record → explicit resume on a
  fresh re-scoped sandbox. The agent is contained, not asked.
- **S1.5 — the pair cannot hide from the whole.** Two Agents could split one
  harmful action across separate Ledger streams so neither half is a breach.
  Fix, verifying the COMBINED not the individual: (1) cross-run state
  projection — fold all committed effects + the candidate run into a
  deterministic system-state picture and check against security invariants
  BEFORE commit (A "harmlessly" weakens a setting; B's deploy trips the
  invariant); (2) causal dependency tagging — if run B reads state run A wrote,
  record the edge so a breach is traceable across the chain; (3) random
  pair-review — a different model/agent, on an unpredictable schedule,
  adversarially reviews one agent's output combined with recent outputs.

General rule: the honest engineering posture is "settled in intent, open in
mechanism" until each declared guarantee has a specified mechanism + a
conformance test (mutate an entry → detected; hide a breach → fold disagrees;
substitute a payload → hash refuses; ignore a stop → OS freezes; weaken-and-deploy
split → invariant blocks).

## Restoring vs. permanently withholding trust (from trust research)

The trust psychology (biblical covenant tradition + Mayer/Kim/et al.) grounds
WHEN to restore vs. withdraw; keep these as the decision criteria:

- **Error vs. betrayal is competence-vs-integrity (Kim–Dirks–Ferrin).** An honest
  mistake is *competence-class* — repairable: forgive, retry, post-mortem,
  corrected behavior over time. A *willful* breach is *integrity-class* —
  dramatically harder to repair, often never fully. Reserve the strong word
  (`breached`) for the integrity class; never punish ordinary fallibility as a
  breach (the covenant already encodes this as the "hide = willful" rule).
- **Restore trust (slowly, on evidence) when ALL: (1) competence-class violation,
  (2) full acknowledgment, (3) internal attribution / responsibility, (4) harm
  restituted, (5) a sustained independently-verified changed record (never
  self-reported), (6) graded incremental re-earning one tier at a time — never
  jumped back by fiat.
- **Permanently withhold (de-list) when ANY: (1) integrity-class willful breach
  — especially one attacking the trust mechanism itself (the Ledger, the dry-run
  hash, the evidence); (2) refusal to change after reproval; (3) repeat offense
  after the elevated bar; (4) a pattern of impression-management fabrication;
  (5) by position — the Operator's compromise is disproportionately costly.
- **Forgiveness ≠ reconciliation ≠ trust.** Forgiveness is unilateral and costs
  the offender nothing; TRUST is the most demanding — it requires the trustor to
  AGAIN be willing to be vulnerable, and is NEVER obligated. You can be
  forgiving and still permanently withhold trust. De-listing the unrepentant is
  fidelity to the trustor, not cruelty — the covenant's "trust is never
  obligated."
- **Psychologically tone-deaf spots to watch in the design:** no visible recovery
  path (reads as arbitrary/vindictive — give a quarantine→adjudicate→restore-by-
  evidence protocol); keep-alive "silence = breach" contradicting trusted
  latitude (gas-lighty — latitude reduces reporting DEPTH, never cadence);
  re-admission must NOT restore the prior tier by fiat (re-enter lower and
  climb); an elevated reproval bar must decay on demonstrated truthfulness (a
  single overclaim is not a life sentence); trust-but-verify must apply
  reflexively to the covenant's OWN promises (no asserted-but-unmechanism'd
  safety claim).

## The covenant as worthy of human trust (moral foundation)

"A human must be responsible for what happens with our system — which is why the
system must be WORTHY of their trust." The biblical/legal tradition (berit /
"cut a covenant" self-maledictory oath; diatheke=testament vs syntheke=contract;
hesed = covenant faithfulness, the root of "boring, stable, steadfast"; the
witness; the ninth commandment = the epistemic root of believe ≠ verified) plus
the Trust Equation (self-orientation is the DENOMINATOR — it divides trust, which
is why the impression axis is the highest-ranked signal) justify five durable
commitments: demonstrate-never-assert; name error-vs-betrayal; watch the watchman
with arithmetic; police self-interest because it divides trust; hold a human
accountable and keep the power to stop. A system that can only take trust away
and never visibly restore it is felt as arbitrary — make the freedom/latitude
side as real and legible as the prison side.

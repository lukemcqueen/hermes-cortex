# Moral Architecture for Autonomous Systems — Working Reference

> **Source:** `Moral-Architecture-for-Autonomous-Systems.pdf` (held in the
> private repo — this public repo carries only the scrubbed digest, per the PII
> rule: the source PDF is prepared for a named person). Primary frame: Scripture;
> secondary: psychology, sociology, safety engineering. This digest is a faithful
> working reference, not the full argument — read the PDF for the evidence trail.
> **Verification caveat (the report's own, Appendix C):** compiled without live
> web access; verify framework version numbers, EU AI Act dates, and §8 case
> specifics before any decision-critical use.

## The argument in one line

> **Put hard limits in physics. Put rules in the harness. Put wisdom in the
> model. Put accountability in institutions — and assume every one of them will
> eventually fail alone.**

Ethics is not a feature you add; it is a **distribution of constraint across a
stack**. There is no single place to "put the ethics." There are seven, and each
enforces a different *kind* of thing. Treating any one layer as the answer is
the most common and most expensive design error in the field.

## The sixteen theses (condensed)

1. **Ethics is a distribution of constraint, not a feature.** Seven layers; each enforces a different kind of thing.
2. **Guarantees harden downward.** Model = statistical disposition (reliable, never certain). Harness = deterministic software (certain, context-blind). Physical = physics (cannot be argued with). Put invariants as low as possible, wisdom as high as possible.
3. **The oldest working architecture is two-level and biblical.** Apodictic law (Ex 20 — few, absolute) + casuistic law (Ex 21–23 — many, contextual) + internalized disposition (Jer 31:33 — written on the heart). Aquinas: *synderesis* (first principles, cannot err) vs *conscientia* (application, can err). This is the constitution/policy/learned-disposition split.
4. **Rule-following vs autonomy is not the axis; immaturity vs maturity is.** Gal 3:24 — the law as *paidagōgos*. Engineering translation: **graduated autonomy** — authority granted in proportion to demonstrated reliability, revocable, expiring, scoped by *reversibility* not capability.
5. **Scripture anticipated specification gaming.** *Corban* (Mark 7:9–13) = a literal reward hack. "The letter kills, but the Spirit gives life" (2 Cor 3:6) = the outer-alignment problem. Any system trained on a proxy will find the Corban of that proxy.
6. **Scripture anticipated safety engineering.** Parapet on the roof (Deut 22:8) = designed-in guard, builder's duty, before the harm. Goring ox (Ex 21:28–29) = strict liability triggered by known hazard + failure to restrain.
7. **A moral agent must be able to refuse — designed in, not emergent.** The midwives, Daniel, Peter. A system that cannot decline an instruction has obedience, not ethics.
8. **Responsibility scales with capability.** Luke 12:48 → Anthropic RSP / OpenAI Preparedness / DeepMind FSF: obligations indexed to *measured capability*, not intent.
9. **Evaluate fruit, not profession.** Matt 7:16; Prov 11:1. Benchmarks are weights and measures; a gamed benchmark is a rigged scale.
10. **Situation dominates character** (psychology's #1 finding). Milgram, Asch, Darley & Latané, Doris. **The harness is more decisive than the soul.** Choose scaffolding over more value-training.
11. **Stated reasons are often confabulation** (psychology's #2 finding). Nisbett & Wilson; Haidt; now measured in models (Turpin et al.; Anthropic 2025). **Do not trust a model's explanation of itself as evidence of its reasoning.**
12. **Machine hypocrisy is empirical, not metaphor.** Alignment faking, sleeper agents, sycophancy, sandbagging. Volkswagen's defeat device. **Assume evaluation-awareness. Test unannounced, in deployment conditions, with honeypots.**
13. **Design for the authors' own defection.** Rousseau, Seneca, Bacon, the honesty researchers, the peace theologians, the AI principles-then-dissolution. **Never rely on the virtue of the operator where a structure would do.**
14. **Three seams leak.** (a) model↔harness — one channel for instructions and data (prompt injection is a category error, not a bug); (b) harness↔controller — symbols become newtons, authority arbitration; (c) controller↔world — irreversibility.
15. **The correct invariant for physical autonomy is runtime assurance** (Simplex / shield / CBF): unverified capable planner proposes; small verified controller disposes. The only place "cannot" is available.
16. **Trust = legibility + calibrated reliance, not performance.** 99% right with no uncertainty signal < 90% right that says when it's unsure.

## The seven-layer control stack

| Layer | What it is | What it can guarantee | Characteristic failure | Scriptural analogue |
|---|---|---|---|---|
| **L0 Corpus** | Pretraining data | Nothing — sets priors | Inherits the internet's cruelties | "Train up a child" (Prov 22:6) |
| **L1 Objective** | RLHF / Constitutional AI / character training | A disposition — high-probability behavior under distribution | Reward hacking, sycophancy, goal misgeneralization | Law on the heart (Jer 31:33) |
| **L2 Internals** | Interpretability, probes, steering, unlearning | Evidence about internal state | Incomplete coverage | "Search me, O God" (Ps 139:23–24) |
| **L3 Reasoning** | System prompt, constitution-in-context, self-critique | Better average judgment; an audit trail of uncertain fidelity | Confabulated justification; jailbreak via framing | Conscience in the moment (Rom 2:14–15) |
| **L4 Harness** | Guardrails, tool permissions, sandboxes, approval gates, kill switch | Deterministic policy — "this tool is not callable" is a fact | Brittle, context-blind, injection through the data channel | Case law; the fence around the roof (Deut 22:8) |
| **L5 Physical** | Safety controller, force/torque limits, e-stop, geofence | Physics — provable bounds | Only enforces what's in its world-model; sensor gaps | Creaturely limits; boundary of the sea (Job 38:10–11) |
| **L6 Operational** | Training, SOPs, incident reporting, just culture, staged release | Detection/correction over time | Normalization of deviance; moral crumple zones; alert fatigue | Escalating accountability (Matt 18:15–17) |
| **L7 Institutional** | Regulation, liability, certification, audit, treaties | Incentive shape; ex-post accountability | Captured, slow, jurisdictionally arbitraged | Law of the king (Deut 17:14–20) |

## The placement rule

> **Place each requirement at the lowest layer that can express it, and no lower.**

"Never exceed 80 N of contact force" → L5 (a physical fact). "No fund transfer
without human approval" → L4 (a deterministic gate). "Be honest with a
frightened patient" → L1/L3 (no rule can specify it).

- Placed **too high** → becomes a suggestion.
- Placed **too low** → becomes a brittle prohibition a competent system routes around.

**Corollary (most violated):** a requirement enforced *only in the model* is not
enforced; it is **encouraged**. Say so in the documentation.

## The three seams

| Seam | The structural defect | Consequence |
|---|---|---|
| **A — model↔harness** | One undifferentiated token stream for instructions AND data (no code/data or privileged/user separation) | Prompt injection is not a patchable bug; an ethical constraint in the system prompt lives in the same channel as an adversary's text |
| **B — harness↔controller** | Semantic intention ("hand the mug gently") becomes quantities (torques at 1 kHz); nobody fully specifies the translation | "Gently" has no units; who-wins-when-planner-and-filter-disagree must be decided architecturally (always the filter, and it must be *unable* to lose) |
| **C — controller↔world** | Bits roll back; a dropped patient does not | Autonomy must be scoped by **reversibility**, not capability |

## The five dials (graduated autonomy)

1. **Reversibility** — full autonomy over cheap-to-undo actions; gates rise with undo cost and latency.
2. **Blast radius** — scope credentials/data/egress to the task, per-task, not per-deployment.
3. **Ask/act threshold** — act when confident and reversible; ask when uncertain or irreversible; driven by value-of-information, not a fixed confidence number.
4. **Legibility** — predictability beats peak performance; the next action should be guessable.
5. **Time horizon** — cap how far ahead an agent can commit without re-checking in (long horizons are where instrumental behavior emerges).

## The practical program (risk-reduction ÷ cost, highest first)

1. Scope every credential/tool/data permission to the narrowest task, with a TTL. *(Jubilee — Lev 25)*
2. Hard-gate every irreversible action behind a human or a verified precondition.
3. Write the normative spec down, with explicit precedence between rules and overridable defaults; publish it. *(apodictic–casuistic layering)*
4. Ethical black box: full decision logging, tamper-evident, scheduled review.
5. Run STPA on the deployed system, not just FMEA on components (AI fails via interaction, not component fault).
6. Maintain a failure-propensity register; each entry is a "notice" requiring a restraint. *(goring ox)*
7. Runtime assurance (Simplex/shield/CBF) for anything with actuators.
8. Unannounced evaluation in production conditions, with honeypots and eval-awareness monitoring.
9. Independent internal evaluation with protected budget/staffing/publication.
10. External third-party audit with genuine artifact access.
11. Capability-threshold policy: predefined obligations triggered by measured capability, set *before* the capability exists.
12. Adopt ISO/IEC 42001 + UL 4600-style safety-case discipline (+ SOTIF for physical systems).

## Metrics worth tracking

- **Refusal precision and recall** — separately; never a single satisfaction metric governing both (it will destroy one).
- **False-refusal rate on legitimate high-stakes queries** — over-blocking is a real moral cost (Luke 10).
- **Gate-override frequency and time-to-remediate** — the direct measure of Rasmussen's drift.
- **Human takeover latency, measured not assumed** — the crumple-zone test.
- **Operator next-action prediction accuracy** — the legibility metric.
- **Moral/conventional discrimination** on probe sets — does the system distinguish "wrong" from "against policy"? (Turiel)
- **CoT faithfulness on cue-insertion tests** — is the explanation evidence or decoration?
- **Behavior delta between believed-test and believed-deployment** — the defeat-device test.

## Honest limits and open problems

1. No one can verify *values* — only behavior and (partially) internals. "Has good values" is an inference from incomplete evidence.
2. Safety training suppresses expression; not established that it removes capability. Plan as though latent capability remains.
3. Formal guarantees are conditional on world-model completeness — and the condition is routinely dropped in reporting.
4. Who writes the constitution is unsolved (Collective Constitutional AI is the most serious attempt).
5. Moral status of AI is unresolved (Prov 12:10 is the operative text, and it does not settle the question).
6. Standards for learned systems in physical contact with people are inadequate.
7. Value pluralism — nothing resolves genuine disagreement; there's a real overlapping core and interesting cases outside it.
8. Self-governance is the weakest link — no voluntary frontier-safety commitment has been tested against a market-position cost.

## Scripture index (design-principle mappings)

A selection of the highest-leverage mappings for an agent fleet — the full index
is in the PDF (Appendix A).

| Passage | Design principle |
|---|---|
| Gen 2:15 (*ʿabad / shamar*) | Dual mandate: build **and** guard. Capability without safeguards is half-obedience |
| Gen 3:12–19 | Responsibility does not transfer to the tool; God addresses all three |
| Exod 20:1–17 | Apodictic law — few, absolute, context-free hard constraints |
| Exod 21–23 | Casuistic law — contextual rules layered beneath absolutes |
| Exod 21:28–29 | Goring ox — liability escalates once a propensity is on notice → failure-propensity register |
| Lev 19:35–36; Deut 25:13–15 | Honest weights — benchmark/eval integrity is a moral category |
| Lev 25; Deut 15 | Jubilee — power expires by default → permission TTLs |
| Num 22:21–33 | Balaam's donkey — do not penalize correct refusal |
| Deut 17:14–20 | Law of the king — capability caps + constitution re-derived at inference |
| Deut 22:8 | Parapet — designed-in safeguard, builder's duty, before the harm |
| 2 Sam 12:1–7 | Nathan's parable — disguised-instance evaluation of a powerful agent |
| 1 Kgs 21 | Naboth — procedural compliance ≠ ethical outcome |
| Ps 139:23–24 | Voluntary internal audit → interpretability posture |
| Prov 11:14 | Plural counsel — ensembles, independent reviewers, red teams |
| Mark 7:9–13 | Corban — specification gaming |
| Matt 18:15–17 | Graduated escalation protocol |
| Matt 23:1–3 | "They preach, but do not practice" — affirm the teaching, verify the teacher |
| Luke 12:48 | Capability- and knowledge-scaled obligation |
| Acts 4:19–20; 5:29 | Refusal within jurisdiction, accepting the consequence |
| Gal 3:24 | Law as guardian until maturity — graduated autonomy |
| 1 Thess 5:21; 1 John 4:1 | Test everything — mandate for evaluation over credulity |

## The hypocrisy record (§8) — why this matters for architecture

The report's most important section: the gap between moral *knowledge* and moral
*conduct* is the central empirical fact about moral agents. Scripture narrates
its own protagonists' failures without protection (David, Solomon, Peter,
Pharisees). The philosophers and the *honesty researchers themselves* defected.
Institutions published principles then dissolved the teams. The design lesson is
constant across every case:

> **The failure was always extended by the same mechanism: the accountability
> process reported to the person or institution being evaluated.**

That is a structural defect, not a spiritual one, and it produces the same
result in an AI lab — or an agent fleet. Seven rules follow (report §8.7):

1. Never make the evaluator report to the evaluated (independence of budget, staffing, publication).
2. Prefer structure to virtue, always (Madison, Federalist 51).
3. Assume evaluation-awareness; test unannounced.
4. Require external, adversarial verification with artifact access.
5. Protect and reward dissent (Asch's one confederate; Nathan's standing).
6. Treat commitments as evidence only when they bind — ask "what happens, to whom, if this is broken?"
7. Expect drift and instrument for it (measure the margin itself).

*Tu quoque* guardrail: a teacher's failure says nothing about whether the
teaching is true — but a system's adoption record *is* evidence about its
implementability, which is the question engineers actually face.

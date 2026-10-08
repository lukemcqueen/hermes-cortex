---
name: enterprise-regrets
description: Check proposals against enterprise regret patterns.
version: 0.1.0
author: Luke, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags:
      - architecture
      - code-review
      - risk
      - decision-making
related_skills:
  - code-review
  - architecture-review
  - engineering-approach
  - data-structure-efficiency-review
  - root-cause-debugging
---

# Enterprise Regrets Skill

Screen architecture proposals, technology choices, and code designs against patterns that engineering teams reliably regret in retrospectives 2-5 years later. Every pattern is drawn from public postmortems, HN threads, and founder retrospectives — not conjecture. The skill operates as a structured checklist: feed it a proposal (PR description, design doc, migration plan, tech-stack discussion) and it returns a regret-lens assessment with concrete findings, reversibility estimates, and alternatives.

## When to Use

- A team proposes adopting a new database, message queue, or infrastructure component.
- A microservices extraction or decomposition is on the table.
- Someone advocates a rewrite of a working system.
- A PR introduces a new abstraction layer, framework, or shared library.
- Cloud migration is being debated (either direction).
- A vendor or outsourcing engagement is under consideration.
- A POC is being built with the stated intent to throw it away later.
- A proposal claims cost savings without an ops-headcount line item.

Don't use for: trivial refactors, bug fixes, dependency version bumps that don't change architecture, or changes to systems with < 2 expected years of lifetime.

## Prerequisites

- The proposal or design under review, in written form (PR description, design doc, or issue body). Verbal proposals should be summarized in writing first.
- Access to the current system's architecture if evaluating a migration or replacement.
- For cost claims: itemized estimates that separate infrastructure from headcount from opportunity cost.

## How to Run

1. `read_file` the proposal document, design doc, or PR description.
2. If the proposal references technologies or patterns you're unfamiliar with, use `web_search` to find recent (last 2 years) production-experience reports — specifically look for regret posts, migration stories, and cost overruns.
3. For cloud cost claims, `web_search` for TCO breakdowns that include operational overhead (headcount, on-call, training), not just infra line items.
4. Run the Regret-Lens Checklist (below) against the proposal. For each matched pattern, cite the corpus source and the specific proposal text that triggers it.
5. Run the Evaluation Rubric (below). Score each dimension Low / Medium / High risk.
6. Produce findings: matched patterns, rubric scores, and a summary recommendation with explicit reversibility estimates.
7. If the proposal passes with manageable risk, note which patterns were considered and cleared. If it fails, recommend a lower-regret alternative drawn from the corpus (e.g., modular monolith instead of microservices, refactor instead of rewrite, Postgres instead of niche DB).

## Regret-Lens Checklist

For each pattern, ask the associated question. A "yes" answer signals elevated regret risk.

### 1. Premature Distribution
Microservices, event streams, or message queues deployed before domain boundaries are proven.

- **Symptom:** Latency debugging, shared-library version hell, distributed monolith with all the network cost and none of the isolation benefit.
- **Question:** Do we have < 20 backend engineers AND/OR no independently-scalable workload that justifies splitting?
- **Corpus:** HN "Microservices Killed Our Startup" (4-engineer startup lost 6 months); HN "Why Twilio Segment moved from microservices back to a monolith" (140 services, shared-library version hell); HN "The Prime Video microservices to monolith story".

### 2. The Big Rewrite
Replacing a working system in one big-bang cutover rather than incrementally.

- **Symptom:** Feature freeze 2-4x past estimate, competitors advance, institutional knowledge (edge cases, bug fixes, real-world adaptations) silently discarded.
- **Question:** Is the proposal to replace a working system in one shot, rather than via strangler fig or incremental refactoring?
- **Corpus:** Joel Spolsky "Things You Should Never Do" (Netscape gave IE the market); potapov.dev "Why Big Rewrites Fail" (25-year pattern, second-system effect); Medium "We Rewrote Our App in React. Two Years Later, We're Back on jQuery" (reverted in 12 days after $200K).

### 3. Trend-Chasing Database
Choosing a database for hype rather than workload shape.

- **Symptom:** Schema flexibility never needed, missing joins force application-level reconciliation, operational complexity explodes, migration costs 6-12 weeks.
- **Question:** Will the data model stabilize within months? If yes, why not a relational DB with boring defaults?
- **Corpus:** r/SaaS "Started with MongoDB because it was trendy" (6-week migration to Postgres, 3-5x faster); Medium "We Replaced PostgreSQL with DynamoDB and Regretted It" ($200K over 6 months, 5.75x bill increase); "Do you really need single-table design for DynamoDB?" (3x billing, new devs take weeks to onboard).

### 4. Premature Abstraction
DRY applied before the pattern appears in at least 3 independent places.

- **Symptom:** Abstraction leaks, every new use case requires refactoring the abstraction, removal ripples through the entire codebase.
- **Question:** Has this pattern appeared independently in ≥ 3 places, or are we abstracting on the first or second occurrence?
- **Corpus:** dev.to "When Abstraction Becomes a Bottleneck" (cost of removing premature optimization is localized; cost of removing premature abstraction ripples through the entire codebase).

### 5. Premature Complexity
Infrastructure deployed for scale the system doesn't have.

- **Symptom:** Postgres + Redis + message queue + Kubernetes for 100 requests/day. Debugging distributed state for a single-user system.
- **Question:** Would one codebase and one database serve the current load (not the hoped-for load in 2 years)?
- **Corpus:** r/ExperiencedDevs infrastructure thread ("biggest regret is premature complexity"); corpus pattern (complexity is asymmetric — easier to add than remove).

### 6. Cloud-As-Default
Cloud chosen without honest TCO modeling.

- **Symptom:** Predictable workloads paying cloud elasticity premiums; repatriation saves 50-65% but only if utilization > 60%.
- **Question:** Is the workload predictable and sustained (> 60% utilization year-round)? Does the TCO model include ops headcount, over-provisioning buffer, and migration cost?
- **Corpus:** 37signals cloud exit (saved ~$10M over 5 years); GEICO Project Boomerang (65% cost cut, $325M/yr); "Why We Ditched Cloud-Native for On-Prem Servers (And Regretted It)" ($210K unplanned, 2.8x TCO); "We Spent $2M Leaving AWS. Then $3M Coming Back." (FinOps beats moving servers).

### 7. POC-Becomes-Product
Velocity-first build with no explicit stabilization gate before production.

- **Symptom:** The POC ships to production because "we'll rewrite it later," and 3 years later it's the backbone with forgotten edge cases and no tests.
- **Question:** Is this being built as a POC with no explicit stabilization gate or rewrite milestone?
- **Corpus:** r/programming "The disproportionate influence of early tech decisions" (never seen a POC not become the product); corpus pattern (early decisions are sticky).

### 8. Shared Database
Multiple applications coupling on a single database schema.

- **Symptom:** Foreign keys between unrelated domains, one app's migration breaks another, impossible to decompose later.
- **Question:** Do multiple applications or services share a single database with cross-domain foreign keys?
- **Corpus:** cep.dev "(Almost) Every Infrastructure Decision I Endorse or Regret" (foreign keys between all objects in the entire stack).

### 9. Deferred Fundamentals
Identity, logging, monitoring, backups, and data retention deferred to "later."

- **Symptom:** Adding SSO, structured logging, or monitoring 2 years in requires touching every service and costs 5-10x the early investment.
- **Question:** Are identity (SSO/OIDC), structured logging, metrics, and data retention policies being postponed?
- **Corpus:** cep.dev (Okta regret, OpenTelemetry regret); r/SaaS (events table with no retention policy growing past the rest of the DB).

### 10. Outsourcing Core Competency
No in-house engineer owns the outsourced component.

- **Symptom:** Vendor delivers something nobody on the team understands; every change requires a new SOW; knowledge never transfers.
- **Question:** Is the outsourced component core to the product, with no in-house engineer who owns it?
- **Corpus:** HN "Ask HN: Do you have a software consultant or outsourcing horror story?" (16 people, 12 weeks, produced only Qt templates); "communication gaps, not skill gaps."

### 11. Credential-Driven Hiring
Hiring on pedigree rather than demonstrated delivery.

- **Symptom:** Engineer from top company can't ship; 2 years before non-technical manager notices.
- **Question:** Does the hiring process rely on credentials/resume rather than a small paid trial task with real deliverables?
- **Corpus:** r/ExperiencedDevs interviewer horror stories ("he spoke well so it took so long"); r/Entrepreneurs "Burned $40k+ on wrong tech hires" (credentials don't matter, delivery does).

### 12. Dependency Drift
Framework or dependency upgrades deferred indefinitely.

- **Symptom:** Framework 3 major versions behind; upgrade takes months; security patches can't be applied cleanly.
- **Question:** Are dependencies > 2 major versions behind, with upgrades deferred without a scheduled window?
- **Corpus:** cep.dev (waiting = upgrade process long + inevitably buggy); corpus pattern (dependency drift is a compounding tax).

## Evaluation Rubric

Score each dimension for the proposal under review.

| Dimension | Low Risk | Medium Risk | High Risk |
|-----------|----------|-------------|-----------|
| **Irreversibility** | Reversible in days (code style, naming) | Reversible in weeks (framework, library) | Reversible in months/years (database, data model, architecture) |
| **Business-Value Test** | Proposal directly enables revenue or user-facing capability | Proposal measurably improves developer productivity | Proposal makes code "cleaner" with no user-facing or revenue impact |
| **Complexity Asymmetry** | Removing the change is as easy as adding it | Removal requires coordinated refactoring across a bounded module | Removal ≈ ground-up rebuild of the affected system |
| **Boring-Tech Test** | Technology is battle-tested, widely adopted, easy to hire for | Technology is established but niche, limited hiring pool | Technology is trendy, < 3 years old, or has known migration stories away from it |
| **TCO Honesty** | Cost model includes infra + ops headcount + training + migration + failure handling | Cost model includes infra + some ops, omits 1-2 indirect costs | Cost model only lists infrastructure line items, ignores headcount and opportunity cost |
| **Scar-Tissue Preservation** | Proposal preserves existing tests and incrementally replaces behavior | Proposal keeps some tests but discards undocumented edge cases | Proposal discards the entire system with no characterization tests; knowledge lives only in the old code |

## Procedure

1. **Read the proposal.** Load the design doc, PR description, or issue body with `read_file`. Identify what is being changed, what technology is being introduced or removed, the stated rationale, and any cost/time estimates.

   *Criterion:* You can summarize the proposal in 3 sentences: what changes, why now, what the success metric is.

2. **Research recent production experience.** For any non-trivial technology choice (new DB, new architecture pattern, cloud migration direction), `web_search` for "[technology] production regret" or "[technology] migration back to [boring alternative]" to find retrospectives from the last 2 years. Extract concrete numbers: cost surprises, timeline blowouts, team-impact reports.

   *Criterion:* At least one recent (≤ 2 years old) retrospective article or thread is found and read for each novel technology in the proposal.

3. **Run the Regret-Lens Checklist.** For each of the 12 patterns, check whether the proposal triggers it. For matches, capture: the pattern name, the specific proposal text that triggers it, the corpus source backing the pattern, and the question the team should answer before proceeding.

   *Criterion:* Every pattern explicitly evaluated (matched or cleared). At least one corpus citation accompanies each match.

4. **Score the rubric.** Assign Low / Medium / High for each of the 6 dimensions. Any dimension scoring High is a blocking concern; Medium scores require documented mitigations.

   *Criterion:* All 6 dimensions scored with a 1-sentence justification per dimension.

5. **Synthesize findings.** Produce a structured output:

   - **Matched Patterns:** List of triggered patterns with citations and specific proposal text.
   - **Rubric Summary:** Risk scores with one-line justification each.
   - **Reversibility Map:** For each matched pattern, estimate how hard it is to undo (days / weeks / months / years).
   - **Recommendation:** Pass (with noted mitigations), Hold (missing information), or Fail (proposal should be redesigned). For Fails, suggest a lower-regret alternative from the corpus.
   - **Alternatives:** Concrete suggestions drawn from corpus patterns (modular monolith over microservices, refactor over rewrite, Postgres over niche DB, FinOps over repatriation, paid trial over credential hiring).

   *Criterion:* Every High-risk dimension has a concrete alternative recommendation.

6. **Verify completeness.** Re-read the proposal against the findings. Confirm no pattern was skipped and every citation maps to a real corpus entry.

   *Criterion:* All 12 patterns evaluated. All High-risk dimensions have alternatives. All citations reference the corpus.

## Pitfalls

- **Do not use this skill to block all change.** The goal is to surface hidden costs and irreversibility, not to veto every new technology. A proposal that scores Medium on most dimensions with documented mitigations can still be sound.
- **Don't trust cost projections without ops headcount.** Both cloud→on-prem and on-prem→cloud regrets share one root cause: models that excluded the people cost. Demand a line item for operational headcount in every TCO claim.
- **The checklist is not a substitute for domain knowledge.** If the proposal concerns a regulated industry, compliance costs may override the rubric. Use `web_search` to supplement.
- **Avoid false equivalence.** "Both directions have been regrets" (cloud and on-prem) doesn't mean they're equal-risk. Variable workloads favor cloud; sustained high utilization favors owned hardware. Context matters more than direction.

## Verification

- Every matched pattern has a corpus citation and a reversibility estimate.
- Every rubric dimension is scored with a justification, not just a label.
- Any High-risk dimension has a concrete, actionable alternative recommendation.
- The output explicitly distinguishes between "this will definitely fail" and "this carries elevated risk that can be mitigated by X."
- If the proposal passes, the output notes which patterns were considered and cleared (e.g., "Pattern 1 (Premature Distribution): cleared — team has 40 backend engineers and independently-scalable billing service").

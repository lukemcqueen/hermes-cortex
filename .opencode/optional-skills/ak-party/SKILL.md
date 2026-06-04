---
name: ak-party
description: |
  Run a structured, multi-role architecture review to evaluate tradeoffs,
  risks, and decisions for enterprise systems without heavy frameworks.

  Triggers when user mentions:
  - "architecture review"
  - "system design"
  - "enterprise design"
  - "tradeoffs"
  - "design review"
  - "council"
---

# AK Party

## Purpose
Provide a **concise, multi-perspective architecture review** to:
- identify risks early
- surface tradeoffs
- define minimum viable architecture
- guide implementation safely

---

## Core Rule

Prefer simple, reliable architecture.

Complexity must be justified.

---

## When to Use

Use for:

- enterprise-grade architecture
- multi-service systems
- API/data boundary design
- security-sensitive features
- infrastructure/platform decisions
- before PRD, ADR, or major implementation

Do NOT use for:

- small bug fixes
- single-file changes
- trivial UI updates
- already well-defined tasks

---

## Output (STRICT)

```md
# AK Party Review

## Summary
High-level recommendation

### Cost/Complexity Snapshot
| Dimension | Estimate | Confidence |
|---|---|---|
| Implementation effort | X–Y person-weeks | H/M/L |
| Infrastructure cost/mo | $Z | H/M/L |
| Maintenance burden | Low/Med/High | H/M/L |

## Product View
- user value
- scope risks
- success criteria

## Architecture View
- system design
- boundaries
- alternatives

## Security View
- auth model
- data protection
- threat risks

## Data View
- ownership
- schema concerns
- consistency

## DevOps View
- deployment
- scaling
- observability

## QA View
- test strategy
- failure coverage
- edge cases

## Conflicts / Tradeoffs
Resolved via decision matrix (see Conflict Resolution below)

## Decisions

### Must Decide Now
- ...

### Can Defer
- ...

## Recommended Architecture
Clear, minimal design

## Risk Register

| Risk | Severity | Mitigation |
|---|---:|---|

## Verification Strategy
- tests
- monitoring
- rollout checks

## First 5 Implementation Slices
- S1:
- S2:
- S3:
- S4:
- S5:

## Post-Implementation Review
_Complete 3 months after shipping. Check actual outcomes against these decisions._
- [ ] Assumptions still valid?
- [ ] Performance meets projections?
- [ ] Security posture holds?
- [ ] Maintenance cost in expected range?
- [ ] Any decision that should be reversed?
```
---

## Council Roles

Each role must provide:

* top 3 concerns
* required decisions
* major risks
* minimum acceptance bar

Use the decision criteria below to weight each role's input.

---

## Workflow (STRICT)

0. If no ak-elicit output exists, run `ak-elicit` first to establish requirements
1. Run `doc-system` to check for existing architecture docs
2. Evaluate across all council roles (use decision criteria per domain)
3. Surface conflicts and tradeoffs
4. Resolve conflicts via decision matrix (see Conflict Resolution)
5. Distinguish must-decide-now vs can-defer
6. Add cost/complexity estimates
7. Define recommended architecture
8. Populate risk register
9. Define verification strategy
10. Identify first 5 implementation slices
11. Append post-implementation review section

---

## Decision Criteria per Domain

When evaluating each role's input, apply these weights. The weights are starting points — adjust for your context.

| Domain | Primary Criterion | Weight | Secondary Criterion | Weight |
|---|---|---|---|---|
| **Product** | User value delivered | 40% | Time-to-market | 30% |
| **Architecture** | Coupling / cohesion | 35% | Extensibility | 25% |
| **Security** | Risk reduction | 50% | Compliance requirement | 25% |
| **Data** | Correctness guarantee | 35% | Schema evolution safety | 25% |
| **DevOps** | Deployability | 40% | Observability | 30% |
| **QA** | Failure coverage | 40% | Reproducibility | 25% |

For each decision, score each option 1–5 per criterion, multiply by weight, sum. The highest-scoring option wins — unless a veto applies (e.g., compliance violation).

Example:

```
Option A (PostgreSQL):
  Product: 4 × 40% = 1.6
  Architecture: 3 × 35% = 1.05
  Security: 5 × 50% = 2.5
  Data: 4 × 35% = 1.4
  DevOps: 3 × 40% = 1.2
  QA: 4 × 40% = 1.6
  Total: 9.35

Option B (MongoDB):
  Total: 7.1

→ Recommend Option A (PostgreSQL)
```

---

## Conflict Resolution

When role views conflict (e.g., Product wants speed, Security wants rigour), use this decision matrix:

```
                  Risk Score (Security + Data + QA)
                  Low (0–3)    Med (4–6)   High (7–10)
Cost of Delay    ┌─────────────────────────────────────
(Product+Arch)   │
  Low (0–3)      │  Quick win    Documented    Monitor
  Med (4–6)      │  Proceed     Mitigated     Escalate
  High (7–10)    │  Fast track  Priority      Full review
```

**How to use:**
1. Estimate **Cost of Delay** — sum Product + Architecture scores (1–5 each): how much value/time is lost per week of delay?
2. Estimate **Risk Score** — sum Security + Data + QA scores (1–5 each): how bad is the worst-case outcome?
3. Find the cell. That's your posture:
   - **Quick win** — implement now, minimal ceremony
   - **Documented** — proceed but document the risk
   - **Monitor** — proceed with watchlist, re-evaluate
   - **Proceed** — go ahead with standard mitigations
   - **Mitigated** — proceed only after mitigations are in place
   - **Escalate** — don't proceed; escalate for broader decision
   - **Fast track** — high value, high risk — allocate resources to resolve
   - **Priority** — high stakes on both axes — full governance review
   - **Full review** — stop; need executive-level architecture review

**Record the cell in the Conflicts section** so the decision is transparent.

---

## Cost/Complexity Estimation

For every recommended architecture, include rough-order estimates:

| Dimension | Scale | How to Estimate |
|---|---|---|
| Implementation effort | Person-weeks (S: 1–2, M: 3–6, L: 7–15, XL: 16+) | Count distinct systems touched, interfaces to define, and migration steps |
| Infrastructure cost/mo | USD (S: <$50, M: $50–500, L: $500–5K, XL: $5K+) | Compute + storage + networking + managed services |
| Maintenance burden | Low / Med / High | Count ongoing tasks: dependency bumps, schema migrations, monitoring upkeep, incident response load |

**Confidence:** Label each estimate H/M/L based on how well the boundary is understood.

---

## Role Guidelines

### Product

* is this valuable?
* is scope realistic?
* what defines success?
* what's the cost of delay if we defer this decision?

---

### Architecture

* boundaries clear?
* minimal viable design?
* coupling risks?
* what's the undo path if this choice is wrong?

---

### Security

* auth and permissions
* data exposure risks
* audit requirements
* what's the blast radius of a compromise?

---

### Data

* ownership defined?
* schema evolution safe?
* consistency model?
* what's the recovery point objective (RPO) / recovery time objective (RTO)?

---

### DevOps

* deploy strategy
* scaling approach
* monitoring/logging
* canary / blue-green possible?

---

### QA

* test coverage
* failure modes
* reproducibility
* how do we prove this works in production?

---

## Enterprise Checklist

Consider:

* bounded contexts
* API contracts
* data ownership
* auth/authorization
* audit logging
* observability (logs, metrics, traces)
* background jobs / queues
* migration strategy
* rollback plan
* failure modes
* deployment topology
* compliance requirements
* testing strategy
* operational support

---

## Decision Rules

* separate **must decide now** vs **can defer**
* prefer additive changes
* avoid premature optimization
* design for rollback
* assume failures will happen
* when in doubt, use the conflict resolution matrix

---

## Template

Write the final output to `docs/architecture/<system>.md`. Use the template at `.agentkore/templates/architecture/AK-PARTY-TEMPLATE.md` (installed by `./run scan-setup` or deploy). It includes all output fields plus Metadata, conflict resolution record, and post-implementation review.

---

## Anti-Patterns

Avoid:

* over-engineering
* vague recommendations
* ignoring tradeoffs
* assuming perfect conditions
* designing without verification plan
* hiding risks
* skipping cost estimates — "we'll figure out infra later"
* assigning equal weight to all role inputs
* forgetting the post-implementation review

---

## Integration with AgentKore

```txt
ak-elicit
→ ak-party
→ prd-lite
→ story-slicing
→ task-executor
```

---

## Goal

Produce a clear, realistic, and safe architecture that:

* balances simplicity and scalability
* exposes risks early
* guides implementation with confidence
* has verifiable cost and complexity estimates
* is reviewable 3 months after shipping

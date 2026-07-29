---
name: architecture-review
version: 1.2.0
description: "Multi-role architecture review (a.k.a. HC-Party) with weighted decision matrices, conflict resolution, and cost estimation."
category: software-development
source: hermes-cortex (ported from AgentKore)
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [architecture, design-review, decision-matrix, cost-estimation, conflict-resolution, party, hc-party]
    aliases: [hc-party, party]
    trigger_phrases: [architecture review, design review, evaluate approach, hc party, arch party]
    related_skills: [plan, writing-plans, spike, change-test-loop, codebase-design, root-cause-debugging]
---

# architecture-review: Architecture Review

## Overview

A structured, multi-role architecture review process designed for complex design decisions (formerly known as HC-Party). It assembles a panel of six expert personas, each evaluating the architecture from their unique vantage point using a weighted decision matrix. Conflicts are surfaced and resolved systematically, and cost estimates ground every recommendation in reality.

**Origin:** Ported from AgentKore into the Hermes Cortex skill set.

## When to Trigger

This skill activates when the user says one of the following phrases (or an equivalent):

- **"architecture review"**
- **"design review"**
- **"evaluate approach"**
- **"arch review"**
- **"compare architectures"**
- **"which approach should I choose"**
- **"trade-off analysis"**

If the user asks for a quick opinion on a small design decision, they might not need a full Party. Use your judgment — when the decision is costly, complex, or irreversible, run the party.

---

## How It Works

The review runs in five phases:

### Phase 1: Scoping

Before roles deliberate, establish the bounds of the review.

```
- What system or component is under review?
- What is the primary goal? (performance, maintainability, cost, time-to-market, security, etc.)
- What are the constraints? (team size, budget, timeline, compliance, existing infra)
- How many approaches/options are being compared? (generally 2–4)
- Any non-negotiables (e.g., must run on AWS, must be PCI-compliant, must use PostgreSQL)
```

### Phase 2: Role Panel Assembly

Six roles are activated. Each role receives the scope document and any proposed approaches, then produces an independent evaluation.

| # | Role | Focus Area | Key Questions |
|---|------|------------|---------------|
| 1 | **Architect** | System structure, scalability, modularity, tech fit | Is this architecture coherent? Does it scale? Are there coupling issues? |
| 2 | **Security Engineer** | Threat model, vulnerabilities, compliance, data protection | What attack surfaces exist? Are secrets handled safely? Is this auditable? |
| 3 | **SRE** | Reliability, observability, deployment, incident response | Can this be operated 24/7? What's the blast radius of a failure? How do we debug it? |
| 4 | **Domain Expert** | Business logic, domain model correctness, edge cases | Does this model the real-world domain correctly? What edge cases are missed? |
| 5 | **Product** | User value, roadmap alignment, delivery timeline, trade-offs | Does this ship value faster? What's the MVP? What's the opportunity cost? |
| 6 | **QA** | Testability, risk areas, integration strategy, regression coverage | How do we verify correctness? What's hard to test? What's the test pyramid? |

Each role produces a structured output:
- **Score** (1–10) on how well the approach satisfies their criteria
- **Rationale** explaining the score
- **Showstoppers** — dealbreakers that would make this approach unacceptable
- **Mitigations** — things that could improve the score

### Phase 3: Weighted Decision Matrix

All scores are assembled into a weighted matrix. The **Architect** role drives this phase.

**Default weights** (can be adjusted per review):

| Criteria | Default Weight |
|----------|---------------|
| Architectural soundness | 20% |
| Security posture | 20% |
| Operational reliability | 15% |
| Domain correctness | 15% |
| Product & business value | 15% |
| Testability & quality | 15% |

**Matrix format:**

```
| Approach | Architect (20%) | Security (20%) | SRE (15%) | Domain (15%) | Product (15%) | QA (15%) | Weighted Total |
|----------|----------------|----------------|-----------|--------------|---------------|----------|---------------|
| Option A | 8              | 6              | 7         | 9            | 8             | 7        | 7.45          |
| Option B | 6              | 9              | 8         | 6            | 7             | 8        | 7.20          |
```

Weighted Total = Σ (score × weight). The matrix makes trade-offs explicit and prevents any single perspective from dominating.

### Phase 4: Conflict Resolution

When roles disagree sharply (score gap ≥ 3 on the same approach), a conflict resolution protocol is triggered:

1. **Surface the conflict** — "Architect scored Option A at 8, Security scored it at 3. Let's resolve."
2. **Dueling briefs** — Each role writes a 3-sentence rebuttal addressing the other's concerns.
3. **Re-score** — Roles may adjust their score after hearing the other side.
4. **Architect mediates** — The Architect role incorporates the resolution into a final recommendation.

**Conflict resolution rules:**
- No score changes without stated rationale
- If a showstopper is identified by any role, it must be addressed before proceeding
- The Product role has veto power on timeline/scope grounds
- The Security Engineer role has veto power on compliance/audit grounds

### Phase 5: Cost Estimation

Every recommendation must include three cost axes:

| Axis | Description | Example Output |
|------|-------------|----------------|
| **Dev Effort** | Engineering hours to build | "~6 engineer-weeks (240 hours) with 2 developers" |
| **Infra Cost** | Ongoing operational cost | "~$400/mo on AWS (ECS + RDS + Redis + ALB)" |
| **Maintenance Burden** | Ongoing maintenance overhead | "~4 hours/week for updates, monitoring, security patching" |

Cost estimates should be **bracketed** (optimistic / likely / pessimistic) and include confidence level.

---

## Output Format

After all five phases, produce a final summary like this:

```
# Architecture Review — Review: [System/Decision Name]

## Recommendation
**Option [X]** — [1-sentence recommendation]

## Weighted Scores
[Matrix table]

## Key Tensions
- [Conflict 1 and resolution]
- [Conflict 2 and resolution]

## Cost Estimate
| Approach | Dev Effort | Infra/Month | Maintenance |
|----------|-----------|-------------|-------------|
| Option A | 4-6 weeks | ~$300-500   | 3-5 hrs/wk  |
| Option B | 8-12 weeks| ~$200-400   | 6-8 hrs/wk  |

## Action Items
1. [Item]
2. [Item]
3. [Item]
```

---

## Example: Service vs. Monolith Decision

**Scope:** Choosing between a modular monolith and microservices for a new billing system.

**Option A:** Modular monolith (shared database, API modules)
**Option B:** Event-driven microservices (per-service DBs, message broker)

After scoring by all 6 roles:

```
| Approach  | Architect (20%) | Security (20%) | SRE (15%) | Domain (15%) | Product (15%) | QA (15%) | Weighted |
|-----------|----------------|----------------|-----------|--------------|---------------|----------|----------|
| Monolith  | 9              | 8              | 9         | 9            | 9             | 8        | 8.65     |
| Microserv | 6              | 7              | 5         | 8            | 5             | 6        | 6.20     |
```

**Key Tension:** SRE (9 vs 5) and Product (9 vs 5) strongly favor the monolith — operational complexity and slower delivery are dealbreakers for microservices given the 2-person team.

**Cost Estimate:**
| Approach | Dev Effort | Infra/Month | Maintenance |
|----------|-----------|-------------|-------------|
| Monolith | 3-5 weeks | ~$200-300   | 2 hrs/wk    |
| Microserv | 10-16 weeks| ~$600-1000  | 8-12 hrs/wk |

**Recommendation:** Modular monolith. Matches team size, reduces operational burden, delivers faster. Evaluate microservices only if traffic exceeds 10K req/s on the monolith.

---

## Best Practices

- **Involve the user.** Ask clarifying questions during scoping. Don't assume you know the constraints.
- **Flag uncertainty.** If you lack domain or infrastructure context, say so and ask for input.
- **Re-weight deliberately.** The default weights are a starting point — adjust them based on the project's priorities.
- **Keep showstoppers honest.** A showstopper must be genuinely blocking (e.g., "not PCI-compliant by default" for a payment system), not a preference.
- **Don't over-engineer the review itself.** For small decisions, a lightweight version with fewer roles or no formal matrix is fine.

---

## Integration with Other Skills

- **codebase-design** — Use deep module vocabulary (module, interface, depth, seam, adapter) during architecture reviews. When comparing approaches, evaluate their depth: does one hide more complexity behind a smaller interface? Is the seam well-placed? The "two adapters" rule prevents over-engineering ports.
- **plan** — Use after the review to turn the recommendation into a concrete implementation plan, applying deep module principles from codebase-design
- **writing-plans** — For documenting the chosen architecture in a structured design doc
- **spike** — For prototyping the recommended approach before committing
- **change-test-loop** — For implementing the chosen architecture with quality assurance built in
- **root-cause-debugging** — When architecture decisions lead to hard bugs, use the feedback loop approach to diagnose

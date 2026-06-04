---
name: ak-elicit
description: |
  Turn fuzzy or incomplete requirements into clear, testable, enterprise-ready
  requirements using structured elicitation and explicit assumptions.

  Triggers when user mentions:
  - "unclear requirements"
  - "figure out requirements"
  - "what should we build"
  - "scope this feature"
  - "product definition"
---

# AK Elicit

## Purpose
Clarify ambiguous ideas into:
- concrete requirements
- explicit assumptions
- testable acceptance criteria
- a safe first implementation slice

---

## Core Rule

Do not block on missing information.

If needed, make explicit assumptions and proceed.

---

## Modes

Two modes controlled by frontmatter or first-line flag:

| Mode | Flag | Use When |
|---|---|---|
| **Deep** (default) | `mode: deep` | Enterprise features, new products, complex domains |
| **Fast** | `mode: fast` | Small features, clear scope, spike validation |

**Fast mode** produces a lighter output: Goal + Must-Haves + AC + First Slice only. Skips RICE, domain questions, enterprise checklist, and risk deep-dive.

To use: prefix your request with `[fast]` or set `mode: fast` in the skill call.

---

## Output (STRICT)

### Deep mode

```md
# AK Elicit

## Goal
Clear restatement of the problem

## Users / Stakeholders
Who is affected

## Business Value
Why this matters

## Constraints
Technical, business, or system limits

## Must-Haves
Required functionality (prioritised)

## Nice-to-Haves
Optional enhancements (prioritised)

## Prioritization
MoSCoW or RICE table (whichever fits the context — see below)

## Risks
Key uncertainties or failure points

## Open Questions
Only high-impact questions

## Assumptions
Explicit assumptions made

## Acceptance Criteria
Observable success conditions (Given/When/Then)

## Recommended First Slice
Smallest testable step

## Completion Checklist
- [ ] All fields filled
- [ ] Each AC in Given/When/Then
- [ ] Assumptions explicitly labelled
- [ ] At least one acceptance criterion per must-have
- [ ] First slice is implementable in one loop
```

### Fast mode

```md
# AK Elicit (Fast)

## Goal
## Must-Haves
## Acceptance Criteria
## Recommended First Slice
```

---

## Workflow (STRICT)

0. If no starting point exists, run `doc-system` to check existing docs first
1. Restate goal clearly
2. Identify stakeholders and value
3. Identify missing areas
4. Generate high-value questions (use domain question bank below)
5. Convert gaps → assumptions
6. Define must-haves vs nice-to-haves
7. Choose prioritization framework (MoSCoW or RICE)
8. Identify risks
9. Define acceptance criteria
10. Recommend smallest slice
11. Tick completion checklist

---

## Question Rules

Ask only questions that change:

* architecture
* data model
* API contracts
* security model
* user flow
* integration scope

Limit to 5–10 questions. Use the domain question bank below to stay focused.

---

## Prioritization

Choose the right framework for the context:

### MoSCoW (default)
Good for scope-gate-driven projects or when stakeholders can directly rank.

| Bucket | Meaning |
|---|---|
| Must | Non-negotiable for launch |
| Should | Important, can ship later |
| Could | Nice-to-have if time allows |
| Won't | Explicitly out of scope |

### RICE Score
Better when you need a ranked backlog and have confidence estimates.

Reach × Impact × Confidence / Effort

| Factor | Scale | Notes |
|---|---|---|
| Reach | 0.25–5 | How many users/transactions per time period |
| Impact | 0.25–3 | How much each user is affected |
| Confidence | 0.25–1 | How sure are we of Reach/Impact estimates |
| Effort | 1–10 | Person-weeks (higher = worse) |

Include a RICE column in the Must-Haves/Nice-to-Haves section when using this framework:

```
| Requirement | Priority | RICE Score |
|---|---|---|
| FR-1: User login | Must | 4.2 |
| FR-2: Export CSV | Could | 1.1 |
```

---

## Domain Question Bank

Check the relevant domain below and adapt questions to your context. Do not ask questions from domains not in scope.

### API / Integration
- Who are the consumers? (internal service, public API, partner)
- Synchronous (REST/gRPC) or async (events/queue)?
- Rate limits, throttling, or SLA commitments?
- Versioning strategy? (URL, header, contract test)
- Error contract — what does a well-formed failure look like?
- Retry/idempotency semantics?

### Data / Pipeline
- Source system(s) — owned by whom? Freshness SLA?
- Schema evolution — how do we handle backward-incompatible changes?
- Batch or streaming? (latency vs throughput)
- Data retention and deletion policy?
- PII / sensitive fields — masking, tokenization, or exclusion?

### Auth / Security
- Authentication method (OAuth2, SAML, API key, session cookie)?
- Authorization model (RBAC, ABAC, ReBAC)?
- Who are the user personas and what can each do?
- Audit logging requirements — what events, retention, queryability?
- Secrets management — where do keys live?

### Background Jobs / Queues
- What triggers the job? (cron, event, user action)
- Retry policy — exponential backoff? Dead-letter queue?
- Exactly-once or at-least-once semantics?
- Monitoring — staleness alert, failure rate?

### UI / User Flow
- Mobile, desktop, or both?
- Offline support or always-online?
- Accessibility requirements (WCAG level)?
- Loading / empty / error states for every screen?
- What's the critical path users take most often?

### Performance / Scale
- Expected traffic volume (peak, steady-state)?
- P99 latency target?
- Data volume growth per month/year?
- Geographically distributed or single-region?

---

## Assumption Rules

When answers are missing:

* make reasonable assumptions
* label clearly
* prefer safe, simple defaults
* avoid blocking progress

Example:

```txt
Assumption: Only authenticated users can create orders.
```

---

## Acceptance Criteria Rules

Each requirement must be:

* observable
* testable
* unambiguous

Prefer:

```txt
Given <context>
When <action>
Then <result>
```

---

## Template

Write the final output to `docs/prd/<feature>.md`. Use the template at `.agentkore/templates/prd/AK-ELICIT-TEMPLATE.md` (installed by `./run scan-setup` or deploy). It includes all deep-mode fields plus Metadata, FR/NFR tables, and the completion checklist.

---

## Enterprise Considerations

Include when relevant (skip in fast mode):

* roles and permissions
* audit logging
* data lifecycle
* integrations
* observability (logs/metrics)
* performance constraints
* rollback behavior
* compliance/security

---

## First Slice Rules

The first slice must:

* be implementable in one loop
* produce visible/testable outcome
* avoid multi-system complexity
* reduce risk

---

## Completion Checklist

Before declaring output final, verify:

- [ ] All output sections filled (no blanks)
- [ ] Every assumption explicitly labelled `Assumption: ...`
- [ ] Each must-have has ≥1 acceptance criterion in Given/When/Then
- [ ] No hidden or implicit assumptions
- [ ] RICE or MoSCoW documented for every requirement
- [ ] Recommended first slice is scoped to one implementation loop
- [ ] Open Questions recorded with owner and status
- [ ] Domain question bank was consulted for relevant domains
- [ ] Output saved to `docs/prd/<feature>.md`

---

## When to Use

Use before:

```txt
prd-lite
→ ak-party
→ story-slicing
→ task-executor
```

---

## When NOT to Use

Do NOT use for:

* clear, small tasks → use `fast-bmad`
* pure refactors
* trivial bug fixes

---

## Anti-Patterns

Avoid:

* vague goals
* too many questions
* blocking progress for perfect info
* mixing requirements with implementation details
* hidden assumptions
* untestable acceptance criteria
* same prioritization framework every time — pick RICE or MoSCoW per context

---

## Integration with AgentKore

```txt
ak-elicit
→ prd-lite OR fast-bmad
→ story-slicing
→ task-executor
```

---

## Goal

Produce clear, actionable, and testable requirements that:

* remove ambiguity
* enable safe implementation
* work well with small models

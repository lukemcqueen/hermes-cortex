---
name: requirements-elicitation
description: "Requirements elicitation for Hermes Cortex — structured domain exploration, RICE/MoSCoW prioritization, and user-story output with acceptance criteria. Ported from AgentKore."
version: 1.1.0
author: Hermes Agent (ported from AgentKore)
license: MIT
category: software-development
source: hermes-cortex
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [requirements, elicitation, specs, prioritization, rice, moscow, user-stories, acceptance-criteria, domain-exploration]
    related_skills: [plan, spike, subagent-driven-development]
---

# requirements-elicitation — Requirements Elicitation

Use this skill when the user says **"elicit requirements"**, **"gather specs"**, or mentions a feature with **unclear scope**. It structures the discovery of what needs to be built, prioritises it, and produces ready-to-use user stories with acceptance criteria.

## When to use

Trigger this skill when:

- The user asks for requirements or specification gathering
- A feature is mentioned but its boundaries are vague
- The team needs a shared understanding before planning
- Stakeholder needs must be captured and prioritised
- The project has multiple unknowns that need structured discovery

## Modes

Two modes let you match the depth of elicitation to the situation.

### Deep mode — Exhaustive Domain Exploration

Used when the feature is complex, unfamiliar, or has many stakeholders. Use this for new initiatives, architectural decisions, or anything where missing a requirement would be costly.

```
Phase 1:  Context & Stakeholders
Phase 2:  Domain Decomposition
Phase 3:  Question Bank (domain-specific)
Phase 4:  Capture & Structure
Phase 5:  Prioritise (RICE + MoSCoW)
Phase 6:  User Stories + Acceptance Criteria
Phase 7:  Review & Handoff
```

### Fast mode — Quick Capture

Used when the requirement is well-understood but just needs formalising. Skip decomposition; go straight to capture-prioritise-output.

```
Phase 1:  Quick Capture
Phase 2:  Prioritise (MoSCoW only)
Phase 3:  User Stories + Acceptance Criteria
```

## Phase details

### Phase 1: Context & Stakeholders (deep only)

Before asking any questions, establish the frame.

| Question | Purpose |
|----------|---------|
| What domain does this feature live in? | Sets the question-bank selection |
| Who are the primary/secondary stakeholders? | Determines perspective for stories |
| What is the single most important outcome? | Defines the success metric |
| What constraints exist? (time, budget, tech, compliance) | Bounds the solution space |
| Are there existing systems to integrate with? | Surfaces interface requirements |

**Output:** A context block written to the top of the elicitation document.

### Phase 2: Domain Decomposition (deep only)

Break the feature into sub-domains. Each sub-domain becomes a section in the elicitation document and later one or more user stories.

```
Feature: User Notification System
├── Delivery Channels (email, SMS, push, in-app)
├── Preferences & Opt-Out
├── Template Management
├── Scheduling & Rate-Limiting
└── Delivery Analytics
```

Limit to 3–7 sub-domains. Too many means the decomposition level is too fine; too few means it's too coarse.

**Output:** A decomposition tree at the top of the elicitation document.

### Phase 3: Question Bank

Ask questions drawn from the domain-specific bank (see below). In **deep mode**, run through all relevant questions. In **fast mode**, ask only the 3–5 most important ones for each sub-domain.

For each question:

1. **Ask** the question to the user
2. **Capture** their answer verbatim or paraphrased
3. **Dig deeper** if the answer reveals unknowns — follow the chain

Use the format:

```
Q: [question]
A: [user's answer]
→ Follow-up: [if needed]
→ Clarified: [resolved answer]
```

**Output:** A question-answer log in the elicitation document.

### Phase 4: Capture & Structure

Organise everything into a structured format.

```markdown
## [Sub-Domain]

### Context
[What we know so far]

### Key Decisions
- Decision: [description] → Rationale: [why]

### Open Questions
- [question still unresolved]

### Functional Requirements (emerging)
- [requirement statement]

### Non-Functional Requirements (emerging)
- [NFR statement]
```

**Output:** A structured requirements section per sub-domain.

### Phase 5: Prioritisation

Apply two frameworks. RICE first for strategic scoring, then MoSCoW for the final classification.

#### RICE Scoring

Score each requirement on four dimensions (1–5 scale):

| Dimension | 1 | 2 | 3 | 4 | 5 |
|-----------|---|---|---|---|---|
| **Reach** — how many users/stakeholders affected | Few (<5) | Several (5–20) | Team (20–100) | Department (100–500) | Organisation (500+) |
| **Impact** — how much does this move the needle | Negligible | Minor | Moderate | Significant | Transformative |
| **Confidence** — how sure are we of the estimates | Wild guess (<20%) | Low (20–40%) | Medium (40–70%) | High (70–90%) | Certain (>90%) |
| **Effort** — person-days to implement | Trivial (<0.5d) | Small (0.5–2d) | Medium (2–5d) | Large (5–15d) | X-Large (>15d) |

**RICE Score = (Reach × Impact × Confidence) / Effort**

Present scores in a table:

| # | Requirement | Reach | Impact | Confidence | Effort | RICE Score |
|---|-------------|-------|--------|------------|--------|------------|
| F-001 | Send email notifications | 4 | 4 | 4 | 2 | 32 |
| F-002 | In-app notification preferences | 3 | 3 | 3 | 3 | 9 |
| ... | ... | ... | ... | ... | ... | ... |

#### MoSCoW Classification

After RICE scoring, classify each requirement:

| Category | Meaning | RICE guidance |
|----------|---------|---------------|
| **M**ust have | Non-negotiable for launch | Score typically > 20 |
| **S**hould have | Important but not critical | Score 10–20 |
| **C**ould have | Nice to have if time permits | Score 5–10 |
| **W**on't have | Explicitly out of scope this round | Score < 5 |

**Output:** A prioritised requirements list with both RICE scores and MoSCoW categories.

### Phase 6: User Stories + Acceptance Criteria

Transform each Must-have and Should-have requirement into a user story with acceptance criteria. Could-have stories are optional.

```markdown
### [US-NNN] — [Story Title]

**As a** [user role],
**I want** [goal/desire],
**So that** [benefit/reason].

**Priority:** [Must / Should]
**RICE:** [score]

**Acceptance Criteria:**

- [ ] Given [context], when [action], then [expected outcome]
- [ ] Given [context], when [action], then [expected outcome]
- [ ] Edge case: [description]
- [ ] Error case: [description]

**Notes:**
- [implementation hints, constraints, links]
```

**Output:** A numbered list of user stories ready for sprint planning.

### Phase 7: Review & Handoff

Present the user with a summary:

- Total requirements captured: X
- Must-haves: X | Should-haves: X | Could-haves: X | Won't-haves: X
- Total user stories created: X
- Open questions remaining: X
- Recommended next step: (e.g., "hand these stories to `plan` skill", "run spike on F-003", "review with stakeholders")

## Domain-Specific Question Banks

Below are question banks organised by domain. Each bank contains 5–15 questions. Pick the relevant bank, ask all questions in deep mode, or select 3–5 in fast mode.

### Web / API Services

1. What API operations are needed (CRUD, webhooks, streaming)?
2. Who are the API consumers (first-party, third-party, internal)?
3. What authentication / authorisation model is required?
4. What are the rate limit and throttling expectations?
5. What SLAs apply (uptime, latency, throughput)?
6. What pagination, filtering, and sorting are needed on list endpoints?
7. What webhook events should be emitted, and to whom?
8. What error response format should be used (RFC 7807 / Problem Details)?
9. What versioning strategy is needed (URL, header, query param)?
10. Are there idempotency requirements for mutating endpoints?
11. What data retention and purging policies apply?
12. Is the API expected to be documented (OpenAPI / Swagger)?

### Database / Data Layer

1. What entities need to be stored, and what are their relationships?
2. What are the expected read/write volumes and patterns?
3. What query patterns need to be supported (exact match, full-text, geo, graph)?
4. What consistency and isolation levels are required?
5. What is the expected data growth rate and retention period?
6. Are there reporting / analytics queries that need optimisation?
7. What migration strategy should be used?
8. What backup and disaster recovery requirements exist?
9. Are there compliance requirements (GDPR, HIPAA, PCI, SOC2)?
10. What audit trail / change capture requirements exist?
11. Should the data layer support multi-tenancy? How is it isolated?
12. What caching strategy is needed (write-through, cache-aside, CDN)?

### User Interface / UX

1. Who are the target users, and what are their primary goals?
2. What devices and screen sizes must be supported?
3. What accessibility standards (WCAG level) are required?
4. What is the expected user journey / flow from entry to completion?
5. What feedback mechanisms should be provided (loading, empty, error, success states)?
6. What i18n / l10n requirements exist (languages, date/number formats)?
7. What customisation / personalisation is expected?
8. What onboarding experience is needed?
9. What keyboard navigation and shortcut support is required?
10. Are there any offline / low-connectivity requirements?
11. What notification patterns are needed (toasts, banners, badges)?
12. What analytics / telemetry should be captured about user interactions?

### Authentication & Authorisation

1. What identity providers need to be supported (SSO, OAuth, SAML, LDAP)?
2. What role hierarchy or permission model is needed (RBAC, ABAC, ReBAC)?
3. What self-service capabilities are needed (registration, password reset, profile management)?
4. What session management requirements exist (JWT, cookies, refresh tokens, expiry)?
5. What MFA / 2FA requirements apply?
6. What account recovery and lockout policies should be enforced?
7. What token scope / delegation model is needed?
8. Are there API-key / machine-to-machine auth requirements?
9. What audit logging requirements exist for auth events?
10. What compliance requirements apply (SOC2, FedRAMP, GDPR Articles)?

### DevOps / Infrastructure / Delivery

1. What deployment environments are needed (dev, staging, production, DR)?
2. What CI/CD pipeline requirements exist (test stages, approval gates)?
3. What monitoring / alerting thresholds are expected?
4. What logging requirements exist (structured, centralised, retention)?
5. What containerisation / orchestration requirements apply?
6. What secret management approach is needed?
7. What are the scalability requirements (auto-scaling, max concurrency)?
8. What are the disaster recovery requirements (RPO, RTO)?
9. What cost management / budget constraints exist for infrastructure?
10. What compliance scanning / security testing is required (SAST, DAST, dependency scanning)?
11. What feature flag / rollout strategy is needed?
12. What database migration automation is required?

### Integration / Third-Party Services

1. What external systems need to be integrated, and what do they expose (API, file, webhook)?
2. What is the expected data flow direction and frequency (real-time, batch, polling)?
3. What error handling and retry strategy should be used on integration points?
4. What data transformation / mapping is required between systems?
5. What circuit breaker / fallback behaviour is needed when an external system is down?
6. What vendor SLA and deprecation policies apply?
7. Are there synchronous vs. asynchronous integration preferences?
8. What idempotency and exactly-once delivery guarantees are needed?
9. What integration testing strategy should be used (contract tests, sandbox)?
10. What billing / metering requirements exist for third-party API usage?

### AI / ML Features

1. What model capabilities are needed (classification, generation, embedding, RAG)?
2. What latency and throughput requirements apply to inference?
3. What data is needed for training / fine-tuning, and where does it live?
4. What evaluation / test set exists to measure model quality?
5. What guardrails and safety filters are required on outputs?
6. What human-in-the-loop / review workflows are needed?
7. What explainability / transparency requirements exist?
8. What model versioning and A/B testing approach is needed?
9. What cost constraints apply to API calls or compute?
10. What prompt engineering / template management approach is needed?
11. What logging and traceability is required for model inputs and outputs?
12. What privacy requirements apply to data sent to external model providers?
13. What fallback behaviour should occur when the model is unavailable?

### Security & Compliance

1. What data classification levels apply (public, internal, confidential, restricted)?
2. What encryption requirements exist (at-rest, in-transit, key management)?
3. What vulnerability management and patching cadence is required?
4. What penetration testing and security review cadence is expected?
5. What third-party vendor security assessment process is needed?
6. What breach notification and incident response procedures apply?
7. What compliance frameworks are in scope (SOC2, ISO 27001, PCI-DSS, HIPAA, FedRAMP)?
8. What data retention and deletion policies apply per regulation?
9. What user consent and data subject request handling is needed (GDPR / CCPA)?
10. What network segmentation and firewall rules are required?
11. Are there BYOK / HYOK expectations for encryption keys?
12. What secure coding standards should be enforced (OWASP Top 10, CWE)?

## Output Format — Elicitation Document

The complete output is a single markdown document saved to `.hermes/elicit/` with this structure:

```markdown
# Elicitation: [Feature Name]

**Mode:** Deep / Fast
**Date:** YYYY-MM-DD
**Stakeholders:** [list]
**Domain:** [primary domain]

---

## Context

[from Phase 1 — what is this feature, key constraints, success metric]

---

## Domain Decomposition

[from Phase 2 — tree or list of sub-domains]

---

## Question Log

### Sub-Domain: [name]

Q: [question]
A: [answer]

Q: [question]
A: [answer]

...

---

## Structured Requirements

### [Sub-Domain]

**Functional:**
- F-001: [requirement]
- F-002: [requirement]

**Non-Functional:**
- NF-001: [requirement]

---

## Prioritisation

| # | Requirement | Reach | Impact | Confidence | Effort | RICE | MoSCoW |
|---|-------------|-------|--------|------------|--------|------|--------|
| ... | ... | ... | ... | ... | ... | ... | ... |

---

## User Stories

### [US-001] — [Title]

**As a** [role] **I want** [goal] **So that** [benefit]

**AC:**
- [ ] Given ..., when ..., then ...

---

## Summary

- Total requirements: X
- Must: X | Should: X | Could: X | Won't: X
- Stories created: X
- Open questions: X
- Recommended next: [plan / spike / review]
```

## Interaction Flow

### Starting the elicitation

When the user triggers the skill, respond with:

1. **Confirm mode:** "I'll use **deep** mode for this — is that right, or would you prefer **fast** mode?"
2. **Ask context questions** (Phase 1 or Phase 1 skip in fast mode)
3. **Proceed through phases**, presenting each result before moving on

### Concurrent elicitation (deep mode, multi-sub-domain)

When a sub-domain has many open questions that are independent, you may ask 3–5 questions in a single turn rather than one at a time. Group them by theme and present as a numbered list.

### Terminating early

The user may say "that's enough, give me the stories" at any point. Honour that immediately. Skip remaining phases and produce stories from whatever you have captured.

## Save location

Save the elicitation document with `write_file` under:

`.hermes/elicit/YYYY-MM-DD_HHMMSS-<feature-slug>.md`

Treat that as relative to the active working directory / backend workspace. If the runtime provides a specific target path, use that exact path.

## Example: Fast Mode (abbreviated)

```
User: "I need a simple API to track user bookmarks."

Agent: [Fast mode]
- Domain: Web / API Services
- Questions asked: 5 (auth, CRUD ops, data model, pagination, error format)
- Requirements captured: 4 functional, 2 non-functional
- MoSCoW: 2 Must, 2 Should, 1 Could, 1 Won't
- Stories created: 3

Time: ~3 turns including this summary.
```

## Example: Deep Mode (abbreviated)

```
User: "We're building an AI-powered customer support system."

Agent: [Deep mode]
- Sub-domains: Intent Classification, Knowledge Base, Conversation History, Escalation, Analytics
- Questions asked: 38 across 5 sub-domains
- Requirements captured: 22 functional, 7 non-functional
- RICE scored, MoSCoW classified: 8 Must, 7 Should, 8 Could, 6 Won't
- Stories created: 12

Time: ~10–15 turns including context and follow-ups.
```

## Attribution

Adapted from AgentKore's requirements elicitation workflow — MIT © 2025. Originally developed for structured domain exploration in AI-assisted software projects.

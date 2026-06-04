---
name: prd-lite
description: |
  Create a concise, enterprise-ready PRD covering scope, constraints,
  architecture impact, risks, and acceptance criteria.

  Triggers when user mentions:
  - "prd"
  - "requirements doc"
  - "feature spec"
  - "define scope"
  - "product requirements"
---

# PRD Lite (Enterprise)

## Purpose
Define a feature clearly enough to:
- build correctly
- test reliably
- avoid rework
- align engineering + product

Keep concise (≈1 page). Expand only if necessary.

---

## Output (STRICT)

```md
# PRD: <Feature Name>

## 1. Problem
What problem exists? Why now?

## 2. User / Stakeholder
Who is affected? (primary + secondary)

## 3. Goal / Success Metrics
What success looks like (measurable if possible)

## 4. Scope (In)
What is included

## 5. Non-Goals (Out)
What is explicitly excluded

## 6. Requirements (Functional)
- clear, testable behaviors

## 7. Requirements (Non-Functional)
- performance (latency, scale)
- reliability (uptime, retries)
- security (auth, data handling)
- compliance (if applicable)

## 8. Edge Cases
- failure modes
- boundary conditions

## 9. Acceptance Criteria
- testable conditions (Given/When/Then preferred)

## 10. Risks
- technical
- product
- operational

## 11. Dependencies
- services, APIs, teams, data

## 12. Rollout / Migration
- deployment strategy
- backward compatibility
- data migration (if any)

## 13. Observability
- logs
- metrics
- alerts

## 14. Open Questions
- unresolved decisions
```

---

## Invocation

For the full PRD workflow, first use `ak-elicit` to clarify
requirements, then `ak-party` for architecture review, then
`doc-system` to save and link the document.

---

## Workflow (STRICT)

1. Clarify unclear requirements (use `ak-elicit` if needed)
2. Keep scope tight
3. Define acceptance criteria early
4. Identify risks before implementation
5. Include only necessary detail (avoid over-spec)

---

## Rules

* Must be testable
* Must define clear boundaries (in/out)
* Avoid vague language ("fast", "better")
* Prefer measurable outcomes
* Keep under ~1 page unless complexity requires more

---

## When to Expand

Switch to deeper mode if:

* multi-system architecture
* high risk / high cost
* unclear ownership
* major data migration

Then pair with:

* `ak-party`
* ADR (architecture decision record)

---

## Save Location

```txt
docs/prd/<feature-name>.md
```

---

## Anti-Patterns

Avoid:

* vague requirements
* missing acceptance criteria
* mixing goals with implementation
* ignoring non-functional requirements
* no rollout plan for risky changes

---

## Goal

Produce a **small, precise PRD** that:

* engineers can implement without guessing
* testers can verify easily
* reduces rework in enterprise systems

---
name: story-slicing
description: |
  Break product or technical work into small, user-visible, testable stories
  with acceptance criteria, risks, and verification steps.

  Triggers when user mentions:
  - "story slicing"
  - "break into stories"
  - "user stories"
  - "implementation slices"
  - "split feature"
---

# Story Slicing

## Purpose
Convert feature scope into small stories that can be executed safely with:

```txt
story-slicing → prd-to-tasks → task-executor → change-test-loop
```

---

## Output (STRICT)

```md
# Story Slices: <Feature>

## S1: <Story Title>
As a <user>, I want <capability>, so that <benefit>.

### Scope
- Included:
- Excluded:

### Acceptance Criteria
- [ ] Success:
- [ ] Failure:
- [ ] Edge case:
- [ ] Test/verification:

### Implementation Notes
- Files/areas likely affected:
- Dependencies:
- Risk: low | medium | high

### Verification
- Command/test:
- Expected result:
```

---

## Workflow (STRICT)

1. Read feature/PRD/context
2. Identify user-visible outcomes
3. Split by smallest valuable behavior
4. Add acceptance criteria per slice
5. Add edge/failure cases
6. Add verification steps
7. Order slices by dependency and risk

---

## Good Slice Rules

A good slice is:

* user-visible or externally observable
* independently testable
* small enough for one agent loop
* deployable or reversible where possible
* clear about what is NOT included

---

## Slice Types

Use one primary type per slice:

* `foundation` → setup needed before user value
* `feature` → user-visible capability
* `integration` → connects services/APIs
* `migration` → schema/data change
* `hardening` → security/performance/reliability
* `test` → coverage for existing behavior

---

## Ordering Rules

Prefer this order:

```txt
foundation → smallest happy path → failure handling → edge cases → hardening
```

High-risk slices should include rollback notes.

---

## Acceptance Criteria Rules

Each story must include:

* success outcome
* failure behavior
* edge case
* test or verification method

Prefer:

```txt
Given <context>
When <action>
Then <observable result>
```

---

## Enterprise Considerations

Add explicit notes when relevant:

* auth / permissions
* audit logging
* data migration
* backward compatibility
* observability
* performance impact
* rollback strategy
* compliance / privacy

---

## Anti-Patterns

Avoid:

* “build the whole feature”
* purely technical slices with no verification
* vague acceptance criteria
* hidden dependencies
* mixing unrelated concerns
* stories too large for one change-test loop

---

## Goal

Produce small, ordered, testable stories that reduce risk and let smaller models implement complex systems safely.
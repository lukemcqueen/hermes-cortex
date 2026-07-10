---
name: story-decomposition
description: "Break features into user-visible, testable stories using vertical slicing patterns."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [story-decomposition, agile, user-stories, acceptance-criteria, vertical-slices, invest]
    related_skills: [plan, change-test-loop, writing-plans]
---

# Story Slicing

## Overview

Turn features into independently deliverable, user-visible stories. A well-sliced story is testable, demonstrable, and fits a single sprint.

**Core principle:** A story must deliver value to a user in a single vertical slice — not a horizontal layer (database, API, UI separately).

## When to Use

- Breaking down epics or feature requests
- Planning a sprint or iteration
- Decomposing ambiguous requirements
- Reviewing existing stories that feel too large or too small
- Before writing acceptance criteria or tests

## Vertical Slicing Pattern

**Vertical slice = a thin end-to-end feature that touches all architectural layers.**

```
           USER
            |
        +---+---+
        |  UI   |  ← story lives here
        +---+---+
            |
        +---+---+
        | Logic |  ← not here in isolation
        +---+---+
            |
        +---+---+
        | Data  |  ← and not here alone
        +---+---+
```

A vertical slice crosses every layer to deliver one piece of user-facing value.

### Good Vertical Slice

- **"User can reset their password via email"** — touches UI (form), logic (token generation, expiry), data (store token, update password)

### Bad Horizontal Slices

- "Design the password reset database schema" — not user-visible
- "Build the password reset API endpoint" — no user value alone
- "Add a reset password button to settings page" — not functional until backend exists

### How to Slice Vertically

1. **Identify the user** — who gets value?
2. **Identify the outcome** — what can they do afterward that they couldn't before?
3. **Find the thinnest path** — simplest end-to-end flow that delivers that outcome
4. **Slice by user action, not by layer** — each story is one user action through all layers
5. **Validate: does this make sense to demo?** — if you can't demo it to a stakeholder, it's not a vertical slice

## Story Sizing Guidelines

Use these as a rough calibration. Adjust based on your team's velocity.

| Size | Scope | Effort | Timeline |
|------|-------|--------|----------|
| **Small** | One clear acceptance criterion, minimal logic change | Minutes to a few hours | Same day |
| **Medium** | 3–5 acceptance criteria, touches 2–3 files, possible new component | Half day to ~2 days | 1–2 days |
| **Large** | Complex workflow, unknowns, multiple acceptance criteria across states | 2–5 days | 3–5 days |

### Small Story (Minutes – Hours)

- Change label text or button copy
- Add a simple form field with validation
- Expose an existing field in the API response
- Single-route redirect

### Medium Story (Half Day – 2 Days)

- Search with filters on an existing data type
- User role-based access control for a single action
- Bulk import with validation and error reporting
- Password reset flow (request → email → reset → confirm)

### Large Story (2–5 Days)

- Multi-step wizard with conditional branches
- Payment integration for one payment method
- User onboarding flow (registration → profile → first action)
- Export with format selection, progress tracking, and file delivery

### When a Story Exceeds 5 Days

**Slice again.** A story larger than 5 days is an epic or a feature. Break it into smaller vertical slices.

## Acceptance Criteria Template (Given/When/Then)

Use this structured format for all stories. It maps cleanly to both manual testing and automated tests.

```gherkin
Feature: [Feature Name]

  Scenario: [Descriptive scenario name]
    Given [precondition or context]
      And [additional precondition]
     When [action is performed]
      And [subsequent action]
     Then [expected outcome]
      And [additional outcome]
```

### Template with placeholders

```gherkin
Feature: <feature name>

  Scenario: <what happens and under what condition>
    Given <initial state / context>
      And <additional precondition>
     When <user action or event>
      And <follow-up action>
     Then <observable result>
      And <additional observable result>
```

### Examples

**Good:**

```gherkin
Feature: Password Reset

  Scenario: User resets password with valid token
    Given a user "alice@example.com" exists
      And a valid password reset token was issued to "alice@example.com"
     When the user submits the reset form with token and new password "NewP@ss1"
     Then the password is updated
      And a confirmation email is sent to "alice@example.com"
```

**Good (negative case):**

```gherkin
Feature: Password Reset

  Scenario: User attempts reset with expired token
    Given a user "bob@example.com" exists
      And an expired password reset token for "bob@example.com"
     When the user submits the reset form with the expired token
     Then an error message "Token expired. Request a new reset link." is shown
      And the password is NOT updated
```

**Bad (vague, not testable):**

```
Feature: Password Reset
  Scenario: User resets password
    Given the user is on the reset page
    When they fill in the form
    Then it works
```

### Guidelines for Good Given/When/Then

- **Given** — setup. Concrete state, not "user is logged in" but "user 'alice' has session"
- **When** — action. One verb per scenario. Avoid "and" in When if possible
- **Then** — observable outcome. Describe the result, not implementation ("a 200 OK" is implementation; "the password is updated" is behavior)
- One scenario tests one behavior. If you need multiple Then clauses checking unrelated things, split the scenario
- **Test happy path + error cases** — each negative scenario is its own scenario

## INVEST Checklist

A good story must be **I**ndependent, **N**egotiable, **V**aluable, **E**stimable, **S**mall, **T**estable.

Run through this checklist for every story before accepting it into a sprint:

| Letter | Criterion | Check | Ask yourself |
|--------|-----------|-------|--------------|
| **I** | **Independent** | ☐ | Can this be built and released without waiting for another story? If not, can it be re-sliced? |
| **N** | **Negotiable** | ☐ | Is there room to adjust scope, implementation, or detail? Or is it a rigid spec? |
| **V** | **Valuable** | ☐ | Does a user get value from this story independently, in a single sprint? |
| **E** | **Estimable** | ☐ | Could two team members independently produce a similar estimate? Or are there too many unknowns? |
| **S** | **Small** | ☐ | Can this be completed within the sprint (ideally < 3 days)? If not, slice it. |
| **T** | **Testable** | ☐ | Are acceptance criteria written as clear pass/fail conditions? Could QA run them without asking for clarification? |

### INVEST in Practice

**Independent** — Stories should be ordered by priority. If story B depends on story A, consider:
- Making them the same story
- Re-slicing so each delivers value independently
- Documenting the dependency explicitly if unavoidable

**Negotiable** — A story is negotiable if the team can discuss implementation details. Red flags:
- "Must use technology X"
- Detailed UI mockup with no room for change
- Requirements that specify implementation rather than behavior

**Valuable** — Value is from the user's perspective, not the developer's:
- "Add a `users_count` field to the API response" (no user value)
- "Show admin how many users are registered on the dashboard" (user value for admin)

**Estimable** — A story is estimable when the team understands the scope. If estimates vary wildly:
- Run a spike to resolve unknowns
- Slice smaller to reduce uncertainty
- Add a timeboxed investigation story

**Small** — Small means completable. If a story wouldn't fit on a 3×5 index card, it's probably too big.

**Testable** — A story needs clear pass/fail. If the acceptance criteria can't be executed as automated or manual tests, rewrite them. "UI looks good" is not testable. "The success message appears below the form in green text" is testable.

## Common Slicing Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| **Horizontal slice** (API layer in one story, UI in another) | Nothing demo-able until both done | Combine into one vertical slice per user action |
| **Technical story** (set up CI, refactor database, add logging) | No user value | Wrap in a user-facing story, or make it a chore (not a story) |
| **Fat story** (everything about users: register, login, profile, reset) | Can't finish in a sprint | Slice by user action — one action per story |
| **Tiny story** (change button color, update error message) | No real value, overhead > benefit | Batch related tiny changes into one story |
| **Zombie story** (no defined acceptance criteria) | Can't test, can't demo, can't estimate | Add Given/When/Then criteria or reject the story |
| **Implementation story** ("Add a database index on email") | Doesn't describe user behavior | Reframe: "User can sign up without timeout" with performance acceptance criteria |

## Verification Checklist

Before marking a story as ready:

- [ ] Sliced vertically (touches all layers, end-to-end)
- [ ] Size is small or medium (< 3 days)
- [ ] Acceptance criteria written as Given/When/Then
- [ ] Happy path scenario covered
- [ ] At least one error/edge-case scenario covered
- [ ] All INVEST items checked
- [ ] Story makes sense when demoed to a non-technical stakeholder
- [ ] Can be independently released (no hard dependency on unstarted stories)

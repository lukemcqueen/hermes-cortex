---
name: change-test-loop
version: 1.1.0
category: software-development
description: "RED-GREEN-REFACTOR loop with confidence scoring, retry limits, coverage requirements, and strict TDD discipline."
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [testing, tdd, red-green-refactor, confidence-scoring, retry, coverage, discipline]
    related_skills: [systematic-debugging, plan, subagent-driven-development]
---

# Change-Test Loop

## Overview

A disciplined RED-GREEN-REFACTOR loop augmented with **confidence scoring**, **retry governance**, and **coverage requirements** per change type. This skill ensures every change — whether a new feature, bug fix, or refactor — follows a repeatable, verifiable cycle with clear success criteria and a hard upper bound on iteration.

**Core principle:** Confidence is measured, not assumed. Each cycle phase scores confidence on a 3/2/1/0 scale. A score of 0 triggers a fallback. Maximum 2 retry iterations per phase before escalation.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over.

**No exceptions:**
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Don't look at it
- Delete means delete

Implement fresh from tests. Period.

## The Loop

```
┌─────────────────────────────────────────────────┐
│                  CHANGE-TEST LOOP                │
│                                                   │
│   RED ──→ GREEN ──→ REFACTOR ──→ [repeat/next]   │
│    │         │          │                         │
│    ↓         ↓          ↓                         │
│  Score     Score      Score                       │
│  (fail)    (pass)    (quality)                    │
│                                                   │
│  If score < threshold → retry (max 2×)            │
│  If all retries fail  → fallback                  │
└─────────────────────────────────────────────────┘
```

## RED — Write Failing Test

Write a single test that describes the desired behavior before any implementation exists.

### Requirements

- One behavior per test
- Clear descriptive name (if name contains "and", split the test)
- Tests real code, not mocks (mocks only if truly unavoidable)
- Name describes behavior, not implementation

### Confidence Scoring

| Score | Criterion |
|-------|-----------|
| 3 | Test is written, fails for the expected reason (feature missing), failure message is clear and correct |
| 2 | Test fails, but failure message is ambiguous or the failure reason is unexpected |
| 1 | Test errors (typo, import error, syntax issue) rather than failing on assertion |
| 0 | Test passes immediately, no test written, or test written after code |

**Pass threshold:** ≥ 2

**Retry limit:** If score < 2, fix the test and re-run. Max **2 retries**. If still < 2 after retries, escalate to fallback.

### Verification

```bash
# Run the specific test and confirm it FAILS
pytest tests/test_feature.py::test_name -v
```

Confirm:
- Test fails (not errors from typos or missing imports)
- Failure message matches expectation
- Fails because the feature is missing, not because the test is wrong

**Test passes immediately?** You are testing existing behavior. The test must describe *new* behavior. Fix the test or delete it and write a proper one.

**Test errors?** Fix the error, re-run until it fails correctly.

## GREEN — Minimal Implementation

Write the simplest code that makes the failing test pass. Nothing more.

### Principles

- **Cheating is allowed:** hardcode return values, copy-paste, duplicate code, skip edge cases — all fine. Cleanup happens in REFACTOR.
- **No extra features:** don't add logging, validation, or polish beyond what the test requires.
- **No refactoring:** resist the urge to improve other code. Stay focused.

### Confidence Scoring

| Score | Criterion |
|-------|-----------|
| 3 | Code passes the test, all existing tests still pass, output is pristine (no warnings/errors), implementation is minimal |
| 2 | Code passes the test but introduces minor warnings, or the implementation includes unnecessary code |
| 1 | Code passes the test but other tests break, or the output shows errors/warnings unrelated to the change |
| 0 | Code does not pass the test, or the implementation was changed to pass by altering the test |

**Pass threshold:** ≥ 2

**Retry limit:** Max **2 retries**. If score < 2 after retries, escalate to fallback.

### Verification

```bash
# Run the specific test — confirm it PASSES
pytest tests/test_feature.py::test_name -v

# Run the full suite — confirm no regressions
pytest tests/ -q
```

Confirm:
- The test passes
- All other tests still pass
- Output is clean (no errors, warnings, deprecation notices)

**Test still fails?** Fix the code, not the test.

**Other tests fail?** Fix regressions immediately or revert the change.

## REFACTOR — Clean Up

Only after GREEN is confirmed. Remove duplication, improve names, extract helpers, simplify expressions. No new behavior.

### Rules

- Keep tests green throughout every refactor step
- Make small, atomic changes
- Run the full test suite after each change

### Confidence Scoring

| Score | Criterion |
|-------|-----------|
| 3 | Code is clean and well-structured, tests still pass, no duplication, clear naming, no regressions |
| 2 | Some minor duplication or naming issues remain but tests pass |
| 1 | Refactoring introduced warnings or near-duplicate code |
| 0 | Tests broke during refactor, or behavior was accidentally changed |

**Pass threshold:** ≥ 2

**Retry limit:** If tests break, undo immediately and take smaller steps. Max **2 retries** per refactor attempt.

### Verification

```bash
# Run the full suite after each refactor step
pytest tests/ -q
```

If tests fail at any point: **Undo immediately.** The change was too large. Take smaller steps.

## Retry Governance

Each phase (RED, GREEN, REFACTOR) has a hard limit of **2 retry iterations**.

```
Phase start
  ↓
Attempt 1 → score ≥ threshold? → Yes → proceed to next phase
  ↓ No
Attempt 2 (retry 1) → score ≥ threshold? → Yes → proceed
  ↓ No
Attempt 3 (retry 2) → score ≥ threshold? → Yes → proceed
  ↓ No
FALLBACK
```

### Fallback Actions

When all retries are exhausted for a phase:

1. **RED fallback:** Ask the user for test guidance. They may provide an example test or clarify desired behavior.
2. **GREEN fallback:** Revert to the last known green state. Ask the user for implementation hints. Consider spike/prototyping first.
3. **REFACTOR fallback:** Skip refactoring for this cycle. Note the debt and move on. The debt is addressed in a dedicated refactor cycle later.

**Never** silently continue with a score of 0 after exhausting retries. Always escalate.

## Coverage Requirements per Change Type

Different types of changes require different levels of test coverage.

| Change Type | Coverage Requirement | Examples |
|---|---|---|
| **New feature** | ≥ 90% of new code covered. All public functions tested. Edge cases and error paths required. | Adding a new API endpoint, new module, new command |
| **Bug fix** | One test reproducing the bug (proves fix). Regression test for related paths. | Off-by-one error, null pointer, race condition |
| **Refactor** | No new behavior, so existing tests must all pass unchanged. If the refactor changes interfaces, update tests first (RED step). | Renaming, extracting helper, simplifying logic |
| **Performance** | Benchmark tests before and after. Functional parity tests unchanged. | Query optimization, cache addition, algorithm change |
| **Configuration** | Test that the config loads correctly. Test that behavior changes as expected with the new config. | Environment variable change, config file update, feature flag |
| **Dependency update** | Full test suite must pass. If breaking changes expected, treat as new feature + deprecation. | Library version bump, framework upgrade |
| **Documentation** | No functional tests needed. Spell-check and link-check CI should pass. | README update, docstring improvements, API docs |
| **Generated code** | Review generated code manually. Add integration tests. Unit tests may be skipped with justification. | Scaffolding, boilerplate, codegen output |

### Minimal Viable Coverage Matrix

For each change, at minimum:

| Change Type | Unit Tests | Integration Tests | E2E Tests |
|---|---|---|---|
| New feature | Required | Required | Recommended |
| Bug fix | Required | Recommended | Optional |
| Refactor | Required (all pass) | Required (all pass) | Required (all pass) |
| Performance | Benchmark | Required (all pass) | Optional |
| Configuration | Required | Recommended | Optional |
| Dependency update | Required (all pass) | Required (all pass) | Recommended |

## Confidence Score Summary

| Phase | 3 | 2 | 1 | 0 |
|---|---|---|---|---|
| **RED** | Test fails for expected reason with clear message | Test fails but message ambiguous | Test errors (typo, import) | Test passes, no test, or code-first |
| **GREEN** | Passes + pristine output + minimal | Passes with minor warnings | Other tests break | Doesn't pass or test was altered |
| **REFACTOR** | Clean code, tests pass, no duplication | Minor issues remain, tests pass | Warnings or near-duplicates | Tests broke or behavior changed |

**Pass threshold for all phases: ≥ 2**

## Complete Workflow Example

```python
# 1. RED — Write failing test
def test_user_can_register_with_email():
    result = register_user(email="a@b.com", password="secret123")
    assert result.success is True
    assert result.user.email == "a@b.com"

# Run test → fails: register_user doesn't exist (score 3 — correct failure)
# Confidence: 3 ✅

# 2. GREEN — Minimal code
def register_user(email, password):
    return RegistrationResult(success=True, user=User(email=email))

# Run test → passes (score 3)
# Run full suite → all pass (score 3)
# Confidence: 3 ✅

# 3. REFACTOR — Clean up
# No duplication found, naming is clear (score 3)
# Confidence: 3 ✅

# Next: repeat loop for password hashing, duplicate email check, etc.
```

## Why Order Matters

**"I'll write tests after to verify it works"**

Tests written after code pass immediately. Passing immediately proves nothing:
- Might test the wrong thing
- Might test implementation, not behavior
- Might miss edge cases you forgot
- You never saw it catch the bug

Test-first forces you to see the test fail, proving it actually tests something.

**"I already manually tested all the edge cases"**

Manual testing is ad-hoc. You think you tested everything but:
- No record of what you tested
- Can't re-run when code changes
- Easy to forget cases under pressure
- "It worked when I tried it" ≠ comprehensive

Automated tests are systematic. They run the same way every time.

**"Deleting X hours of work is wasteful"**

Sunk cost fallacy. The time is already gone. Your choice now:
- Delete and rewrite with TDD (high confidence)
- Keep it and add tests after (low confidence, likely bugs)

The "waste" is keeping code you can't trust.

**"TDD is dogmatic, being pragmatic means adapting"**

TDD IS pragmatic:
- Finds bugs before commit (faster than debugging after)
- Prevents regressions (tests catch breaks immediately)
- Documents behavior (tests show how to use code)
- Enables refactoring (change freely, tests catch breaks)

"Pragmatic" shortcuts = debugging in production = slower.

**"Tests after achieve the same goals — it's spirit not ritual"**

No. Tests-after answer "What does this do?" Tests-first answer "What should this do?"

Tests-after are biased by your implementation. You test what you built, not what's required. Tests-first force edge case discovery before implementing.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Too simple to test" | Simple code breaks. Test takes 30 seconds. |
| "I'll test after" | Tests passing immediately prove nothing. |
| "Tests after achieve same goals" | Tests-after = "what does this do?" Tests-first = "what should this do?" |
| "Already manually tested" | Ad-hoc ≠ systematic. No record, can't re-run. |
| "Deleting X hours is wasteful" | Sunk cost fallacy. Keeping unverified code is technical debt. |
| "Keep as reference, write tests first" | You'll adapt it. That's testing after. Delete means delete. |
| "Need to explore first" | Fine. Throw away exploration, start with TDD. |
| "Test hard = design unclear" | Listen to the test. Hard to test = hard to use. |
| "TDD will slow me down" | TDD faster than debugging. Pragmatic = test-first. |
| "Manual test faster" | Manual doesn't prove edge cases. You'll re-test every change. |
| "Existing code has no tests" | You're improving it. Add tests for the code you touch. |

## Integration with Hermes Agent

### With delegate_task

Enforce the change-test loop in subagent goals:

```python
delegate_task(
    goal="Implement user registration using the change-test loop",
    context="""
    Follow the change-test-loop skill:
    1. RED — Write a failing test first
       - Score your confidence (target ≥ 2)
       - Max 2 retries per phase
    2. GREEN — Minimal implementation to pass
       - Score your confidence
       - Run full test suite
    3. REFACTOR — Clean up while keeping tests green
       - Score your confidence
    4. Check coverage requirements for 'new feature'

    Project test command: pytest tests/ -q
    Project structure: [relevant paths]
    """,
    toolsets=['terminal', 'file']
)
```

### With systematic-debugging

Bug found? Use the change-test loop:

1. **RED:** Write a test that reproduces the bug (fails as expected)
2. **GREEN:** Fix the code minimally
3. **REFACTOR:** Clean up the fix

The test that reproduced the bug becomes a permanent regression guard.

## When to Skip (ask the user first)

- Throwaway prototypes
- Configuration-only changes (but config loading still needs a test)
- Generated code (with manual review + integration tests)

## Testing Anti-Patterns

- **Testing mock behavior instead of real behavior** — mocks should verify interactions, not replace the system under test
- **Testing implementation details** — test behavior/results, not internal method calls
- **Happy path only** — always test edge cases, errors, and boundaries
- **Brittle tests** — tests should verify behavior, not structure; refactoring shouldn't break them

## Red Flags — STOP

If you catch yourself doing any of these, delete the code and restart with TDD:

- Skipping a phase (especially RED)
- Code written before the test
- Test passes immediately on first run
- Test after implementation, or tests added "later"
- Can't explain why test failed
- Confidence scored without verification
- Continuing after exhausting retries without fallback
- Ignoring failing tests from other parts of the suite
- Coverage below the minimum for the change type
- Rationalizing "just this once", "this is different because...", or any of the rationalizations above
- "I already manually tested it" or "Keep as reference, adapt existing code"
- "Tests after achieve the same purpose" or "TDD is dogmatic, I'm being pragmatic"
- "Already spent X hours, deleting is wasteful"

**All of these mean: Delete code. Start over with TDD. No exceptions without the user's explicit permission.**

## Verification Checklist

Before marking work complete:

- [ ] RED: Test written and witnessed failing for the correct reason
- [ ] RED: Confidence score ≥ 2 (or fallback invoked)
- [ ] GREEN: Minimal implementation passes the test
- [ ] GREEN: Full suite passes without regressions
- [ ] GREEN: Confidence score ≥ 2 (or fallback invoked)
- [ ] REFACTOR: Code cleaned up while keeping tests green
- [ ] REFACTOR: Confidence score ≥ 2 (or fallback invoked)
- [ ] Coverage meets the minimum requirement for the change type
- [ ] Retry limit not exceeded (or fallback was escalated)

## Final Rule

```
Production code → test exists and failed first
Otherwise → not TDD
```

No exceptions without the user's explicit permission.

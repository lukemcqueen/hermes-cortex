---
name: test-driven-development
description: "TDD: enforce RED-GREEN-REFACTOR, tests before code."
version: 1.2.0
category: software-development
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [testing, tdd, development, quality, red-green-refactor]
    related_skills: [systematic-debugging, subagent-driven-development, change-test-loop]
---

# Test-Driven Development (TDD)

## The Iron Law


NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST


Write code before the test? Delete it. Start over. No "keep as reference", no "adapt while writing tests" — delete means delete. Implement fresh from tests.

Core principle: if you didn't watch the test fail, you don't know if it tests the right thing.

## When to Use

**Always:** new features, bug fixes, refactoring, behavior changes.

**Exceptions (ask the user first):** throwaway prototypes, generated code, config files. Thinking "skip TDD just this once" is rationalization.

## Red-Green-Refactor Cycle

### RED — Write the failing test

One minimal test per behavior. Requirements:
- One behavior per test; clear name ("and" in the name → split it)
- Real code, not mocks (unless truly unavoidable)
- Name describes behavior, not implementation

### Verify RED — watch it fail

```bash
pytest tests/test_feature.py::test_specific_behavior -v
```

Confirm it fails for the RIGHT reason (feature missing, not a typo). If it passes immediately, you're testing existing behavior — fix the test. If it errors, fix the error first.

### GREEN — minimal code

Write the simplest code to pass. Nothing more — no extra features, no "improvements". Cheating is OK here (hardcode, duplicate): REFACTOR cleans it up.

### Verify GREEN — watch it pass

```bash
pytest tests/test_feature.py::test_specific_behavior -v   # the specific test
pytest tests/ -q                                           # full suite — no regressions
```

Test fails → fix the code, not the test. Other tests fail → fix regressions now.

### REFACTOR — clean up (green only)

Remove duplication, improve names, extract helpers. Keep tests green; don't add behavior. If tests fail during refactor, undo and take smaller steps.

### Repeat

Next failing test for next behavior. One cycle at a time.

## Avoid Horizontal Slices

Don't write all tests then all implementation. Use vertical tracer bullets — one end-to-end behavior slice per cycle:


WRONG:  RED: test1,test2,test3  →  GREEN: impl1,impl2,impl3
RIGHT:  RED→GREEN: test1→impl1   →   RED→GREEN: test2→impl2   →   ...


A tracer bullet proves the path works, teaches the interface, and grounds the next test.

## Why Test-First (not test-after)

- Tests written after pass immediately and prove nothing (test the wrong thing, test implementation, miss edge cases).
- Manual testing is ad-hoc — no record, can't re-run, easy to miss cases under pressure.
- "Deleting X hours is wasteful" is sunk-cost fallacy; keeping unverified code is technical debt.
- TDD finds bugs before commit (faster than debugging after), prevents regressions, documents behavior, enables refactoring.

## Red Flags — STOP and Start Over

Code before test | test after implementation | test passes on first run | can't explain why test failed | "just this once" | "keep as reference" | "already manually tested" | "already spent X hours" | "this is different because…"

All of these mean: delete the code, restart test-first.

## Verification Checklist

- [ ] Every new function/method has a test
- [ ] Watched each test fail BEFORE implementing (for the right reason)
- [ ] Wrote minimal code to pass each test
- [ ] All tests pass; output pristine (no errors/warnings)
- [ ] Tests use real code (mocks only if unavoidable)
- [ ] Edge cases and errors covered

Can't check all boxes? You skipped TDD. Start over.

## Regression Testing — Not Just the One Test
After GREEN, run the FULL suite and related tests exercising the same path. One passing test proves the fix; a full suite proves nothing broke.

## When Stuck

| Problem | Solution |
|---------|----------|
| Don't know how to test | Write the wished-for API + assertion first. Ask the user. |
| Test too complicated | Design too complicated — simplify the interface. |
| Must mock everything | Code too coupled — use dependency injection. |
| Test setup huge | Extract helpers; still complex → simplify the design. |

## With delegate_task

When dispatching subagents, enforce TDD in the goal: "write the failing test FIRST, run it to verify it fails, then minimal code to pass, then refactor."

## Final Rule


Production code → test exists and failed first
Otherwise → not TDD


No exceptions without the user's explicit permission.

---
name: testing-strategy
description: |
  Select and apply the smallest effective tests first, then expand to broader
  verification for release readiness across unit, integration, and E2E levels.

  Triggers when user mentions:
  - "testing strategy"
  - "which tests"
  - "test plan"
  - "verify changes"
  - "add tests"
---

# Testing Strategy (Enterprise)

## Purpose
Ensure changes are:
- correct
- safe to ship
- verified efficiently

Optimized for:
- small models
- change-test-loop execution
- enterprise reliability

---

## Core Rule

```txt
narrow test → fix → pass → expand verification
```

Never start with full-suite testing unless required.

---

## Test Pyramid (PRIORITY)

1. **Unit Tests**

   * pure logic
   * fast, isolated
   * no external dependencies

2. **Integration Tests**

   * API boundaries
   * DB interactions
   * service integrations

3. **System / E2E Tests**

   * critical user flows
   * UI + backend interaction

4. **Manual Verification**

   * only when automation is not feasible

---

## Test Selection (STRICT)

For each change:

1. Identify affected area
2. Select the **narrowest test** that can fail
3. Run only that test first
4. Expand scope only after pass

---

## Verification Order

```txt
single test
→ test file
→ related module tests
→ integration tests
→ typecheck / lint
→ build
→ full test suite
→ E2E (if critical path)
```

---

## Test Design Rules

Each feature/change should include:

* success case
* failure case
* edge case

Tests must:

* assert observable behavior
* avoid internal implementation coupling
* be deterministic (no timing hacks)

---

## Refactoring Tests

When refactoring:

* keep existing tests passing
* add tests before changing behavior
* do not delete tests unless obsolete
* update tests only when behavior intentionally changes

---

## Flaky Test Handling

If a test is flaky:

1. identify root cause:

   * timing issue
   * async handling
   * shared state
2. fix deterministically
3. avoid:

   * retries as default
   * arbitrary waits

---

## Performance & Scale (ENTERPRISE)

* keep unit tests fast (<100ms ideal)
* parallelize where safe
* isolate DB usage in tests
* mock external services when appropriate
* run E2E selectively on critical paths

---

## Data & Environment

* use test fixtures or factories
* avoid shared mutable state
* reset DB/state between tests
* use environment isolation (`test` env)

---

## Security Testing

Include when relevant:

* auth/permission checks
* input validation failures
* injection attempts
* sensitive data exposure

---

## Migration Testing

For schema/data changes:

* test forward migration
* test rollback if possible
* verify data integrity
* test on realistic dataset if risk is high

---

## Observability Checks

When applicable, verify:

* logs emitted correctly
* no sensitive data in logs
* metrics/events triggered

---

## Anti-Patterns

Avoid:

* starting with full test suite
* skipping tests for "small changes"
* brittle assertions (exact HTML structure, etc.)
* arbitrary sleeps
* shared state between tests
* silent test failures

---

## Integration with AgentKore

Execution flow:

```txt
change-test-loop
→ testing-strategy (select tests)
→ task-executor (apply + verify)
```

---

## Goal

Provide fast, reliable, and scalable verification so changes can be shipped safely with minimal overhead.

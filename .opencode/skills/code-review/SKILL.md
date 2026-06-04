---
name: code-review
description: |
  Review code changes for correctness, maintainability, tests, security,
  migration risk, and final-response accuracy.

  Triggers when user mentions:
  - "code review"
  - "review this change"
  - "check my code"
  - "pre-merge review"
  - "quality review"
---

# Code Review

## Purpose
Review changes before merge or release to catch:
- correctness bugs
- missing tests
- poor maintainability
- security regressions
- migration/backcompat risks
- inaccurate final reports

---

## Output (STRICT)

```md
## Review Result
pass | needs changes | blocked

## Findings
### F1: <title>
- Severity: critical | high | medium | low
- File:
- Issue:
- Fix:

## Required Changes
- ...

## Verification
- checks reviewed:
- tests recommended:

## Notes
- assumptions, risks, follow-ups
```

---

## Workflow (STRICT)

1. Inspect diff and relevant files
2. Confirm change solves stated task
3. Check correctness and edge cases
4. Check tests and verification
5. Check security and data handling
6. Check migration/backcompat risk
7. Check maintainability
8. Check final response accuracy
9. Report only actionable findings

---

## Severity Rules

### Critical

* data loss
* security breach
* auth bypass
* broken production-critical path
* false claim that tests passed

### High

* incorrect behavior
* missing authorization
* unsafe migration
* major untested feature path
* backwards-incompatible API change

### Medium

* edge case bug
* unclear error handling
* missing important test
* duplicated logic
* maintainability issue

### Low

* naming clarity
* minor cleanup
* small docs mismatch
* non-blocking style issue

---

## Review Checklist

### Correctness

* solves the stated task
* preserves existing behavior
* handles success, failure, and edge cases
* no hidden behavior changes
* errors handled clearly

### Tests

* tests added/updated when needed
* narrow test run first
* relevant suite run if available
* no skipped/disabled tests without reason
* final report matches actual test results

### Maintainability

* change is minimal and focused
* code follows existing patterns
* names are clear
* duplication is reduced or justified
* no unnecessary abstraction
* no dead code or debug logs

### Security

* no auth/permission regression
* input validated
* output safe
* secrets not exposed
* logs do not leak sensitive data

Use `security` for deeper review when risk exists.

### Database / Migration

* migration is reversible or safe
* no long-lock production risk
* backcompat considered
* data changes verified
* rollback path exists

Use `database-migrations` for risky DB changes.

### API / Compatibility

* public contracts preserved or versioned
* response/request shapes intentional
* errors are stable and explicit
* clients will not break unexpectedly

### Performance

* no obvious N+1
* no unbounded queries
* no unnecessary client/server work
* large data paths are paginated or bounded

### Final Response Accuracy

* files changed are accurate
* verification commands are real
* failures are not hidden
* uncertainty/blockers are stated clearly

---

## Review Modes

### Quick Review

Use for small diffs:

* correctness
* tests
* obvious risks

### Deep Review

Use for:

* auth/security
* migrations
* architecture changes
* public APIs
* performance-sensitive paths

---

## Anti-Patterns

Avoid:

* vague feedback
* personal preference comments
* broad rewrites as review fixes
* ignoring tests
* approving unverified claims
* nitpicking while missing real risk

---

## Goal

Provide clear, actionable review that improves correctness, safety, and maintainability without slowing small-model execution.

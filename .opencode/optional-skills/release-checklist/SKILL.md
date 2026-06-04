---
name: release-checklist
description: |
  Verify release readiness: code, tests, build, migrations, config, rollback, risk.
  Triggers: "release", "ready to deploy", "final check", "pre-release", "ship this"
---

# Release Checklist

## Core Rule

Do NOT deploy if: tests failing | verification unknown | migrations unsafe | rollback unclear (unless user accepts risk).

## Checklist (EXECUTE IN ORDER)

### 1. Repo State
`git status --short` + `git diff` — no unintended files, no debug artifacts, no secrets

### 2. Diff Review
Scope matches intended change. No unrelated edits. No debug code. No security regressions.

### 3. Tests
Targeted → related → full suite. All pass. No skipped critical tests. Flaky tests addressed.

### 4. Build / Lint / Typecheck
No build errors, no type errors, no critical lint issues.

### 5. Migrations (CRITICAL)
Safe for production. No long table locks. Rollback exists. Large updates batched. Data integrity preserved.

### 6. Config / Environment
Env vars documented. No secrets committed. Backward compatible. Safe defaults.

### 7. Security Check
Auth not weakened. Permissions enforced. No sensitive data exposed. Logs don't leak secrets.

### 8. Docs / Memory
Update README, API docs, setup instructions as needed. Store durable decisions in memory.

### 9. Rollback Plan (REQUIRED)
How to revert code? Rollback migration? What happens to data?

## Report

```md
## Release Status
ready | not ready | risk accepted

## Summary
What's being released

## Verification
- tests:
- build:
- migrations:

## Risks

## Rollback
- steps:

## Notes
```

---
name: change-test-loop
description: |
  Small changes with real verification, bounded retries, self-healing.
  Triggers: "fix tests", "make tests pass", "refactor", "change-test loop", "debug failing test"
---

# Change-Test Loop

## Core

One change at a time. Never batch. Never skip verification. Never loop indefinitely.

```
inspect → change → test → fix → retry → fallback (once) → verify → report
```

## Workflow

1. Inspect relevant files — identify smallest safe change
2. Make only that change
3. Run narrowest relevant test
4. If fail: read exact error → classify (syntax/compile | logic | test-mismatch | missing dep/config | environment | data/state) → fix root cause → rerun same test
5. Max **2 retries** per task. Retry only when failure is understood and fix is small.
6. If retries fail: **one fallback attempt** (simplify, revert+reimplement, adjust test expectation) — still small, no scope expansion
7. If narrow passes: expand → related tests → full suite → lint/typecheck
8. Report

## Test Order

```
single test → test file → related suite → full suite → lint/typecheck
```

Prefer `./run <command>` over direct tool invocation.

## Confidence Score

**3** (confirmed by exact error/failing test/code inspection) → apply small fix
**2** (plausible) → gather one more piece of evidence first
**1** (weak guess) → do not edit
**0** (no evidence) → stop, report blocker

Never edit below 3 unless diagnostic and reversible.

## Stop When

Test passes and verified | retry limit hit | failure unclear | fix exceeds scope | dependency missing | destructive action needed

## Anti-Patterns

Infinite retries | guessing fixes | batching changes | skipping narrow tests | jumping to full suite | hiding failures | simulating outputs

## Report Format

```md
## Result
## Files changed
## Verification
## Retries: X/2
## Confidence: score + evidence
## Unresolved
## Notes
```

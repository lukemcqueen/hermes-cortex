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

## Tests in a repo with GATES (file-based gates, process-level tests)

A repo gate that looks for a test FILE does not see tests that live INSIDE the source. In Rust,
`#[cfg(test)] mod tests` in `src/` satisfies the spirit and not the gate — and adding the file is the
better answer anyway: an integration test that drives the built artifact AS A PROCESS is the only one
that can assert the contract a caller actually sees (exit codes, what lands on stdout versus stderr,
a protocol mode answering over a pipe).

```rust
// tests/end_to_end.rs — cargo exports the built binary's path to integration tests
let out = std::process::Command::new(env!("CARGO_BIN_EXE_my-tool"))
    .args(["doctor"]).output().unwrap();
assert_eq!(out.status.code(), Some(0));
```

Rules that each save a round trip:

- **A test filter needs the FULL path.** `<mod>::tests::<name> -- --exact` matches; the bare
  `<name> --exact` matches NOTHING and prints `0 passed; N filtered out`, which reads exactly like a
  missing test. Quote a run that actually executed the test you are claiming.
- **One command, one summary PER TEST BINARY.** A crate with unit tests plus an integration target
  prints two `test result:` lines; a second one saying `0 passed; N filtered out` is the other binary
  reporting no match — not a failure, and not a count for the first.
- **When the claim is about a BUILD ARTIFACT, rebuild it inside the script that measures it.** A test
  run produces a DEBUG build; a release binary is a separate artifact that a demonstration will
  happily run stale, silently showing pre-change behaviour. The rebuild belongs at the top of the
  measuring script, before any size / RSS / behaviour reading.
- **A list that mirrors the tests must be regenerated and DIFFED by the runner**, never hand-kept: an
  inventory that has drifted from the suite reads as authoritative. Regenerate it to a temp file and
  fail on any difference, so adding or renaming a test breaks the runner until the list is updated.
- **Probe the runner once against a target that cannot succeed** — a suite name that does not exist,
  run from the SAME directory as the real invocation. A green run proves the tests pass today; only a
  demonstrated failure proves the runner would notice tomorrow. A probe that fails because the
  project is missing proves nothing about the suite.

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

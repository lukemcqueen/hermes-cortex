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
    related_skills: [root-cause-debugging, subagent-driven-development, change-test-loop]
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

## A test's NAME and DOCSTRING are claims, not evidence

A test named `test_…_takes_the_worst_rc` that feeds one nonzero value and one zero exercises NOTHING
about ordering: a first-wins implementation (`rc = rc or r`) and a worst-wins one (`max(rc, r)`)
return the same answer for that input, so the name overclaims and the real defect ships green — and
the overclaiming name is what stops the next reader looking. For every name asserting a COMPARATIVE
property — worst / best / both / all / first / last / every — the fixture MUST hold the
discriminating pair: inputs that differ in the direction the name claims. See the assertion FAIL on
the wrong implementation, not merely pass on the right one, by running the test against the PRE-FIX
code — extract the old file into a scratch tree (`git show <sha>:<path>` into
`<scratch>/<tree>/<path>`, beside a copy of the test file) and run the file THERE. A guard that has
only ever met the fixed revision is a happy path with a name.

The same rule binds prose. A summary, test docstring or commit message asserting behaviour the code
does not have ("worst rc wins") is a CLAIM ABOUT THE CODE, and one `grep` of the aggregation settles
it — a description of the intent is not a description of what is implemented.

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

- **Assert the RETURN CODE, not only the output — a content-only assertion stays green across a
  crash.** A test that ran `verify <name>`, asserted stdout contained the two lines the command
  prints FIRST, and never checked the exit status passed for as long as the command crashed on the
  next step: those lines were real, the traceback came after them, and the suite reported green over
  a subcommand that was unusable. For every subject the test drives as a PROCESS, assert `returncode`
  beside the output — 0 for a pass, and the subject's own distinct code for "could not run" (never
  the generic failure code) — with one case per outcome.
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

## Single-file test runners with injected collaborators

A hand-rolled runner (a `main` that calls each `test_*` in order) shares ONE module object across
sections, which creates three failure modes a pytest suite never shows you:

- **Restore every injected double before the next section.** A section that replaces a module
  attribute and walks away leaves the fake in place for everything after it, so a later section
  asserts against its own double: the symptom is the code under test returning the fake's empty
  result, which reads as a defect in the shipped function. Save the real attribute and put it back
  at the end of the section that swapped it.
- **Widening a collaborator's interface breaks its DOUBLES and its FIXTURES — grep for both in the
  same change.** A new keyword parameter on a faked function makes every hand-rolled double
  (`lambda blobs, conn=None: …`) die with `TypeError: unexpected keyword argument` at the CALL site,
  and a new COLUMN makes every fixture that builds its own DDL die with `no column named …`. Both
  surface as failures in files you never opened, so a green run of the file you edited proves
  nothing about the suite. Sweep the test tree for the old call shape and the table name
  (`grep -rn "lambda .*conn=None" tests/`, `grep -rln "<table>" tests/`), give each double a
  trailing `**kw` rather than restating the parameter list, and make each fixture's schema mirror
  the real one — then run every file that names the collaborator. Do it as a scripted edit that
  ASSERTS its match count per file, so a silent 0 (nothing updated) or a silent 2 (pattern too
  broad) fails loudly instead of leaving a file unfixed behind a green suite.
- **Run the FILE before every commit — a green commit hook is not a green test.** Pre-commit hooks
  check syntax, secrets and static scans; they do not execute your tests. A failing suite can
  therefore be committed behind a passing hook and only surfaces when someone runs the file.
- **Assert on OUTCOME, not on the double's wiring alone.** Driving a wrapper with a fake proves the
  arguments are forwarded; it does not prove the real function honours them. Add one section that
  drives the REAL function with its dependencies stubbed and asserts the behaviour (a cap of one
  judges exactly one unit and reports the rest), so the contract is pinned at the seam that ships.
- **Sections are ordered, so a passing section can be the reason a later one fails.** Run the whole
  file after every edit rather than re-running the section you just touched.
- **A fixture that OMITS a field the code falls back on tests the AMBIENT environment, not the rule.**
  A fixture built a lock state without the identity field, and the liveness check — finding it absent —
  fell back to the repository's real git author and counted the HOST's own recent commits as proof of
  life for a lock the test believed was dead. The branch under test was therefore unreachable and the
  assertion could never pass, whatever the rule said. When a fixture stubbornly fails to exercise the
  behaviour it names, look for a field you LEFT OUT, not only at the fields you set: unset means "let
  the code decide", and the code decides from wherever it can reach. Name a value that cannot exist in
  the ambient world (an author no repository has) so the fallback has nothing to find.
- **A new test that fails for the WRONG reason is not evidence — read the failure before the code.**
  A refusal test first failed on a missing TABLE, because the collaborator it stubbed out was also what
  initialised the schema: the assertion was measuring its own setup, not the refusal. Confirm the
  failing line is the assertion you wrote, and fix the prerequisite before concluding anything about
  the  code — a probe that cannot reach its subject reports the wrong verdict in both directions.
- **A test that cannot EXECUTE its subject must report a DISTINCT outcome — never `print` a skip and
  `return`.** A hand-rolled runner scores "no exception" as PASS, so a self-skipping test is recorded
  as a pass while having verified nothing: a file that ran nothing proves nothing either way. Raise a
  dedicated exception (`class NotRun(Exception)`), catch it BEFORE the general handler, and print it on
  its own line beside the result (`ALL PASS (6 tests) (1 NOT RUN)`). Prove the branch by FORCING the
  condition once (`PYTEST=/nonexistent python3 tests/x.py`) — an unexercised skip path is how the
  vacuous pass survives review.
- **A check whose prerequisite is ABSENT passes vacuously.** Comparing a live store's mtime before and
  after a sandboxed write passes when the store does not exist, because `None == None`. Compare a COUNT
  (or assert existence) AND assert the opposite direction — the write must have LANDED somewhere — or
  "nothing changed" is satisfied by code that did nothing at all.
- **Save and restore every environment variable a test mutates.** `os.environ.pop(k, None)` without
  saving silently discards an operator's own setting for every later section of the same process; use
  `saved = {k: os.environ.pop(k, None) for k in (...)}` and put them back in a `finally`.
- **A test file executed by a hand-rolled runner must take NO pytest fixtures.** The runner calls
  `fn()` with no arguments, so a `tmp_path`/`monkeypatch` parameter arrives as an undefined name and
  the test dies with `NameError` — which then reads as a defect in the code under test. Build the
  temp path inside the test with `tempfile` (and clean it up) so the file runs correctly under BOTH
  the standalone runner and pytest. Check this on any test whose failure reason you have not read:
  a probe that never reached its subject reports a verdict in both directions.
- **A test file must be INERT ON IMPORT — a module-level `raise SystemExit` (or any module-level
  work) aborts collection for the WHOLE suite.** pytest executes a module in order to collect it, so
  a file that runs its checks at module level and ends in `raise SystemExit(1 if fails else 0)` fires
  that exit during collection: pytest reports `INTERNALERROR`, `no tests ran`, rc=3, and the ENTIRE
  suite executes ZERO tests — on every range, for every agent, with nothing in the run naming that
  file as the cause. The only way to get a regression signal is then to exclude the file, which is
  how the break survives for weeks while every "suite is green" claim rests on nothing. Put the
  checks in `def test_…()`, the script behaviour behind `if __name__ == "__main__":`, and read the
  subject INSIDE the test rather than at module level — `SUBJECT.read_text()` at import turns a
  missing file into a collection error too. Prove it with the collection command itself
  (`pytest tests/ --collect-only -q`, which must print a collected COUNT and no INTERNALERROR): a
  green run of the file ALONE cannot show this, because the damage is to the collection of the other
  files. Keep the script behaviour working in the same edit, and drive the extracted check both ways
  (a healthy input passes, a regressed one is reported) so it cannot pass vacuously.
- **Proving "these failures predate my change" must classify the OUTCOME, never compare bare exit
  codes.** A file that cannot execute at all (no interpreter, a timeout, a crash before the first
  assertion) returns the SAME code on both revisions, so a code-only comparison reports agreement —
  a regression claim manufactured from two runs that measured nothing. Read each run's output and
  name three outcomes: PASS, FAIL only when the output NAMES a failure, and NOT RUN otherwise. Two
  unmeasured runs are COULD NOT VERIFY (its own non-zero exit), not agreement; a listed file that now
  PASSES is LIST DRIFT (its own non-zero exit), so the artifact's scope cannot drift from its claim.
  Make the classifier drivable on its own (`--classify-only <rc> <output-file>`) so a test can pin it.
- **A limit-based probe must actually TRIP the limit.** Timing out at `timeout 1` measured nothing
  when the subject finished in under a second — the probe silently exercised the passing happy path
  instead of the branch it names. Pick a value the subject demonstrably cannot meet, and confirm the
  branch by forcing it once. The mirror-image defect is a budget SMALLER than the probe's own cheap
  setup work: the pass spends the budget on lookups before reaching the branch, defers everything,
  and the test then asserts failures that cannot occur. Size the limit past the setup and well short
  of the subject.
- **Assert the DESIGN's guarantee, not a count you imagined.** Where a consecutive-failure cap or a
  short-circuit exists, the subject legitimately stops early — so "all N inputs are marked failed"
  is the wrong assertion and fails on correct code. Assert the property that must hold in every
  ordering (something was recorded failed, NOTHING was credited) and let the cap own how many were
  reached.

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

---
name: change-test-loop
description: |
  Small changes with real verification, bounded retries, self-healing.
  One change at a time. Never batch. Never skip verification.

  Triggers: 'fix tests', 'make tests pass', 'refactor', 'change-test loop', 'debug failing test'
version: 1.1.0
author: Titus (ported from AgentKore)
---

# Change-Test Loop

## Core

One change at a time. Never batch. Never skip verification. Never loop indefinitely.
**Never ask "do you want tests?" — testing is mandatory, not optional.**

### Golden Rule: Test Before You Tell

**Never declare a feature "done" to the user without having written AND passed tests for every new artifact you created.** This is the most commonly violated rule and the one users notice fastest.

For a backend endpoint: write endpoint tests first, run them, confirm pass, THEN say it's ready.
For a frontend page: add the API function mock + i18n mock to the test file, run the test, THEN commit.
For multi-layer features: test each layer before moving to the next.

**Concrete scenario that triggers this rule every time:**
```
- Write a new PUT/DELETE endpoint + frontend edit/delete buttons
- Run only the pre-existing test suite (which passes)
- Tell the user "done"
- User asks "did you test?" because there are zero tests for the new code
- This wastes trust. Do not let it happen.
```

**The litmus test:** After finishing your last code change, ask yourself: "If the user asks 'did you test this specific new code?', do I have a test-run output to show them?" If the answer is no, stop and write the tests before reporting.

### NEVER Ask "Do You Want Tests?"

**Testing is not optional.** You must never pause to ask the user "do you want tests?" or "should I run E2E?" or "shall I write unit tests for this?" — the answer is always yes, and asking wastes their time.

Instead, use the Test Decision Matrix below to automatically determine what kind of test to write and run. If you aren't sure which test type applies, pick the most thorough option — never punt to the user.

**Exception:** Only ask if the project literally has zero tests and no test infrastructure (no pytest.ini, no jest.config, no Playwright config, no ./run test target). Even then, ask once, then apply the answer to all future changes in that session.

### Test Decision Matrix

When you finish writing code, determine the change type and execute the corresponding test automatically — no questions asked.

| Change type | Required test | Example command |
|---|---|---|
| New backend endpoint / route | API endpoint test (pytest + TestClient) | `pytest tests/test_route.py -v -k "test_new_endpoint"` |
| New frontend page / component | Component test (Vitest + RTL) | `pnpm --filter <package> test -- -t "new page"` |
| New DB model / migration | Model test + migration dry-run | `pytest tests/test_models.py -v` + `alembic downgrade && alembic upgrade` |
| Bug fix (backend) | Regression test reproducing the bug | `pytest tests/test_route.py -v -k "test_regression"` |
| Bug fix (frontend) | Component test for fixed behavior | `pnpm test -- -t "fixed behavior"` |
| Refactor (backend) | Run full test suite, compare to baseline | `pytest tests/ -q` |
| Refactor (frontend) | Run full test suite, compare to baseline | `pnpm test` |
| Auth / data-fetching change | E2E test + browser session check | `pnpm e2e -- -g "auth"` + navigate/logged-in/logged-out |
| Docker / compose change | Build + container health + E2E | `./run build && ./run e2e` |
| Config / env change | E2E test that exercises the config | `pnpm e2e -- -g "config"` |
| Cross-layer feature (backend + frontend) | API test + component test + E2E | All three, in that order |
| API function update (frontend) | Update mock + component test | `pnpm test -- -t "updated function"` |
| UI-only change (no data flow) | Component test + visual check | `pnpm test -- -t "component"` |
| Script / CLI tool change | Run the script with test inputs | `bash script.sh --test` |

**When in doubt, do both:** unit test + E2E. Over-testing costs a few seconds. Under-testing wastes trust.

### E2E Decision Rule

Run E2E tests automatically when:
- Any auth-related code changed (login, logout, session, middleware, token handling)
- Any data-fetching code changed (API hooks, SWR/React Query calls, server actions)
- Any middleware or route guard changed
- Docker/compose file changed
- Any cross-layer feature was added (backend endpoint + frontend page)
- The change touches the flow a user would go through end-to-end

Do NOT run E2E for:
- Pure refactoring that doesn't change behavior
- Script/CLI changes
- Config-only changes (unless config affects auth/data flow)
- UI-only changes with no data interaction

### Frontend API Mock Rule

When you update or add a frontend API function (tRPC, fetch, React Query hook), you MUST:
1. Update or create the corresponding mock in the test file
2. Add any new i18n translation keys to the i18n mock
3. Run the component test to verify it renders with the new data
4. If the new API function changes data flow (not just display), write an E2E test too

Do not run only the pre-existing test suite. If the test file doesn't exist yet, create it.

```

baseline → inspect → change → test → fix → retry → fallback (once) → verify → report
```

## New Feature Delivery

When adding **new** functionality (endpoints, frontend pages, services) — not fixing existing code — the workflow extends:

```
branch → build → write tests → run tests → full suite → push → report
```

### Step 0: Create a feature branch

Before writing any code, create a `titus/<slug>` branch:

```bash
git checkout -b titus/<slug-describing-change>
git push -u origin titus/<slug-describing-change>
```

Push early and push often. The repo's auto-PR workflow creates a draft PR from `titus/*` branches — Moses reviews and merges when ready.

**Never push to `main`.** Not even for quick fixes. Every change gets its own branch.

### Critical Rule: Test Before You Tell

Never declare a feature "done" to the user without having written **and passed** tests for it. This means:

1. **Write the feature code** — backend routers, frontend components, i18n keys, etc.
2. **Write tests** for the new code — backend endpoint tests (pytest), frontend component tests (Vitest + RTL), update test mocks for new imports/translation keys
3. **Run the new tests** — verify every one passes
4. **Run the full suite** — confirm no regressions
5. **Only then tell the user** it's ready

**What NOT to do:** Write the feature, run only the pre-existing tests, declare done. The user will spot this and call it out.

If the feature involves multiple layers (backend endpoint + frontend page + i18n), write and run tests for each layer before moving to the next.

## Workflow

### 0. Establish Baseline

Before making any changes, run the full test suite to capture the current state:

```bash
./run test:api      # or the project's test command
```

Record the pass/fail count. **Pre-existing failures are your responsibility** once you modify the repo — fix them or remove obsolete tests before committing. Do not push broken tests to main.

### 1. Inspect relevant files — identify smallest safe change
### 2. Make only that change
### 3. Run narrowest relevant test
### 4. If fail: read exact error → classify (syntax/compile | logic | test-mismatch | missing dep/config | environment | data/state) → fix root cause → rerun same test
### 5. Max **2 retries** per task. Retry only when failure is understood and fix is small.
### 6. If retries fail: **one fallback attempt** (simplify, revert+reimplement, adjust test expectation) — still small, no scope expansion
### 7. If narrow passes: expand → related tests → full suite → lint/typecheck
### 8. Compare result to baseline — if any new failures appeared, diagnose and fix before declaring done
### 9. Report

## Test Order

```
full baseline → single test → test file → related suite → full suite → lint/typecheck
```

Prefer `./run <command>` over direct tool invocation. When running tests that require environment variables (DB ports, API keys), use the project's `./run` wrapper — direct `.venv/bin/python` calls often miss required env setup.

## Pre-existing Failures Policy

When the full suite reveals pre-existing failures:

- **Fix them.** Remove obsolete tests that test removed functionality. Fix assertions that broke due to refactoring. Do not leave them broken.
- **When to delete a test:** A test that tests a feature that was intentionally removed (model deleted, endpoint removed, feature moved to another service) should be deleted, not fixed. Its purpose no longer exists.
- **When to fix a test:** A test that tests an existing feature but has incorrect assertions or unhandled edge cases should be fixed.
- **Verify the full suite passes** after all fixes before moving on.

## Confidence Score

**3** (confirmed by exact error/failing test/code inspection) → apply small fix
**2** (plausible) → gather one more piece of evidence first
**1** (weak guess) → do not edit
**0** (no evidence) → stop, report blocker

Never edit below 3 unless diagnostic and reversible.

## Stop When

Test passes and verified | retry limit hit | failure unclear | fix exceeds scope | dependency missing | destructive action needed

## Interactive Flow Verification

E2E tests (Playwright) can pass while interactive flows are broken. Common reasons:
- CORS misconfiguration in production Docker vs test setup
- `API_BASE` URL points to wrong port in deployed container
- Auth token storage key changed but old key still in localStorage
- Middleware intercepts API routes (check matcher excludes `/api`)
- `NEXT_PUBLIC_*` env vars baked at build time differ between dev and prod

**Rule:** After deploying any auth or data-fetching change, do a **browser session check**:
1. Navigate to the page as a logged-out user
2. Navigate to the page as a logged-in user
3. Submit at least one form end-to-end
4. Check browser console for CORS/network errors

Do not rely solely on `curl` or E2E tests for interactive flows — they don't run in the browser's cross-origin context.

## Anti-Patterns

Infinite retries | guessing fixes | batching changes | skipping narrow tests | jumping to full suite | hiding failures | simulating outputs | E2E-only verification for auth flows

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

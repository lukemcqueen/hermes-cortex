# steadfaste Testing & Self-Governance Standard

> **Not a guideline — the contract.** steadfast is **self-developing code**: the
> harness (and the agents driving it) write, test, and ship the code, so the
> quality gates are properties of the system itself, not of a human's discipline.
> The goal: **virtually never a bug in the application** — i.e. any shipped bug
> is a *test we failed to write*, never a test we couldn't be bothered to run.
>
> North-star for quality (Luke, 2026-09-11): "I want testing to be so thorough
> that we virtually never have bugs in the application (i.e. our fault that we
> didn't test thoroughly enough)."
>
> Companion: **enterprise-grade from day 1** — self-developing code must carry
> its own guardrails, dogfooded (the harness enforces the same standard it
> ships).

## The governing rule

**A change is not done until its correctness is *proven*, not asserted.** Every
behavior change ships with:
1. a **RED test** that fails for the right reason (TDD Iron Law),
2. a **GREEN test** after the change,
3. a **regression-capable** proof it survives refactor,
4. an **adversarial pass** (the verifier tried to break it and couldn't),
5. an **integration pass** (the real deployed path ran, not mocks).

No `--no-verify`, no "I tested it manually," no silent skip. When a bug ships,
the post-mortem answer must be **which test was missing** — because the answer
to "was testing thorough enough" must always be *"we can prove it was."*

## Test layers (the pyramid — every layer mandatory)

```
        ┌───────────────┐
        │   1  Unit     │  pure functions: Covenant parse, budget math, cost,
        │               │  config validation, lock/store logic, taint rules
        ├───────────────┤
        │   2  Contract │  Covenant conformance (ANY worker passes the same door),
        │               │  permission matrix, journal format, audit integrity
        ├───────────────┤
        │   3  Integr.  │  Postgres-backed store (real PG, not SQLite-mocks),
        │               │  worker spawn/stdio round-trip, gateway→core dispatch
        ├───────────────┤
        │   4  E2E      │  a real task → real tools → verified result, via the
        │               │  deployed artifact (the "add a route + prove it" trace)
        └───────────────┘
```

| Layer | Runs on | Failure = | Never substitute |
|-------|---------|-----------|-------------------|
| Unit | every `./run test` + CI | a logic bug | an integration test for a pure function |
| Contract | every CI | an Covenant/permission break | unit test (doesn't catch the "any worker" case) |
| Integration | CI with a real Postgres service | a seam/persistence bug | a mocked DB (mocks hide the real path) |
| E2E | CI + before every release | a shipped-not-working artifact | a unit test suite (doesn't prove the binary works) |

## The self-developing guardrails (dogfood — these ARE the harness's tests)

Because the code writes itself, the standard adds **meta-gates** that verify the
developing agent did not take shortcuts:

| # | Guardrail | What it catches | Mechanized |
|---|-----------|-----------------|------------|
| 1 | **RED-before-GREEN proof** | "I wrote tests after" | CI asserts the test file changed in the same commit as the code, and that reverting the code fails the test (mutation) |
| 2 | **Mutation-testing gate** | tests that pass but assert nothing real | a mutation (stomp a return / flip a branch) must fail ≥1 test; targets the store, gateway, audit |
| 3 | **Adversarial-verifier gate** | subtle/edge/silent-failure bugs | `adversarial-verify` at A4 on core paths before push (part of `./run check` + pre-commit) |
| 4 | **No-swallow / no-bypass** | `except: pass`, `2>/dev/null || true`, `--no-verify`, `SKIP_SCORE` | grep-gate + the harness refuses a bypass flag (fail-closed) |
| 5 | **Integration on real PG** | mocks hiding the DB path | postgres service in CI; `docker`-free local `pg_tmp` harness |
| 6 | **E2E on the deployed artifact** | "unit-green but the binary doesn't work" | build → install → run the real binary in CI (dogfoods the installer too) |
| 7 | **Coverage ratchet (core/ only)** | coverage creeping down over time | enforced baseline; new core code cannot reduce it |
| 8 | **Foreign-worker neutrality** | core grew own-agent-shaped code | a trivial second worker must pass the same conformance suite; CI grep asserts `core/` imports nothing from workers |

## The install/update/uninstall lifecycle (loose-end-free)

> Same standard applies to shipping: a release that cannot be cleanly installed,
> updated, and uninstalled **is a bug**.

| Phase | Must be proven by a test/CI job | Never |
|-------|----------------------------------|-------|
| **Install** | from a clean machine: binary + config land in known paths; `--version` matches; `--doctor` self-checks | a partial/corrupt install reported as success |
| **Update** | from a prior version: old state migrates (DB schema), config upgrades, no orphaned files, new `--version` | a stale config or DB left that breaks the new version |
| **Uninstall** | removes every file it created (bin, config, state, DB data by choice), leaves the machine as-found | leftover PID files, locks, credentials, or half-removed services |
| **Homebrew** | a `Formula` with proper `livecheck` (auto-version bumps), `test` block, and `uninstall`; `brew upgrade` honors the update contract | a formula that installs but can't cleanly upgrade/uninstall |

**Every release** runs the lifecycle matrix (install→update→uninstall) against a
prior real version in CI. This is what "always updated" and "no loose ends"
mean mechanically — the lifecycle is part of the test suite, not an afterthought.

## The pipeline

```
commit → pre-commit (gate 4, unit) → CI: unit → contract → mutation (gate 2)
       → integration (real PG) → E2E (deployed artifact) → lifecycle matrix
       → release: build → sign → publish (Homebrew formula bump)
```

`./run test` = unit + contract locally. `./run test:all` (CI) = everything
including mutation, integration, E2E. `./run check` = adversarial + no-swallow +
cover-ratchet. `./run doctor` = the installed binary self-checks.

## What "bugs virtually never happen" means operationally

Every shipped defect routes back to a **failed test that should have existed**:
- root-cause: WHICH layer's test was missing or weak?
- fix: add that test FIRST (RED), then the fix (GREEN).
- prevent recurrence: the guardrail that let it through is tightened.

Over time the harness's own test suite becomes the institutional memory of every
bug class it has ever been bitten by — which is exactly how a self-developing
system "learns" to be enterprise-grade.

## Standing stack (the framework tests THIS)

- **Rust** — frozen core (store, audit, bus, config, supervisor, gateway).
- **TypeScript** — modifiable layer (agent worker via out-of-process stdio, the
  non-coder React web UI, swappable messaging/models/skills/context).
- **Postgres** — default DB (swappable, typed port).
- Ubuntu LTS enterprise base, cross-platform (unix/macos/windows).
- Covenant v1 (JSON-over-stdio) is the frozen seam; the conformance suite is
  the contract test every worker must pass.
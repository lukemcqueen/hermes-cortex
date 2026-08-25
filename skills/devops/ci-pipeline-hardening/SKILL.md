---
name: ci-pipeline-hardening
description: "Fix CI gates: bounded subsets, parity, coverage baselines."
version: 1.0.0
author: Titus
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [ci, gitlab, github-actions, gates, coverage, typecheck]
    related_skills: [ci-cd-pipeline, test-driven-development]
---

# CI Pipeline Hardening

Class-level playbook for auditing and fixing an existing CI pipeline before a
release — the gap-analysis pass you run when a review or story says "CI is
missing/broken" but a pipeline file already exists. Focus: gate correctness,
bounded subsets, coverage honesty, and the small command pitfalls that break
jobs silently.

## When to Use

- A review/story claims "no CI in repo" or "CI gate missing" — verify first
- test-api runs the FULL suite and takes 20-30+ min or OOMs on small DBs
- A lint/typecheck job wraps an npm script with `npx`
- Coverage NFR rows in an ADR have percentages but zero measurements
- A parity/consistency script exists but nothing in CI calls it

## Verify the Claim First

Before believing a review that says CI is absent, check history — reviews are
written against a commit and go stale fast:

```bash
git log --oneline --all -- .gitlab-ci.yml .github/workflows/ci.yml .circleci
```

One review dated 2026-08-20 claimed "no CI in repo" while `.gitlab-ci.yml` had
been committed 12 days earlier. Trust git, not the review's assertion.

## Audit Checklist (run against the pipeline file)

- [ ] **Typecheck command**: does any step use `npx <flags> <cmd>` with flags AFTER the command? `npx tsc --noEmit --prefix apps/web` passes `--prefix` to tsc → job fails. Fix: `npm run typecheck --prefix apps/web` (npm accepts `--prefix` after the subcommand) or `npx --prefix apps/web tsc --noEmit`. npx and npm flag placement are NOT symmetric.
- [ ] **Full suite as push gate**: if pytest runs everything, bound it. Full suite 30+ min with OOM risk on a small dev DB is not a push gate. Pick a core subset that proves release-critical paths (health, lookups, iswc, multitenant, golden fixtures, webhooks, shares) — ~109 tests ≈ 23s — and keep the full suite runnable via the local runner.
- [ ] **Consistency/parity scripts wired in**: `grep` the pipeline for any repo consistency gate (e.g. `scripts/check_job_parity.py`). A gate that isn't in CI is not a gate. Call it BEFORE the tests it guards.
- [ ] **Coverage measured, not asserted**: `pytest --cov=app --cov-report=xml` and `vitest run --coverage` must exist in the pipeline, and the numbers must be recorded in the test-strategy ADR — with ratcheting targets (e.g. web 56% → 80% over two waves), not a bare ">90%" claim.
- [ ] **YAML validity**: validate before merging (`python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml'))"` from a venv with PyYAML).
- [ ] **Run every command locally with identical args**: you can't always trigger the runner — prove each CI step locally with the same flags, and say so honestly in the report.

## Coverage Baseline Workflow

1. Run the bounded API subset with coverage: `pytest <core-files> --cov=app --cov-report=term-missing` — record total % and test count.
2. Run web coverage: `vitest run --coverage` — record statements/lines %.
3. Update the test-strategy ADR: status → Implemented/measured, NFR rows re-baselined with real numbers and rationale, ratcheting targets named.
4. Wire both into CI (`--cov-report=xml` artifact for API; `-- --coverage` for web).

## Verification

- `tsc --noEmit` → 0 errors (also catches fixture drift — see below)
- Bounded subset green (e.g. 109/109 in ~23s)
- Parity/consistency gate PASS (e.g. 51/51)
- Pipeline YAML parses
- ADR shows measured numbers, not assertions

## Pitfalls

- **Schema field additions break typed test fixtures** (typecheck gate is the trap-catcher, not vitest — loose runtime mocks pass vitest but fail `tsc`). When an API type gains required fields (e.g. m26 name separation added `firstname/firstname_ko/lastname/lastname_ko` to MemberRead/PublisherRead/CreatorListRead and `first_name/last_name` to UserResponse), 22 errors across 8 web fixture files appeared. Fix fixtures in the SAME change as the type change — never defer to a "separate cleanup PR" — then re-run `tsc --noEmit` to 0 errors. Publishers keep nulls (never auto-split); realistic parts for members/creators.
- **`test-web` needs `-- --coverage` passthrough**: `npm run test --prefix apps/web` runs `vitest run` without coverage; add `-- --coverage` to exercise the cov report in CI.
- **Transient DB recovery**: `asyncpg.exceptions.CannotConnectNowError: the database system is in recovery mode` is a known postgres blip — retry the run after ~15s before investigating.

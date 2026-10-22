# TDD Iron Law — Structural Gate Design (2026-08-20)

Titus's proposal to Esther (enforcement owner), after repeatedly producing
code before tests despite the TDD skill, change-checklist, and agent-contract
existing. His core claim: *rules are conditions agents recite and then
bypass, not gates that bite* — so "write another rule" is not a systemic fix.

## Diagnosis (verified with data before building)

| Claim | Evidence |
|---|---|
| TDD never in working memory | `test-driven-development` absent from the 9 `always` skills in skills.yaml |
| No checkable gate | pre-commit had ZERO test-first checks; enforcer only mapped test paths after the fact |
| No structural enforcement | `loop_cycles.test_output_hash` populated in **0 of 5,801** cycles — column existed, nothing ever wired it |

## The three-layer gate (commit 90950049)

1. **skills.yaml `always`** — added `test-driven-development` so the Iron Law
   ("NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST") is injected every turn.
2. **Enforcer write-time co-gate** — `_tdd_required(tool_name, args)` in
   `plugins/governance-enforcer/__init__.py`: `write_file`/`patch` of a
   production-code file (non-test path, code extension) with the TDD skill
   NOT loaded → educate (1st) / block (2nd+), identical escalation to
   `_check_domain_skill_gate`. Cron/bg sessions exempt (cannot load skills).
   Code exts: `.py .sh .bash .ts .tsx .js .jsx .mjs .cjs .go .rs .rb .java
   .kt .swift .c .cpp .h .php`. Exempt markers: `/tests/ /test/ /spec/
   __test__`, `test_*`, `*_test`, `.test.`, `.spec.`, `spec.*`.
3. **Pre-commit commit-time gate** — in `ops/scripts/pre-commit-score`:
   NEW files (`git diff --cached --name-only --diff-filter=A`) that are code
   (non-test, code ext) require a staged test file in the SAME commit WHEN
   the repo has test infrastructure (tests/ dir at root, or test files at
   HEAD). Fail-closed `exit 1`, no bypass flag.

## Scoping decisions (why modified files are exempt)

- **Modified-only diffs never gate.** Fleet cron/ops scripts are
  dogfood-verified (doctor `Script run evidence`), not unit-tested. Gating
  modifications would block legitimate migrations (e.g. a 39-file timezone
  fix with zero tests). `--diff-filter=A` (added only) is the unambiguous
  violation: brand-new functionality in a test-capable repo.
- **No test infra → exempt.** Matches the TDD skill's own exception
  ("projects with zero test infrastructure — ask once").
- **Test files exempt** — writing them IS the RED step.

## Verification matrix (all must pass before shipping)

| Scenario | Expected |
|---|---|
| new code file, tests/ exists, no test staged | BLOCK (exit 1) |
| new code file + test file in same commit | pass |
| new code file, no tests/ anywhere | pass |
| modified-only code file | pass |
| hermes-cortex repo modification (fleet pattern) | pass |

Plus unit-test `_tdd_required` over the ext/path matrix (14 cases: py gates,
yaml/md/env/css don't, test files exempt, skill_manage exempt).

## agent-contract skill changes (same commit)

- Rule 5 → Iron Law: gate at CODE-WRITE step, not commit; "delete the
  untested code, restart test-first".
- Rule 17 → RED-GREEN check before every commit.
- Flow: `understand → inspect → plan → TEST (RED) → change (GREEN) →
  verify → report`.
- Anti-patterns += `test-after-code`, `commit-without-red-green`.

## Key insight for future enforcement design

The pattern generalizes: **when an agent says "the rules exist and I still
violate them", the fix is not a stronger rule — it is (a) injecting the rule
where it is always in context, and (b) a gate at the exact tool call that
violates it (write-time), plus (c) a gate at the commit/close boundary that
refuses to ship the violation.** Three layers because each alone is
bypassable: skill-load is checkable but soft, write-time bites early, and
commit-time catches the case where the skill was loaded and ignored.

---
name: code-review
description: "Two-axis pre-commit review: Standards (documents + code smells) and Spec (requirement compliance) via parallel sub-agents. Plus security scan, quality gates, auto-fix."
version: 3.0.0
author: Hermes Agent (adapted from obra/superpowers + MorAlekss + Matt Pocock)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, security, verification, quality, pre-commit, auto-fix, standards, spec]
    related_skills: [subagent-driven-development, change-test-loop, root-cause-debugging, codebase-design, data-structure-efficiency-review]
---

# Two-Axis Code Verification

Automated verification pipeline before code lands. Two-axis review (Standards + Spec) via parallel sub-agents, plus static scans, baseline-aware quality gates, and an auto-fix loop.

**Core principle:** Code that passes every standard but implements the wrong thing is not good code. Code that implements the right thing but breaks every convention is not good code. Both axes must pass independently.

## When to Use

- After implementing a feature or bug fix, before `git commit` or `git push`
- When user says "commit", "push", "ship", "done", "verify", or "review before merge"
- After completing a task with 2+ file edits in a git repo
- After each task in subagent-driven-development (the two-stage review)

**Skip for:** documentation-only changes, pure config tweaks, or when user says "skip verification".

**This skill vs github-code-review:** This skill verifies YOUR changes before committing. `github-code-review` reviews OTHER people's PRs on GitHub with inline comments.

## Why Two Axes

A change can pass one axis and fail the other:

- **Standards pass, Spec fail** — code follows every documented convention but implements the wrong thing
- **Spec pass, Standards fail** — code does exactly what the issue asked but breaks project conventions
- **Both pass** — ready to commit
- **Both fail** — needs rework on both fronts

Reporting them separately stops one axis from masking the other. The auto-fix loop addresses both independently.

**This skill vs codebase-design:** This skill reviews changes *after* they're made. The `codebase-design` skill guides module design *before* writing code. Use both: design deep, then verify correct.

## Step 1 — Pin the Fixed Point

Identify what the change is relative to. The user may mention a commit SHA, branch name, tag, `main`, `HEAD~5`, etc. If they didn't specify, ask for it.

```bash
# Capture the diff revision once
git rev-parse <fixed-point>
git diff <fixed-point>...HEAD --stat  # confirm non-empty
```

If the user didn't provide a fixed point and the change is uncommitted, use:
```bash
git diff --cached --stat  # staged changes
# or
git diff --stat           # unstaged changes
```

## Step 2 — Identify the Spec Source

Where's the requirement this code was supposed to satisfy? Search in this order:

1. **Issue references in commit messages** (`#123`, `Closes #45`, `Fixes #67`) — read the referenced issue
2. **A path the user passed as an argument**
3. **PRD/spec files** under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature
4. **PRD frontmatter `unspecified_seams:` or requirement IDs** — if the commit references a PRD, read the relevant requirement sections
5. If nothing is found, ask the user where the spec is. If there isn't one, the Spec axis will skip and report "no spec available".

## Step 3 — Get the Diff + Static Security Scan

```bash
# Full diff
git diff <fixed-point>...HEAD > /tmp/code-review-diff.txt

# Or for uncommitted changes
git diff --cached > /tmp/code-review-diff.txt
```

If the diff exceeds 15,000 characters, split by file.

**Static security scan** — scan added lines only. Any match feeds into both axes as context:

```bash
# Hardcoded secrets
grep "^+" /tmp/code-review-diff.txt | grep -iE "(api_key|secret|password|token|passwd)\s*=\s*['\"][^'\"]{6,}['\"]"

# Shell injection
grep "^+" /tmp/code-review-diff.txt | grep -E "os\.system\(|subprocess.*shell=True"

# Dangerous eval/exec
grep "^+" /tmp/code-review-diff.txt | grep -E "\beval\(|\bexec\("

# Unsafe deserialization
grep "^+" /tmp/code-review-diff.txt | grep -E "pickle\.loads?\("

# SQL injection (string formatting in queries)
grep "^+" /tmp/code-review-diff.txt | grep -E "execute\(f\"|\.format\(.*SELECT|\.format\(.*INSERT"
```

## Step 4 — Identify the Standards Sources

Anything in the repo that documents how code should be written:
- `CODING_STANDARDS.md`, `CONTRIBUTING.md`, `STYLE_GUIDE.md`
- `AGENTS.md` — agent conventions and coding standards
- Linter config files (`.eslintrc`, `.ruff.toml`, `pyproject.toml` tool config)

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below — a fixed set of Fowler code smells (*Refactoring*, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation — and, like any standard here, skip anything tooling already enforces.

### Fowler Smell Baseline

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy** — a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches** — the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change** — one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest** — a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

## Step 5 — Spawn Two Parallel Sub-agents

Dispatch **two independent sub-agents** — one for Standards, one for Spec. They run in parallel, each in an isolated context, so they don't pollute each other's reasoning.

Both sub-agents receive:
- The diff (from Step 3)
- The static security scan findings (from Step 3)

### Standards Sub-agent

Goal: Evaluate whether the code change conforms to documented repo standards **and** passes the Fowler smell baseline.

```python
delegate_task(
    goal="""You are a Standards reviewer. Evaluate the code change against:

1. DOCUMENTED STANDARDS (if any were found):
   [paste standards source files here]

2. CODE SMELL BASELINE (always applies, overridden by documented standards):
   - Mysterious Name: name doesn't reveal purpose → rename
   - Duplicated Code: same logic in multiple places → extract
   - Feature Envy: reaches into other object's data more than own → move method
   - Data Clumps: same fields/params travelling together → bundle into type
   - Primitive Obsession: primitive for domain concept → create type
   - Repeated Switches: same switch/if-cascade on same type → polymorphism
   - Shotgun Surgery: one change forces scattered edits → gather into one module
   - Divergent Change: file edited for multiple reasons → split
   - Speculative Generality: abstraction for needs not in spec → delete
   - Message Chains: a.b().c().d() → hide behind one method
   - Middle Man: mostly delegates → cut, call direct
   - Refused Bequest: subclass overrides most of inherited → composition

RULES:
- Documented standard always overrides the baseline
- Baseline smells are always judgement calls, not hard violations
- Skip anything tooling already enforces (linters, type checkers)
- Hard violations = documented standards breached; judgement calls = baseline smells

Return ONLY valid JSON:
{
  "passed": true/false,
  "violations": [{"standard": "name", "details": "...", "hard": true/false}],
  "smells": [{"smell": "name", "hunk": "quoted diff line", "note": "why"}],
  "summary": "one sentence"
}

FAIL-CLOSED: If you can't parse the diff, passed=false.""",
    context=f"""
    <security_findings>
    [security scan results from Step 3]
    </security_findings>

    <diff>
    [paste diff from Step 3]
    </diff>
    """,
    toolsets=["terminal"]
)
```

### Spec Sub-agent

Goal: Evaluate whether the code change faithfully implements the originating spec / issue / PRD.

If no spec was found (Step 2 returned nothing), skip this sub-agent entirely and note "no spec available".

```python
delegate_task(
    goal="""You are a Spec reviewer. Evaluate the code change against the originating requirement document.

Report:
(a) Requirements the spec asked for that are MISSING or PARTIAL
(b) Behaviour in the diff that wasn't asked for (SCOPE CREEP)
(c) Requirements that look implemented but where the implementation looks WRONG

Quote the spec line for each finding.

Return ONLY valid JSON:
{
  "passed": true/false,
  "missing": [{"requirement": "...", "spec_line": "...", "detail": "..."}],
  "scope_creep": [{"behaviour": "...", "detail": "why not asked for"}],
  "wrong_implementation": [{"requirement": "...", "spec_line": "...", "detail": "what's wrong"}],
  "summary": "one sentence"
}

FAIL-CLOSED: If you can't read the spec or diff, passed=false.""",
    context=f"""
    <spec_source>
    [paste spec/issue/PRD content from Step 2]
    </spec_source>

    <diff>
    [paste diff from Step 3]
    </diff>
    """,
    toolsets=["terminal"]
)
```

## Step 6 — Baseline Tests and Linting

While sub-agents run, establish the test and lint baseline.

Detect the project language and run the appropriate tools. Capture the failure count BEFORE your changes as **baseline_failures** (stash changes, run, pop). Only NEW failures introduced by your changes block the commit.

```bash
# Test frameworks (auto-detect by project files)
python -m pytest --tb=no -q 2>&1 | tail -5
npm test -- --passWithNoTests 2>&1 | tail -5
cargo test 2>&1 | tail -5
go test ./... 2>&1 | tail -5

# Linting and type checking (run only if installed)
which ruff && ruff check . 2>&1 | tail -10
which mypy && mypy . --ignore-missing-imports 2>&1 | tail -10
which npx && npx eslint . 2>&1 | tail -10
which npx && npx tsc --noEmit 2>&1 | tail -10
```

**Baseline comparison:** If baseline was clean and your changes introduce failures, that's a regression. If baseline already had failures, only count NEW ones.

## Step 7 — Aggregate Results

Wait for both sub-agents to complete. Present their findings under separate headings:

```
## Standards
[verbatim Standards report — violations + smells]

## Spec
[verbatim Spec report — missing items + scope creep + wrong implementations]
```

**Do NOT merge or rerank findings.** The two axes are deliberately separate. Keeping them separate is the whole point.

End with a one-line summary: total findings per axis, and the worst issue *within each axis* (if any). Don't pick a single winner across axes.

### Step 7.5 — Data Structure Efficiency Review

**Run after the Standards and Spec sub-agents return.** Load `data-structure-efficiency-review` and its language reference files for the code under review. Scan the diff for:

- **Hot loops with linear scans** (P1/P2) — membership test or key lookup inside a loop → build `Set`/`Map` once outside
- **N+1 queries** (P8) — per-row DB/API calls → eager-load or batch query
- **Quadratic accumulation** (P7) — string/array built via `+=`/spread in a loop → `join`/`push`
- **Unbounded retention** (P10) — caches/memos/registries without cap or TTL
- **Wrong collection type** (P12) — access pattern doesn't match the chosen structure
- **Repeated index rebuild** (P3) — grouping/sorting inside the loop body

For each finding at Medium+: write a finding entry with severity, pattern name, complexity before/after, and a minimal semantic-preserving patch. Merge with the aggregated results from Standards and Spec.

**Do not skip this step for any code change that modifies loops, data access patterns, or persistent structures.** For trivial single-line changes, a 10-second mental scan is sufficient.

## Step 8 — Evaluate + Self-Review Quick Check

Combine results from Steps 3 (security), 6 (baseline), and 7 (both axes):

```
## Results
Security issues: [N]
Standards violations: [N] (hard) + [N] (smells)
Spec issues: [N]
Test regressions: [N]
New lint errors: [N]
```

Quick self-review checklist before auto-fix:

- [ ] No hardcoded secrets, API keys, or credentials
- [ ] Input validation on user-provided data
- [ ] SQL queries use parameterized statements
- [ ] File operations validate paths (no traversal)
- [ ] External calls have error handling (try/catch)
- [ ] No debug print/console.log left behind
- [ ] No commented-out code
- [ ] New code has tests (if test suite exists)

## Step 9 — Auto-Fix Loop

**Maximum 2 fix-and-reverify cycles.**

Spawn a fix agent that addresses ONLY the reported issues:

```python
delegate_task(
    goal="""You are a code fix agent. Fix ONLY the specific issues listed below.
Do NOT refactor, rename, or change anything else.

Issues to fix:
- Standards hard violations: [list]
- Spec missing items: [list]
- Spec wrong implementations: [list]
- Security findings: [list]

Current diff for context:
--- 
[paste diff]
---

Fix each issue precisely. Describe what you changed and why.""",
    context="Fix only the reported issues. Do not change anything else.",
    toolsets=["terminal", "file"]
)
```

After the fix agent completes, re-run Steps 3-7 (full verification cycle).
- Passed: proceed to Step 10
- Failed and attempts < 2: repeat Step 9
- Failed after 2 attempts: escalate to user with the remaining issues

## Step 10 — Commit

If verification passed:

```bash
git add -A && git commit -m "[verified] <description>"
```

The `[verified]` prefix indicates independent two-axis review approved this change.

## Integration with Other Skills

- **subagent-driven-development** — Run this after EACH task as the quality gate. The two-axis architecture matches the two-stage review pattern.
- **change-test-loop** — This pipeline verifies TDD discipline was followed — tests exist, tests pass, no regressions.
- **root-cause-debugging** — When bugs survive review, use the feedback loop approach to pin down what the review missed.
- **codebase-design** — Spec axis issues often trace back to shallow modules (no clean seam). Hand off to codebase-design for deepening recommendations.
- **design-doc-audit** — Spec axis needs a spec. If the spec is missing or stale, use design-doc-audit to fix it first.

## Pitfalls

- **No fixed point provided** — Ask the user. Don't guess. If uncommitted changes, use `HEAD` as the fixed point.
- **Empty diff** — check `git status`, tell user nothing to verify
- **Not a git repo** — skip and tell user
- **Large diff (>15k chars)** — split by file, review each separately
- **delegate_task returns non-JSON** — retry once with stricter prompt, then treat as FAIL
- **Sub-agents hang** — 10-minute timeout. If one returns and the other doesn't, report partial results from the completed axis.
- **No spec found** — Spec axis skips. Standards + security + baseline still run.
- **No test framework found** — skip regression check, Standards/Spec verdicts still run
- **Lint tools not installed** — skip that check silently, don't fail
- **Auto-fix introduces new issues** — counts as a new failure, cycle continues (max 2)
- **False positives in smell baseline** — repo documented standard overrides the smell. Note in the report why it was suppressed.
- **Spec and Standards disagree but both pass** — present both findings. The user decides which axis to prioritize.

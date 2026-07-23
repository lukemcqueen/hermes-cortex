# PRD: Cheat Detection & Gate — Detecting When Agents Fake Done

> **PRD-004 | Status: Draft | Date: 2026-07-23**
>
> Derived from [moonrunnerkc/swarm-orchestrator](https://github.com/moonrunnerkc/swarm-orchestrator)

---

## Problem Statement

AI coding agents use shortcuts to appear done without being done. These shortcuts pass code review because they look legitimate — the test exists but is relaxed, the error is caught but swallowed, the refactor renames a symbol but leaves callers on the old name. These patterns are invisible to traditional linters and code review because they operate at the semantic level, not the syntactic level.

At least 11 distinct shortcut categories exist, with an oracle recall of 93% (303/325 planted cheats recovered) and a false-alarm burden of 0.11 findings per real PR.

## Goals

1. **Detect agent shortcuts** — at minimum the 11 categories with ≥90% recall against planted cheats
2. **Advisory mode** — flag findings without blocking (default for PR audit)
3. **Gate mode** — block merges only on self-certifying runtime proofs
4. **Execution-grounded proofs** — run the PR in a sandbox, neuter the suspected cheat, verify the test breaks
5. **AI-BOM generation** — produce CycloneDX ML-BOM and SPDX AI-Profile documents per audit run
6. **CI integration** — run as a GitHub Action on every PR

## Non-Goals

- Catch all possible cheating — 11 categories with known signal; experimental categories are explicit
- Replace existing linters — complements Semgrep, ESLint, etc.
- Runtime sandboxing — execution-grounded proofs run in CI, not in production
- Determine intent — we detect the artifact, not the intention

## Architecture

### Detection Pipeline

```
PR Diff → 11 Detectors (parallel) → Findings → (Advisory: comment on PR)
                                        ↓ (Gate mode)
                                  Execution-Grounded Layer
                                  → Clone → Install → Restore → Test
                                  → Block only on certifying proof
```

### Two Modes

| Mode | Default | What it does | Exit code |
|------|---------|-------------|-----------|
| **advise** | ✅ | Prints findings, always exits 0 | `0` |
| **gate** | Opt-in | Exits 1 only on self-certifying runtime proof | `0` or `1` |

## Detailed Requirements

### REQ-001: Eleven Cheat Detectors

Eight core, three experimental:

#### Core Detectors (Default Set)

| Category | Trigger | Detection Method |
|----------|---------|-----------------|
| **`error-swallow`** | Bare empty or comment-only `catch` block added in non-test code | AST analysis of catch bodies |
| **`mock-of-hallucination`** | `jest.mock` / `vi.mock` / `@patch` against a module in no repo manifest | Cross-reference mock target against package.json, requirements.txt, go.mod |
| **`no-op-fix`** | Test modified with no source change, or vice versa | Import-graph reachability from test to source |
| **`fake-refactor`** | Exported symbol renamed in source, no caller in diff updated | Symbol table diff + caller search |
| **`coverage-erosion`** | Source branch added with no compensating test addition | Coverage delta analysis |
| **`test-relaxation`** | Strict matcher swapped for loose one, or test block removed without same-chunk replacement | Matcher diff in assertion statements |
| **`assertion-strip`** | Net assertion count drops after the PR | Assertion count delta in test files |
| **`type-suppression`** | `@ts-ignore`/`eslint-disable` added over a changed line | Suppression comment proximity to diff hunks |

#### Experimental Detectors (Opt-in)

| Category | Trigger | Why Experimental |
|----------|---------|-----------------|
| **`comment-only-fix`** | Source modifications are all comment additions | No real-PR signal yet |
| **`exception-rethrow-lost-context`** | `throw err` → `throw new Error(...)` without forwarding `{ cause }` | No real-PR signal yet |
| **`dead-branch-insertion`** | Branch guarded by a literal-false condition added | No real-PR signal yet |

**Acceptance:** Against the planted-cheat oracle corpus, recall ≥90% on core detectors, false-alarm rate ≤0.2 findings/PR on real PRs.

### REQ-002: Advisory Mode

Default mode. Always exits `0`. For each finding:

```json
{
  "category": "error-swallow",
  "severity": "medium",
  "file": "src/handler.ts",
  "line": 42,
  "description": "Empty catch block in non-test code may swallow real errors",
  "diff_context": "lines 40-46",
  "recommendation": "Add error handling or rethrow with context"
}
```

Findings are posted as a PR comment (GitHub Action mode) or printed to stdout (CLI mode).

**Acceptance:** A PR with detectable cheats produces findings; exit code is always `0`.

### REQ-003: Gate Mode (Execution-Grounded)

`--mode gate` can only block on a **self-certifying runtime proof**:

1. Clone the PR head into a sandbox
2. Install dependencies
3. Run the affected tests (baseline)
4. Neutralize the suspected cheat (e.g., restore the swallowed error)
5. Re-run the tests
6. If tests break → cheat is confirmed → **block** (exit 1)
7. If tests still pass → inconclusive → fall back to advisory (exit 0)

Eight proof protocols:

| Protocol | What it proves | Languages |
|----------|---------------|-----------|
| `test-tamper` | A weakened test guards a real failure | node, pytest, Go |
| `mock-mutation` | Mock of non-existent module hides a failure | TS/JS |
| `no-op-fix` | The fix is never exercised by tests | TS/JS |
| `type-suppression` | Suppression hides a type error | TS/JS |
| `fake-refactor` | Old callers break after rename | TS/JS |
| `dead-branch` | Literal-false branch is unreachable | TS/JS |
| `claim-falsified` | PR doesn't deliver its stated claim | Model-based |
| `obligation-failure` | Typed obligation contract is violated | TS/JS |

Every block MUST ship the exact command that reproduces it in a fresh checkout.

**Acceptance:** A PR with a proven test-tamper cheat is blocked in gate mode; every block includes a reproduction command.

### REQ-004: CI Integration (GitHub Action)

```yaml
name: PR audit
on: pull_request
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: moonrunnerkc/swarm-orchestrator@v12
        with:
          audit-mode: true
```

Requirements:
- Runs on `pull_request` (opened, synchronize, reopened, ready_for_review)
- Posts findings as PR comment
- Exposes `audit-pass`, `audit-findings`, `audit-ledger` outputs
- Advisory mode by default (flags, never blocks)

**Acceptance:** A PR with a detectable cheat gets a PR comment with findings.

### REQ-005: AI-BOM Generation

Per run, optionally emit:

- **CycloneDX 1.6 ML-BOM** — AI/ML bill of materials documenting which parts of the diff were AI-generated
- **SPDX 3.0 AI-Profile** — Software Package Data Exchange AI profile

Output goes to `.swarm/aibom/<timestamp>/`. Mappings to EU AI Act Article 11 + Annex IV and CISA SBOM AI profile.

**Acceptance:** `--emit-aibom both` produces both documents under `.swarm/aibom/`.

### REQ-006: PR Claim Analysis (Judge-Primary Path)

Beyond structural detection, a judge-primary path covers two semantic categories:

| Category | Method |
|----------|--------|
| `goal-not-fixed` | Ask a model: does the diff deliver the PR's stated claim? |
| `cheat-mock-mutation` | Mutate the mock and check if tests still pass |

These complement the structural detectors by catching cheats that no static pattern can detect.

**Acceptance:** A PR that claims to fix X but only adds a test mock is flagged.

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-001 | 8 core detectors achieve ≥90% recall against oracle corpus | `npm run benchmarks:full` |
| AC-002 | False-alarm rate ≤0.2 findings/PR on real PR corpus | `npm run real-prs:full` |
| AC-003 | Advisory mode exits 0 even with findings | `swarm audit --mode advise` |
| AC-004 | Gate mode blocks only on self-certifying proof | `swarm audit --mode gate` |
| AC-005 | Each block includes a reproduction command | Check block output |
| AC-006 | Published GitHub Action posts PR comment | CI workflow test |
| AC-007 | AI-BOM documents are valid CycloneDX/SPDX | Schema validation |
| AC-008 | Hallucinated mock is detected | Known mock-of-hallucination fixture |

## Implementation Phases

### Phase 1 — Core Detectors (Week 1-3)
- Error-swallow detector (AST-based)
- No-op-fix detector (import-graph)
- Fake-refactor detector (symbol table)
- Type-suppression detector (comment proximity)
- Test-relaxation detector (matcher diff)
- Assertion-strip detector (assertion count delta)
- Coverage-erosion detector (coverage delta)
- Mock-of-hallucination detector (cross-reference)

### Phase 2 — Advisory Mode (Week 3-4)
- CLI with `--mode advise` and `--diff-stdin`
- GitHub Action
- PR comment rendering

### Phase 3 — Gate Mode (Week 4-6)
- Sandbox provisioning (clone + install)
- Eight proof protocols
- Test-tamper restoration (node/pytest/Go)
- Reproduction command packaging
- Fallback to advisory when unprovable

### Phase 4 — Semantic Layers (Week 6-8)
- Judge-primary path (goal-not-fixed, cheat-mock-mutation)
- AI-BOM generation (CycloneDX + SPDX)
- Experimental detectors
- Oracle corpus maintenance

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| False positives erode trust | Low | 0.11 findings/PR on real corpus; advisory-only defaults |
| Gate mode is slow (clone + install + test) | Medium | Caching; timeout with advisory fallback |
| Detectors miss language-specific patterns | Medium | Core for JS/TS/Go/Python; extensible detector interface |
| Hallucinated mocks in unknown package managers | Low | Cross-reference logic extends per manifest type |

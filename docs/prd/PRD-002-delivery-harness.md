# PRD: Delivery Harness — Spec-First Disciplined Delivery

> **PRD-002 | Status: SUPERSEDED | Date: 2026-07-23**
>
> ⚠️ **This PRD is superseded.** The delivery harness concept was absorbed into:
> - **Wave orchestration** (`ops/scripts/manage/wave-orchestrate.py`) — 5-wave delivery pipeline
> - **Outerloop** (`ops/scripts/manage/outerloop.py`) — evidence/verdict cycle
> - **Change-checklist skill** — pre-ship verification (6-question checklist)
>
> See [`PRD-003-session-orchestration.md`](./PRD-003-session-orchestration.md) and
> [`PRD-005-enterprise-integration-v2.md`](./PRD-005-enterprise-integration-v2.md) for current architecture.
>
> Derived from [Chachamaru127/claude-code-harness](https://github.com/Chachamaru127/claude-code-harness)

---

## Problem Statement

Agentic coding today follows an implicit flow: user describes intent, agent writes code, user reviews result. This breaks down because:

1. **No spec contract** — the agent interprets intent without documenting its understanding. Ambiguity is resolved by guessing, not by asking.
2. **No plan gate** — code is written before the approach is agreed. Reversals are expensive.
3. **Review is too late** — quality is checked at the PR stage, not enforced during development.
4. **Evidence is ad-hoc** — every release rebuilds its proof of correctness from scratch.
5. **Unknowns are silently filled** — data the agent hasn't seen becomes assumptions that look like facts.
6. **No separation of concerns** — the same agent plans, writes, and reviews its own work.

## Goals

1. **Spec contract** — every task starts by writing `spec.md` and `Plans.md` with scope, acceptance criteria, unknowns, and stop conditions
2. **Plan gate** — the plan must be user-approved before implementation begins
3. **TDD enforcement** — tests are written before (or alongside) implementation when the task requires it
4. **Independent review** — review is a separate phase from implementation, using a different perspective
5. **Evidence packaging** — `release` phase packages only verified evidence
6. **Multi-host support** — the same workflow runs on Claude Code, Codex CLI, Cursor, Grok

## Non-Goals

- Replace the agent's native tooling — harness works alongside it
- Handle every possible tool — supported hosts have explicit tiers
- Runtime-level enforcement — no sandboxing or isolation beyond what each host provides

## Architecture

### Harness Operating Loop

```
User intent → /harness-plan (write spec + plan) → User approves → /harness-work (implement)
  → /harness-review (independent check) → /harness-release (package evidence)
```

### Five Verb Skills

| Verb | Input | Output | Gate |
|------|-------|--------|------|
| **Plan** | Natural language intent | `spec.md` + `Plans.md` | User approval of generated contract |
| **Work** | Approved task slice | Code + tests | TDD gate, verification pass |
| **Review** | Implementation | Independent verdict | Blockers block completion |
| **Sync** | State files | Drift detection | Files match spec + plan |
| **Release** | Verified artifacts | PR + evidence pack | Preflight + CHANGELOG check |

## Detailed Requirements

### REQ-001: Spec-First Contract

Every task MUST start with `/harness-plan` which produces:

```markdown
# Spec: <feature name>

## Understanding
What the user asked for, in the agent's own words. Confirms shared context.

## Scope
- **In scope:** Explicit list of what will be built
- **Out of scope:** Explicit list of what will NOT be built

## Acceptance Criteria
1. AC-001: Clear, testable criterion with verification method
2. AC-002: ...
3. AC-003: ...

## Unknowns
- What the agent doesn't know yet (data not observed, questions unanswered)
- Marked as `unknown` — never silently filled in

## Stop Conditions
- When to stop (all ACs met)
- When to escalate (ambiguity, risk, blocked dependency)
- When to abort (architecture issue, infeasibility)
```

**Acceptance:** Every `/harness-plan` run produces a spec.md with ALL sections filled. Unknowns are explicitly marked, never assumed.

### REQ-002: Plan Gate

Implementation MUST NOT begin until the user explicitly approves the plan. The flow:

1. `/harness-plan` drafts spec.md + Plans.md
2. The user reads and either approves or corrects
3. Only after approval does `/harness-work` execute

For non-trivial changes, the plan MUST be validated through:

- **Team perspective** — does this plan work for the whole team?
- **Sub-agent validation** — a second agent reviews the plan for completeness
- **Memory reuse** — are existing patterns/solutions being reused where appropriate?
- **Product fit** — does this solve the right problem?
- **Security fit** — any security concerns?
- **Works-in-practice** — can this actually be implemented as specified?

**Acceptance:** A `/harness-work` call before `/harness-plan` approval is blocked.

### REQ-003: Work Phase with TDD Gate

The `/harness-work` command:

1. Accepts a task ID or slice reference (e.g., `/harness-work 1.1.1`)
2. Writes tests FIRST when the task requires them (configurable per project)
3. Implements the approved scope ONLY — no scope creep
4. Runs verification after implementation
5. Flags any deviation from the approved plan

**Acceptance:** A work phase that exceeds the approved plan is flagged with a drift warning.

### REQ-004: Independent Review Phase

Review is a SEPARATE phase from implementation:

| Aspect | Implementer | Reviewer |
|--------|------------|----------|
| Focus | Correctness | Quality, maintainability, spec compliance |
| Perspective | "Does it work?" | "Is it right?" |
| Scope | Within task | Across the whole change |
| Output | Working code | Findings + verdict |

Review findings are categorized:

- **Blocker** — must fix before release
- **Major** — should fix, may defer with rationale
- **Minor** — nice to have
- **Suggestion** — not required

**Acceptance:** A review with blocker findings prevents release until resolved.

### REQ-005: Release Phase with Evidence

`/harness-release` packages:

1. `RELEASE.md` — what changed, why, verification summary
2. Test results — pass/fail summary with key assertions
3. Review verdict — all findings with resolution status
4. CHANGELOG update — auto-generated from spec/plan changes
5. Tag — semantic version increment

**Preflight checks:**
- [ ] All acceptance criteria met
- [ ] No blocker review findings open
- [ ] Tests pass in CI
- [ ] CHANGELOG updated
- [ ] Version tag matches semver

**Acceptance:** A release preflight with any failure blocks the release.

### REQ-006: Unknown Tracking

Any data point the agent needs but hasn't observed MUST be tracked:

```markdown
## Unknowns
| Unknown | Why it matters | How to resolve |
|---------|---------------|----------------|
| Current prod API response format | Tests may mock wrong shape | Check prod — assigned to user |
| Auth token expiry time | Integration test timing | Check docs — assigned to implementer |
```

**Acceptance:** A spec with unresolved unknowns is not ready for implementation.

### REQ-007: Multi-Host Support

The harness MUST support at least these tiers:

| Tier | Meaning | Hosts |
|------|---------|-------|
| **supported** | Full workflow tested in CI | Claude Code, Codex CLI, Cursor, Grok |
| **candidate** | Setup works, runtime not fully tested | Hermes Agent, GitHub Copilot CLI |
| **future** | No current install path | Antigravity, future tools |

Each host has:
- A setup script (`scripts/setup-<host>.sh`)
- Documented gaps vs. reference implementation (Claude Code)
- Smoke test that confirms the basic workflow

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-001 | `/harness-plan` produces complete spec with unknowns | Check output for all required sections |
| AC-002 | `/harness-work` after plan approval runs within scope | Drift detection catches scope creep |
| AC-003 | `/harness-review` with blockers prevents release | `harness-release` exits non-zero |
| AC-004 | Release package contains spec, plan, tests, review, CHANGELOG | Verify artifact contents |
| AC-005 | Unknowns are tracked and never silently filled | Check spec for `unknown` markers |
| AC-006 | Same workflow works on Claude Code + Codex CLI | Run smoke on both |
| AC-007 | Migration report from old setup is generated | `harness doctor --migration-report` produces actionable output |

## Implementation Phases

### Phase 1 — Core Verbs (Week 1-2)
- `/harness-plan` — spec.md + Plans.md generation
- `/harness-work` — task execution with scope enforcement
- `/harness-review` — independent review phase
- `/harness-release` — evidence packaging + preflight

### Phase 2 — Spec System (Week 2-3)
- Unknown tracking
- Plan validation (team, sub-agent, security, product fit)
- Multi-tool setup scripts (Claude Code, Codex CLI, Cursor)

### Phase 3 — TDD Integration (Week 3-4)
- TDD gate enforcement
- Auto-generated test scaffolding from spec
- Test coverage tracking in release

### Phase 4 — Cross-Session (Week 4-5)
- Session persistence (harness-mem pattern)
- Migration reporting
- Hermes Agent integration as candidate tier

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Plan overhead too high for small tasks | Medium | Skip plan gate for "small fix" classification; simple-code flow |
| Review phase adds latency | Medium | Review is async — work can continue on independent slices |
| Multi-host drift | Low | CI smoke tests per host; explicit tier documentation |
| Unknowns ignored in practice | Medium | Spec template forces unknowns section; plan gate enforces it |

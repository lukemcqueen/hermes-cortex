# PRD: Session Orchestration — Wave Execution with Quality Gates

> **PRD-003 | Status: Draft | Date: 2026-07-23**
>
> Derived from [Kanevry/session-orchestrator](https://github.com/Kanevry/session-orchestrator)

---

## Problem Statement

Agent sessions follow an unstructured path: describe intent, write code, maybe test, deliver. This creates systemic problems:

1. **No session lifecycle** — sessions don't have a defined start, execution, review, and close. Work drifts without boundaries.
2. **No wave decomposition** — complex tasks are attempted as one batch, not decomposed into logical phases (discovery → core → polish → quality → finalize).
3. **Quality checked too late** — regressions aren't caught until the end, after bad patterns have propagated.
4. **Crash loses progress** — if the session crashes, all in-progress work is lost.
5. **No cross-session learning** — patterns from one session never inform the next.
6. **No scope enforcement** — agents write files they shouldn't, run commands they shouldn't.

## Goals

1. **Session lifecycle** — `/session start → /go → /close` with defined phases and gates
2. **Five typed waves** — Discovery → Impl-Core → Impl-Polish → Quality → Finalization
3. **Inter-wave quality gates** — between every wave, run verification; regressions caught immediately
4. **Crash recovery** — `STATE.md` survives crashes; next session offers resume
5. **Cross-session learning** — `/evolve` extracts confidence-scored patterns across 5+ sessions
6. **Scope enforcement** — pre-edit guard blocks writes outside allowed paths
7. **Carryover tracking** — unfinished work becomes issues for the next session

## Non-Goals

- Real-time multi-agent coordination — waves are sequential, not concurrent across agents
- Full CI/CD integration — orchestration is session-level, not pipeline-level
- Replace the Hermes agent flow — orchestration sits ON TOP of agent-flow

## Architecture

### Session Lifecycle

```
/session <type> → research + Q&A → agree scope
  → /go → Wave 1 (Discovery) → Gate → Wave 2 (Impl-Core) → Gate
    → Wave 3 (Impl-Polish) → Gate → Wave 4 (Quality) → Gate
      → Wave 5 (Finalization) → /close → verify → commit → carryover
```

### Five Typed Waves

| Wave | Purpose | Read-Only? | Deliverable | Max Agents |
|------|---------|-----------|-------------|-----------|
| **1. Discovery** | Audit existing code, read docs, understand state | ✅ Yes | Shared context doc, risk register | 1-2 |
| **2. Impl-Core** | Primary code — architecture, models, core logic | ❌ No | Core implementation | 2-4 |
| **3. Impl-Polish** | Integration, edge cases, error handling | ❌ No | Complete feature | 2-4 |
| **4. Quality** | Simplify AI-generated code, THEN write tests, THEN adversarial verify | ❌ No | Simplified code + test suite + adversarial findings | 2-3 |
| **5. Finalization** | Commit, close issues, update docs | ❌ No | Clean commit + carryover | 1 |

**Why adversarial verification in Wave 4:** AI-generated code often passes standard tests but has hidden failure modes — swallowed errors, brittle assumptions, unhandled edge cases. The adversarial verifier actively tries to break the code: fuzzing inputs, corrupting state, sabotaging dependencies, attacking concurrency. If the code survives adversarial review, it earns certification. See PRD-006.

## Detailed Requirements

### REQ-001: Session Start (`/session`)

`/session <type>` does:

1. **Phase analysis (parallel):**
   - Inspect git state (branch, uncommitted, ahead/behind)
   - Check open issues and recent commits
   - Read SSOT (source of truth) freshness
   - Check resource health (disk, services)
   - Read prior-session memory
2. **Distill into Session Overview:**
   - Current state summary
   - Recommendation (what to do next)
   - Risks and known issues
3. **Agree scope via picker:**
   - Claude Code: tool-rendered picker
   - Codex/Cursor: numbered list fallback
   - Orchestrator has an opinion and states what it would do
4. **Write session config:**
   - Set `test-command`, `typecheck-command`, `lint-command`
   - Set `agents-per-wave`, `waves`
   - Set `persistence: true`, `enforcement: warn`

**Acceptance:** `/session feature` produces a Session Overview with recommendation before any code is written.

### REQ-002: Wave Execution (`/go`)

`/go` executes the five waves sequentially:

1. **Wave 1 — Discovery (read-only):**
   - Audit the codebase for the relevant area
   - Document existing patterns, architecture, risks
   - Output: `discovery.md` shared context document

2. **Wave 2 — Impl-Core:**
   - Implement the core architecture
   - Models, data flow, primary interfaces
   - NO edge cases yet

3. **Wave 3 — Impl-Polish:**
   - Integration points, error handling, edge cases
   - Connect the core to the rest of the system

4. **Wave 4 — Quality:**
   - SIMPLIFY the generated code first (removes AI over-engineering)
   - THEN write tests
   - Run full test suite

5. **Wave 5 — Finalization:**
   - Stage files individually (prevent parallel-session stomping)
   - Update docs, close issues
   - Create carryover issues for unfinished work

**Acceptance:** After `/go` completes, all five waves have produced their deliverables and gates have passed.

### REQ-003: Inter-Wave Quality Gates

Between every wave, a **session-reviewer** audits the output on eight dimensions:

| Dimension | What it checks | Confidence floor |
|-----------|---------------|-----------------|
| Scope compliance | Did the wave deliver what was planned? | 90% |
| Code quality | Readability, conventions, duplication | 80% |
| Test coverage | Are there tests for new code? | 80% |
| Error handling | Are errors caught and handled? | 70% |
| Security | Any obvious vulnerabilities? | 90% |
| Performance | Any obvious performance issues? | 70% |
| Regressions | Did this wave break anything from previous waves? | 90% |
| Consistency | Does the output match the project's patterns? | 80% |

Only findings at confidence ≥ 80% reach the user. Lower-confidence findings are logged but not surfaced.

**Acceptance:** A regressing change between waves is caught by the gate.

### REQ-007a: Adversarial Verification Gate (Wave 4)

Wave 4 (Quality) includes an adversarial verification step AFTER standard tests pass:

```
Wave 4 entry → Simplify generated code → Write standard tests
  → Run standard test suite (must pass)
  → ACTIVATE ADVERSARIAL VERIFIER
    → Attack surface enumeration
    → Input fuzzing
    → State corruption
    → Dependency sabotage
    → Concurrency attacks
    → Invariant violation
    → Evidence packaging
  → If findings: fix → re-verify → loop
  → If certification: proceed to Wave 5
```

Adversarial verifier uses a DIFFERENT model than the implementer (e.g., implementer
on a Tier 3 model, verifier on a Tier 1 model). Maturity level configurable:
A1-A5 from PRD-006.

**Acceptance:** A wave 4 quality gate with adversarial verification catches code
that passes standard tests but has hidden failure modes.

### REQ-004: Crash Recovery (STATE.md)

A `STATE.md` file persists across sessions:

```markdown
# Session State

## Progress
- Wave 1: COMPLETED (2026-07-23T10:00Z)
- Wave 2: IN_PROGRESS (2026-07-23T10:30Z)
- Wave 3: PENDING
- Wave 4: PENDING
- Wave 5: PENDING

## Deviations
- Wave 1 expanded scope: found 3 undocumented APIs (logged, escalated)
- Wave 2: delayed by broken test infra (logged, working around)

## Carryover
- [ ] Update API docs for 3 undocumented endpoints
- [ ] Investigate test infra flake
```

On crash/restart, the next `/session` reads STATE.md and offers to resume from the last completed wave.

**Acceptance:** A mid-session crash followed by restart offers resume from the correct wave.

### REQ-005: Cross-Session Learning (`/evolve`)

After 5+ sessions, `/evolve analyze`:

1. Reads all session records
2. Extracts patterns across sessions:
   - What went well (repeatable good patterns)
   - What went wrong (recurring mistakes)
   - What was surprising (unexpected findings)
3. Scores each pattern by confidence
4. Presents findings for human review/pruning
5. Feeds back into session-start context

```yaml
## Pattern: Test-first for API changes
confidence: 0.85
evidence: 4 sessions, 6 instances
rule: Always write the API test before implementing the endpoint. Catches spec gaps.
```

**Acceptance:** After 5 sessions, `/evolve analyze` produces a confidence-scored pattern list.

### REQ-006: Scope Enforcement (Pre-Edit Guard)

A pre-edit hook MUST block writes outside the allowed scope:

```yaml
# Session Config
enforcement: strict  # strict | warn | off
allowed_paths:
  - src/feature-x/**
  - tests/feature-x/**
deny_paths:
  - src/auth/**
  - .env
  - infra/**
```

- `strict` — blocks the write, logs the attempt
- `warn` — allows the write, logs the warning
- `off` — no enforcement (for exploration/debug sessions)

A destructive-command guard ALSO blocks:
- `git reset --hard`, `rm -rf`, `git push --force`
- Bypass per session: `allow-destructive-ops: true`

**Acceptance:** A write to a denied path is blocked in `strict` mode.

### REQ-007: Session Close (`/close`)

`/close` does:

1. **Verify every planned item** — check each AC against current state
2. **Run quality gates full** — typecheck + lint + test suite
3. **Stage files individually** — prevent parallel-session file conflicts
4. **Create carryover issues** — for any incomplete work
5. **Write session record** — append to session log
6. **Clean up** — remove temp files, worktrees, STATE.md

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-001 | `/session` produces Overview with recommendation | Check output format |
| AC-002 | 5 waves execute with quality gates between each | Gate failure stops the wave |
| AC-003 | Crash recovery resumes from correct wave | Kill session → restart → check resume offer |
| AC-004 | `/evolve` after 5 sessions produces patterns with confidence scores | Run `/evolve analyze` |
| AC-005 | Denied-path write is blocked in `strict` mode | Attempt write → gets blocked |
| AC-006 | `/close` stages files individually, not with bulk `git add` | Check git staging |
| AC-007 | Unfinished work creates carryover issues | Check issue tracker after close |

## Implementation Phases

### Phase 1 — Session Lifecycle (Week 1-2)
- `/session` — phase analysis, overview, scope agreement
- `/go` — wave execution framework
- `/close` — verification, staging, carryover

### Phase 2 — Quality Gates (Week 2-3)
- Typechecked, lint, test gate between waves
- Session-reviewer sub-agent with 8-dimension audit
- Confidence scoring

### Phase 3 — Persistence (Week 3-4)
- STATE.md read/write for crash recovery
- Session log append
- `/evolve` cross-session learning

### Phase 4 — Enforcement (Week 4-5)
- Pre-edit scope guard (strict/warn/off)
- Destructive-command guard
- Path denylist configuration
- Session config YAML template

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Wave overhead for simple tasks | Medium | Skip waves for simple-code classification; 1-wave mode |
| Session-reviewer slows waves | Medium | Review runs in parallel with wave cleanup; async |
| Cross-session learning is noise | Low | Confidence scoring filters; human review before applying |
| Scope enforcement false positives | Medium | `warn` mode for exploration; override per path |

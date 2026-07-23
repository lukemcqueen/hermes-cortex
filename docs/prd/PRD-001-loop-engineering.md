# PRD: Agent Loop Engineering — Automated Agent Loops

> **PRD-001 | Status: Draft | Date: 2026-07-23**
>
> Derived from [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering)

---

## Problem Statement

Agents are prompted per-task, not per-system. Every new task starts from zero context — no memory of prior runs, no budget awareness, no safety rails. The user remains responsible for prompting, triaging, and verifying every cycle. This does not scale beyond a handful of tasks because:

1. **No scheduling** — tasks that should run daily/weekly require manual re-prompting
2. **No cost controls** — runaway loops consume tokens silently until the user notices
3. **No verification split** — the same agent that writes code judges its own work
4. **No state persistence** — every run is amnesic, re-deriving context
5. **No safety denylist** — agents can modify secrets, infra, or auth files

## Goals

1. **Loop primitives** — schedule, triage skill, worktree isolation, maker/checker split, state file, safety gates
2. **Budget system** — per-loop and per-run token budgets with kill switch
3. **Loop audit** — readiness scoring with actionable upgrade suggestions
4. **Cost estimation** — predict token spend before running a loop pattern
5. **Drift detection** — detect when `STATE.md` and `LOOP.md` diverge

## Non-Goals

- Replace the existing cron system — loops supplement scheduled work
- Full multi-agent coordination — that's PRD-005 (Integration)
- Real-time streaming — loops run on intervals

## Architecture

### Loop Anatomy

```
Schedule/Automation → Triage Skill → Read/Write STATE → Isolated Worktree
  → Implementer Sub-agent → Verifier Sub-agent → MCP/Git/APIs → Human Gate → Commit
```

### Five Building Blocks

| Primitive | Job in the Loop | Existing (Hermes) | Gap |
|-----------|-----------------|-------------------|-----|
| **Scheduling** | Triage on a cadence | `cronjob` MCP tool + no_agent crons | No triage skill pattern |
| **Worktrees** | Safe parallel execution | Git worktrees available manually | No loop-worktree CLI |
| **Skills** | Persistent project knowledge | `skills/` directory, `skill_view()` | No skill loading in cron context |
| **MCP Connectors** | Reach into real tools | `cronjob` tool, `terminal` | Limited to Hermes toolset |
| **Sub-agents** | Maker/checker split | `delegate_task` | Not wired into cron flow |

## Detailed Requirements

### REQ-001: Loop State File

Every active loop MUST maintain a `STATE.md` file in `.hermes/loops/<loop-name>/`:

```markdown
# Loop State: <name>

## Purpose
One sentence: what this loop accomplishes.

## Non-Goals
What this loop will NOT do.

## Last Run
- Timestamp: 2026-07-23T04:00:00Z
- Items found: 3
- Actions taken: 2
- Escalations: 1
- Token cost: 12,345

## Budget
- Daily cap: 50,000 tokens
- Current cycle: 12,345 / 50,000
- Kill switch: OFF
```

**Acceptance:** After any loop run, STATE.md is updated with outcomes and cost.

### REQ-002: Loop Budget System

Every loop MUST have a `loop-budget.md` with:

```yaml
daily_cap_tokens: 50000
max_auto_prs_per_day: 3
max_iterations_per_item: 3
kill_switch: false  # set true to pause this loop
run_log: loop-run-log.md
```

The budget MUST be checked at the START and END of every run. If the daily cap is exceeded, the loop MUST skip execution and log the skip.

**Acceptance:** A loop that exceeds its daily budget skips with a logged warning.

### REQ-003: Maker/Checker Split

Every loop MUST use separate agents for implementation and verification:

```
Implementer → writes code/changes
Verifier → runs tests, checks quality, approves/rejects (different agent, different instructions)
```

The implementer MUST NOT be able to mark its own work as "done." The verifier MUST run tests in isolation (worktree) before approving.

**Acceptance:** A loop with a deliberately bad change is caught by the verifier.

### REQ-004: Loop Audit Score

A `loop-audit` script MUST score every loop on a 0-100 scale across:

| Category | Weight | Checks |
|----------|--------|--------|
| Purpose & Scope | 15% | Single goal, non-goals, watched scope |
| Scheduling | 10% | Cadence, durability, self-cleanup |
| Skills | 15% | Triage skill, action skills, build/test commands |
| Maker/Checker | 20% | Split enforced, verifier runs tests, isolation |
| State & Memory | 15% | Read/write state, prune resolved items, human overrides |
| Human Handoff | 10% | Escalation triggers, denylist, notification rules |
| Cost & Budget | 10% | Token budget, daily caps, kill switch |
| Safety | 5% | No auto-merge, secrets denylist, flake handling |

**Acceptance:** Running `loop-audit --suggest` on any loop produces a score + actionable upgrade steps.

### REQ-005: Loop Patterns Catalog

The following loop patterns MUST be documented and scaffoldable:

| Pattern | Cadence | Use Case | Est. Tokens |
|---------|---------|----------|-------------|
| **daily-triage** | Daily | Review open issues, PRs, alerts | 5-15K |
| **weekly-maintenance** | Weekly | Dep updates, branch prune, doc sync | 20-50K |
| **pr-babysitter** | Continuous | Monitor a PR's CI, re-review on push | 10-30K/run |
| **cleanup-loop** | Weekly | Stale branches, temp files, orphaned state | 5-10K |
| **dependency-audit** | Weekly | Check for vulnerable deps, open PRs | 15-25K |
| **health-watchdog** | Every N min | Check service health, alert on regression | 1-3K |

### REQ-006: Loop Context Management (Circuit Breaker)

Long-running loops MUST have context management:

- **Daily budget** — hard cap on tokens consumed per day
- **Path locking** — prevent two loops from editing the same files
- **Ledger** — append-only run log with timestamps, outcomes, costs
- **Kill switch** — pause a loop by setting `kill_switch: true` in budget

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-001 | A loop can be `loop-init` scaffolded in under 10 seconds | `time loop-init --pattern daily-triage` |
| AC-002 | Loop audit score reaches 80+ for any properly configured loop | `loop-audit . --badge` |
| AC-003 | A loop with exceeded budget skips execution and logs reason | Check run-log.md |
| AC-004 | A deliberately bad change is rejected by the verifier | Inject bad test → verifier catches |
| AC-005 | Cost estimate prints before first run | `loop-cost --pattern daily-triage` |
| AC-006 | Drift between STATE.md and LOOP.md is detected | Modify STATE.md → `loop-sync` flags drift |

## Implementation Phases

### Phase 1 — Foundation (Week 1-2)
- Create `.hermes/loops/` directory structure
- Implement `STATE.md` read/write pattern
- Token budget ledger (`loop-budget.md`)
- Kill switch mechanism

### Phase 2 — Audit & Cost (Week 2-3)
- `loop-audit` scoring script
- `loop-cost` estimation tool
- Loop design checklist as a skill

### Phase 3 — Patterns (Week 3-4)
- Scaffold `daily-triage` pattern
- Scaffold `health-watchdog` pattern
- Loop-init CLI (`loop-init --pattern <name>`)

### Phase 4 — Safety & Context (Week 4-5)
- Path denylist enforcement
- Drift detection (`loop-sync`)
- Circuit breaker for runaway loops
- Worktree management (`loop-worktree`)

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Loops silently fail | Medium | STATE.md records last-run status; doctor checks for stale loops |
| Loops conflict with each other | Low | Worktree isolation + path locking |
| Budget exceeded silently | Low | Budget checked at start/end of every run |
| Infinite loop | Medium | Max iterations + kill switch + circuit breaker |

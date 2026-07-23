# PRD: Enterprise Agent Orchestration — Integration of All Layers

> **PRD-005 | Status: Draft | Date: 2026-07-23**
>
> Integration of PRD-001 (Loops), PRD-002 (Harness), PRD-003 (Session Orchestration), PRD-004 (Cheat Detection)

---

## Problem Statement

We have four independent systems that each solve one piece of the agent orchestration puzzle, but they don't connect:

| System | What it solves | Missing connection |
|--------|---------------|-------------------|
| **Loop Engineering** | Automated scheduled agent loops | Loops don't use the session lifecycle or delivery harness |
| **Delivery Harness** | Spec-first disciplined delivery | Harness doesn't run as a loop or report to cheat detection |
| **Session Orchestration** | Wave execution with quality gates | Sessions don't persist across agents or integrate with fleet bus |
| **Cheat Detection** | Detecting when agents fake done | Detectors don't gate the delivery pipeline automatically |

An enterprise-grade orchestration system needs ALL four layers working together:

```
Loops (scheduling & automation)
  → Session Orchestration (wave execution & gates)
    → Delivery Harness (spec-first delivery)
      → Cheat Detection (verify no shortcuts)
        → Fleet Bus (coordination across agents)
          → Observability (Langfuse + cost tracking + scoring)
```

## Goals

1. **Unified orchestration pipeline** — from scheduled trigger to verified delivery across N agents
2. **Fleet-aware session management** — sessions can span orchestrator and server agents
3. **Quality gating with cheat detection** — every delivery passes cheat detection before release
4. **Cross-agent task routing** — the orchestrator delegates waves to appropriate agents
5. **Observability at every layer** — cost, quality, and outcome tracked per task
6. **Enterprise compliance** — AI-BOM, audit trails, role-based access

## Non-Goals

- Real-time agent coordination — orchestration is session-level, not sub-second
- Replacement of human code review — cheat detection is advisory; human review still gates merges
- Multi-cluster orchestration — single orchestrator fleet with backup

## Architecture

### Unified Stack

```
┌──────────────────────────────────────────────────────────────┐
│                    ENTERPRISE ORCHESTRATION                    │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: Scheduling (Loops)                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Daily Triage│  │ Health Watch │  │ Dependency Audit     │  │
│  │ (loop-init) │  │ (loop-init)  │  │ (loop-init)          │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬──────────┘  │
│         ▼                ▼                      ▼            │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: Session Execution (Session Orchestration)           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  /session → /go → 5 Waves with Gates → /close          │  │
│  │  Discovery → Impl-Core → Impl-Polish → Quality → Final │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         ▼                                    │
├──────────────────────────────────────────────────────────────┤
│  Layer 3: Delivery (Harness)                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  /harness-plan → User approves → /harness-work          │  │
│  │  → /harness-review → /harness-release                    │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         ▼                                    │
├──────────────────────────────────────────────────────────────┤
│  Layer 4: Verification (Cheat Detection)                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  swarm audit --mode gate → PR comment → Block/Aprove   │  │
│  │  8 core detectors → 3 experimental → AI-BOM             │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         ▼                                    │
├──────────────────────────────────────────────────────────────┤
│  Layer 5: Coordination (Fleet Bus)                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  PGMQ Bus → EXEC / UPDATE_REQUEST / ROLLBACK_REQUEST    │  │
│  │  Agent Registry → bus_access: host | client             │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  Layer 6: Observability (Langfuse + Cost + Scoring)          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Langfuse traces → Judge Scorer → Quality Watchdog      │  │
│  │  Cost tracking → Scoring Activity Watchdog              │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Detailed Requirements

### REQ-001: Unified Orchestration Pipeline

A single command flow that spans all layers:

```bash
# On the orchestrator:
orch trigger daily-triage --agents server-agent-1,server-agent-2
```

This triggers:

1. **Loop** triggers on schedule (e.g., daily-triage at 4am KST)
2. **Session** starts on the orchestrator (`/session triage`)
3. **Harness plan** generates spec (`/harness-plan`)
4. **Waves** execute, with inter-wave quality gates
5. **Cheat detection** runs on the resulting diff (`swarm audit`)
6. **Fleet dispatch** if agent work needed (`hc exec`)
7. **Results** stored in gbrain + reported via Langfuse + Telegram

**Acceptance:** A single `orch trigger` command starts the full pipeline and delivers a summarized result.

### REQ-002: Fleet-Aware Session Management

Sessions must know about the fleet:

- **Session config** includes `target_agents: [list]` — which agents this session involves
- **Wave routing** — some waves run on the orchestrator, others delegate to server agents
  - Discovery wave: orchestrator audits fleet state via bus
  - Implementation wave: delegates EXEC to server agents
  - Quality wave: runs tests on each affected agent
  - Finalization: orchestrator collects results
- **Resume across agents** — if the orchestrator crashes, the backup orchestrator can read STATE.md from the bus and resume

**Session state is shared** via the PGMQ bus so any orchestrator can resume:

```
STATE.md → archived to bus.lesson_learned on session close
Session records → stored in bus.sessions table (PGMQ)
```

**Acceptance:** A session with `target_agents: [joseph, gisu]` delegates implementation waves to those agents and collects results.

### REQ-003: Quality Gating with Cheat Detection Pipeline

Every delivery MUST pass through an automated quality pipeline:

```
Harness /harness-work output
  → Typecheck gate
  → Lint gate
  → Test gate
  → Cheat detection (swarm audit --mode advise)
  → Score gate (LLM judge scores traces)
  → If all pass → /harness-release
  → If any fail → /harness-review with findings
```

Cheat detection runs on EVERY diff, not just PRs. The harness wraps `swarm audit` into its release preflight:

```yaml
# harness-config.yaml
quality-gates:
  typecheck: true
  lint: true
  test: true
  cheat-detection: true        # runs swarm audit on the diff
  cheat-detection-mode: advise  # advise | gate (gate requires sandbox)
  llm-judge-score: 0.7         # minimum average score across traces
  llm-judge-min-samples: 3     # at least N traces scored
```

**Acceptance:** A diff with a known cheat pattern (e.g., error-swallow) is flagged by the harness preflight and blocks release.

### REQ-004: Cross-Agent Task Routing (Bus Integration)

The orchestrator uses the PGMQ bus to route wave work to server agents:

```
Orchestrator                Server Agent
    │                            │
    │── EXEC (wave-2: impl) ──▶  │
    │                            │── implement task
    │                            │── run tests
    │◀── EXEC_RESULT ────────────│
    │                            │
    │── EXEC (wave-4: quality) ▶ │
    │                            │── run quality checks
    │◀── EXEC_RESULT ────────────│
    │                            │
    │ Collect results → verify   │
    │ → continue to next wave    │
```

The wave executor on the orchestrator:

1. Checks agent registry for `bus_access: client` agents
2. Sends EXEC with task payload (script path, params, timeout)
3. Polls inbox for EXEC_RESULT with matching correlation_id
4. Validates result (exit code, stdout, evidence)
5. If success → continue to next step
6. If failure → retry or escalate

**Acceptance:** An orchestrator can delegate an implementation wave to a server agent via bus EXEC and receive verified results back.

### REQ-005: Observability at Every Layer

Each layer MUST produce structured observability data:

| Layer | Traces | Metrics | Artifacts |
|-------|--------|---------|-----------|
| Loop | Run start/end, items found, actions | Token cost, run duration | STATE.md, run-log |
| Session | Wave start/end, gate pass/fail | Waves completed, gates passed | spec.md, session record |
| Harness | Plan→work→review→release timing | Cycle time, review findings | Plans.md, review verdict |
| Cheat | Detector findings, gate mode verdict | Findings/PR, false positive rate | AI-BOM, audit report |
| Fleet | EXEC sent/received, agent health | Agent uptime, response time | EXEC_RESULT, health vector |
| Overall | **End-to-end trace per orchestration** | **Success rate, avg cycle time** | **Unified session report** |

The end-to-end trace links all layers via a single `correlation_id`:

```
orch:daily-triage-2026-07-23
  → loop:triage-run-42
    → session:wave-2-impl-core
      → exec:joseph-doctor-run
        → trace:langfuse-abc123
          → score:overall=8.5
```

**Acceptance:** A single orchestration run produces a unified trace in Langfuse linking all layers.

### REQ-006: Enterprise Compliance

| Requirement | Implementation |
|-------------|---------------|
| **Audit trail** | Every orchestration action logged to bus.audit_log with agent, action, timestamp |
| **AI-BOM** | Cheat detection emits CycloneDX ML-BOM per delivery |
| **Cost allocation** | Per-agent token costs tracked in cron-costs.db |
| **Role separation** | Orchestrator has bus_access:host, agents have bus_access:client |
| **Data retention** | Session records archived for 90 days; cost data for 1 year |
| **Failure isolation** | One agent's wave failure doesn't block other agents' work |

### REQ-007: Session Recovery and Redundancy

If the primary orchestrator fails mid-session:

1. STATE.md is persisted to the shared bus (bus.sessions table)
2. Backup orchestrator detects primary failure via health check timeout
3. Backup reads STATE.md from bus
4. Backup resumes from last completed wave
5. Wave in progress at time of failure is retried (idempotency via correlation_id)
6. Result: no loss of completed work, no skipped steps

**Acceptance:** Primary orchestrator crash mid-session → backup resumes from correct wave.

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-001 | Single `orch trigger` starts full pipeline across all layers | Run trigger → observe all layers in Langfuse trace |
| AC-002 | Session with target_agents delegates waves via bus EXEC | Check bus queues for EXEC messages with wave payloads |
| AC-003 | Cheat detection runs as harness preflight; blocks on finding | Inject cheat → harness preflight fails |
| AC-004 | All layers share a single correlation_id in Langfuse | Query Langfuse for correlation_id → N linked traces |
| AC-005 | Primary orchestrator crash → backup resumes correctly | Kill orchestrator → verify backup state |
| AC-006 | Cost per orchestration run is attributable by agent | Check cron-costs.db for run's correlation_id |
| AC-007 | AI-BOM is emitted per delivery | Check .swarm/aibom/ after release |

## Implementation Phases

### Phase 1 — Foundation (Weeks 1-3)
- Implement all 4 individual PRDs as standalone systems
- Loop engineering: state, budget, audit, cost
- Delivery harness: plan→work→review→release verbs
- Session orchestration: wave lifecycle with gates
- Cheat detection: 8 core detectors + advisory mode

### Phase 2 — Bus Integration (Weeks 4-6)
- Wave executor that delegates to agents via bus EXEC
- Session state persistence to shared bus
- Cross-agent resume (backup orchestrator)
- Fleet-aware session config (target_agents)

### Phase 3 — Pipeline Integration (Weeks 7-8)
- Orchestration trigger command (`orch trigger`)
- Cheat detection as harness preflight gate
- Quality gating pipeline (typecheck→lint→test→cheat→score)
- End-to-end correlation_id across all layers

### Phase 4 — Enterprise (Weeks 9-12)
- AI-BOM per delivery
- Cost allocation by agent and run
- Audit trail with retention policies
- Session recovery and redundancy
- Role-based access control

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Integration complexity overwhelms individual system quality | Medium | Phase 1 — build each system standalone first |
| Bus latency too high for wave synchronization | Low | Waves are sequential; latency tolerance is minutes |
| Cheat detection false positives block legitimate work | Low | Advisory mode default; gate mode requires explicit opt-in |
| Backup orchestrator state is stale | Medium | STATE.md syncs to bus after every wave; max staleness = 1 wave |
| Cost attribution is inaccurate | Medium | cron-costs.db uses estimated_cost_usd; reconcile weekly |

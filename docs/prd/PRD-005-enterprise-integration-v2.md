# PRD: Enterprise Agent Orchestration — Ecosystem Synthesis (v2)

> **PRD-005 v2 | Status: Draft | Date: 2026-07-23**
>
> Derived from research across 9 companion repos + 12 real-world production post-mortems

---

## 1. The Real Ecosystem Stack

The four repos form an **interlocking ecosystem**, not four independent projects. Each layer has a defined upstream and downstream:

```
memory-engineering → loop-engineering → harness-foundry → outerloop → fleet-engineering
   (persist)            (patterns)         (runtime)        (govern)     (population)
```

### Companion Repo Map

| Layer | Repo | npm Packge | Role | Maturity |
|-------|------|-----------|------|----------|
| **Memory** | [memory-engineering](https://github.com/cobusgreyling/memory-engineering) | `@cobusgreyling/memory-*` | Memory tiers, Memory Ready score M0-M3 | Patterns + CLI |
| **Loops** | [loop-engineering](https://github.com/cobusgreyling/loop-engineering) | `@cobusgreyling/loop-*` (9 packages) | Loop patterns, Loop Ready score, budget, context, worktree | Production |
| **Goals** | [goal-engineering](https://github.com/cobusgreyling/goal-engineering) | `@cobusgreyling/goal-*` | Run-until-done primitives (complements loops) | Production |
| **Runtime** | [harness-foundry](https://github.com/cobusgreyling/harness-foundry) | `@cobusgreyling/harness-foundry` | Composable harness, session traces | Alpha |
| **Governance** | [outerloop](https://github.com/cobusgreyling/outerloop) | `@cobusgreyling/outerloop` | Evidence → verdict → answerability | Alpha |
| **Fleet** | [fleet-engineering](https://github.com/cobusgreyling/fleet-engineering) | `@cobusgreyling/fleet-*` (4 packages) | Registry, identity, permissions, budgets, audit, F0-F3 | Patterns + CLI |
| **Delivery** | [harness](https://github.com/Chachamaru127/claude-code-harness) | Plugin | Spec-first plan→work→review→release | Production |
| **Session** | [session-orchestrator](https://github.com/Kanevry/session-orchestrator) | `session-orchestrator` | 5 waves, quality gates, crash recovery, learning | Production |
| **Cheat Detection** | [swarm-orchestrator](https://github.com/moonrunnerkc/swarm-orchestrator) | `swarm-orchestrator` | 11 detectors, gate mode, AI-BOM | Production |

### What I Missed in v1

| Missed Concept | Found In | Why It Matters |
|---------------|----------|----------------|
| **5 Fleet Concerns** | fleet-engineering | Topology, choreography, identity, economics, sovereign control — the complete governace model |
| **Accountability Test** | fleet-engineering | "Which agent, with what authority, against what task, evidenced by what?" — the single standard that separates fleets from populations |
| **Fleet Ready Score F0-F3** | fleet-engineering | Maturity model: F0=none, F1=registry+permissions, F2=inbox+budgets, F3=unattended+kill switch |
| **Fleet vs Frameworks** | fleet-engineering | Governance vs execution — frameworks (LangGraph/CrewAI) don't replace registry, inbox, or budget |
| **Evidence→Verdict→Answerability** | outerloop | Governance primitives: package evidence, issue verdict with rationale, reconstruct why a decision was made |
| **Run-until-done** | goal-engineering | Goals complement loops: loops discover work on a cadence, goals finish bounded tasks |
| **Dispatcher command** | session-orchestrator | Cross-repo dispatch to multiple agents — `/dispatcher` sends tasks to other repos/agents |
| **Wave orchestration with 5 roles** | session-orchestrator | Typed waves with inter-wave quality gates at confidence ≥80% |
| **Proof protocols (8)** | swarm-orchestrator | Execution-grounded: test-tamper, mock-mutation, no-op-fix, type-suppression, fake-refactor, dead-branch, claim-falsified, obligation-failure |
| **Benchmark methodology** | swarm-orchestrator | Oracle corpus (325 planted cheats), real-PR corpus (18 PRs, 5 repos), AB reports — every number reproduced from clone |

## 2. Real-World Failure Research (12 Sources)

### Top Production Failures

| # | Finding | Source | Impact |
|---|---------|--------|--------|
| 1 | **Context inconsistency is the #1 failure mode** — not pattern choice | Atlan, Jan 2026 | "Agent memory is transient; the shared context layer must be persistent" |
| 2 | **Flat architectures break at ~50 concurrent tasks** | ForgeWorkflows, May 2026 | Implicit data passing doesn't hold up — need typed handoff contracts |
| 3 | **70-85% of AI agent deployments fail to meet objectives** | McKinsey + LinkedIn analysis | Root causes: missing governance, no observability, security as afterthought |
| 4 | **Peer-collaboration failed in production** | NiteAgent, May 2026 | Only 3 patterns survived: supervisor/worker, agent-flow (sequential), bounded collaboration |
| 5 | **"The brain vs the spine"** | TryRunable, 2026 | Most failures are runtime/infrastructure (spine), not model reasoning (brain) |
| 6 | **Edge case retries cost 50× normal path** | ML Mastery via NiteAgent | One edge case can cascade through retries in multi-agent systems |
| 7 | **No output schema validation at handoffs** | Alice Labs, May 2026 | One agent's malformed output corrupts all downstream agents |
| 8 | **Governance must exist before deployment** | ForgeWorkflows | "Teams that skip governance frameworks don't hit 50 concurrent tasks" |

### What Surviving Deployments Have in Common

1. **Explicit handoff contracts** — schema-validated between every pair of agents
2. **Supervisor/worker topology** — not flat, not full P2P, not blackboard
3. **Observability from day one** — structured traces, not ad-hoc logging
4. **Progressive autonomy** — supervised first, then graduated to unattended
5. **Fault isolation** — one agent's failure doesn't cascade
6. **Budget controls per agent** — token caps, rate limits, admission control
7. **Human-in-the-loop at escalation points** — not for every action, but for high-risk ones

## 3. Enterprise Architecture (v2)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FLEET GOVERNANCE                             │
│              (fleet-engineering: registry + F0-F3)                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────────────┐   ┌───────────────────────────────────────┐  │
│  │  AGENT INBOX       │   │  ACCOUNTABILITY TEST                 │  │
│  │  (PGMQ bus)        │   │  "Which agent, with what authority,  │  │
│  │                    │   │   against what task, evidenced by    │  │
│  │  Orchestrator ◄──► │   │   what?"                             │  │
│  │  Server Agents      │   │                                      │  │
│  │  Dev Agents         │   └───────────────────────────────────────┘  │
│  └───────────────────┘                                              │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│               ORCHESTRATION PIPELINE (per task/run)                  │
│                                                                      │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ MEMORY  │  │ GOALS   │  │ SESSION  │  │ DELIVERY │  │ CHEAT  │  │
│  │ TIERS   │  │ (run-   │  │ WAVES    │  │ HARNESS  │  │ DETECT │  │
│  │ ─────── │  │  until- │  │ ──────── │  │ ──────── │  │ ────── │  │
│  │ Scratch │  │  done)   │  │ 1.Discov │  │ Plan     │  │ 8 core │  │
│  │ Episodic│  │         │  │ 2.Impl   │  │ Work     │  │ +3 exp │  │
│  │ Durable │  │ /goal   │  │ 3.Polish │  │ Review   │  │       │  │
│  │         │  │ /pause  │  │ 4.Quality│  │ Release  │  │ Gate   │  │
│  │ M0-M3   │  │ /resume │  │ 5.Final  │  │          │  │ AI-BOM │  │
│  └────┬────┘  └────┬────┘  └────┬─────┘  └────┬─────┘  └────┬───┘  │
│       │            │            │             │            │       │
│       └────────────┴────────────┴─────────────┴────────────┘       │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│          RUN-TIME LAYER (harness-foundry)                           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Primitives → Runtime → Session → Trace → Evidence          │  │
│  │                                                              │  │
│  │  foundry validate → foundry run → foundry sessions list     │  │
│  │  → foundry trace show → foundry evolve report                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│          GOVERNANCE LAYER (outerloop)                               │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Evidence Package → Human Verdict → Ledger → Answerability   │  │
│  │                                                              │  │
│  │  outerloop evidence package --run-id <id>                    │  │
│  │  outerloop verdict issue --decision ship/block --rationale   │  │
│  │  outerloop ledger why <evidence-id>                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 4. Detailed Requirements

### REQ-001: Agent Registry (fleet-engineering: F1)

Every agent in the fleet MUST be registered with:

```yaml
agent:
  id: agent-name               # Stable agent ID (not "the Slack bot")
  version: 1.2.0               # Version or config hash
  role: server-agent | orchestrator | dev-agent
  
  # Identity & Trust
  principal:                    # Service account (claw) vs end user (assistant)
    type: claw | assistant
    permissions: clone | run | edit
    tool_scope:                 # Which MCP servers, APIs, repos
  
  # Topology (5 Concern #1)
  topology: hierarchical | p2p | blackboard | router | market-based
  parent: orchestrator-name     # For hierarchical fleets
  
  # Choreography (5 Concern #2)  
  bus_access: host | client
  inbox: inbox_<agent-name>
  handoff_schemas:              # Typed, validated at boundaries
    - from: sender-agent
      schema: schema-v1
      validator: validate-handoff.sh
  
  # Economics (5 Concern #4)
  budget:
    daily_token_cap: 50000
    concurrent_runs: 1
    cost_center: team-a
  
  # Sovereign Control (5 Concern #5)
  autonomy_tier: F1 | F2 | F3   # F1=supervised, F3=unattended
  kill_switch: false
  allow_destructive_ops: false
  deny_paths:
    - src/auth/**
    - .env
    - infra/**
```

**Acceptance:** Every agent in the fleet has a complete registry entry with all five concerns addressed.

### REQ-002: Accountability Test (fleet-engineering)

Every orchestrated action MUST pass the four-clause test:

| Clause | Question | Implementation |
|--------|----------|---------------|
| **Which agent?** | Stable agent ID, version, instance | Agent registry + audit log |
| **With what authority?** | Principal, permission level, tool scope | Claw/assistant model + deny paths |
| **Against what task?** | User request, scheduled job, state item | correlation_id across all layers |
| **Evidenced by what?** | Structured trace, audit log, commit | outerloop evidence package |

**Acceptance:** A post-hoc reconstruction of any action resolves all four clauses.

### REQ-003: Fleet Ready Score (F0-F3)

| Level | Name | Requirements | Gates |
|-------|------|-------------|-------|
| **F0** | None | Agents exist | None |
| **F1** | Registry + Permissions | All agents registered. Permissions set. Bus routes defined. | `fleet-audit --level F1 --suggest` |
| **F2** | Shared Inbox + Budgets | Human-in-the-loop inbox. Per-agent budgets. Cost attribution. | `fleet-audit --level F2` |
| **F3** | Unattended + Kill Switch | F3 agents run without human. Kill switch works. Audit trail complete. | `fleet-audit --level F3` |

**Acceptance:** A fleet at F3 meets the Accountability Test for all F3-designated agents.

### REQ-004: Five Typed Waves with Quality Gates (session-orchestrator)

Every orchestrated task follows the wave pattern:

```
Wave 1: Discovery (read-only)    → Gate (audit findings)
Wave 2: Impl-Core                → Gate (architecture review)
Wave 3: Impl-Polish              → Gate (edge case review)
Wave 4: Quality                  → Gate (simplify → test)
Wave 5: Finalization             → Gate (verify → commit)
```

**Quality gates** between every wave check 8 dimensions at confidence ≥80%.

The implementer (Wave 2-3) and verifier (Wave 4-5) are DIFFERENT agents — maker/checker split enforced.

**Acceptance:** A task that fails a quality gate is blocked from progressing to the next wave.

### REQ-005: Cross-Agent Wave Routing (Bus Integration)

The orchestrator routes waves to appropriate agents:

| Wave | Where it runs | Mechanism | 
|------|--------------|-----------|
| Discovery | Orchestrator | Local session + bus audit of fleet state |
| Impl-Core | Target server agent(s) | Bus EXEC with script path + params |
| Impl-Polish | Target server agent(s) | Bus EXEC |
| Quality | ALL affected agents | Bus EXEC on each, collect results |
| Finalization | Orchestrator | Collect results, verify, commit |

**Handoff contracts:** Every bus EXEC carries a typed payload with expected output schema. Output validation runs at the orchestrator before the next wave proceeds.

**Acceptance:** An orchestrator can route an implementation wave to 3 server agents in parallel and aggregate the results.

### REQ-006: Cheat Detection Pipeline (swarm-orchestrator)

Every delivery MUST pass cheat detection before release:

```
/harness-work output
  → typecheck gate
  → lint gate  
  → test gate
  → cheat detection: swarm audit --mode advise
    → 8 core detectors (error-swallow, no-op-fix, fake-refactor, etc.)
    → if finding: block release, escalate to /harness-review
    → if clean: proceed
  → harneess-quality-scoring (LLM judge on traces)
  → /harness-release
```

For F3 (unattended) agents, `--mode gate` may block merges on self-certifying runtime proofs (8 proof protocols).

**Acceptance:** A PR with a deliberate error-swallow is blocked by the harness preflight.

### REQ-007: Evidence → Verdict → Answerability (outerloop)

Every completed run produces:

1. **Evidence Package:** What happened (traces, outputs, costs, findings)
2. **Human Verdict:** Ship or block, with **mandatory rationale** (why was this decision made?)
3. **Ledger Entry:** Immutable record linking evidence + verdict
4. **Answerability Chain:** Reconstructable "why" for any decision

```bash
outerloop evidence package --run-id 2026-07-23-daily-triage
outerloop verdict issue --evidence-id <id> --decision ship --rationale "All gates passed, no findings"
outerloop ledger why <evidence-id>
# → "Decision: ship. Rationale: All gates passed, no findings.
#    Traces: langfuse/abc123. Agent: moses@1.2.0. Task: daily-triage-2026-07-23"
```

**Acceptance:** A post-hoc query reconstructs who decided what, why, and with what evidence.

### REQ-008: Memory Tiers with Budget (memory-engineering)

| Tier | Lifetime | Trust | Examples | Budget Allocation |
|------|----------|-------|----------|-------------------|
| **Scratch** | This session | Low | Working notes, open questions | Unlimited (cleared on session end) |
| **Episodic** | Days-weeks | Medium | Session records, decisions, handoffs | 10% of total memory budget |
| **Durable facts** | Until revoked | High | Stack, owners, invariants, "never do X" | 20% of total memory budget |
| **Retrieved** | Per inference | Variable | Chunks pulled under budget | 70% for retrieval; hard cap on tokens |

Rules:
- Scratch is cheap to write, expensive to promote
- Durable facts need a human or verifier gate
- Retrieval without a budget is context spam
- Hygiene is a loop — memory rots

**Memory Ready Score (M0-M3):**
- M0: No persistent memory
- M1: Session scratchpad + episodic log
- M2: Durable facts store with verifier gate
- M3: Full tiered system with budget enforcement and hygiene loop

### REQ-009: Run-Until-Done / Goal Primitive (goal-engineering)

Goals complement loops:

```
Prompt = one turn, one answer
Loop   = recurring discovery + triage on a cadence
Goal   = run until done (or blocked / paused)
```

Use goals for bounded tasks with verifiable completion conditions:

```bash
/goal All tests pass
# Agent runs across turns until condition is met
/goal status    # check progress
/goal pause     # pause without clearing
/goal resume    # continue
/goal clear     # end goal mode
```

**Integration:** Loops CAN contain goals. A daily-triage loop might set a goal for one specific fix, then monitor its completion across runs.

### REQ-010: Context Consistency at Handoff Boundaries

Per research — context inconsistency is the #1 failure mode:

1. **Every agent handoff MUST have a typed schema**
2. **Output validation runs at the orchestrator before the next agent starts**
3. **Shared context is PERSISTENT (bus/Postgres), not transient (in-memory)**
4. **One agent's failure must NOT corrupt the shared context**
5. **Handoff schemas are versioned and contract-tested**

```yaml
handoff_schema:
  version: 1
  producer: wave-2-impl-core
  consumer: wave-3-impl-polish
  fields:
    - name: files_created
      type: string[]
      required: true
      validator: all_files_exist
    - name: test_results
      type: TestResult[]
      required: true
      validator: no_failures
    - name: known_issues
      type: Issue[]
      required: false
  error_on_unknown_fields: true  # strict mode
```

**Acceptance:** A handoff with schema violations is rejected before the next wave starts.

## 5. Maturity Model

### Level F1 — Registry + Supervision (Now)
- Agent registry with all 5 concerns
- Bus-based communication (PGMQ)
- Harness spec-first delivery
- Loop patterns (daily-triage, health-watchdog)
- Langfuse observability + judge scoring

### Level F2 — Inbox + Budgets (Next)
- Shared inbox with human-in-the-loop
- Per-agent token budgets + cost attribution
- Wave execution with quality gates
- Cheat detection (advisory mode)
- outerloop evidence packaging
- Memory tiers (episodic + durable)

### Level F3 — Unattended + Kill Switch (Future)
- F3 agents run without human supervision
- Cheat detection gate mode with execution-grounded proofs
- Goal-engineering run-until-done primitives
- Full Accountability Test at 4/4 for all F3 actions
- outerloop answerability chain
- Fleet-wide kill switch and rollback

## 6. Implementation Phases

### Phase 1 — Foundation (Weeks 1-4)
- Agent registry v1 (all 5 concerns)
- Bus-based orchestration (EXEC with typed payloads)
- Harness spec-first delivery pipeline
- Session quality gates (8 dimensions)
- 8 core cheat detectors (advisory mode)

### Phase 2 — Integration (Weeks 5-8)
- Cross-agent wave routing via bus
- Handoff schema validation
- Fleet Ready Score F1 certification
- Loop patterns (daily-triage, health-watchdog)
- outerloop evidence packaging

### Phase 3 — Governance (Weeks 9-12)
- outerloop verdict + answerability
- Per-agent budgets + cost attribution
- Shared inbox HITL
- Memory tiers with budget
- Fleet Ready Score F2 certification

### Phase 4 — Autonomy (Weeks 13-16)
- F3 unattened agent operation
- Cheat detection gate mode with execution-grounded proofs
- Goal-engineering run-until-done
- Fleet-wide kill switch + rollback
- Full Accountability Test at 4/4

## 7. Acceptance Criteria

| ID | Criterion | Verification Method |
|----|-----------|-------------------|
| AC-001 | Every fleet agent has a registry entry with all 5 concerns | `fleet-audit --level F1` |
| AC-002 | Post-hoc action reconstruction resolves all 4 Accountability clauses | Walk one action through the four clauses |
| AC-003 | A task passes through all 5 waves with quality gates between each | Run a task; verify wave transitions |
| AC-004 | Bus EXEC with typed payload reaches target agent and returns verified result | `hc exec` with schema validation |
| AC-005 | Cheat detection blocks a deliberate error-swallow in harness preflight | Inject cheat → release blocked |
| AC-006 | outerloop evidence→verdict→ledger→answerability chain is reconstructable | `outerloop ledger why <id>` |
| AC-007 | A goal runs until verifiable done condition is met | `/goal` with completion condition |
| AC-008 | Context inconsistency at handoff is caught by schema validation | Send malformed payload → rejected |
| AC-009 | A fleet at F3 meets Accountability Test at 4/4 for designated agents | Walk through all four clauses |
| AC-010 | Memory tiers respect budget caps | Exceed budget → retrieval blocked |

## 8. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Context inconsistency despite schema validation | Medium | Strict mode + error-on-unknown-fields + schema versioning |
| Peer-collaboration failure cascade | Medium | Supervisor/worker topology only; no unbounded P2P |
| Execution-grounded proof sandbox is too slow for CI | Medium | Timeout + advisory fallback; caching of dependencies |
| Evidence package volume exceeds storage | Low | Retention policy: 90 days, then summary-only |
| Agent identity spoofing in bus messages | Medium | Basic auth + correlation_id + audit log cross-check |
| F3 agent makes undetected bad decision | Low | Cheat detection + human review at escalation thresholds |
| Memory hygiene loop becomes a cost center itself | Medium | Budget enforcement applies to hygiene too; M3 requires it |

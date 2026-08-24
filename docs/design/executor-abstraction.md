# Executor Abstraction — Agent-Agnostic Execution Layer

**Date:** 2026-08-24 · **Author:** Esther · **Status:** Design v1
**Supersedes:** claude-worker-integration.md (ChatGPT review — obsolete)
**Core principle:** Hermes is **Executor Adapter #1** (reference implementation).
Claude is Adapter #2. The abstraction is defined by what Cortex expects from
any autonomous runtime — never around Hermes.

---

## 1. The three layers (agent identity ≠ agent runtime)

```
Cortex Agent        "Who am I?"
                    Moses / Esther / Titus / TitusClaude / Joseph …

Execution Profile   "What am I allowed/expected to do?"
                    orchestrator / coding / review / research
                    + capabilities + data tier + cost budget

Executor Adapter    "What software actually performs the work?"
                    HermesAdapter / ClaudeAdapter / CodexAdapter
```

**The key shift:** Moses is a Cortex *role*, not a synonym for Hermes. Moses
can run on Hermes today; a different role could run on Claude tomorrow.
Changing `primary_executor` must NOT change identity, permissions, memory,
bus routing, or governance.

```yaml
agent:
  id: titusclaude
  role: dev-agent

execution:
  primary_executor: claude
  fallback: [hermes]
  capabilities: [code.read, code.write, shell, tests, git]
  data_tier: projects        # R0.7 — never full/personal
  cost_budget_per_run: 2.00
```

## 2. The ExecutorAdapter contract

```python
class ExecutorAdapter(Protocol):
    def probe(self) -> ExecutorStatus: ...
    # ↑ capability card: available, healthy, models, cost profile, data tier

    def prepare(self, request: ExecutionRequest) -> PreparedExecution: ...
    # ↑ worktree/branch/context envelope — no side effects on shared state

    def execute(self, prepared: PreparedExecution) -> ExecutionHandle: ...
    # ↑ starts the run (async handle — streamable, cancellable)

    def status(self, handle: ExecutionHandle) -> ExecutionStatus: ...
    def cancel(self, handle: ExecutionHandle) -> None: ...
    def collect(self, handle: ExecutionHandle) -> ExecutionResult: ...
```

### ExecutionRequest (what Cortex sends)

```json
{
  "request_id": "uuid",
  "slice_id": "…",              // task-model-v3 slice
  "profile": "coding",
  "capabilities_required": ["code.read", "code.write", "tests", "git"],
  "data_tier": "projects",
  "context": {                  // built by Cortex, never the raw vault
    "plan": "…",                // slice plan (orchestrator-written)
    "vault_context": "…",       // vault_build_context output (budgeted)
    "constraints": ["do not modify unrelated files", "run tests"]
  },
  "model": "sonnet",            // adapter maps to its own model names
  "timeout_s": 1800,
  "cost_budget": 2.00
}
```

### ExecutionResult (what comes back — maps 1:1 to task-model-v3 verify)

```json
{
  "request_id": "uuid",
  "status": "success | failed | cancelled | timeout",
  "summary": "…",
  "files_changed": ["…"],
  "tests": {"command": "…", "passed": true},
  "git_diff_stat": "…",
  "evidence": "…",              // the report_done() evidence string
  "cost": {"tokens_in": 0, "tokens_out": 0, "usd": 0.0},
  "duration_s": 123,
  "needs_review": true
}
```

## 3. Governance — the critical improvement over the ChatGPT design

**ChatGPT's proposal has no governance, no PII tiers, no evidence contract.**
The fleet's whole safety model is loop-governance + evidence-based verify +
PII-never-bleeds. The adapter layer must NOT bypass any of it:

- **No `SKIP_SCORE`, no `--no-verify`, no bypass flags** — the adapter
  executes within the same governance rules as a Hermes agent.
- **PII boundary (R0.7)**: `data_tier` is enforced at the *Cortex* boundary
  (context builder), not trusted to the adapter. The executor receives a
  budgeted context envelope. Clarification (Luke 2026-08-24): this is a
  **tier filter, not a per-executor ban** — Claude (or any executor) with
  `data_tier: projects` gets the same project/learning brain context any
  agent gets (via `vault_build_context`); only the **personal tier**
  (people/, notes/ — R0.7 Esther-only) is filtered, and that applies to
  every agent except Esther, not to Claude specifically.
- **Evidence is mandatory**: `collect()` returns evidence; the orchestrator
  verifies (task-model-v3 `verify_slice`) before the work is accepted.
  **Never trust a self-reported done** — applies to Claude exactly as to
  Hermes.
- **Deterministic routing only** (Luke's O4 principle): the Execution
  Controller routes by capability table — never LLM-judged, never vibes.

## 4. The Execution Controller (router)

```
                  CORTEX CORE
                task / agent / policy
                       │
                       ▼
             EXECUTION CONTROLLER
                       │
              deterministic routing
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
 HermesAdapter    ClaudeAdapter   CodexAdapter
        │              │              │
        ▼              ▼              ▼
     Hermes        Claude Code      Codex
```

Routing rules (capability table, deny-by-default):

| Task shape | Default executor | Why |
|---|---|---|
| Trivial edit, lookup, shell | HermesAdapter | Native tools are cheapest & fastest |
| Multi-file refactor, arch reasoning | ClaudeAdapter | Deep-reasoning worker (V4 Pro via opus alias if verified) |
| Independent implementation/review | ClaudeAdapter / second adapter | Compete-mode light |
| Anything needing cronjob/bus/gateway | HermesAdapter only | Orchestrator capabilities are Hermes-native today |

The controller holds the **capability table** (adapter → capabilities →
cost profile) and answers "can this executor satisfy the request?" —
deterministic, testable, no LLM in the loop.

## 5. Adapter isolation — worktrees (unchanged, already documented)

```
repo/                     # main checkout (Cortex/Hermes)
└── .worktrees/
    └── <executor>-<slice>/   # adapter works here
```
- Controller creates: `git worktree add ../.worktrees/<exec>-<slice> -b agent/<exec>-<slice>`
- Adapter never touches the main checkout
- Accept → merge/cherry-pick; reject → `git worktree remove`

## 6. The regression invariant (the test that proves the abstraction)

> **If introducing the executor abstraction changes Hermes behavior, the
> abstraction layer is doing too much.**

Test: run the existing Hermes task flow (claim → execute → report → verify)
through `HermesAdapter` and assert byte-identical outcomes vs. today's direct
path. Green = the adapter is a pure wrapper. Then Claude plugs into the same
`ExecutionRequest`/`ExecutionResult` path — if Claude needs Cortex-specific
exceptions, the adapter boundary is wrong.

## 7. Rollout (3 steps, no Hermes behavior change until the last)

| Step | Build | Verify |
|---|---|---|
| **1. HermesAdapter** | Wrap existing Hermes task path behind the protocol (claim→execute→report→verify). Registry + capability table. | Regression invariant passes (identical behavior) |
| **2. ClaudeAdapter** | Same contract onto Claude Code: worktree + `claude -p` + structured result. titusclaude registers on bus with capability card. | One real refactor slice end-to-end; PII tier enforced |
| **3. Router + more** | Route by capability table; add Codex/OpenCode; Flash-implements/Pro-reviews escalation | Deterministic routing tested; no LLM in routing path |

**Step 1 is deliberately a no-op for behavior.** It proves the abstraction
before Claude touches anything.

## 8. What moves behind adapters (gradually)

Hermes-specific concepts that Cortex Core should NOT know:
- Hermes CLI flags (`hermes config set`, `hermes cron create`)
- Hermes sessions / tool schemas / process lifecycle

Cortex Core keeps (runtime-agnostic):
- identity (SOUL), policy (governance), task model, bus, brain, cost
- the **enforcer** — enforcement is Cortex policy, applies to ALL adapters

## 9. Open questions for Luke

1. **titusclaude registration**: separate bus agent (own `inbox_titusclaude`,
   capability card) vs. capability of titus's Hermes? — Recommend: separate
   bus agent; matches the abstraction and the task model.
2. **DeepSeek Claude-compat**: verify `claude` CLI → DeepSeek Anthropic
   endpoint honors sonnet→V4-Flash / opus→V4-Pro aliases (cost-critical).
3. **Where does the adapter layer live**: `hermes-cortex` as the Execution
   Controller repo (Cortex is becoming the control plane — Luke's earlier
   "this should be an orchestrator" direction) — confirm.
4. **Registry schema**: `executors.yaml` vs. bus capability cards — I
   recommend capability cards on the bus (already the agent-card pattern).

---

## 10. MCP executor layer — the pluggability mechanism (Luke 2026-08-24)

> "If we need to put more functionality in MCP to have pluggable
> executors/harnesses, please consider that. Better to 'over engineer' for
> future proofing than to have to redesign/refactor core tooling."

**The key realization: the fleet's core services are ALREADY MCP servers**
(agent-bus, loop-governance, tasks — verified in `~/.hermes/config.yaml`).
Any harness that speaks MCP (Claude Code, Codex, OpenCode) can connect to
them **today**. The executor abstraction is therefore a **fourth MCP
server**, not a new framework:

```
                    CORTEX CORE (MCP servers — runtime-agnostic)
   ┌───────────────┬───────────────┬───────────────┬────────────────┐
   ▼               ▼               ▼               ▼                ▼
agent-bus        loop-gov        tasks          executor        mycortex
(dispatch)      (policy)       (task model)    (CONTROLLER)    (vault/brain)
                                                    │
                                          deterministic routing
                                                    │
                              ┌─────────────────────┼──────────────────┐
                              ▼                     ▼                  ▼
                       HermesAdapter           ClaudeAdapter      CodexAdapter
                       (executor MCP)          (executor MCP)     (executor MCP)
                              │                     │                  │
                              ▼                     ▼                  ▼
                          Hermes               Claude Code           Codex
```

### 10.1 Why MCP is the right pluggability seam

- **MCP is the universal tool protocol** — every modern agent runtime
  (Hermes, Claude Code, Codex, OpenCode) speaks it as a client. One contract,
  every harness.
- **The fleet already proves it**: 3 MCP servers run today; Claude Code can
  be pointed at the same `agent-bus`/`tasks`/`loop-governance` servers with
  zero changes. The harness doesn't care what implements the server.
- **No new framework**: the ExecutorAdapter protocol (from §2) becomes the
  *tool surface* of one MCP server. Over-engineering here means: capability
  cards, registry, routing, and lifecycle are all first-class MCP tools —
  not buried in one agent's Python.

### 10.2 `executor` MCP server — tool surface

```python
server = Server("executor", on_list_tools=list_tools, on_call_tool=call_tool)
```

| Tool | Contract | Notes |
|---|---|---|
| `executor_list` | list registered executors + capability cards | registry read |
| `executor_probe` | health + model + cost profile of one executor | adapter `probe()` |
| `execution_request` | submit ExecutionRequest → handle | adapter `prepare()`+`execute()`; opens a governance cycle (no bypass) |
| `execution_status` | poll a running execution | adapter `status()` |
| `execution_cancel` | cancel a running execution | adapter `cancel()` |
| `execution_collect` | gather ExecutionResult + evidence | adapter `collect()`; feeds `report_done()`/`verify_slice()` |

**Every tool enforces Cortex policy at the server boundary** (same pattern
as the enforcer):
- `execution_request` with `data_tier: full` → refused for non-orchestrators
- no governance lock open → refused (begin_change first)
- evidence-less `execution_collect` → `needs_review: true` forced

### 10.3 Registry — capability cards (recommended: on the bus)

Each executor publishes a capability card (JSON) on the bus, same pattern as
agent cards:

```json
{
  "executor_id": "titusclaude",
  "type": "claude",
  "host": "<executor-host>",
  "models": ["sonnet", "opus"],
  "capabilities": ["code.read", "code.write", "shell", "tests", "git"],
  "data_tiers": ["none", "projects"],
  "cost_profile": {"sonnet": 0.05, "opus": 0.22},
  "health_endpoint": "http://<executor-host>:8911/health"
}
```

The controller caches cards; `executor_list`/`executor_probe` read them.

### 10.4 Adapters are MCP servers too (uniform contract)

- **HermesAdapter** = an executor-MCP server wrapping Hermes's native tools
  (terminal/file/tests) behind the ExecutionRequest/Result contract. The
  controller calls it exactly like it calls ClaudeAdapter.
- **ClaudeAdapter** = executor-MCP server wrapping `claude -p` (subprocess,
  worktree, env: DeepSeek Anthropic endpoint) behind the same contract.
- The controller never knows which is which — that's the point.

### 10.5 Over-engineering budget (what we build NOW so we never redesign)

| Build | Why now | Cost |
|---|---|---|
| `executor` MCP server (tool surface §10.2) | The seam — any harness plugs here; adding tools later is additive, never breaking | 1d |
| Capability-card registry (§10.3) | Deterministic routing needs machine-readable executor facts | 0.5d |
| Controller policy gate (§10.2) | PII tier + governance lock enforced ONCE at the boundary, all adapters | 0.5d |
| HermesAdapter (no-op wrapper) | Proves the abstraction + regression invariant before Claude exists | 1d |
| ClaudeAdapter | The first real second harness — proves runtime-independence | 1-2d |

**Explicitly deferred (additive, non-breaking later):** streaming progress
events, structured tool interception, session continuation, usage
accounting, richer lifecycle control — all are new MCP tools or new adapter
methods, never rewrites.

### 10.6 What does NOT go into MCP

- **The enforcer** — governance enforcement stays in the Cortex policy layer
  (it gates the `executor` server from outside; the server doesn't re-implement
  enforcement).
- **The brain/vault** — stays a separate MCP server (mycortex); the executor
  server *consumes* its context envelopes, never owns it.
- **Cron scheduling** — Hermes-native today; a future scheduler-MCP would be
  additive, not a replacement of this layer.

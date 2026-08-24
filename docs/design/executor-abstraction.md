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
  (context builder), not trusted to the adapter. ClaudeAdapter physically
  cannot see brain personal data — it only receives the budgeted context.
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

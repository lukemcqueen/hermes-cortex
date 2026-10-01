# Code Harness — Boring, Stable, Agentic

> Design + minimal working scaffold. Built from a deep read of
> [`earendil-works/pi`](https://github.com/earendil-works/pi) (agent loop, event
> model, protocol, tool contract, supply-chain discipline),
> [`Intrect-io/OpenSwarm`](https://github.com/Intrect-io/OpenSwarm) (TUI
> cockpit, atomic durable task store, admission control), and
> [Manus](https://manus.im) / `FoundationAgents/OpenManus` (plan-as-context,
> context-budget and harness optimizations — see
> [`docs/manus-openmanus-notes.md`](docs/manus-openmanus-notes.md)).

## The problem this solves

Pi upstream **explicitly permits breaking API changes in minor releases** and is
evolving fast. OpenSwarm is a large, beta-stage moving system. OpenManus is a
fast-moving demo. We don't want to inherit any of their release lifecycles. We
want a foundation that can sit unchanged for a year and keep working.

## The answer: a frozen runtime contract

Cortex defines reality. Everything else adapts to it. A three-year-old worker
must still be able to connect.

```
                CORE (this repo — versions extremely slowly)
        ┌───────────────────────────────────────────────┐
        │  Task state machine      Queue / leases        │
        │  Worker supervision      Workspace isolation   │
        │  Tool gateway            Governance             │
        │  Checkpoints             Retry / recovery       │
        │  Cost accounting         Audit log              │
        │  Observability contracts (event stream)         │
        └───────────────────────────────────────────────┘
                              │
                        Worker ABI v1
                              │
        ┌──────────────┬───────┴────────┬──────────────┐
        │   Pi worker  │  Claude Code   │  Manus-style │
        │   (pinned)   │   (pinned)     │   planner    │
        └──────────────┴────────────────┴──────────────┘
                     └─── disposable, replaceable ────┘
```

The core has **zero dependency** on Pi, Hermes, Claude Code, OpenSwarm, Manus,
Qwen, or any other coding agent. Those are peripheral drivers.

## What this scaffold proves

`src/` contains the four frozen pieces, small enough to read in one sitting:

| File | Purpose | Derived from |
|------|---------|--------------|
| `abi.ts` | Worker ABI v1 — the frozen vocabulary | ChatGPT's Cortex contract + Pi's `protocol.ts` versioning |
| `loop.ts` | The agent loop — llm → tool → append → repeat | Pi `agent-loop.ts` (simplified) |
| `store.ts` | Atomic durable task store + token lock | OpenSwarm `taskState/store.ts` |
| `adapter.ts` | LLM adapter interface + deterministic fake | Pi `ai` provider layering |

Run the proof:

```bash
bun test        # the loop executes a tool and completes, end-to-end
bun run src/main.ts --fake   # run a demo task against the fake model
```

## The frozen ABI (Worker ABI v1)

Deliberately tiny. Do not let it become a 300-method framework.

```ts
type Task = {
  task_id: string
  objective: string
  workspace: string
  permissions: string[]
  budget: { max_tokens: number; max_cost_usd: number; max_turns: number }
  model_policy: { provider: string; model: string; fallback?: string[] }
  verification_policy: { command?: string; require_evidence: boolean }
}
```

**Worker events** (worker → core): `WORKER_STARTED`, `MODEL_REQUEST_STARTED`,
`MODEL_REQUEST_FINISHED`, `TOOL_REQUESTED`, `TOOL_STARTED`, `TOOL_FINISHED`,
`PROGRESS`, `CHECKPOINT`, `RESULT`, `FAILED`, `STOPPED`.

**Worker operations** (core → worker): `start`, `send`, `cancel`,
`checkpoint`, `status`, `kill`.

The core's vocabulary is `task_id`, `attempt_id`, `worker_id`, `workspace_id`,
`checkpoint_id`, `lease_id`. It does **not** know what a "Pi session" or a
"Claude conversation" is.

## What we steal from Pi (and what we skip)

**Steal — the agent loop shape** (`agent-loop.ts`). The whole thing is one
`while` loop: stream assistant response → extract tool calls → execute →
append tool results → repeat. With steering/follow-up queues,
`shouldStopAfterTurn`, `prepareNextTurn`, `beforeToolCall`/`afterToolCall`
hooks. That is *the* value — and it's ~800 lines we can vendor, not reinvent.

**Steal — the event vocabulary** (`types.ts` `AgentEvent`): `agent_start/end`,
`turn_start/end`, `message_start/update/end`, `tool_execution_start/update/end`.
Small, clean, complete.

**Steal — the tool contract** (`types.ts` `AgentTool`): TypeBox schema
validation, `prepareArguments`, `execute`, `replay` policy (`"never" | "safe"`),
`executionMode` (`sequential`/`parallel`). This is how tools become boring.

**Steal — supply-chain discipline** (`README.md`): pinned exact deps,
`save-exact`, lockfile-as-ground-truth, shrinkwrap, `min-release-age`, reviewed
lifecycle-script allowlist. Pi is *already* a model of how to freeze deps.

**Steal — protocol versioning** (`protocol.ts`): `PROTOCOL_VERSION` constant,
`hello` handshake with version, TypeBox schemas with
`additionalProperties: false`. This is the ABI-discipline pattern.

**Skip** — chord (app-composition runtime), telemetry package, evals, the TUI
framework itself, server/client split. Too much surface.

## What we steal from OpenSwarm

**Steal — the TUI cockpit shape** (`src/tui/`): Ink/React tabs
(Chat / Pipeline / Logs / Monitor), `ContextBar` + `TabBar` + `HelpBar` chrome,
a `PipelinePanel` that subscribes to a daemon SSE stream and renders
`StageTimeline` + `SubagentTree` + `LiveLog`. That's the "supervise the swarm"
view we want — and its own `tui-plan.md`-style layout discipline.

**Steal — the atomic store** (`taskState/store.ts`): write + `fsync` + atomic
`rename`, a token-guarded lock file, zod validation of every read/write,
versioned schema. This is *the* pattern for a boring, crash-safe task store.
The comments are a masterclass in failure-mode thinking (torn files, stale
locks, ENOSPC).

**Steal — admission control** (`decisionEngine.ts` + `writeScope.ts`):
`fileScope` write boundaries, dependency-readiness gating, priority ranking.

**Skip** — Linear/Discord/LanceDB integration, the benchmark ladder, the
Codex/GPT provider specifics.

## What we steal from Manus / OpenManus

The one big idea: **the plan is the context.** Manus drafts a structured plan,
dispatches each step to a specialized sub-agent, and hands each worker only the
tracked plan status + its one step — never the whole transcript. The concrete
harness optimizations (all worker-layer, none touching `abi.ts`):

- `max_observe` — truncate every tool result before it enters context
- `max_steps` turn budget (already `budget.max_turns`)
- duplicate-turn ("stuck") detection → inject strategy-change signal
- token-limit → graceful terminal state, never a crash
- state machine with safe transitions (`state_context`)
- MCP as the runtime tool-extension boundary; sandbox as the execution boundary

The design test: a three-year-old worker can adopt Manus-style planning
**without a core change**. `abi.ts` never knew about sessions, and it stays
that way.

## Stability rules (the operational contract)

1. **No auto-updates. Pinned versions.** Workers are immutable images
   (`worker-pi:1.4.2`). An agent discovering a bug files `runtime_issue`; it
   does not mutate its own runtime.
2. **Maintenance fork, not innovation fork.** Security patches by default;
   bug fixes need regression tests; provider updates cherry-picked one at a
   time; new capability needs a concrete use case.
3. **Semver per component.** `core 1.x` never breaks. `worker-pi 1.9`,
   `worker-claude 1.4` version independently. A broken Pi worker never forces a
   core upgrade.
4. **Promotion is one-way.** `develop → soak → candidate → 30-day fleet →
   stable`. Stable gets security/data-loss/severity fixes only.
5. **Reproduce to the byte.** Lockfiles + container digests + pinned Node
   version. No `latest`, no rolling distro.

## Open decisions for Luke

1. **Language.** Both references are TypeScript; Node 22 + Bun are installed
   here. Recommend **TypeScript** (vendor Pi's loop directly). Go is the
   alternative if "zero runtime churn, single static binary" outweighs
   "reuse Pi verbatim".
2. **Naming.** Directory is `~/codeharness/` as a placeholder.
3. **First worker.** Recommend: (a) own tiny runtime first (this loop + real
   toolset), (b) frozen Pi worker as the first sophisticated implementation,
   (c) Claude Code adapter as premium specialist, (d) a Manus-style planner as
   a worker-layer concern. OpenSwarm/OpenHands only where their
   sandbox/workspace clearly wins.

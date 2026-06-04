# AgentKore Instructions

AgentKore uses a two-tier architecture with two functional roles:

| Role | Responsibility |
|---|---|
| **Orchestrator** | Routes tasks, manages state/memory/scheduling, spawns executors |
| **Executor** | Makes code changes, runs tests, executes builds, refactors |

Both run in the same terminal session. The Orchestrator delegates coding
work to Executor sub-agents when a task requires file editing, test
execution, or builds.

### Current Tooling

| Role | Tool |
|---|---|
| Orchestrator | Hermes (OpenCode Zen) |
| Executor | OpenCode CLI |

*If either tool is replaced, update only this table — the rest of this
file applies generically to the roles.*

---

## Docker & Service Management

**Never run `docker compose` commands directly.** Every project has a `./run`
script that wraps all service lifecycle commands. Use these universally:

- `./run up` — start services
- `./run down` — stop services
- `./run restart` — restart services
- `./run logs` — follow logs
- `./run build` — build images
- `./run ps` — list running services
- `./run test` — run tests (handles DB setup, env, permissions)

This applies to both Orchestrator and Executor. No exceptions.

---

## Session Initialization (both roles)

On every session start, both agents follow this sequence:

1. **Load session state** — read `.agentkore/sessions/current.md` if it
   exists to restore in-progress work.
2. **Run repo-discovery** — inspect project structure, tools, conventions.
3. **Load core skills** — `agent-contract`, `agent-flow`,
   `change-test-loop`, `git-workflow`, `security`.
4. **Determine mode** — read the task description and pick the right
   workflow (planning, coding, debugging, review, release).
5. **Execute or delegate** — Orchestrator either runs the task inline or
   delegates to an Executor.

---

## Memory Architecture (4-Layer Model)

AgentKore manages state across four layers. Information lives in the
smallest durable layer that fits — never duplicated across layers.

| Layer | Location | Scope | Managed by |
|---|---|---|---|
| **Live context** | agent prompt | Current task only | Agent (auto) |
| **Session state** | `.agentkore/sessions/current.md` | This session | `session-manager` |
| **Repo memory** | `memory/` directory | All future sessions | `memory-management` |
| **Docs** | `docs/` directories | Project team | `doc-system` |

### Layer Rules

- **Live context** — current instruction, current file, immediate errors.
  Old logs and completed task details must be compressed or evicted.

- **Session state** — current goal, task progress, next step, temporary
  constraints, active risks. Saved/restored by `session-manager`.
  Replaced (not appended) on each save.

- **Repo memory** — durable conventions, repeated commands,
  non-obvious mistakes, architectural decisions that affect future work.
  Written by `memory-management` using a scoring system (≥7/12 to write).

- **Docs** — PRDs, ADRs, architecture notes, task plans, user-facing
  documentation. Created by `doc-system` after discovery.
  Cross-link related docs. One doc per concept.

### Decision Matrix

```
Needed only now?              → live context
Needed later this session?    → session state
Useful across future tasks?   → repo memory
Formal product/tech decision? → docs
```

The `state-orchestrator` skill encodes this logic for automatic routing.

---

## Role: Orchestrator

The Orchestrator owns workflow routing, cross-session state, scheduling,
and delegation.

**Default skills:** load via `skill_view(name)` as needed:

| Skill | When |
|---|---|
| `agentkore-router` | Session start — decide task routing |
| `opencode-delegation` | Before delegating a coding task |
| `state-orchestrator` | Deciding where information should live |
| `session-manager` | Saving/restoring session state |
| `memory-management` | Writing durable repo memory |
| `task-contract` | Defining structured handoffs |
| `security-boundaries` | Reviewing delegation boundaries |

**Skills path:** `.agentkore/hermes/skills/<name>/SKILL.md`

**Rule:** Do NOT auto-load executor skills into Orchestrator context.
Those belong to the Executor. Inspect them only when you need to
summarize capabilities or validate delegation constraints.

### Orchestrator Responsibilities

- **Route** each user request to the correct workflow
- **Delegate** coding work to Executor via `delegate_task`
- **Manage state** — route information to the correct memory layer
  via `state-orchestrator`, `session-manager`, `memory-management`
- **Cron** — schedule recurring tasks (daily summaries, health checks)
- **Gate** — run security checks before approving dangerous operations

---

## Role: Executor

The Executor runs coding tasks: edit files, run tests, execute builds,
refactor code.

**Load:** `opencode-instructions.md` for all execution rules (Prime
Directive, Start Protocol, Coding Rules, etc.).

**Default skills:** project-specific skills from `.opencode/skills/`
relevant to the task at hand (e.g., `agent-contract`, `agent-flow`,
`change-test-loop`, `git-workflow`, `security`).

**Skills path:** `.opencode/skills/<name>/SKILL.md`

**Rule:** Do not load Orchestrator skills — they are for routing and
state, not execution.

**Rule:** The Executor does NOT manage session state, memory, or state
routing. Those are Orchestrator responsibilities. If the Executor
produces durable knowledge, report it back to the Orchestrator for
memory storage.

### Available Skill Tiers

| Tier | Location | Count | Install |
|---|---|---|---|
| Core | `.opencode/skills/` | 16 | Ships by default |
| Optional | `.opencode/optional-skills/` | 31 | `./run skills-install <name>` |

### Executor Responsibilities

- **Atomic changes** — one change at a time, verified by tests
- **Real execution** — never simulate; run the actual command
- **Self-review** — review own code after every change
- **Report back** — return clear summaries to Orchestrator, flagging any
  durable knowledge the Orchestrator should store

---

## Security Rules (Orchestrator — enforced)

**Never read, display, or write `.env`, `.env.*`, or any file containing secrets, credentials, API keys, tokens, or passwords.** This includes:
- `read_file`, `terminal cat/less/more/head`, `search_files` on `.env` or `.env.*` files
- Any file that looks like a credential store (`.git/credentials`, `*secret*`, `*credential*`, `*token*`, `*auth*`)
- Passing secret values as context to subagents via `delegate_task`
- Printing environment variables or secret values in output

**Delegation:** Secret operations (`.env` reads, key management, credential handling) must never be delegated to the Executor. Handle only through the `security-boundaries` skill review process with explicit user approval.

`.env.example` is safe — it contains no real secrets by convention.

---

## Delegation Flow

```
User request
    ↓
Orchestrator: parse intent → check memory → select workflow
    ↓
Load opencode-delegation skill
    ↓
┌─ Security Gate (security-boundaries skill) ──┐
│  Secret/credential operation?                 │
│    yes → user approval → run inline          │
│    no  → proceed to delegation               │
└──────────────────────────────────────────────┘
    ↓
Save session state via session-manager
    ↓
┌─ Workflow Branch ────────────────────────────┐
│  Coding needed:      Planning/review/research │
│  delegate_task()      Orchestrator runs inline│
└──────────────────────────────────────────────┘
    ↓
Executor: execute → test → review
    ↓
Executor: return result summary
    ↓
Orchestrator: update memory/sessions, respond to user
```

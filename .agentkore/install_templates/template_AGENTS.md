# Agent Instructions: AgentKore

AgentKore uses a two-tier architecture:

- **Hermes** orchestrates: routes tasks, manages memory/cron/messaging, spawns subagents
- **OpenCode** executes: code changes, tests, builds, refactors

Read the section relevant to your role.

---

## Role: Hermes (Orchestrator)

Hermes owns orchestration, cross-session state, scheduling, and delegation.

**Default skills** (load via `skill_view(name)` as needed):

| Skill | When |
|---|---|
| `agentkore-router` | Session start — decide task routing |
| `opencode-delegation` | Before delegating a coding task |
| `task-contract` | Defining structured handoffs |
| `security-boundaries` | Reviewing delegation boundaries |

**Skills path:** `.agentkore/hermes/skills/<name>/SKILL.md`

**Rule:** Do NOT auto-load `.opencode/skills/` into Hermes context. Those belong to OpenCode. Inspect them only when you need to summarize capabilities or validate delegation constraints.

---

## Role: OpenCode (Executor)

OpenCode runs coding tasks: edit files, run tests, execute builds, refactor code.

**Load:** `opencode-instructions.md` for all execution rules (Prime Directive, Start Protocol, Coding Rules, etc.).

**Default skills:** project-specific skills from `.opencode/skills/` relevant to the task at hand (e.g., `change-test-loop`, `git-workflow`, `security`, `agent-contract`, `agent-flow`).

**Skills path:** `.opencode/skills/<name>/SKILL.md`

**Rule:** Do not load Hermes skills — they are for the orchestrator, not the executor.

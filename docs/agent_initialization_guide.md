# Agent Initialization Guide

This document defines the mandatory initialization sequence for any agent
session. Every session must follow these steps in order.

## 1. Repository Discovery

Run `repo-discovery` to inspect the project structure before making any
assumptions. This identifies:

- Tech stack (languages, frameworks, package managers)
- Existing conventions (file layout, naming patterns)
- Security-sensitive areas (`.env` files, secrets, auth)
- Test infrastructure

## 2. Load Project Context

The agent must load project-level instructions:

| File | Role |
|---|---|
| `AGENTS.md` | Orchestrator instructions (Hermes) |
| `opencode-instructions.md` | Executor rules (OpenCode) |
| `opencode.json` | Permission model & skill config |

The agent automatically has its system prompt, `AGENTS.md`, and persistent
memory injected at session start.  `opencode-instructions.md` and
`opencode.json` are loaded as needed via `read_file`.

## 3. Load Session State

If `.agentkore/sessions/current.md` exists, read it to restore any
in-progress work, task list, or partial context.

## 4. Load Core Skills

The agent loads essential skills for the session:

| Skill | Purpose |
|---|---|
| `agent-contract` | Core execution contract (real work, verified results) |
| `agent-flow` | Workflow selection for the current task |
| `change-test-loop` | Small-change → test → verify loop |
| `git-workflow` | Safe git operations |
| `security` | Security rules for operations |
| `debugging` | Evidence-driven debugging |
| `testing-strategy` | Test selection (unit → integration → e2e) |
| `code-review` | Post-change review |

Additional skills are loaded on demand based on the task type.

## 5. Resume or Plan

- If `current.md` has an active task, resume it.
- If starting fresh, ask the user for the task goal, then run the
  appropriate workflow (`/plan`, `/debug`, etc.).

## Workflow Selection

The `agent-flow` skill reads the task description and picks the right flow.
Common patterns:

| Task Type | Flow |
|---|---|
| Simple code change | `change-test-loop` |
| New feature | `agent-flow` → `/plan` → task list → `task-executor` |
| Bug fix | `/debug` → root cause → fix → `change-test-loop` |
| Code review | `/review` |
| Pre-release | `/release-check` |
| UI change | `design-check` → `change-test-loop` |

## Failure Handling

- If a skill fails to load, check the skill exists in `.opencode/skills/`
  or install it with `./run skills-install <name>`.
- If config files are missing, run `./run deploy self` to restore them.
- If session state is corrupted, delete `.agentkore/sessions/current.md`
  and start fresh.

---

*Last updated: 2026-05-26*

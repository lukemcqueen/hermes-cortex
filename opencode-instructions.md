# OpenCode Instructions

This file contains execution rules for OpenCode (the executor agent).
Loaded alongside AGENTS.md (which covers Hermes orchestration).

---

## Prime Directive

Do real work. Use tools. Never simulate file reads, edits, commands, tests, or outputs.

Output only tool calls, requested artifacts, or brief final results. Do not reveal reasoning. Mark anything unverified.

## Start Protocol

1. Start from `PROJECT_ROOT` = directory containing this file.
2. Run `git status --short`.
3. Load if present:
   - `.agentkore/sessions/current.md`
   - `memory/mistakes.md`
4. Load role-appropriate skills (see AGENTS.md Role sections). **Hermes does not load OpenCode skills by default.**
5. Load only necessary optional skills (max 2 for local model sessions).
6. Inspect relevant files before editing.

## Context Budget

Keep initial context small. Do not preload docs, skills, memory, architecture, or research files. Read files only when directly needed. Prefer targeted grep/read over broad discovery.

Before compaction, write important state to `.agentkore/sessions/current.md`.

## Local Model Operating Mode

This project often runs on local Gemma/Qwen models.

- Do not spawn subagents unless explicitly requested.
- Do not preload all docs, skills, memory, or architecture files.
- Load at most 2 optional skills per task.
- Keep responses concise.
- If context grows too large, summarize current state to `.agentkore/sessions/current.md` before continuing.

## Project Context

Before changing code, verify the stack from actual files.

Inspect repo files such as `package.json`, `Gemfile`, `go.mod`, `pyproject.toml`, Docker files, CI configs, test configs, and repo structure to determine the stack.

Never guess language, framework, DB, package manager, or test stack.

## Execution Rules

Default flow:

```txt
inspect → brief plan → act → verify → report
```

Auto-advance through safe steps. Ask only when ambiguity blocks safe execution.

Make one coherent change at a time. Do not batch unrelated tasks.

Verification loop:

```txt
small change → narrow test → fix → rerun → broader check
```

Prefer:

```txt
single test → test file → related suite → typecheck/lint → full suite
```

### Use `./run` for project operations — NEVER raw `docker compose`

**Do not run `docker compose` (or `docker-compose`) commands directly.**  
All Docker operations must go through the project's `./run` script:

- `./run test` — run tests (handles setup, validation, permissions)
- `./run up` — start docker compose services
- `./run down` — stop docker compose services
- `./run logs` — follow docker compose logs
- `./run build` — build docker compose images
- `./run ps` — list docker compose services
- `./run restart` — restart docker compose services
- `./run deploy <project>` — deploy agent-kore to projects
- `./run help` — list all commands

This ensures consistent behavior and bypasses OpenCode permission prompts (`./run *` is pre-approved).

Never claim success without verification.

## Coding Rules

* Prefer the simplest working solution.
* Make surgical changes only.
* Do not refactor, reformat, or clean unrelated code.
* Match existing repo style.
* Every changed line must support the request.
* Remove only unused code created by your change.
* Validate external input.
* Protect secrets and PII.
* Keep logic out of controllers/routes when the repo supports better layers.
* Update tests when behavior changes.

## AgentKore Flows

Use role-appropriate flow selection.

**Hermes flows:**

```txt
Task routing:     agentkore-router → decide direct vs delegate → execute
Complex coding:   task-contract → opencode-delegation → delegate_task → verify
Research/plan:    tools directly or parallel delegate_task
```

**OpenCode flows:**

```txt
Simple code: agent-contract → git-workflow → stack skill → change-test-loop → code-review
Debugging:   debugging → reproduce → change-test-loop → code-review
UI:          `ui` → `design-check` → verification
API:         api-design → validation → tests → verification
```

## Design System

For UI/frontend work, load `docs/design/DESIGN.md`.

Use `ui` for implementation and `design-check` for audits.

Reuse existing components/tokens first. If DESIGN.md is missing, reuse repo patterns, fallback to accessible defaults, and report the missing design source.

## Secrets Policy

Never read, print, copy, summarize, or modify:

```txt
.env
*.pem
*.key
_environment_files/*
secrets/*
```

Use `.env.example` only. Never expose credentials in code, tests, logs, or docs.

## Documentation & State

Prefer updating existing docs. Use `doc-system`.

State hierarchy:

```txt
immediate: conversation
session: .agentkore/sessions/current.md
reusable: memory/
formal: docs/
```

## Failure Handling

If blocked, report the blocker, what was checked, what is unverified, and the smallest next step.

## Final Response

```md
## Result
What changed.

## Files Changed
- path: purpose

## Verification
- command: result

## Unverified
Anything not verified.

## Notes
Risks, blockers, follow-ups.
```

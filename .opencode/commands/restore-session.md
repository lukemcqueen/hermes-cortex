---
description: Initialize and restore AgentKore session state
---

Load skills:
- `state-orchestrator`
- `session-manager`
- `task-executor` if a task plan exists

1. Run `git status --short` to check repo state.
2. Read `AGENTS.md`, `.agentkore/sessions/current.md` if exists, `memory/mistakes.md` if exists.
3. Load baseline skills: `agent-contract`, `agent-flow`, `git-workflow`, `state-orchestrator`.
4. If session file exists, validate: files mentioned still exist, open tasks still relevant, tests/errors still reproducible, no newer instruction overrides snapshot.
5. Continue from the recorded next step. Make one change, then test.
6. Update `.agentkore/sessions/current.md` after progress.
7. Report: repo status, active session summary, immediate risks, recommended next workflow.

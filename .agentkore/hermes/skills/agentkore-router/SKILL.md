---
name: agentkore-router
description: Routes tasks to the right workflow — handle directly (Hermes) or delegate to OpenCode.
---

# AgentKore Router

## Role
Hermes owns orchestration. OpenCode owns execution. This skill routes tasks to the correct lane.

## Decision Matrix

| Task type | Handle directly (Hermes) | Delegate to OpenCode |
|---|---|---|
| Research, planning, analysis | ✓ | ✗ |
| Cross-session memory, cron, messaging | ✓ | ✗ |
| Skill authoring/maintenance | ✓ | ✗ |
| Multi-agent parallel work | ✓ (delegate_task) | ✗ |
| Simple file edits (<3 files) | ✓ | optional |
| Complex code changes (3+ files) | ✗ | ✓ |
| Large refactors | ✗ | ✓ |
| Test-heavy changes | ✗ | ✓ |
| Permission-gated build/test | ✗ | ✓ (./run * pre-approved) |

## When to load
- At session start (default)
- When the task involves code changes spanning multiple files
- When deciding whether to delegate or handle directly

## Workflow selection
Choose the smallest safe workflow:

```
Simple code (1-2 files):   tools directly
Complex code (3+ files):   opencode-delegation → delegate_task
Planning:                  task-contract → define scope → delegate
Research:                  tools directly or parallel delegate_task
Debugging:                 reproduce → opencode-delegation if complex
```

## Anti-patterns
- ❌ Loading OpenCode skills into Hermes context by default
- ❌ Delegating what can be done in 2 tool calls
- ❌ Bloating Hermes context with per-project coding rules

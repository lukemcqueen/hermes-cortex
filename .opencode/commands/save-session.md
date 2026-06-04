---
description: Save current AgentKore session state
---

Load skills:
- `state-orchestrator`
- `session-manager`

Write session snapshot to `.agentkore/sessions/current.md` with this format:

```md
# AgentKore Session Snapshot

## Timestamp
YYYY-MM-DD HH:MM

## Current Goal
Briefly describe what the user is trying to accomplish.

## Current Phase
Planning / Implementation / Debugging / Review / Testing / Handoff

## Completed Work
- Item 1

## Open Tasks
- [ ] Task 1

## Important Files
- `path/to/file` — why it matters

## Recent Decisions
- Decision 1

## Known Constraints
- Constraint 1

## Current Errors or Risks
- Error/risk 1

## Test Status
Last command: ...
Result: pass/fail/unknown

## Suggested Next Action
One clear next step.
```

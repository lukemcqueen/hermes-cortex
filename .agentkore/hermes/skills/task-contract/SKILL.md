---
name: task-contract
description: Handoff protocol between Hermes orchestrator and OpenCode executor.
---

# Task Contract

## Contract format

```
## Task: <title>
Scope:    What to do
Files:    Files to touch
Accept:   How to verify success
Constrain: Timing, model, permissions
Depends:  What must exist before starting
```

## Handoff protocol

```
1. Hermes defines the contract
2. Hermes delegates via delegate_task
3. OpenCode executes, returns summary
4. Hermes verifies independently (stat, readback, ./run test)
5. Hermes reports to user
```

## Acceptance criteria
- Tests pass (`./run test`)
- No regressions in unrelated files
- Style matches repo conventions
- Files exist with expected changes

## Anti-patterns
- ❌ Vague goals without acceptance criteria
- ❌ Trusting subagent claims without verification
- ❌ Delegating what Hermes can do in 1-2 calls
- ❌ Omitting constraints (timeout, model, permissions)
- ❌ Nested delegation (Hermes → OpenCode → OpenCode)

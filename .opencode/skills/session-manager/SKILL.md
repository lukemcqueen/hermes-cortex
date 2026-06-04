---
name: session-manager
description: |
  Manage session state, continuity, checkpoints, and context compression
  for long or complex workflows.

  Triggers when user mentions:
  - "save session"
  - "restore session"
  - "checkpoint"
  - "summarize progress"
  - "continue work"
---

# Session Manager

## Purpose
Maintain reliable context across long workflows by:
- saving progress
- restoring state
- compressing context
- tracking next steps

---

## Invocation

When invoked for session save/restore, also load `state-orchestrator`
to coordinate state routing before session operations.
When resuming work, also load `task-executor` if a task plan exists.

---

## Core Rule

Session state must be:
- concise
- accurate
- verifiable

Never rely on memory alone.

---

## Session File

Primary:

```txt
.agentkore/sessions/current.md
```

Archive:

```txt
.agentkore/sessions/archive/<timestamp>.md
```

---

## Save Session (STRICT)

Save when:

* user requests
* before large refactor
* before risky change
* long context sessions
* before ending work

---

## Save Format

```md
# Session State

## Goal
Current objective

## Progress
What is completed

## Current Task
What is being worked on

## Completed Tasks
- T1
- T2

## Remaining Tasks
- T3
- T4

## Key Files
- path: purpose

## Decisions
- important choices made

## Constraints
- technical/business limits

## Risks
- known issues

## Test Status
- passing/failing

## Next Step
Immediate next action
```

---

## Restore Session (STRICT)

On start:

1. Check if session file exists
2. Read it
3. Validate against repo:

   * files exist
   * tests still relevant
4. Continue from:
   → Next Step

---

## Context Compression

When context grows:

* summarize old steps
* keep:

  * current goal
  * active task
  * key constraints
* remove:

  * detailed history
  * logs
  * redundant info

---

## Update Rules

After each meaningful step:

* update:

  * progress
  * current task
  * next step
* keep file concise
* do not append endlessly → replace sections

---

## Safety Rules

* do not trust stale session blindly
* verify against repo state
* do not overwrite user progress
* avoid losing critical context

---

## Anti-Patterns

Avoid:

* storing full conversation
* keeping outdated tasks
* vague next steps
* duplicating session files
* never updating session

---

## Integration with AgentKore

```txt
prd-lite
→ prd-to-tasks
→ session-manager (save plan)
→ task-executor
→ session-manager (update progress)
→ change-test-loop
```

---

## Goal

Provide stable, minimal, and reliable context so smaller models can:

* continue work correctly
* avoid confusion
* execute long workflows safely

---
name: task-executor
description: |
  Execute ordered task plans using small verified changes, real tests,
  and progress tracking.

  Triggers when user mentions:
  - "execute task"
  - "next task"
  - "work through tasks"
  - "implement task plan"
  - "continue implementation"
---

# Task Executor

## Purpose
Execute one task at a time from a task plan.

---

## Invocation

Before executing a task, load `agent-contract` for the structured task
handoff and `change-test-loop` for the implementation loop.

Use with:
```txt
prd-lite → prd-to-tasks → task-executor → change-test-loop
```

---

## Inputs

* Task plan
* Current repo state
* Optional: selected task ID

---

## Output (STRICT)

```md
## Result
What was completed.

## Task executed
- T#: task name

## Files changed
- path: purpose

## Verification
- command: result

## Progress
- done:
- remaining:
- next:

## Notes
Risks, blockers, or follow-ups.
```

---

## Workflow (STRICT)

1. Start at `PROJECT_ROOT`
2. Run `git status`
3. Read current task plan
4. Select task:

   * user-specified task, OR
   * first unblocked incomplete task
5. Inspect relevant files
6. Execute ONLY that task
7. Use `change-test-loop`
8. Update progress if a task file/session file exists
9. Report result

---

## Task Selection Rules

Prefer tasks in this order:

1. Explicit user-selected task
2. First incomplete task with no blockers
3. Lowest-risk prerequisite task
4. Stop if dependencies are unclear

Do not skip required dependencies.

---

## Execution Rules

* One task per run
* One coherent change per task
* No unrelated cleanup
* Preserve existing behavior unless task requires change
* Verify before reporting success

---

## Verification Rules

Run the narrowest relevant check first.

Then, if successful, run broader checks when practical:

```txt
single test
→ test file
→ related suite
→ lint/typecheck
→ full suite
```

Never invent results.

---

## Failure Handling

If verification fails:

1. Read exact error
2. Fix only the cause
3. Re-run same command
4. Repeat until pass or blocked

Stop if:

* missing dependency/tool
* unclear requirement
* unsafe migration/data change
* repeated failure needs human decision

---

## Progress Tracking

If available, update one of:

```txt
.agentkore/sessions/current.md
docs/tasks/<feature-name>.md
docs/prd/<feature-name>.md
```

Mark task status as:

```txt
todo | in_progress | done | blocked
```

Do not create new tracking files unless requested or clearly needed.

---

## Safety Rules

* Check `git status` before edits
* Do not overwrite user changes
* Avoid destructive commands
* Ask before data loss or risky migrations
* Do not modify unrelated files

---

## Anti-Patterns

Avoid:

* executing multiple tasks at once
* skipping tests
* changing scope mid-task
* ignoring blockers
* editing files before inspection
* simulating command output
* reporting success without verification

---

## Goal

Complete tasks safely, incrementally, and verifiably so smaller models can execute complex projects without losing control.

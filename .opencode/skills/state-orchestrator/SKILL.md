---
name: state-orchestrator
description: |
  Decide what belongs in live context, session state, repo memory, or docs
  to reduce context bloat and preserve useful knowledge.

  Triggers when user mentions:
  - "state management"
  - "context bloat"
  - "save context"
  - "session or memory"
  - "continue work"
  - "orchestrate state"
---

# State Orchestrator

## Purpose
Control where information lives:

```txt
live context → current task only
session state → short-term continuity
repo memory → durable reusable knowledge
docs → product/architecture decisions
```

---

## Core Rule

Store information in the smallest durable place that fits.

Do not duplicate the same content across context, session, memory, and docs.

---

## State Types

### 1. Live Context

Use for:

* current instruction
* current file/task
* immediate errors
* active test output

Do not keep:

* old logs
* completed task details
* unrelated history

---

### 2. Session State

Use for:

* current goal
* task progress
* next step
* temporary constraints
* active risks

Location:

```txt
.agentkore/sessions/current.md
```

Use `session-manager`.

---

### 3. Repo Memory

Use for:

* durable repo conventions
* repeated commands
* non-obvious mistakes
* architectural decisions that affect future work

Location:

```txt
memory/
```

Use `memory-management`.

---

### 4. Docs

Use for:

* PRDs
* ADRs
* architecture notes
* task plans
* user-facing documentation

Location examples:

```txt
docs/prd/
docs/decisions/
docs/tasks/
docs/architecture/
```

Use `doc-system` before creating docs.

---

## Decision Matrix

```txt
Needed only now?              → live context
Needed later this session?    → session state
Useful across future tasks?   → repo memory
Formal product/tech decision? → docs
```

---

## Workflow (STRICT)

1. Identify information type
2. Choose destination:

   * context
   * session
   * memory
   * docs
3. Avoid duplication
4. Compress before storing
5. Verify stored info is accurate
6. Update existing file instead of creating duplicates

---

## Compression Rules

When saving state:

* keep facts, not chatter
* summarize logs
* preserve commands + results
* preserve decisions + reasons
* remove repeated history

Good:

```md
Tests: `go test ./...` failed in proxy parser due to missing required arg validation.
Next: add required-arg validation test, then implement fix.
```

Bad:

```md
Long copied terminal output...
```

---

## When to Use Each Skill

```txt
session-manager     → short-term continuation
memory-management   → durable repo learning
doc-system          → docs before creating/updating docs
prd-lite            → product requirements
prd-to-tasks        → implementation plan
```

---

## End-of-Task Check

Before final response:

1. Should session state be updated?
2. Did we learn durable repo knowledge?
3. Did docs need updating?
4. Is anything duplicated?
5. Is context now compressible?

---

## Anti-Patterns

Avoid:

* saving full conversations
* storing raw logs
* duplicating PRD content in memory
* putting temporary task progress in repo memory
* relying on stale session files
* creating docs without discovery
* keeping unnecessary history in prompt context

---

## Goal

Keep AgentKore accurate, lightweight, and continuous by placing information in the right state layer.
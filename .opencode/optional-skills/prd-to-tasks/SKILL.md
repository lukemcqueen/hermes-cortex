---
name: prd-to-tasks
description: |
  Convert a PRD into small, testable, execution-ready tasks with clear order,
  dependencies, and verification steps.

  Triggers when user mentions:
  - "break down prd"
  - "create tasks"
  - "implementation plan"
  - "story slicing"
  - "task list"
---

# PRD → Tasks

## Purpose
Transform a PRD into:
- small, executable tasks
- test-first steps
- safe implementation order

Optimized for:
- small models
- iterative execution (change-test-loop)

---

## Inputs

- PRD (preferred from `prd-lite`)
- Optional: constraints, tech stack, deadlines

---

## Output (STRICT)

```md
# Task Plan: <Feature>

## 1. Overview
Short summary of implementation approach

## 2. Task List (ORDERED)

### T1: <Task name>
- Type: setup | feature | refactor | test | migration
- Goal: what this task achieves
- Steps:
  1. ...
  2. ...
- Tests:
  - success:
  - failure:
  - edge:
- Depends on: T0 / none
- Risk: low | medium | high

(repeat for all tasks)

## 3. Execution Order

T1 → T2 → T3 ...

## 4. Parallel Work (if safe)

- T2, T3 can run in parallel

## 5. Verification Strategy

- narrow test per task
- full suite after milestones

## 6. Rollback Plan

- how to undo changes safely

## 7. Notes

- assumptions
- follow-ups
```

---

## Workflow (STRICT)

1. Read PRD fully
2. Identify:

   * core functionality
   * dependencies
   * risks
3. Split into smallest meaningful tasks:

   * each task ≤1 logical change
4. Ensure each task is:

   * testable
   * reversible
5. Order tasks by dependency
6. Add verification per task
7. Avoid over-fragmentation

---

## Task Design Rules

Each task must:

* be completable in one change-test-loop cycle
* have clear success criteria
* include tests (or verification step)
* avoid mixing unrelated concerns

---

## Task Types

Use consistent types:

* `setup` → config, scaffolding
* `feature` → new functionality
* `refactor` → internal improvement
* `test` → test coverage additions
* `migration` → data/schema changes

---

## Sizing Rules

Good task:

* 1 feature slice OR
* 1 refactor OR
* 1 migration step

Bad task:

* “build entire system”
* “refactor everything”
* vague multi-step work

---

## Dependency Rules

* Explicitly list dependencies
* Avoid hidden ordering
* Prefer linear flow unless parallel is safe

---

## Testing Rules

Every task must include:

* success case
* failure case
* edge case

If not possible:
→ include explicit verification command

---

## Risk Handling

Mark tasks as `high` risk if:

* data migration
* auth/security changes
* external API dependency
* performance-sensitive logic

Add extra verification steps for high-risk tasks.

---

## Anti-Patterns

Avoid:

* tasks without tests
* unclear task boundaries
* hidden dependencies
* overly large tasks
* mixing migration + feature + refactor
* skipping rollback considerations

---

## Integration with AgentKore

Execution flow:

```txt
prd-lite
→ prd-to-tasks
→ change-test-loop (per task)
```

Each task should be executed using:
→ small change → test → fix → repeat

---

## Goal

Produce **clear, ordered, testable tasks** that:

* can be executed step-by-step
* minimize risk
* work reliably with smaller models
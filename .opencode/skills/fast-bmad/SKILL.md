---
name: fast-bmad
description: |
  Ultra-light planning to convert a task into intent, constraints,
  smallest slice, files, and verification for immediate execution.

  Triggers when user mentions:
  - "fast plan"
  - "quick breakdown"
  - "smallest slice"
  - "what's the first step"
  - "bm ad"
---

# Fast BMAD

## Purpose
Create the **smallest executable plan** so work can start immediately.

Use when:
- task is small to medium
- requirements are mostly clear
- you want speed over full PRD

---

## Core Rule

If the first slice cannot be done in one loop, it is too big.

---

## Output (STRICT)

```md
## Fast BMAD

### Intent
What are we trying to do?

### User Value
Why does this matter?

### Constraints
Technical, business, or system limits

### Smallest Slice
One-sentence task that can be completed in one loop

### Files
- path: purpose

### Verification
- command/test:
- expected result:
```

---

## Workflow (STRICT)

1. Restate task clearly
2. Identify user value
3. Identify constraints
4. Reduce to smallest slice
5. Identify minimal files
6. Define verification

---

## Smallest Slice Rules

A valid slice:

* fits in one `change-test-loop`
* affects minimal files
* has clear success criteria
* is independently testable

Bad:

```txt
"Implement full auth system"
```

Good:

```txt
"Add user login endpoint returning 200 on valid credentials"
```

---

## When to Use

Use instead of:

* full PRD
* story-slicing
* multi-step planning

Use before:

```txt
task-executor
→ change-test-loop
```

---

## When NOT to Use

Do NOT use for:

* unclear requirements → use `ak-elicit`
* large features → use `prd-lite` + `story-slicing`
* architecture decisions → use `ak-party`

---

## Constraints Examples

* existing framework (Rails, FastAPI, etc.)
* database schema
* API contracts
* auth rules
* performance limits

---

## Verification Rules

Must include:

* exact command or test
* observable success result

Example:

```txt
command: pytest tests/test_login.py
expected: test passes
```

---

## Anti-Patterns

Avoid:

* vague slices
* multi-step tasks
* unclear verification
* listing too many files
* skipping constraints

---

## Integration with AgentKore

```txt
fast-bmad
→ task-executor
→ change-test-loop
→ code-review
```

---

## Goal

Enable fast, safe execution by reducing any task to a single,
clear, testable unit of work.

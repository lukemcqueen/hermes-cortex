---
name: memory-management
description: |
  Store only durable, high-value repo knowledge using strict scoring
  to avoid noise and improve long-term reuse.

  Triggers when user mentions:
  - "save memory"
  - "remember this"
  - "store pattern"
  - "lessons learned"
---

# Memory Management

## Purpose
Capture durable knowledge that improves future work.

Avoid clutter and noise.

---

## Core Rule

Store only if:
- reusable
- non-obvious
- impactful

---

## Memory Locations

```txt
memory/patterns.md
memory/decisions.md
memory/mistakes.md
memory/commands.md
memory/index.md
```

---

## Workflow (STRICT)

1. Ask:
   "Is this reusable and important?"
2. Score memory
3. Write only if score ≥ 7
4. Place in correct file

---

## What to Store

* repeated patterns
* architectural decisions
* tricky configs/commands
* common mistakes
* repo conventions
* debugging insights

---

## What NOT to Store

* temporary notes
* raw logs
* one-off bugs
* obvious facts
* sensitive data
* step-by-step task history

---

## Memory Scoring

```md
Durability (0-3): will this matter later?
Reuse (0-3): will it be used again?
Non-obviousness (0-3): is it hard to rediscover?
Risk if forgotten (0-3): impact if lost?

Total:
```

Write only if total ≥ 7.

---

## Entry Format

```md
## YYYY-MM-DD — <Title>

Category: pattern | decision | mistake | command
Score: X/12

Context:
What situation this applies to

Decision / Pattern / Command / Mistake:
Clear statement

Why it matters:
Impact on future work

Related:
- file paths
- docs
```

---

## Quality Rules

* keep entries concise
* avoid duplication
* update existing entries if similar
* prefer clarity over completeness

---

## End-of-Task Rule

At task completion:

1. Ask: "Did I learn something reusable?"
2. If yes → score it
3. If ≥7 → write memory
4. If not → skip

---

## Anti-Patterns

Avoid:

* over-saving
* vague entries
* storing everything
* mixing unrelated info
* saving without scoring

---

## Goal

Build a clean, high-value memory system that:

* improves future speed
* reduces repeated mistakes
* supports small-model efficiency
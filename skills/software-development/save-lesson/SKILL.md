---
name: save-lesson
description: |
  Auto-save a bug-fix lesson after resolving any non-trivial error.
  Builds a personal bug-fix memory that makes the agent smarter over time.
  Trigger: after fixing a bug, after resolving an error, after debugging.

  Lessons are markdown files in `~/brain/lessons/` (YAML frontmatter + Problem/
  Root Cause/Solution sections), mined automatically by the daily
  `daily-lesson-mine.sh` cron and indexed by mycortex.

  IMPORTANT: `offline_knowledge lesson create|search|index` does NOT exist —
  the `offline_knowledge` tool has only `bible` and `hymns` subcommands.
  Save lessons by writing the markdown file directly; search with grep or
  mycortex search. See "How to Create a Lesson" below.

  Use before attempting to debug: search lessons first to see if the fix is
  already known.
version: 1.0.0
author: Hermes Cortex
platforms: [linux, macos, windows]
related_skills: [offline-knowledge, offline-code-corpus]
---

# Save Lesson — Personal Bug-Fix Memory

## When to Save a Lesson

Save a lesson when:
- You fixed a bug that took >2 attempts or >30 seconds
- The root cause was non-obvious (not a simple typo)
- You searched the web or docs to find the fix
- The error message was cryptic or misleading
- You expect this pattern to recur in the future

Do NOT save a lesson for:
- Simple typos or syntax errors (you don't need a reminder)
- Trivial config mistakes you'd never make again
- Environment-specific issues that won't transfer

## How to Create a Lesson

After fixing a bug, write a markdown file directly to `~/brain/lessons/`
(the `offline_knowledge lesson` subcommand does NOT exist — do not use it):

```bash
# Filename convention: YYYY-MM-DD_<timestamp>_<hash>.md
LESSON="$HOME/brain/lessons/$(date +%F)_$(date +%H%M%S)_$RANDOM.md"
```

```markdown
---
title: "FastAPI 422 on Pydantic model with alias_generator"
created: "2026-09-08T10:00:00+00:00"
updated: "2026-09-08T10:00:00+00:00"
language: python
framework: fastapi
tags: [pydantic, validation, error-handling]
project: ""
success_count: 1
source: manual
---

## Problem

POST endpoint returning 422 on valid-looking body.

## Root Cause

Missing `populate_by_name=True` in model_config — aliases not populated by
field name.

## Solution

Add `ConfigDict(populate_by_name=True)` to the model's `model_config`.
```

### Field Guidelines

| Field | Required? | Guidance |
|-------|-----------|----------|
| `title` | Yes | Descriptive title others can grep for. Include error code if relevant. |
| `## Problem` | Yes | What went wrong from the user's perspective |
| `## Root Cause` | Yes | The root cause — not the symptom |
| `## Solution` | Yes | The fix — exactly what changed |
| `## Evidence` | Optional | Stack traces, error codes, repro steps |
| `language` / `framework` / `tags` | Recommended | Categorization for search |
| `success_count` | Yes | Start at 1; increment via `lesson-hit.sh` on each reuse |

## How to Search Before Debugging

Before spending significant effort on a new error, search existing lessons:

```bash
# Search by keyword across all lessons (grep the body, not just titles)
grep -rli "database is locked" ~/brain/lessons/

# Search titles only
grep -rl '^title:.*422' ~/brain/lessons/

# Read the match, then if the fix applies:
bash ~/.hermes-cortex/scripts/lesson-hit.sh --by-id "<basename>.md"   # increments success_count
```

### Agent Workflow

```
1. Receive error or bug report
2. grep -rli "<error keyword>" ~/brain/lessons/   (or mycortex search)
3. If a matching lesson found:
   a. Apply known fix from the lesson
   b. bash ~/.hermes-cortex/scripts/lesson-hit.sh --by-id "<basename>.md"
4. If no match:
   a. Debug and fix as normal
   b. After fix is verified, write a lesson file per the template above
   c. mycortex re-indexes automatically (~2 min)
```

## Example — Full Session

```text
# Agent encounters error
❌ sqlite3.OperationalError: database is locked

# Step 1: Search lessons
grep -rli "database is locked" ~/brain/lessons/
# Match found: "SQLite WAL checkpoint timeout during concurrent writes" (success_count: 1)
# Solution: set timeout=5000 on connection, use WAL mode

# Step 2: Apply fix
# ... (fix applied and verified)

# Step 3: Increment success count (proves the lesson was useful)
bash ~/.hermes-cortex/scripts/lesson-hit.sh --by-id "2026-07-22_20260713-102221-e19f923c.md"
```

## Auto-Save Hook (Recommended)

Add to your session workflow: after every bug fix, ask:
- "Was this non-trivial?"
- "Would I want to remember this?"
- If yes → write a lesson file per the template above (and run the daily miner keeps compounding automatically)

This builds the database passively with normal work.

## Related

- `offline-code-corpus` — curated code snippets (correct examples)
- `offline-knowledge` — general knowledge cascade
- `web-cache` — cached web results

## Absorbed Skills

- `skill-from-lesson` — Absorbed into this skill. The decision tree for promoting a lesson to a skill (or saving to memory instead), the "Be ACTIVE" attitude, and structured bug report handling (P0/P1/P2 triage) now live in this skill.

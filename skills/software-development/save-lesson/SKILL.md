---
name: save-lesson
description: |
  Auto-save a bug-fix lesson after resolving any non-trivial error.
  Builds a personal bug-fix memory that makes the agent smarter over time.
  Trigger: after fixing a bug, after resolving an error, after debugging.

  Run: offline_knowledge lesson create --title "..." ...
  Search: offline_knowledge lesson search "error message"

  Use before attempting to debug: search lessons first to see if the fix is already known.
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

After fixing a bug:

```bash
# Quick save with mandatory fields
offline_knowledge lesson create \
  --title "FastAPI 422 on Pydantic model with alias_generator" \
  --problem "POST endpoint returning 422 on valid-looking body" \
  --cause "missing populate_by_name=True in model_config" \
  --solution "Add ConfigDict(populate_by_name=True)" \
  --language python \
  --framework fastapi \
  --tags pydantic validation error-handling

# Interactive mode (prompts for all fields)
offline_knowledge lesson create --interactive
```

### Field Guidelines

| Field | Required? | Guidance |
|-------|-----------|----------|
| `--title` | Yes | Descriptive title others can search for. Include error code if relevant. |
| `--problem` | Yes | What went wrong from the user's perspective |
| `--cause` | Yes | The root cause — not the symptom |
| `--solution` | Yes | The fix — exactly what changed |
| `--evidence` | No | Supporting details: stack traces, error codes, steps to reproduce |
| `--language` | Recommended | Programming language |
| `--framework` | Recommended | Framework / library (fastapi, react, django, etc.) |
| `--tags` | Recommended | Categorization tags (validation, auth, database, etc.) |
| `--project` | No | Project name |

## How to Search Before Debugging

Before spending significant effort on a new error, search the lesson database:

```bash
# Search by error message or description
offline_knowledge lesson search "422 Validation Error"

# Search with filters
offline_knowledge lesson search "database timeout" --language python --tag postgres

# Check if the exact error has been seen before
offline_knowledge lesson search "sqlite database is locked"
```

### Agent Workflow

```
1. Receive error or bug report
2. Run: offline_knowledge lesson search "<error message>"
3. If match found (similarity ≥ 0.55):
   a. Apply known fix from the lesson
   b. Increment success_count by editing the lesson file's frontmatter
4. If no match:
   a. Debug and fix as normal
   b. After fix is verified, create a lesson
   c. Run: offline_knowledge lesson index (to make it searchable)
```

## Index Management

After creating lessons, rebuild the embedding index so new lessons are searchable:

```bash
# After every batch of new lessons
offline_knowledge lesson index
```

The index is also automatically rebuilt by mycortex's sync daemon within 2 minutes,
but for immediate searchability after creating lessons in the same session, run index manually.

## Example — Full Session

```bash
# Agent encounters error
❌ sqlite3.OperationalError: database is locked

# Step 1: Search lessons
offline_knowledge lesson search "sqlite database locked"

# Match found: "SQLite WAL checkpoint timeout during concurrent writes"
# Similarity: 0.72
# Solution: set timeout=5000 on connection, use WAL mode

# Step 2: Apply fix
# ... (fix applied)

# Step 3: Increment success count
# Edit the lesson file's frontmatter: success_count: 2 (was 1)
```

## Auto-Save Hook (Recommended)

Add to your session workflow: after every bug fix, ask:
- "Was this non-trivial?"
- "Would I want to remember this?"
- If yes → `offline_knowledge lesson create ...`

This builds the database passively with normal work.

## Related

- `offline-code-corpus` — curated code snippets (correct examples)
- `offline-knowledge` — general knowledge cascade
- `web-cache` — cached web results

## Absorbed Skills

- `skill-from-lesson` — Absorbed into this skill. The decision tree for promoting a lesson to a skill (or saving to memory instead), the "Be ACTIVE" attitude, and structured bug report handling (P0/P1/P2 triage) now live in this skill.

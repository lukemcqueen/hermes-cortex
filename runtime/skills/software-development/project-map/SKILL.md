---
name: project-map
description: |
  Structural project analysis — build a dependency graph so agents
  don't guess which files a change affects.
  Trigger: before multi-file changes, entering a new project, code review.

  Run: project-map analyze
  Read: .hermes-cortex/project-map.json
version: 1.0.0
author: Hermes Cortex
platforms: [linux, macos, windows]
related_skills: [save-lesson, agent-contract]
---

# Project Map — Structural Project Analysis

## When to Use

Run `project-map analyze` when:
- You enter a new project for the first time
- You're about to make a change that touches multiple files
- You're debugging and need to understand the dependency graph
- You want to verify your mental model of the project structure

## Quick Start

```bash
# Full analysis (auto-detects project root)
project-map analyze

# Quick stats without full analysis
project-map stats

# View cached map
project-map status
```

## Output

The analysis writes to `.hermes-cortex/project-map.json`:

| Section | Content |
|---------|---------|
| `stats` | Files, lines, languages, module/test/route counts |
| `routes` | All detected API routes with file, function, and URL |
| `models` | Detected data models (Pydantic, Django, SQLAlchemy) with fields |
| `entry_points` | Main entry points (main.py, app.py, install.sh, etc.) |
| `modules` | Every file with its imports and exported functions/classes |
| `dependency_graph` | File → imports mapping |
| `reverse_dep_graph` | File → imported by mapping |
| `framework` | Detected frameworks (FastAPI, Flask, React, etc.) |

## Agent Workflow

```
1. Enter project or start new task
2. Check: does .hermes-cortex/project-map.json exist?
   a. If no → run: project-map analyze
   b. If yes → run: project-map status
3. Before multi-file changes, check dependency_graph for impacted files
4. After significant structural changes, re-run: project-map analyze
```

## Example

```bash
$ project-map status

📁 Project:  hermes-cortex
   Files:    576 (103115 lines)
   Routes:   9
   Models:   0
   Tests:    1
   Entry:    1 point(s)
   Framework: fastapi

   🛣️  Routes:
      src/dashboard/server.py:api_health → /api/health
      src/dashboard/server.py:api_langfuse → /api/langfuse

📐 Models:
      src/app/models.py:User (12 fields)
      src/app/models.py:Item (8 fields)
```

## Related

- `save-lesson` — personal bug-fix memory (complementary: map tells you WHERE, lesson tells you HOW)
- `offline-code-corpus` — curated code snippets for generation
- `agent-contract` — reminds you to inspect before acting (project-map is how you inspect)

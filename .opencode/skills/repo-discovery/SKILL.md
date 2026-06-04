---
name: repo-discovery
description: |
  Inspect and understand a codebase before making changes by identifying
  structure, tools, patterns, and constraints.

  Triggers when user mentions:
  - "explore repo"
  - "understand project"
  - "new codebase"
  - "before coding"
---

# Repo Discovery

## Purpose
Understand the repo before making changes.

Avoid breaking conventions or architecture.

---

## Workflow (STRICT)

1. List structure
2. Identify stack
3. Find entry points
4. Locate tests
5. Detect patterns
6. Summarize findings

---

## Commands

```bash
ls
find . -maxdepth 2 -type f | sort | sed 's#^./##' | head -200
git status --short
```

---

## What to Look For

### Project Basics

* README
* package.json / pyproject.toml / go.mod / Gemfile
* environment setup
* scripts/commands

---

### Structure

Identify:

* app/src directory
* routes/controllers
* services/business logic
* components/UI
* database/migrations

---

### Testing

Find:

* test framework
* test locations
* how to run tests
* test coverage patterns

---

### Build / Tooling

Look for:

* linting tools
* type checking
* build commands
* CI configs

---

### Patterns

Detect:

* naming conventions
* folder structure
* architecture style
* shared utilities

---

## Rules

* Prefer existing patterns over new ones
* Do not introduce new frameworks without need
* Match code style exactly
* Avoid assumptions

---

## Output (STRICT)

```md
## Repo Summary

### Stack
- language:
- framework:
- tools:

### Structure
- key folders:

### Entry Points
- ...

### Testing
- ...

### Patterns
- ...

### Risks / Unknowns
- ...

### Recommended Next Step
- ...
```

---

## Anti-Patterns

Avoid:

* coding before understanding
* ignoring existing structure
* introducing new patterns prematurely
* assuming conventions

---

## Goal

Understand the repo enough to make safe, consistent changes.
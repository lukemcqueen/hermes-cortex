---
name: session-start-discipline
version: 1.1.0
category: devops
description: "Restore cross-session todos, enforce skill-loading discipline at session start"
platforms: [linux, macos]
related_skills:
  - todo-persistence
  - task-start
  - agent-flow
  - change-checklist
---

## Session Start — Mandatory Skill Loading

**You must never `touch ~/.hermes-cortex/state/.skills-loaded`.** The enforcer
auto-creates this marker when all 9 always-section skills have been loaded
via actual `skill_view()` calls. A bare `touch` creates an empty file that
fails content verification — blocking you until you load the real skills.

## Sequence

Load all 9 always-section skills in this order. The marker follows automatically:

1. `skill_view('task-start')` — bundles the complete pre-task sequence
2. `skill_view('session-start-discipline')` — **this skill** — restore pending todos after always-skills load
3. `skill_view('agent-flow')` — workflow router
4. `skill_view('reasoning-patterns')` — reasoning mode selection
5. `skill_view('reflexion-check')` — self-critique before delivery
6. `skill_view('change-checklist')` — pre-ship verification
7. `skill_view('survey-before-action')` — check existing resources first
8. `skill_view('cortex-preflight')` — repo-specific pre-flight checks
9. `skill_view('agent-contract')` — non-negotiable execution rules

Then restore any pending cross-session todos:

10. `~/.hermes-cortex/scripts/todo-db.py pending` — query DB for pending items
11. If items exist, `todo(todos=<json_items>, merge=true)` — restore to in-memory list

Then proceed to `begin_change()`. The marker is self-verifying — it contains
your session ID, not just a file existence flag.

## Enforcement

- The enforcer blocks ALL write tools without the marker
- **Do NOT touch the marker file** — it will be rejected    
- Load the skills instead; the marker follows

## Self-Verification

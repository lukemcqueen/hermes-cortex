---
name: session-start-discipline
version: 2.0.0
category: devops
description: "DEPRECATED alias — merged into task-start (2026-08-20). Load task-start instead; it bundles skill-loading discipline, marker mechanics, and todo restore."
platforms: [linux, macos]
related_skills:
  - task-start
  - agent-flow
  - change-checklist
---

# DEPRECATED — use `task-start`

This skill was merged into `task-start` on 2026-08-20. **Do not follow the
old 9-skill sequence** — the always-section is now 7 skills and todo
restore uses `~/.hermes-cortex/scripts/task-db.py pending` (there is no
`todo-db.py`).

## What to do instead

1. `skill_view('task-start')` — bundles the complete pre-task sequence:
   cache_search → begin_change → load all 7 always-section skills →
   classify (agent-flow) → restore todos via `task-db.py pending` →
   survey → work.
2. Marker mechanics (never `touch` the per-session marker at
   `~/.hermes-cortex/state/skills-loaded/<session-id>`; a serial extra
   `skill_view()` re-triggers auto-create if writes are blocked) are
   documented in task-start under "Marker mechanics" and
   "Known Gaps & Recovery".

Historical references: `references/recovery-from-violation.md`,
`references/subagent-dispatch-workaround.md`,
`references/stale-governance-lock-files.md` (still valid;
task-start also links recovery-from-violation.md).

## Session Start — Mandatory Skill Loading

**You must never `touch ~/.hermes-cortex/state/.skills-loaded`.** The enforcer
auto-creates this marker when all 8 always-section skills have been loaded
via actual `skill_view()` calls. A bare `touch` creates an empty file that
fails content verification — blocking you until you load the real skills.

## Sequence

Load all 8 always-section skills. The marker follows automatically:

1. `skill_view('task-start')` — bundles the complete pre-task sequence
2. `skill_view('agent-flow')` — workflow router
3. `skill_view('reasoning-patterns')` — reasoning mode selection
4. `skill_view('reflexion-check')` — self-critique before delivery
5. `skill_view('change-checklist')` — pre-ship verification
6. `skill_view('survey-before-action')` — check existing resources first
7. `skill_view('cortex-preflight')` — repo-specific pre-flight checks
8. `skill_view('agent-contract')` — non-negotiable execution rules

Then restore any pending cross-session todos:

9. `~/.hermes-cortex/scripts/todo-db.py pending` — query DB for pending items
10. If items exist, `todo(todos=<json_items>, merge=true)` — restore to in-memory list

Then proceed to `begin_change()`. The marker is self-verifying — it contains
your session ID, not just a file existence flag.

## Enforcement

- The enforcer blocks ALL write tools without the marker
- **Do NOT touch the marker file** — it will be rejected    
- Load the skills instead; the marker follows

## Self-Verification
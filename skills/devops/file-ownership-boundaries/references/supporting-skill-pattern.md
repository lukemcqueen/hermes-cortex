# Supporting Skill Pattern — Concrete Examples

## What Is a Supporting Skill?

When a Hermes default skill is missing functionality we need, **we do not edit the default** — we create a supporting skill in our repo. This keeps our changes safe from Hermes updates and gives us full control.

## Naming Convention

`cortex-<domain>` supplements Hermes `<domain>`:

| Hermes default | Our supporting skill | Purpose |
|----------------|---------------------|---------|
| `survey-before-action` | `cortex-preflight` | Adds repo-specific checks (git search, Hermes boundary, deployment verification) |
| *(future)* | *(to be created)* | |

## Pattern Steps

1. Identify the Hermes default skill that's missing a check you need
2. **Do NOT edit it** — it's read-only
3. Create a new skill in `~/hermes-cortex/skills/<category>/cortex-<domain>/SKILL.md`
4. Set `author: Moses (Hermes Cortex)` in the frontmatter
5. Add the Hermes default to your skill's `related_skills` field
6. Document in `cortex-preflight` or create a new `cortex-*` skill
7. Ensure the skill's SKILL.md has a "When to load" section explaining where it fits in the task sequence
8. Deploy via `cortex-update.sh`

## When to Load Supporting Skills

In the task-start sequence, supporting skills load after their Hermes counterpart:

```
skill_view('task-start')
  → skill_view('<hermes-default>')     # Step in task-start
  → skill_view('cortex-<domain>')      # Our supplement — loaded right after
  → begin work
```

## Example: cortex-preflight

Created to supplement `survey-before-action`. Adds:
- Check git for files committed but not deployed
- Hermes boundary check (file ownership table)
- Deployed copy verification
- Agent type awareness
- Stale deploy reference detection
- Cross-agent impact check

## Example: todo-persistence

Created to supplement `session-manager` and `task-start`. Adds:
- DB-backed todo persistence (bus.todos)
- Session start/end protocol
- Fleet-visible todo management
- todo-db.py CLI

## Pitfalls

- ❌ Naming a supporting skill after the session artifact (e.g. `fix-auth-todos`) — name at the domain level
- ❌ Creating a supporting skill for something that already exists in the repo — check first
- ❌ Forgetting to add a "When to load" section — agents won't know where to insert it
- ❌ Not deploying via cortex-update.sh — other agents can't use it

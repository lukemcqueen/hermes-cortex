# Supporting Skill Pattern — Concrete Examples

## What Is a Supporting Skill?

When a Hermes default skill is missing functionality we need, **we do not edit the default** — we create a supporting skill in our repo. This keeps our changes safe from Hermes updates and gives us full control.

## Naming Convention

`cortex-<domain>` supplements Hermes `<domain>`:

| Hermes default | Our supporting skill | Purpose |
|----------------|---------------------|---------|
| `survey-before-action` | *(merged in 2026-08-20 — see note)* | Repo-specific checks (git search, Hermes boundary, deployment verification) were folded INTO survey-before-action; new supporting skills use a descriptive `cortex-*` name |
| *(future)* | *(to be created)* | |

> **Note (2026-08-20):** `cortex-preflight` was merged into `survey-before-action`
> during the always-skill consolidation (10 → 7). The pattern below still
> applies to NEW supporting skills — the merge was a dedup of an existing
> supplement, not a repeal of the pattern. See
> `survey-before-action` → "Repo-Specific Pre-Flight" section.

## Pattern Steps

1. Identify the Hermes default skill that's missing a check you need
2. **Do NOT edit it** — it's read-only
3. Create a new skill in `~/hermes-cortex/skills/<category>/cortex-<domain>/SKILL.md`
4. Set `author: Moses (Hermes Cortex)` in the frontmatter
5. Add the Hermes default to your skill's `related_skills` field
6. Document the new skill in its own SKILL.md — or, if the supplement is small and tightly coupled to an always-skill, propose folding it into that skill during the next curation pass
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

## Example: task-persistence

Created to supplement `session-manager` and `task-start`. Adds:
- DB-backed task persistence (tasks schema)
- Session start/end protocol
- Fleet-visible todo management
- task-db.py CLI

## Historical example: cortex-preflight (merged 2026-08-20)

Created to supplement `survey-before-action`. Added:
- Check git for files committed but not deployed
- Hermes boundary check (file ownership table)
- Deployed copy verification
- Agent type awareness
- Stale deploy reference detection
- Cross-agent impact check

All six checks now live inside `survey-before-action` under
"Repo-Specific Pre-Flight (formerly cortex-preflight, merged 2026-08-20)".
The skill dir was deleted; `aliases: [cortex-preflight]` keeps old
references resolving.

## Pitfalls

- ❌ Naming a supporting skill after the session artifact (e.g. `fix-auth-todos`) — name at the domain level
- ❌ Creating a supporting skill for something that already exists in the repo — check first
- ❌ Forgetting to add a "When to load" section — agents won't know where to insert it
- ❌ Not deploying via cortex-update.sh — other agents can't use it

---
name: file-ownership-boundaries
version: 1.0.0
category: devops
description: >-
  Know which files are yours to modify vs Hermes defaults.
  Covers the two-domain split (Hermes Agent vs hermes-cortex repo),
  what each domain owns, and how to check before editing.
author: Moses
platforms: [linux, macos]
metadata:
  hermes:
    tags: [ownership, boundaries, repo, hermes, architecture, domain]
    related_skills: [survey-before-action, agent-fundamentals, repo-organization, cortex-preflight]
---

# File Ownership Boundaries

## Why This Exists

This system has **two domains** with different ownership:

| Domain | Location | Who owns it | Can we modify? |
|--------|----------|-------------|----------------|
| **Hermes Agent** | `~/.hermes/` (core files) | Hermes Agent / Nous Research | **No** — gets overwritten on updates |
| **Our repo** | `~/hermes-cortex/` | Us | **Yes** — this is our codebase |
| **Deployed runtime** | `~/.hermes-cortex/` | Us (deployed from repo) | Edit repo source, then deploy |
| **State/config** | `~/.hermes-cortex/state/*`, `~/.hermes/config.yaml` | Per-machine | Yes — direct modification OK |

## The Core Rule

**Only create and modify files that have a source in our repo (`~/hermes-cortex/`).**

If a file only exists in `~/.hermes/` and not in the repo: **do not touch it.**

## Before Every File Edit

Ask yourself these three questions IN ORDER:

1. **Is this file in `~/hermes-cortex/`?**
   → Yes: ✅ Edit freely. It's ours.

2. **Is it ONLY in `~/.hermes/` and NOT in the repo?**
   → Yes: ❌ **STOP.** It's a Hermes default. Do not touch it.

3. **Is it somewhere else (deployed runtime, state file)?**
   → Deployed runtime (`~/.hermes-cortex/scripts/`): find the repo source, edit there, then deploy
   → State/config: modify directly

## What Are Hermes Defaults?

Hermes Agent ships with bundled skills, config templates, and core modules. These are maintained by the Hermes project and should never be modified locally.

**Hermes default skills (do NOT edit):**
- `task-start`, `session-manager`, `agent-flow`, `reasoning-patterns`
- `reflexion-check`, `agent-contract`, `agent-inbox`, `hermes-agent`
- `survey-before-action`, `public-contribution`, `orch-skill-lifecycle`
- Any skill that does NOT have a source in `~/hermes-cortex/skills/`

**Heads-up: name collisions.** Some Hermes defaults share names with our repo skills (e.g. `change-checklist` exists in both Hermes defaults and `~/hermes-cortex/skills/devops/change-checklist/`). The Hermes default one loads from `software-development/change-checklist`; ours is at `devops/change-checklist` with `author: Moses`. Always check the category path and `author` field to know which is which.

**Our skills (edit freely):**
- Anything in `~/hermes-cortex/skills/<category>/<name>/`
- Anything in `~/hermes-cortex/ops/scripts/`
- Any skill WHERE `skill_manage(action='create')` was called (agent-created)
- Skills with `author: Moses` or our team's author in frontmatter

## The Deployed Copy Trap

Files at `~/.hermes-cortex/scripts/` and `~/.hermes-cortex/skills/` are **deployed copies** from the repo. If you edit them directly:
1. Your changes will be **lost** on the next `cortex-update.sh --force-all`
2. Other agents won't get your improvements

**Always edit the repo source first**, then run `cortex-update.sh --force-all` to sync.

Exception: `~/.hermes-cortex/state/*` files are per-machine state, not deployed from repo.

## What To Do Instead of Editing a Hermes Default

If you need a capability that a Hermes default skill provides but it's missing something:

1. **Don't edit the Hermes default** — it will be overwritten
2. **Create a complement in our repo** — a new skill at `~/hermes-cortex/skills/<category>/<name>/`
3. **Reference the Hermes default** in your new skill's `related_skills` field
4. **Deploy via cortex-update.sh** so the fleet gets it

## Pitfalls

- ❌ Editing `task-start` to add todo restore — Hermes owns it, change gets lost
- ❌ Editing `session-manager` to add todo lifecycle — same problem
- ❌ Patching `~/.hermes-cortex/scripts/` files — next deploy overwrites your edits
- ❌ Creating a new file in `~/.hermes/skills/` — fleet can't get it; put it in the repo
- ✅ Creating `todo-persistence` skill in our repo — correct: all agents get it, Hermes doesn't overwrite
- ❌ **Creating a new file when an existing one can be extended.** Search 3+ different terms before concluding nothing exists. The most expensive mistake is building a parallel system because a single search missed the existing one.

## The Sharing Filter

When the skill lifecycle or learnings pipeline evaluates something for upstreaming, apply this filter in order:

1. **Is it a Hermes default skill?** (`task-start`, `session-manager`, etc.)
   → ❌ Skip. The framework owns these — not ours to share.

2. **Is it already in `hermes-cortex` repo with no substantive change?**
   → ❌ Skip. Already shared with the fleet.

3. **Is it a genuinely new or substantively improved hermes-cortex skill?**
   → ✅ Share.

**The test:** *"Would someone running Hermes Cortex benefit from this? Or is it already available through either the Hermes or hermes-cortex repos?"*

**Examples of what NOT to share:**
- ❌ A patch to a Hermes default skill (already in Hermes repo)
- ❌ A one-line doc fix in an existing hermes-cortex skill (already shared)
- ❌ A session-specific workaround or one-off fix (ephemeral)
- ✅ A new hermes-cortex skill with reusable steps + pitfalls
- ✅ A substantive new phase in an existing our-skill (e.g. a new Phase in `change-checklist`)
- ✅ A reference document under an existing our-skill umbrella

## Quick Reference Card

| You want to... | Right action |
|----------------|-------------|
| Change a skill behavior | Check if it's ours → if Hermes default, create a new skill in repo |
| Add a workflow step | Create or update an agent-created skill |
| Fix a deployed script | Find the repo source at `~/hermes-cortex/ops/scripts/`, edit there, deploy |
| Update a config file | Direct edit OK if it's state/config |
| Share with other agents | Put it in the repo under `skills/` or `ops/scripts/` |
| Extend a Hermes default | Create a **supporting skill** — see `references/supporting-skill-pattern.md` |

## Related

- AGENTS.md item 22: Only modify files in our repo — never touch Hermes defaults
- AGENTS.md item 23: Sharing filter — only share new/substantive hermes-cortex changes
- `survey-before-action` skill: Pre-flight checklist before file edits (Hermes default, read-only)
- `repo-organization` skill: Repo structure and naming conventions
- `public-contribution` skill: Decision tree for sharing improvements (Hermes default, read-only)
- `change-checklist` (devops): Pre-ship validation that includes file-ownership checks in Phase 0

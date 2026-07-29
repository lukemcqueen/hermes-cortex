---
name: file-ownership-boundaries
version: 1.0.0
category: devops
description: >-
  Know which files are yours to modify vs Hermes defaults.
  Covers the two-domain split (Hermes Agent vs hermes-cortex repo),
  what each domain owns, and how to check before editing.
author: Hermes Cortex
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

## Identifying Our Skills vs Hermes Defaults

Skills in `~/.hermes/skills/` come from two places. Know which is which:

| Origin | Path check | Action |
|--------|-----------|--------|
| Hermes Cortex (ours) | In `~/hermes-cortex/skills/` | ✅ Edit the repo source, deploy via cortex-update.sh |
| Hermes Agent (upstream) | In `~/.hermes/hermes-agent/skills/` but NOT in repo | ❌ Do not edit — create a supplement instead |

**Hermes Agent upstream skills (do NOT edit):** Any skill at `~/.hermes/hermes-agent/skills/` that does NOT have a matching source in `~/hermes-cortex/skills/`. This includes all skills in `apple/`, `creative/`, `email/`, `github/`, `media/`, `note-taking/`, `productivity/`, `research/`, `smart-home/`, `social-media/`, `software-development/spike`, and others shipped by upstream.

**Our skills (edit freely):** All skills under `~/hermes-cortex/skills/<category>/<name>/`, including those that share names with Hermes defaults (we customized them — `root-cause-debugging`, `survey-before-action`). Skills with `author: Hermes Cortex` or `author: Moses` in frontmatter are ours.

**Name collisions:** The only Hermes upstream skill that shares a name with ours is `root-cause-debugging` — our v2.0.0 is customized (6-phase vs upstream's 4-phase), being renamed to `root-cause-debugging`.

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

- ❌ Editing a skill that's only at `~/.hermes/hermes-agent/skills/` (e.g. `software-development/spike`) — we don't own it, upstream overwrites
- ❌ Patching `~/.hermes-cortex/scripts/` files — next deploy overwrites your edits
- ❌ Creating a new file in `~/.hermes/skills/` — fleet can't get it; put it in the repo
- ✅ Creating `todo-persistence` skill in our repo — correct: all agents get it, Hermes doesn't overwrite
- ❌ **Creating a new file when an existing one can be extended.** Search 3+ different terms before concluding nothing exists. The most expensive mistake is building a parallel system because a single search missed the existing one.

## The Sharing Filter

When the skill lifecycle or learnings pipeline evaluates something for upstreaming, apply this filter in order:

1. **Is it a Hermes Agent upstream skill?** (at `~/.hermes/hermes-agent/skills/` but NOT in `~/hermes-cortex/skills/`)
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
- `survey-before-action` skill: Pre-flight checklist before file edits (Hermes Cortex, read-only)
- `repo-organization` skill: Repo structure and naming conventions
- `public-contribution` skill: Decision tree for sharing improvements (ours)
- `change-checklist` (devops): Pre-ship validation that includes file-ownership checks in Phase 0

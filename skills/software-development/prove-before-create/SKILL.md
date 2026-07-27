---
name: prove-before-create
version: 1.0.0
category: software-development
description: >-
  Enforce the "prove existing can't handle it" discipline before creating
  any new file. Supplements survey-before-action with the HARD RULE that
  every agent defaults to "extend existing" first. Prevents codebase
  fragmentation from unnecessary parallel systems.
pinned: true
related_skills:
  - survey-before-action
  - cortex-preflight
  - session-orchestration
---

# Prove Before Create — Don't Rebuild What Exists

**The single most expensive mistake is creating a new file when an existing
one could be extended.** Every new file is debt that compounds: review time,
merge conflicts, doc drift, and confusion for future agents about which of
two parallel systems is canonical.

This skill enforces the "update existing before creating new" rule.

## When to Load

Load this skill whenever you are about to create a new:
- Script (`ops/scripts/` or `~/.hermes-cortex/scripts/`)
- Config (cron, installer, env)
- Cron job definition
- Skill (`skills/<category>/<name>/`)
- Bus message type or schema
- Agent profile or SOUL.md
- Documentation file

## The 4-Step Survey

### Step 1: Search with 3+ different terms

```bash
search_files(pattern="<term-1>", path="~/hermes-cortex/ops/scripts/", target="files")
search_files(pattern="<term-2>", ...)   # different angle
search_files(pattern="<term-3>", ...)   # synonym / broader concept
skills_list()
cronjob(action="list")
```

**One search is not a survey.** If nothing matches term-1, you haven't
proven the gap exists. Try term-2 and term-3 before concluding.

### Step 2: Load matching skill references

When a skill name matches, call `skill_view(name)` and check its linked
files. A skill's `references/` directory may contain:

- A ready-to-use script you were about to build
- A template you can copy and modify
- An example that shows the exact wiring pattern

These ARE the solution. Don't rebuild them.

### Step 3: Extend — don't rebuild

If the capability exists but isn't wired, **wire it**:

| Capability state | What to do |
|-----------------|------------|
| Skill has technique but no CLI script | Add a CLI entry point to the skill |
| Script has logic but no cron | Wire it as a cron with `cronjob action='create'` |
| CLI exists but no `--json` flag | Add `--json` to the existing script |
| Config template exists but no install path | Add a `register()` call to `cortex-update.sh` |
| Concept exists in one codebase but not another | Port it, don't rewrite it |

Adding a flag to an existing system costs 1/10th the debt of a new
parallel system.

### Step 4: If you still create something new

Document in the commit message:
1. What terms you searched
2. What you found (and why it didn't fit)
3. The minimum viable scope of the new file

Name the file at the **class level**, not after today's session artifact.
A file called `fix-registry-timeout.py` is wrong (session-specific).
A file called `circuit-breaker.py` is right (class-level).

## Violation Classification

Creating a new file when an existing system could be extended is a
**structural violation**. It:

- Fragments the codebase into parallel systems
- Increases review time for every future change
- Creates merge conflicts between the two systems
- Confuses future agents about which is canonical
- Compounds with every new file

If you catch yourself mid-creation with a "this is faster to write than
find the existing one" thought — stop. That thought is wrong. Surveying
saves more time than writing.

## Pitfalls

| Pitfall | Why it's wrong |
|---------|----------------|
| "I'll search later" | You won't. Search BEFORE writing. |
| "This is different enough" | 80% overlap means extend the existing tool. |
| "The existing one is poorly written" | Improve it. Don't abandon it — that's how you get 3 half-written libraries. |
| "It's faster to just write it" | Faster NOW, slower forever. Every new file is a permanent tax. |
| Searched once, nothing found | One search is not a survey. Try 3 different search terms. |
| Found a match but didn't load its references | The references/ dir may contain the exact solution. |

## Relationship to Other Skills

- **survey-before-action** (Hermes default) — covers the general survey
  checklist. This skill adds the enforcement layer and the "extend, don't
  rebuild" rule.
- **cortex-preflight** (repo-specific) — adds git search and deployment
  checks. Run after this skill.
- **session-orchestration** — Wave 1 (Discovery) should include the 4-step
  survey before proceeding to implementation.

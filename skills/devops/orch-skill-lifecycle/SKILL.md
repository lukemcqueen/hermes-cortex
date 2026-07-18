---
name: orch-skill-lifecycle
category: devops
description: "Unified daily skill lifecycle pipeline — collects lessons, evaluates quality, and upgrades skills/SOUL.md. Replaces skill-miner, harvest-lessons, skill-triage, soul-refinement, and agent-weekly-loop-eval."
version: 1.0.0
author: Moses (Hermes Cortex)
license: MIT
platforms: [linux, macos]
---

# Orch Skill Lifecycle — Unified Daily Pipeline

## Overview

Single daily cron (04:00 KST) that replaces 5 separate processes. Runs the full skill lifecycle end-to-end: **collect → evaluate → upgrade**.

The cron has `terminal` + `file` + `web` tool access and uses `session_search()` for historical analysis.

## Replacements

| Old Cron | Fate | Absorbed Into |
|----------|------|---------------|
| `skill-miner` (Mon 06:00) | Removed | Collection + Evaluation |
| `skill-triage` (06:00/18:00) | Removed | Collection (bus reads) + Upgrade (upstream) |
| `harvest-lessons` (Mon 05:00) | Removed | Collection (session mining) |
| `agent-weekly-loop-eval` (Mon 09:00) | Removed | Evaluation (weekly deep) |
| `agent-daily-soul-refinement` (23:00) | Removed | Evaluation + Upgrade (SOUL.md) |

## Pipeline Phases

### Phase 1 — Collection

Gather raw material from all sources:

1. **Session mining** — `session_search()` for sessions since last run (~24h). Look for:
   - User corrections or repeated guidance
   - Workflow discoveries (new commands, tools, patterns)
   - Bug fixes or error resolutions
   - Configuration changes

2. **Bus check** — Check `inbox_moses` PGMQ queue for:
   - `Subject: Skill Report:` messages from fleet agents
   - Parse skill name, category, description, content
   - Any pending skill-related requests

3. **Skill inventory scan** — Check all skills under `~/.hermes/skills/`:
   - List all SKILL.md files with modification dates
   - Check for stale references (paths, commands, URLs that no longer exist)

4. **Pre-commit trail** — Check recent git commits in `~/hermes-cortex/` for:
   - Self-improvement patches that may need broader consolidation
   - Patterns across multiple commits

**Output:** A compiled list of items to evaluate. Each item has:
```
{item_type: "lesson"|"bus_report"|"stale_ref"|"consolidation_candidate",
 source: "session"|"bus"|"inventory"|"git",
 content: "...",
 agent: "moses"|"fleet_agent_name",
 priority: high|medium|low}
```

### Phase 2 — Evaluation

For each collected item, classify and decide:

1. **Classification** — Is this:
   - **New lesson** → skill pitfall / step / warning to add
   - **Reinforcement** → existing skill already covers it, strengthen
   - **Principle** → belongs in SOUL.md, not a skill
   - **New skill** → fleet agent discovered something new
   - **Consolidation** → multiple skills overlap, should merge
   - **Stale** → skill references dead path/command, needs pruning

2. **Dedup** — Before acting, check:
   - Does this exact lesson already exist in a skill?
   - Is there a skill with the same name/content already?
   - Has this been applied before? (check git log, skill decisions state)

3. **Priority** — Apply the correct action:
   - **HIGH** — Broken command, security issue, stale cron → fix immediately
   - **MEDIUM** — Workflow improvement, new pitfall → fix during this run
   - **LOW** — Nice-to-have, speculative → defer or archive

4. **Weekly deep evaluation** (if today is Monday):
   - Full consolidation pass: check ALL skills for cross-overlap
   - Staleness scan: check every skill's paths, commands, and references
   - Pruning: flag skills with zero usage or that have been superceded

### Phase 3 — Upgrade

Execute all approved actions:

1. **Patch existing skill** — `skill_manage(action='patch', ...)` with new pitfall, corrected step, updated path
2. **Create new skill** — `skill_manage(action='create', ...)` for genuinely new discoveries (from fleet or own work)
3. **Merge skills** — Read both, compose unified SKILL.md, delete old
4. **Prune stale skills** — `skill_manage(action='delete', ...)` with `absorbed_into=""` for truly dead skills
5. **SOUL.md update** — Append principle changes to `~/.hermes/SOUL.md` with `<!-- Added YYYY-MM-DD -->`
6. **Upstream new skills to repo** — For fleet-submitted skills:
   - Create `hermes-cortex/skills/<category>/<name>/SKILL.md`
   - `git add`, commit, push
7. **Archive processed bus messages** — Clean inbox_moses for processed skill reports

### Verification

After all changes:
1. Confirm skills are readable: `skill_view(name)` for each changed skill
2. Check syntax: `skill_manage(action='patch')` returns a diff — verify it looks correct
3. Verify SOUL.md is valid markdown
4. Run `cronjob action='list'` to confirm old crons are gone
5. If Monday: verify the session cache exists and is current

## Output Format

Produce a structured report each run:

```
orch-skill-lifecycle (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Collection:
- Sessions mined: 12 (3 corrections, 1 discovery)
- Bus: 2 Skill Report messages from fleet
- Skills scanned: 142 files, 2 stale refs found
- Pre-commit: 1 consolidation pattern detected

Phase 2 — Evaluation:
- 4 items classified: 3 skill patches, 1 SOUL.md principle
- 1 duplicate filtered (already in skill 'agent-flow')
- 2 stale refs: archived for Monday deep eval

Phase 3 — Upgrade:
- Patched: agent-flow (pitfall section), agent-bus (new step)
- SOUL.md: 1 principle added
- Upstreamed: 1 new skill from fleet (swap-refresh)
- Bus: 2 messages archived
- Git: committed + pushed

Result: 3 skills updated, 1 upstreamed, 1 SOUL.md entry.
```

## Schedule

- **Daily (04:00 KST)** — Full pipeline with light evaluation
- **Monday deep eval** — Additional consolidation + pruning + staleness pass

## Pitfalls

- **Don't patch the same skill twice in one run** — deduplicate before acting
- **Don't upstream fleet skills that already exist** — check repo + Hermes bundle
- **Don't modify SOUL.md for workflow lessons** — skills are for workflow, SOUL.md is for principles
- **Don't skip verification** — a bad skill patch breaks every agent that loads it
- **Confidence scoring**: HIGH = verified with real commands, MEDIUM = manual analysis, LOW = untested — do not release LOW
- **Archive bus messages after successful upstream, not before** — if push fails, message stays in queue for retry

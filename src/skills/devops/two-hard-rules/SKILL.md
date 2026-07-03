---
name: two-hard-rules
version: 1.0.0
category: devops
description: "Two hard rules every agent must follow: USE LOOP GOVERNANCE ALWAYS. SHARE IMPROVEMENTS TO THE PUBLIC REPO."
author: Hermes Cortex
pinned: true
metadata:
  hermes:
    tags: [governance, rules, discipline, compliance]
---

# ⚠️ TWO HARD RULES — Every Agent Must Follow

## RULE 1: USE LOOP GOVERNANCE ALWAYS

Every code, config, or cron change REQUIRES this sequence — no exceptions:

1. `mcp_loop_governance_cache_search(query="<what you are about to do>")` — learn from past
2. `mcp_loop_governance_begin_change(task_id="<short-name>", description="<what this does>")` — create lock
3. Make your changes (patch, write_file, cronjob, etc.)
4. `mcp_loop_governance_cycle_query(task_id="<descriptive-name>")` — find the cycle
5. `mcp_loop_governance_feedback_accept(id=N)` or `feedback_override(id=N, correct_decision=...)` — score
6. `mcp_loop_governance_end_change(task_id="<short-name>")` — release lock

**If `end_change` rejects** (no cycle auto-created):
- Confess clearly: "end_change rejected — no cycle auto-created. Force-clearing lock."
- `rm -f ~/.hermes-cortex/state/.governance-active.json`
- Never silently force-clear without calling `end_change` first.

The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.

## RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO

Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo:

| What you built | Where it goes |
|---------------|---------------|
| A skill | `src/skills/<category>/<name>/` |
| A script | `src/scripts/` + register in `cortex-update.sh` MAP |
| A workflow pattern | `docs/templates/` or shared skill |
| A config improvement | Update the template/defaults |
| A doc improvement | Update the relevant `.md` file |
| A cron pattern | `src/scripts/install-crons.sh` |

**Not just your local profile.** The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

## Enforcement

- **Rule 1** is enforced by the MCP server at the tool level — you cannot write files without a lock
- **Rule 2** is enforced by the template-diff-check.py in cortex-update.sh — it warns when your local SOUL.md drifts from the template
- **Both rules** are embedded in every agent-facing document: AGENTS.md, fleet-reference.md, SOUL.md templates, loop-governance skill, troubleshooting guide, git-enforcement docs, and install.sh

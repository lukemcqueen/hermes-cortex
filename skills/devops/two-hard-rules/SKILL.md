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
    related_skills: [agent-contract, loop-governance, change-checklist, public-contribution]
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
| A skill | `skills/<category>/<name>/` |
| A script | `ops/scripts/` + register in `cortex-update.sh` MAP |
| A workflow pattern | `docs/templates/` or shared skill |
| A config improvement | Update the template/defaults |
| A doc improvement | Update the relevant `.md` file |
| A cron pattern | `ops/scripts/install-crons.sh` |

**Not just your local profile.** The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

## Enforcement

- **Rule 1** is enforced by the MCP server at the tool level — you cannot write files without a lock
- **Skills gate** — `~/.hermes-cortex/state/.skills-loaded` is auto-created when all 8
  always-section skills are loaded via `skill_view()`. Do NOT `touch` this file — the enforcer
  rejects empty/session-mismatched markers.
- **Reflexion gate** — The pre-commit hook queries the session DB for proof that `reflexion-check`
  was loaded. Do NOT use `--no-verify` — it's logged and audited.
- **Adversarial verify** — The pre-commit scanner checks for issues. **Correct:** Fix what it reports.
  **Wrong:** Remove the check from the hook.
- **Dogfood gate** — The pre-commit hook enforces that deployed code matches the repo source.
  **Correct:** `bash ops/scripts/cortex-update.sh --force-all`, run doctor, fix issues, commit.
  **Wrong:** Push without testing.
- **Rule 2** is enforced by the template-diff-check.py in cortex-update.sh — it warns when your local SOUL.md drifts from the template
- **Both rules** are embedded in every agent-facing document: AGENTS.md, fleet-reference.md, SOUL.md templates, loop-governance skill, troubleshooting guide, git-enforcement docs, and install.sh

## The Litmus Test

If your next step would work around a governance mechanism rather than complying with it —
**stop and confess instead.** Ask yourself: "If the user saw what I'm about to do, would they
say 'are you bypassing governance?'" If yes, you're about to make a mistake.

| Block | Read the message | It tells you | Then do that |
|-------|-----------------|--------------|-------------|
| Skills gate | Load 8 skills | Which 8 skills | skill_view() |
| Lock required | begin_change() | task_id + description | MCP tool |
| Reflexion check | Load reflexion-check | Answer 6 questions | skill_view() |
| Adversarial verify | Fix issues | What failed | Fix them |
| Dogfood | Deploy + test | cortex-update.sh | Run it |

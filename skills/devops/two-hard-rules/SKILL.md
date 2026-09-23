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

1. `mcp__loop_governance__cache_search(query="<what you are about to do>")` — learn from past
2. `mcp__loop_governance__begin_change(task_id="<short-name>", description="<what this does>")` — create lock
3. Make your changes (patch, write_file, cronjob, etc.)
4. `mcp__loop_governance__cycle_query(task_id="<short-name>")` — find the cycle
5. `mcp__loop_governance__feedback_accept(cycle_id=N, task_id="<short-name>", note="<evidence>")` or `feedback_override(...)` — score
6. `mcp__loop_governance__end_change(task_id="<short-name>")` — release lock

**If `end_change` rejects** (no cycle auto-created, or cycle not scored — 2026-08-08):
- `end_change` now BLOCKS while the task's cycle is unscored, and `begin_change`
  refuses a new task while earlier PENDING cycles exist (close-out enforcement,
  Luke directive). Score first: `cycle_query` → `feedback_accept/override` →
  `end_change`, THEN the next `begin_change`.
- If genuinely stuck: confess clearly: "end_change rejected — no cycle auto-created. Force-clearing lock."
- Locks are session-scoped: `rm -f ~/.hermes-cortex/state/.governance-<session-id>.json`
  (find yours with `ls -t ~/.hermes-cortex/state/.governance-*.json | head -1`;
  the legacy name `.governance-active.json` is obsolete).
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
- **Skills gate** — `~/.hermes-cortex/state/skills-loaded/<session-id>` is auto-created when all 7
  always-section skills are loaded via `skill_view()` (task-start bundles the list). Do NOT `touch` it —
  the enforcer rejects empty/session-mismatched markers. Per-session files mean concurrent sessions
  never stomp each other's proof.
- **After a gateway restart, load all 7 always-skills with `skill_view()` (read-only, so the gate lets
  them through); the 7th call regenerates the marker.** A deploy only invalidates the marker when a
  skill's CONTENT changed (fingerprint = content hash since 2026-09-23) — and then the block message
  names exactly which skills to reload, so re-load that list, not the whole set.
- **Reflexion gate** — The pre-commit hook queries the session DB for proof that `reflexion-check`
  was loaded. Do NOT use `--no-verify` — it's logged and audited.
- **Adversarial verify** — The pre-commit scanner checks for issues. **Correct:** Fix what it reports.
  **Wrong:** Remove the check from the hook.
- **Dogfood gate** — The pre-commit hook enforces that deployed code matches the repo source.
  **Correct:** `bash ops/scripts/cortex-update.sh`, run doctor, fix issues, commit.
  **Wrong:** Push without testing.
- **Rule 2** is enforced by the template-diff-check.py in cortex-update.sh — it warns when your local SOUL.md drifts from the template
- **Both rules** are embedded in every agent-facing document: AGENTS.md, fleet-reference.md, SOUL.md templates, loop-governance skill, troubleshooting guide, git-enforcement docs, and install.sh

## The Litmus Test

If your next step would work around a governance mechanism rather than complying with it —
**stop and confess instead.** Ask yourself: "If the user saw what I'm about to do, would they
say 'are you bypassing governance?'" If yes, you're about to make a mistake.

| Block | Read the message | It tells you | Then do that |
|-------|-----------------|--------------|-------------|
| Skills gate | Load 7 skills | Which 7 skills | skill_view() (list bundled in task-start) |
| Lock required | begin_change() | task_id + description | MCP tool |
| Reflexion check | Load reflexion-check | Answer 7 questions | skill_view() |
| Adversarial verify | Fix issues | What failed | Fix them |
| Dogfood | Deploy + test | cortex-update.sh | Run it |

### Two independent gates — expect the second block

The skills gate and the lock gate BOTH block write tools, each with its own
message and remedy, and neither implies the other:

1. **Gate 1 (skills gate):** all 7 always-section skills loaded → marker auto-created.
2. **Gate 2 (lock gate):** an active governance lock → `begin_change()`.

Fixing gate 1 does NOT satisfy gate 2 — a "GOVERNANCE LOCK REQUIRED" block
immediately after loading skills is EXPECTED, not a malfunction. The reverse
also holds. Both block messages now label themselves (GATE 1 of 2 / GATE 2 of 2).

Also: a terminal command with compound metacharacters (semicolon, pipe, ampersand,
redirection, backtick, `$()` — or a newline; including `python3 -c "..."`) is
classified write-capable even when
it only reads. For lock-free inspection use a SINGLE clean command or
read_file/search_files. That is conservative-by-design, not a bug.

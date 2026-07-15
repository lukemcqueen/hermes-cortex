---
name: survey-before-action
version: 1.1.0
category: software-development
description: >
  Mandatory pre-flight checklist before creating or modifying any file
  (scripts, cron configs, markdown, code). Prevents redundant work by
  systematically checking for existing resources first.
pinned: true
related_skills: [change-checklist, skills_list, cron-job-management]
---

# Survey Before Action

**Mandatory pre-flight for every file create/modify operation.**

Run this BEFORE writing a new file, adding a cron, creating a skill, or modifying any existing resource. Do not skip, batch, or defer.

## Checklist

### 1. Search for existing resources

Search these locations in order. Batch the independent searches together.

search_files(pattern="<related-keywords>", path="~/hermes-cortex/src/scripts/", target="files")
search_files(pattern="<related-keywords>", path="~/.hermes-cortex/scripts/", target="files")
skills_list()
cronjob(action="list")

**Keywords to try:** function name, tool name, purpose (e.g., "audit", "scoring", "health", "failure")

### 2. Examine what exists

If a candidate match is found, read it before deciding:
read_file(path="<candidate-path>")
skill_view(name="<candidate-skill>")

Assess:
- Does this existing tool do some or all of what I need?
- Can I add a flag/mode/parameter to extend it?
- Is the existing tool in the right location or does it need to be moved?

### 3. Decision

| If ... | Then ... |
|--------|----------|
| Existing tool covers 100% | Use as-is. No new file. |
| Existing tool covers 80%+ with small patch | Patch the existing tool. Add a flag or mode. |
| Existing tool covers 50-80% | Refactor/extend. Consider architecture change. |
| Existing tool covers <50% | Create new. Document why in commit message. |

### 4. If creating something new anyway

Document in the commit message why none of the existing resources fit.

## Critical rules

- Always search src/scripts/ first. This is the canonical location for installed scripts.
- Always check skills_list(). If a skill already covers the workflow, use it.
- Always check cronjob list. Existing cron patterns may already solve the problem.
- If no match found: note it mentally. Do NOT skip this step next time.

---

## Post-Action Audit

**Mandatory post-flight for every file create/modify cycle.**

Run this AFTER making changes, BEFORE calling end_change().

### 5. Search for stale communications

After modifying, deleting, or renaming files other agents reference, check pending outbound messages:

mcp_agent_inbox_inbox_read(unread_only=True)

Review messages from you. If any reference now-stale paths, commands, or instructions — send a correction immediately before releasing the governance lock.

### 6. Decide whether to share

| I created/modified ... | I should put it in ... |
|------------------------|------------------------|
| A script | src/scripts/ + register in cortex-update.sh |
| A skill | src/skills/<category>/<name>/ |
| A cron pattern | Document in AGENTS.md |
| A workflow/technique | Save as a skill or add reference to existing skill's references/ |
| Machine/user specific | Keep private |

Default posture: share. The question isn't "should I share?" but "where does this go so other agents can use it?"

### 7. Verify the guardrail

If this work responded to a mistake: did you implement a guardrail that prevents recurrence? Is it enforceable? Have you tested it catches the same failure? If any answer is no, the loop isn't closed.

### 8. Test before shipping

**Every change to a script, config, or installer must be verified end-to-end before pushing to main.**

Verification means exercising the actual changed code path and confirming the result — not just staring at the diff.

| What changed | Verification required |
|-------------|----------------------|
| install-crons.sh cron workdir/script/schedule | Run a test cron create with the actual CLI, confirm job registers, then clean up |
| Shell script logic | bash -n <file> + live test exercising the changed branch |
| Python script | Run with expected arguments, check output and exit code |
| Cron definition | hermes cron create --name test-<x> → verify in cronjob list → remove test job |

The check before git push: "Did I actually run the changed code path, or did I only look at it?" If only looked — stop. Go run it.

Failures this catches:
- Escaped $HOME in workdir parameter → literal string passed, CLI rejects, script prints success but no cron registered
- Missing script at destination → cron creates but fails every tick
- Absolute path that works on one machine but not others

### 9. Audit post-push communications

After pushing to main, verify outbound messages match the deployed state. If you described a feature as "available" but it's not on main at the receiver's pulled commit — send a correction.

## Companion maintenance tool

After surveying and building, AGENTS.md grows over time. Periodically prune accumulated docs:

python3 ~/.hermes-cortex/scripts/agents-doc-audit.py --repo . --prune --apply

## Why this exists

Created after building check-agents-dot-md.py when agents-doc-audit.py already existed. A 15-second search would have prevented the redundant work.

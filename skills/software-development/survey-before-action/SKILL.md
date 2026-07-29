---
name: survey-before-action
version: 1.3.0
category: software-development
description: >-
  Mandatory pre-flight checklist before creating or modifying any file.
  Prevents redundant work by systematically checking for existing resources
  first. Also includes a full-repo stale-artifact audit pattern.
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
related_skills: [change-checklist, skills_list, cron-job-management]
---

# Survey Before Action

**Mandatory pre-flight for every file create/modify operation.**

Run this BEFORE writing any file, adding a cron, creating a skill, or modifying any existing resource. Do not skip, batch, or defer.

## Survey

### 1. Search for existing resources

Search these in order. Batch independent searches together.

```
search_files(pattern="<keywords>", path="~/hermes-cortex/ops/scripts/", target="files")
search_files(pattern="<keywords>", path="~/.hermes-cortex/scripts/", target="files")
skills_list()
cronjob(action="list")
```

**Keywords:** function name, tool name, purpose (e.g. "audit", "health", "failure")

### 2. Examine what exists

If a candidate match is found, read it before deciding. Assess:
- Does it do some or all of what I need?
- Can I add a flag/parameter to extend it?
- Is it in the right location or needs moving?

### 3. Decision

| If ... | Then ... |
|--------|----------|
| Covers 100% | Use as-is |
| Covers 80%+ with small patch | Patch the existing tool |
| Covers 50-80% | Refactor or extend |
| Covers <50% | Create new. Document why in commit. |

### 4. Creating something new anyway

Document in commit why existing resources don't fit.

### 4b. User approval for deletions

If your plan includes deleting files or directories, present the deletion plan for approval BEFORE executing. Show what, why safe to remove (zero consumers, stale duplicate, etc.), and expected improvement. Wait for explicit confirmation before `git rm` or `rm -rf`.

### 4c. Make old names discoverable before deletion

Before deleting a renamed/merged artifact, ensure the surviving artifact makes the old name findable:
- **Skills:** add `aliases: [old-name]` or `tags: [old-name]` in frontmatter
- **Scripts/tools:** add `# Formerly known as` comment or `--compat` flag
- **Docs:** add deprecation note at the top (e.g. `> Moved to [new-path](new-path.md)`)
- **Git history:** mention both names in commit message

**Why:** A deletion without discoverability orphans every inbox message, cron config, and agent reference that used the old name.

### 4d. Guardrail: verify target exists before editing

Before calling `patch()`, `write_file()`, or any tool that modifies a file, confirm the exact target path exists with `read_file()` or `search_files(target="files")` first. Patching a nonexistent path silently fails — the edit never lands. Always verify with a second method. `search_files(target="files")` matches basenames only, not directory names.

## Critical rules

- **Search ops/scripts/ first** — canonical location for installed scripts
- **Check skills_list()** — if a skill already covers the workflow, use it
- **Check cronjob list** — existing cron patterns may already solve the problem
- **Never trust a single zero-result `search_files`.** When you get 0 results, verify with `ls`, `find`, `git ls-tree`, or `git log` before concluding the resource doesn't exist.
- **If no match found:** note it mentally. Do not skip this step next time.

---

## Post-Action Audit

**Mandatory post-flight before calling end_change().**

### 5. Search for stale communications

After modifying, deleting, or renaming files other agents reference, check pending outbound messages with `mcp_agent_inbox_inbox_read(unread_only=True)`. If any reference now-stale paths or instructions, send a correction before releasing the governance lock.

### 6. Decide whether to share

| I created/modified ... | I should put it in ... |
|------------------------|------------------------|
| A script | ops/scripts/ + register in cortex-update.sh |
| A skill | skills/<category>/<name>/ |
| A cron pattern | AGENTS.md or cron-schedules.md |
| A workflow/technique | Save as a skill or reference |
| Machine/user specific | Keep private |

Default posture: share.

### 7. Verify the guardrail

If this work responded to a mistake: did you implement a guardrail that prevents recurrence? Is it enforceable? Test it catches the same failure. If any answer is no, the loop isn't closed.

### 8. Test before shipping

**Every change must be verified end-to-end before pushing to main.** Verification means exercising the actual changed code path — not just staring at the diff.

| What changed | Verification required |
|-------------|----------------------|
| install-crons.sh cron | Run test cron via CLI, confirm registration, clean up |
| Shell script | `bash -n <file>` + live test of changed branch |
| Python script | Run with expected args, check output and exit code |
| Cron definition | Create test cron, verify in list, remove |
| Pre-commit/git hook | Commit through the RUNNING hook, not the repo copy |
| Any file with runtime copy | Verify the RUNTIME copy changed — not just the repo source |

The check before git push: "Did I actually run the changed code path?" If only looked — stop. Run it.

**Failures this catches:**
- Escaped `$HOME` in workdir → literal string passed, CLI rejects silently
- Missing script at destination → cron creates but fails every tick
- Absolute path that works on one machine but not others
- **Repo source changed but running copy stale** — editing `.hermes-cortex/hooks/pre-commit` while `core.hooksPath` points to `~/.hermes-cortex/hooks/` where the old version still runs

### 9. Audit post-push communications

After pushing to main, verify outbound messages match the deployed state. If you described a feature as "available" but it's not on main at the receiver's pulled commit, send a correction.

## Companion tools

- `scripts/agents-doc-audit.py` — prune accumulated doc refs after surveys
- `references/hook-deployment-audit.md` — runtime-vs-repo path mistakes
- `references/testing-deployable-scripts.md` — detailed test patterns by type

---

## Appendix: Repo-Wide Stale-Artifact Audit

When the task is a comprehensive repo review, the per-operation checklist above is too narrow. Run this instead:

1. **Structural integrity** — README vs Reality, VERSION consistency, DOCS-INDEX stale paths
2. **Git-tracked build artifacts** — `git ls-files | grep -E '(__pycache__|\.pyc$)'` 
3. **.gitignore accuracy** — stale negated patterns for deleted files; missing ignores for artifacts found
4. **Skill duplicates** — `find . -name SKILL.md -exec sh -c 'basename $(dirname $_)' \; | sort | uniq -d`
5. **Doc-vs-reality** — docker-compose links, script counts, cron counts, alleged file paths
6. **Test paths** — search tests for stale source paths (`src/`, `deploy/`, etc.)
7. **Mid-survey user requests** — tag as follow-up, finish current step, return immediately

## Why this exists

Created after building `check-agents-dot-md.py` when `agents-doc-audit.py` already existed. A 15-second search would have prevented the redundant work.

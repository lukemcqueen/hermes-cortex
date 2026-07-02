---
name: survey-before-action
version: 1.0.0
category: software-development
description: >
  Mandatory pre-flight checklist before creating or modifying any file
  (scripts, cron configs, markdown, code). Prevents redundant work by
  systematically checking for existing resources first.
pinned: true
---

# Survey Before Action

**Mandatory pre-flight for every file create/modify operation.**

Run this BEFORE writing a new file, adding a cron, creating a skill, or modifying any existing resource. Do not skip, batch, or defer.

## Checklist

### 1. Search for existing resources

Search these locations in order. Batch the independent searches together.

```tool
search_files(pattern="<related-keywords>", path="~/hermes-cortex/src/scripts/", target="files")
search_files(pattern="<related-keywords>", path="~/.hermes-cortex/scripts/", target="files")
skills_list()
cronjob(action="list")
```

**Keywords to try:** function name, tool name, purpose (e.g., "audit", "scoring", "health", "failure")

### 2. Examine what exists

If a candidate match is found, read it before deciding:
```tool
read_file(path="<candidate-path>")
skill_view(name="<candidate-skill>")
```

Assess:
- Does this existing tool do **some or all** of what I need?
- Can I add a flag/mode/parameter to extend it?
- Is the existing tool in the right location or does it need to be moved?

### 3. Decision

| If ... | Then ... |
|--------|----------|
| Existing tool covers 100% of need | **Use as-is.** No new file. |
| Existing tool covers 80%+ with a small patch | **Patch the existing tool.** Add a flag or mode. |
| Existing tool covers 50-80% + needs significant change | **Refactor/extend.** Consider architecture change. |
| Existing tool covers <50% or fundamentally different | **Create new.** Document why in the commit message. |

### 4. If creating something new anyway

Document in the commit message why none of the existing resources fit:
```
why-new: [specific reason — e.g., "existing X does Y but this needs Z architecture"]
```

## Critical rules

- **Always search src/scripts/ first.** This is the canonical location for installed scripts.
- **Always check skills_list().** If a skill already covers the workflow, use it instead of writing ad-hoc instructions in SOUL.md or cron prompts.
- **Always check cronjob list.** Existing cron patterns may already solve the problem.
- **If no match found:** note it mentally. Do NOT skip this step next time — the absence is also data.

## Why this exists

Created after: building `check-agents-dot-md.py` when `agents-doc-audit.py` already existed in `src/scripts/`. A 15-second search would have prevented the redundant work. Every such miss erodes trust — this skill exists to make misses impossible.

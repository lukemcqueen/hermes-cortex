--- Full content (truncated) ---
---
name: cross-repo-sync
version: 1.0.0
category: devops
description: >
  Update the same file (config, docs, boilerplate) across multiple project
  repos in a single coordinated pass. Covers the full pipeline: parallel
  survey, batch content generation, bulk write, verification, and
  multi-repo git commit/push with real-world failure handling.
pinned: false
---

# Cross-Repo Sync

**Keep a file synchronized across all project repos in one pass.**

Use when a standard file (AGENTS.md, .gitignore, README, config template)
needs updating everywhere. Not for one-off per-repo work — only when the
same file class exists across many repos with repo-specific content.

## Workflow

### Phase 1: Inventory (survey)

First, discover all repos and understand their current state.

```bash
# Find all repos with the target file
find /Users/luke -maxdepth 4 -name "TARGET_FILE" -not -path "*/node_modules/*" 2>/dev/null

# Optionally check git repos too
find /Users/luke -maxdepth 4 -name ".git" -type
... [truncated]
--- End skill ---
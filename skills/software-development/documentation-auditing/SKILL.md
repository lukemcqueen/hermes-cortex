---
name: documentation-auditing
version: 1.0.0
category: software-development
description: >-
  Audit documentation for stale file paths, broken cross-references, and
  correctness gaps. Systematic approach for identifying, verifying, and
  reporting stale references in docs directories.
pinned: true
related_skills: [survey-before-action, cortex-preflight, codebase-inspection]
---

# Documentation Auditing

**Systematic approach for auditing documentation correctness — focused on stale file path references, broken links, and out-of-sync doc content.**

Triggers: "audit docs for stale paths", "check documentation for broken references",
"find stale src/ or deploy/ paths in docs", "verify docs are in sync with repo
structure", "run a stale-paths audit", "fresh audit of the docs directory".

## Prerequisites

**Repo layout (verified 2026-09-08 on host esther):**
- The old `src/` tree and the root `deploy/` symlink are **GONE** from this repo — only historical/prose mentions remain (e.g. `core/governance/__init__.py` says the legacy `src/loop-governance/` shim was removed). Treat every live `src/` or bare `deploy/` reference as STALE unless it is prose in a migration doc.
- The deploy tree lives at `ops/install/deploy/` (e.g. `ops/install/deploy/nginx/hermes-services.conf`).
- `docs/DOCS-INDEX.md` exists — Phase 6 checks it.
- There is currently **no** `docs/stale-paths-audit.md` in the repo — if it doesn't exist when you reach Phase 9, CREATE it fresh (use the Phase 8 report structure as its skeleton) instead of assuming a prior audit file exists.

**Required tools:** `search_files` (or `grep`/`rg`), `read_file`, filesystem access to `~/hermes-cortex/`. No external network access needed.

## Audit corpus boundary

Search ALL `.md` files under `docs/` (including `docs/prd/` and `docs/runbooks/`), plus top-level `README.md` and `AGENTS.md`. Do not scan `ops/offline/code-corpus/` (third-party snippets, not our docs) or `skills/` (audited separately).

## Workflow

### Phase 1: Identify Stale Path Patterns

Know which paths are known to be stale:

| Old Path | Canonical Path (if known) | Common In-Docs Form |
|----------|--------------------------|---------------------|
| `src/` (root) | `core/` / `ops/` / `mcp-servers/` / `skills/` | `src/scripts/`, `src/mcp-servers/`, `src/skills/`, `src/agent-inbox/`, `src/dashboard/`, `src/offline/`, `src/loop-governance/`, `src/auth/` |
| `deploy/` (root symlink → `ops/install/deploy/`) | `ops/install/deploy/` *(symlink may be removed!)* | `deploy/nginx/`, `deploy/patches/`, `deploy/docker-compose.langfuse.yml` |
| `runtime/` (if applicable) | (varies) | |

**Always verify symlink status on-disk before classifying a `deploy/` ref as "works via symlink"** — the symlink may have been removed since the last audit.

### Phase 2: Search Docs for Each Pattern

For each stale path prefix, search all docs `.md` files:

```bash
# Exclude integration-audit.md (intentional historical record) and stale-paths-audit.md (the report itself)
grep -rn --include='*.md' -E '\bsrc/(scripts|mcp-servers|skills|agent-inbox|dashboard|offline|loop-governance|auth)/' docs/ | grep -v 'integration-audit.md' | grep -v 'stale-paths-audit.md'
grep -rn --include='*.md' -E '(^|[ `(/])deploy/' docs/ | grep -v 'ops/install/deploy/' | grep -v 'integration-audit.md' | grep -v 'stale-paths-audit.md'
```

Note the `--` before the pattern and quoted regexes: an unquoted or un-dashed grep treats a leading-dash pattern as a flag and fails with "unrecognized flag".

Batch the searches — they are independent. Use `search_files` tool with appropriate `file_glob` and `output_mode`. For large docsets (80+ files), consider using `delegate_task` to offload the heavy scanning to a background subagent — this keeps your context uncluttered while the subagent does the exhaustive search and returns a structured report.

**Critical nuance:** Some files may have been **fixed since the last audit**. Keep a running tally of what changed.

### Phase 3: Categorize Matches

Not every `src/` or `deploy/` reference is stale. Classify each:

| Category | Description | Action |
|----------|-------------|--------|
| **STALE — actionable** | A live command/code block/path instruction that will fail if run today | Flag as High/Medium severity |
| **STALE — conceptual** | Template examples, placeholder paths | Flag as Low severity |
| **INTENTIONAL historical** | Migration docs, audit records documenting *what was moved* | Do NOT flag (document the exemption) |
| **ALREADY FIXED** | Content changed since last audit to use correct path | Record as fixed, do not re-flag |

**Distinction for migration/onboarding docs:** Bash code blocks containing `src/` paths are **actionable** — someone could copy-paste them and they'd fail. Prose describing old paths in a historical context is **intentional** and should not be flagged.

### Phase 4: Verify Each Path on Filesystem

For every stale reference found, check the filesystem:

```bash
# Replace <old-path> with the actual stale path found in Phase 2, e.g.:
test -f ~/hermes-cortex/src/scripts/foo.py && echo "EXISTS at old path" || echo "NOT FOUND at old path"

# Check canonical/new path
test -f ~/hermes-cortex/ops/scripts/foo.py && echo "EXISTS at canonical path" || echo "NOT FOUND at canonical path"

# Check symlinks
test -e ~/hermes-cortex/deploy && echo "deploy/ exists (symlink or dir)" || echo "deploy/ GONE — bare deploy/ refs are stale"
ls -la ~/hermes-cortex/deploy 2>&1  # confirm whether it is a live symlink
```

Also check the directory's parent to discover what *does* exist there:

```bash
ls <parent-dir-of-canonical-path> 2>&1
```

This uncovers cases like "the file doesn't exist at the stated path and the canonical directory doesn't even have it either."

### Phase 5: Load Previous Audit (if exists)

```bash
find ~/hermes-cortex/docs -iname '*stale*path*audit*' -o -iname '*audit*stale*'
```

If the find returns nothing, there is no previous audit — proceed to Phase 6 and note "no prior audit exists" in the report. Do not invent prior findings.

Read it and note:
- Which references were **previously flagged** vs. **newly discovered**
- Which references were **previously described as "works via symlink" but the symlink may now be removed**
- **Severity changes** from previous audit (e.g., low → high because symlink was removed)

### Phase 6: Check DOCS-INDEX.md for Deleted Doc Cross-References

When the previous audit noted a file was deleted (e.g., `docs/agent-inbox-setup.md`):
- Check if `docs/DOCS-INDEX.md` still links to it
- If yes, flag as broken cross-reference

### Phase 7: Check Missing Files Referenced by Docs

Some docs reference files by name without a full path — these could be missing entirely:

```
# In docs
(see cortex-bus-nginx.conf)
```

Search for the file at every plausible location:
```bash
find ~/hermes-cortex/ -name '<referenced-filename>' 2>/dev/null
```

### Phase 8: Produce Structured Report

Write the report with these sections:

1. **Summary** — counts: stale found, fixed since last audit, new discoveries, missing files
2. **Previously Identified — Status per item** — table: File, What Was Stale, Status (FIXED / STILL STALE)
3. **Newly Discovered** — table: File, Line, Stale Reference, Correct Path, Severity
4. **Missing Files** — paths that don't exist at any location on disk
5. **Filesystem State** — key paths and their current existence status
6. **Patterns & Recommendations** — grouped by migration pattern with priority

### Phase 9: Apply Fixes and Update Audit Report

After fixing stale paths, update the audit report itself (create `docs/stale-paths-audit.md` if it doesn't exist — as of 2026-09-08 it does not) to reflect what was fixed:

1. Update the **Summary** section to note fixes applied
2. Move items from "STILL STALE" to "ALL FIXED" (with date)
3. Append fix lines in "Newly Discovered" sections (with ✅)

When fixing template/placeholder paths (e.g., `src/auth/middleware.py` in `task-contract.md`), prefer using the `ops/` prefix as the updated example path rather than leaving them stale. Even conceptual examples benefit from being technically accurate.

## Pitfalls

- **The `deploy/` symlink may be gone.** Don't assume `deploy/nginx/hermes-services-apply.py` works via symlink unless you've confirmed the symlink exists. Check it every audit.
- **`src/` may still partially exist** (e.g., `src/loop-governance/` kept as backward compat, `src/cortex_bus/__pycache__/` as stale cache). A stale path pointing to a still-extant file is less urgent than one pointing to a deleted file, but it's still stale — the backward-compat copy is unsupported and may be removed. Always verify the **actual source file** exists, not just the directory.
- **Check whether `src/` root exists** — it may be a hollow shell with only `__pycache__` and `.pytest_cache` dirs. `test -d src/` returning true doesn't mean source files are there.
- **Migration docs are not stale.** A file like `docs/migration-*.md` intentionally documents old paths as they were during the migration. Flag only the **actionable code blocks** within them, not the historical prose.
- **Code blocks are actionable.** Even in a migration doc, a ````bash` code block with `bash src/scripts/cortex-update.sh` will **fail** if run. These are High severity.
- **Line numbers shift between audits.** Files get edited. Search by pattern, not by line number from the previous report. A previous report that says "line 586" may now refer to completely different content.
- **DOCS-INDEX.md lags behind file deletions.** When a doc file is deleted, the index often keeps its entry.

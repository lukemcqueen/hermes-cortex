# Stale-Path Audit Recipe — Hermes Cortex Docs

> Session: 2026-07-20 — Fresh stale-paths audit after July 15 baseline.
> Repo: ~/hermes-cortex/docs/ (83 .md files at time of audit)

## Context

The repo underwent a three-layer migration (`src/` → `core/` + `ops/` + `runtime/`, `deploy/` → `ops/install/deploy/`). During the migration:
- `src/` was hollowed out (only `src/agent_bus/__pycache__/` + `src/loop-governance/` backward compat remain)
- `deploy/` was a symlink → `ops/install/deploy/` — **symlink has since been removed**
- `skills/` moved from `src/skills/` to repo-level `skills/`
- `runtime/` was removed entirely

## Search Patterns Used

```bash
# Known stale prefixes
src/
deploy/              # WITHOUT ops/ prefix — distinguish from ops/deploy/ and ops/install/deploy/
deploy/nginx/
deploy/patches/
```

Watch out for false positives from:
- `ops/deploy/` — CORRECT path (for cloud-init, ansible, bootstrap)
- `ops/install/deploy/` — CORRECT path (for nginx configs, langfuse docker-compose)
- `docs/integration-audit.md` — intentional historical migration record
- `docs/stale-paths-audit.md` — the audit report itself

## File-System Verification Commands

```bash
# Check symlink status (critical — state changes between audits)
ls -la ~/hermes-cortex/deploy
test -d ~/hermes-cortex/deploy && echo "EXISTS" || echo "GONE"

# Check old path existence
test -f ~/hermes-cortex/src/scripts/manage/cortex-doctor.py && echo "old path EXISTS" || echo "NOT FOUND"

# Check canonical path existence
test -f ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py && echo "canonical EXISTS" || echo "NOT FOUND"

# Check directory listing at canonical path
ls ~/hermes-cortex/ops/install/deploy/nginx/ 2>&1
```

## Severity Classification

| Severity | Criteria | Examples |
|----------|----------|---------|
| **High** | Command in code block using stale path — will fail if run | `bash src/scripts/cortex-update.sh` in migration doc |
| **Medium** | Reader-directed path reference that resolves to nowhere | ``Edit `deploy/docker-compose.langfuse.yml` `` when deploy/ is gone |
| **Low** | Template example, user story AC, conceptual placeholder | `src/auth/middleware.py` in task contract template |

## Previous-Fixed Tracking

When updating an existing stale-paths audit, track items from the previous report:

1. Read previous `docs/stale-paths-audit.md`
2. For each flagged file, re-search for the stale pattern (don't trust old line numbers — they shift)
3. Classify each previous item as: FIXED, STILL STALE, or NEW (file deleted, content changed, path corrected)
4. Tag NEW items discovered that weren't in previous report

## Additional Nuances (from July 20 audit)

- **DOCS-INDEX.md** often has stale links to deleted files (e.g., `docs/agent-inbox-setup.md` was deleted but index still links it) — strike-through the entry with a redirect note rather than removing it entirely, so readers know where to go
- **Task-contract.md** template uses conceptual example paths (`src/auth/middleware.py`) — update these to the canonical `ops/auth/` prefix so they don't confuse future readers
- **Migration docs** (`docs/migration-*.md`) contain intentional old-path references in prose, but actionable code blocks with those paths are High-severity — patch code blocks, leave prose
- **`agent-bus-nginx.conf`** is referenced by name in docs but doesn't exist at any location on disk — document as a missing file
- **`mcp-servers/inbox-mcp.py`** doesn't exist — references to it are all dead unless restored
- **After fixing, always push to remote** before declaring the audit done — the stale-paths-audit.md in the repo must reflect the fix state

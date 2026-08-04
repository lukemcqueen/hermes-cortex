# Path Migration Procedure — Cross-Ecosystem Rename Audit

Use this when renaming a directory, service, or naming convention across the
entire codebase and deployment ecosystem (e.g., `src/` → `ops/`, `a2a` → `bus`).

## Critical First Step: Understand, Don't Blindly Fix

**Before touching any file, understand whether the file should exist at all.**
A stale systemd template for a service that was "removed — merged into bus"
should be DELETED, not path-fixed. If you're unsure about a file's purpose,
check the docs first (`grep -rn <service-name> docs/` for deprecation notices),
then ask if still unclear.

Pitfall: "I'll just fix the path, the user can delete it later" → the user
will be angry you didn't notice it shouldn't exist.

## Step 1: Survey — Find Every Reference

Search ALL three deployment ecosystems for the old term:

```
# 1. Repo source
grep -rn 'old-term' ~/hermes-cortex/ --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='*.yaml' --include='*.service' --include='*.conf'

# 2. Hermes config and deployed scripts
grep -rn 'old-term' ~/.hermes/scripts/ ~/.hermes/cron/jobs.json ~/.hermes/templates/ ~/.hermes/config.yaml ~/.hermes/memories/ ~/.hermes/plugins/ ~/.hermes/hooks/ ~/.hermes/bin/ ~/.hermes/SOUL.md

# 3. Agent infra (deployed copies that may not be synced from repo)
grep -rn 'old-term' ~/.hermes-cortex/scripts/ ~/.hermes-cortex/templates/ ~/.hermes-cortex/hooks/
```

**Within each location, check these file types:**
- `.py`, `.sh` — scripts with hardcoded paths
- `.md` — docs with path references
- `.json` — cron jobs (jobs.json has prompts with embedded paths), configs
- `.yaml` / `.yml` — config files
- `.service` — systemd/launchd templates
- `.conf` — nginx and other config templates

## Step 2: Identify Intentional vs Stale References

Not every reference needs changing. Classify each hit:

| Type | Action | Example |
|------|--------|---------|
| **Active code path** | Fix path | `script="~/hermes-cortex/src/web-cache/web_cache.py"` |
| **Comment/doc** | Fix if describing current state | `# Template source: ops/scripts/...` |
| **Migration doc** | Skip (intentionally documents old→new) | `cortex-path-migration-july2026.md` |
| **Historical plan** | Optionally update for currency | `.hermes/plans/2026-07-14-*.md` |
| **Stale file** | DELETE (file should not exist) | Orphaned template for merged service |
| **Auto-generated cache** | Skip (regenerates) | `state/skill-contents/`, `data/skill-miner-report.json` |
| **Cached cron output** | Skip (historical logs) | `cron/output/` |
| **Venv / node_modules** | Skip (third-party) | `.venv/`, `venv/`, `node_modules/` |
| **UUID hex match** | Skip (random hex digits) | `a2a0` in `bus-forwarder-state.json` |

## Step 3: Fix in Order

1. **Repo source first** (`~/hermes-cortex/`) — this is the canonical version
2. **Deploy after** — run `cortex-update.sh` to sync repo fixes
3. **For files NOT synced by cortex-update** (templates, non-script files):
   - Fix deployed copy directly with `sed` or `patch`
4. **Clean up orphaned directories** — `rm -rf ~/.hermes-cortex/old-name/`

## Step 4: Bulk Fix Technique

For mass fixes across deployed files, `sed` is faster than individual `patch()` calls:

```bash
# Fix paths across ALL deployed skills
find ~/.hermes/skills/ -name '*.md' -exec sed -i 's|old-path|new-path|g' {} \;

# Fix specific files
sed -i 's|hermes-cortex/a2a/|hermes-cortex/bus/|g' ~/.hermes-cortex/scripts/*.py

# Fix cron prompt embedded paths (inside JSON — be careful with escaping)
sed -i 's|skills/|skills/|g' ~/.hermes/cron/jobs.json
```

**After bulk sed: always verify** — run a verification grep to confirm.

## Step 5: Verification

Run a clean verification grep excluding noise:

```bash
echo "=== Remaining references ==="
grep -rn 'old-term' ~/hermes-cortex/ ~/.hermes/ ~/.hermes-cortex/ 2>/dev/null | \
  grep -v '__pycache__' | grep -v '.pyc' | \
  grep -v 'node_modules' | grep -v '.git/' | \
  grep -v 'cron/output/' | grep -v 'logs/' | \
  grep -v '.venv/' | grep -v 'venv/' | \
  grep -v 'state/skill-contents' | grep -v 'data/skill-miner' | \
  grep -v 'data/loop-events' | grep -v 'health-server/server.log' | \
  grep -v 'cortex-path-migration' | grep -v 'staleness-audit' | \
  { grep . || echo "✅ None"; }
```

The exclusions matter — caches, venvs, logs, and intentional migration docs
should NOT count as remaining references. Be explicit about what you excluded
and WHY.

## Pitfalls

| Pitfall | Why it's dangerous | How to avoid |
|---------|-------------------|--------------|
| **Only checked the repo** | Deployed copies and cron configs diverge from repo | Search all 3 ecosystems (Step 1) |
| **Blind path fix without understanding** | You might fix a file that should be deleted | Check docs for deprecation notices first |
| **Skipped cron prompts** | Crons have embedded paths in `jobs.json` prompts | Always grep `jobs.json` |
| **Skipped templates** | systemd/launchd templates in `.hermes/templates/` have WorkingDirectory paths | Always grep templates/ |
| **Skipped deployed skills** | `~/.hermes/skills/` has its own copies not synced by cortex-update | Run bulk sed on skills/ too |
| **Skipped `.hermes-cortex/`** | Agent infra scripts like web-cache live here, not in repo | Always check this location |
| **Skipped file content names** | Protocol identifiers like `a2a.agent-card` also need renaming | Search for the term in JSON content too |
| **Claimed "done" too early** | Erosion of trust — user believes you're wrong | Do Step 5 verification BEFORE reporting |

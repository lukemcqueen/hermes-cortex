# Missing Source Script — Referenced But Never Created

## Error Signal

A cron job has `last_status: error` with a message like:
```
ERROR: <script>.py not found at /home/$USER/hermes-cortex/ops/services/<path>/<script>.py
```

And the file doesn't exist anywhere in the repo either.

## Root Cause

The script was referenced in one or more of these locations but **never written**:

- `cortex-update.sh` — has a `register` line mapping the repo path to deploy path
- A wrapper script (`agent-card-daily.py`, etc.) — calls the missing script
- `docs/cron-schedules.md` — lists it as the cron's script
- `jobs.json` — the cron config references the wrapper

The design intended the script to exist but it was never created.

## Diagnosis Steps

```bash
# 1. Confirm the file is missing from the repo entirely
find ~/hermes-cortex -name "<script-name>*" 2>/dev/null

# 2. Find every reference to the missing script name
grep -r "<script-name>" ~/hermes-cortex/ ~/.hermes/ --include="*.py" --include="*.sh" --include="*.md" --include="*.json" -l

# 3. Check the wrapper script to understand expected interface
cat ~/.hermes/scripts/<wrapper>.py
#   → what env vars does it set?
#   → what CLI args does it pass?
#   → what output format is expected?

# 4. Check for existing similar scripts to use as template
ls ~/hermes-cortex/ops/services/*/  # sibling services
ls ~/hermes-cortex/ops/scripts/*/   # other scripts with similar interface
```

## Fix Pattern (from generate-agent-card.py creation)

1. **Determine the expected format.** Check for existing output files (e.g. `~/.hermes-cortex/a2a/agent-card.json`) or docs describing the schema.
2. **Create the script** following established patterns (shebang, argparse, env var defaults, Path for file ops).
3. **Fix the wrapper** — ensure it passes `AGENT_NAME` and any other required env vars that the runtime context doesn't provide.
4. **Verify end-to-end:**
   ```bash
   # Test the new script directly
   AGENT_NAME=esther CORTEX_DOMAIN=example.org CORTEX_A2A_PORT=14004 \
     python3 ~/hermes-cortex/ops/services/<dir>/<script>.py --output /tmp/test-out.json

   # Validate output
   python3 -c "import json; c=json.load(open('/tmp/test-out.json')); print(c['name'], c['url'])"

   # Test through the wrapper
   python3 ~/.hermes/scripts/<wrapper>.py
   ```
5. **Fleet-first:** commit the new file to the public repo first, push, then it's available to all agents.
   ```bash
   cd ~/hermes-cortex
   git add ops/services/<dir>/<script>.py
   git commit -m "feat(<area>): add <script>.py for <purpose>"
   git pull --rebase origin main && git push origin main
   ```

## Verification

```bash
# Script exists, executable, runs clean
python3 -c "
from pathlib import Path
g = Path.home() / 'hermes-cortex/ops/services/<dir>/<script>.py'
assert g.exists() and g.stat().st_size > 200
assert os.access(str(g), os.X_OK)
"
```

## Key Difference From Sibling References

| Reference | Problem | Fix |
|-----------|---------|-----|
| `stale-required-scripts.md` | File **exists in repo** but not deployed (repo reorg moved it) | Copy from actual repo path |
| `missing-source-scripts.md` | File **never existed** in repo (design gap) | Create the file from scratch |
| See §Intentionally Removed below | File **existed, was intentionally deleted** (architectural change) | Check git history; recreate with current config OR remove stale cron entry |

## Intentionally Removed — Script Purged From Repo But Cron Entry Remains

### Error Signal

Cron `last_status: error` with `Script not found: <path>` AND:
- File absent from all repo paths (empty `find` / `git ls-files`)
- `git log --all -- '**/<script>'` shows a **removal** commit, not a move/rename
- Removal commit message indicates design change (`purge`, `deprecated`, `replaced by`, `migration`, `stale`)

### Root Cause

A script intentionally removed from the repo (function deprecated, replaced by another system, architecture change) was never cleaned up from the cron schedule. The cron entry is stale.

### Diagnosis Steps

```bash
# 1. Check git history for the script
git -C ~/hermes-cortex log --all --oneline -- '**/<script>'
# → shows removal commit like "purge stale X references"

# 2. Read the old version to understand what it did
git -C ~/hermes-cortex show <removal-commit>^:<old-path>

# 3. Check what replaced it
git -C ~/hermes-cortex log --all --oneline --grep="<keyword from removal msg>"

# 4. Assess if the cron entry is still useful:
#    - Is the old system/endpoint still running (just updated URL/port)?
#    - Do existing monitoring scripts now cover this function?
```

### Fix: Two Options

#### Option A — Recreate with current config (function still relevant)

If the service the script monitored still exists (updated URL/port/auth):

```bash
# Extract current config from running service
grep 'ENV_VAR' ~/.config/systemd/user/<service>

# Test the endpoint directly
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:<port>/api/<endpoint>

# Recreate script with updated config, keep watchdog pattern
```

**Example:** `inbox-depth-watchdog.sh` was purged (commit `218d5de`: "purge stale agent-inbox references") but the bus was still running on port 8903 (old script used 8905). The monitoring function was still useful with `CORTEX_BUS_TOKEN` auth. Recreated at deployed path only.

**Design rule for recreated scripts:** Auth failures and network errors should be **tolerant** (silent exit 0, assume no backlog). Bus health is monitored separately. The recreated script fills a gap until the stale cron entry is cleaned up.

#### Option B — Remove stale cron entry (function dead)

If the old system no longer exists and monitoring is handled elsewhere:

```bash
hermes cron delete <job-id>
```

Only do this after confirming the function is genuinely dead:
- Old API/service port closed, no replacement
- Another script explicitly covers the same monitoring
- Git commit message says "replaced by X" and X is running

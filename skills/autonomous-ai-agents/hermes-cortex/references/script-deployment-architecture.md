# Hermes Cortex Script Deployment Architecture

## Directory Roles

| Directory | Purpose | Managed by |
|-----------|---------|-----------|
| `~/hermes-cortex/` | Git repo — source of truth for all scripts | `git pull` → `cortex-update.sh` |
| `~/.hermes-cortex/scripts/` | Canonical runtime location | `cortex-update.sh` register map (`HERMES_HOME=${HOME}/.hermes-cortex`) |
| `~/.hermes/scripts/` | Hermes Agent cron resolution | Copies from `~/.hermes-cortex/scripts/` via sync script |

## Deployment Flow

```
Repo source (ops/scripts/ or core/governance/)
    ↓  cortex-update.sh --force-all (via register() lines)
~/.hermes-cortex/scripts/<file>
    ↓  sync-scripts.sh (copy, not symlink — cron sandbox blocks external symlinks)
~/.hermes/scripts/<file>
    ↓  cron scheduler resolves script
Script runs
```

## Adding a New Script

1. Create the script in the repo under `ops/scripts/` or `core/governance/`
2. Add a `register()` line in `ops/scripts/cortex-update.sh`:
   ```bash
   register "ops/scripts/my-script.py" "${HERMES_HOME}/scripts/my-script.py"
   ```
3. Deploy via cortex-update:
   ```bash
   bash ~/hermes-cortex/ops/scripts/cortex-update.sh --force-all
   ```
4. Copy to cron directory:
   ```bash
   cp ~/.hermes-cortex/scripts/my-script.py ~/.hermes/scripts/my-script.py
   ```
5. If it's a cron script, register in `install-crons.sh`:
   ```bash
   create_cron "my-cron" "0 */6 * * *" "my-script.py" "" "" "" "origin" "" "true"
   ```

## ⚠ Critical: Cron Sandbox

The Hermes cron scheduler enforces a security sandbox: **scripts must resolve within `~/.hermes/scripts/`**. Symlinks that resolve outside this directory are blocked with:
```
Blocked: script path resolves outside the scripts directory
```

This means:
- **Do NOT use symlinks** to `~/.hermes-cortex/scripts/` — they will fail silently.
- Use **file copies** (`cp`) instead of symlinks.
- Files that exist as regular files in `~/.hermes/scripts/` work fine.
- After a cortex-update.sh deployment, re-copy changed scripts to `~/.hermes/scripts/`.

## Symlink Cleanup (June 2026 — REVERTED)

Previous approach replaced 42+ files with symlinks for consistency, but the cron sandbox blocked them. All external symlinks reverted to copies. See commit f48f73d for details.

## Pitfalls

- **`cortex-update.sh --force-all` requires `~/.hermes-cortex/bin/` to exist** — if missing, the `offline_knowledge` symlink fails and `set -e` stops the entire update.
- **New register lines require `--force-all`** — delta mode skips files with matching commit hashes. Always run `cortex-update.sh --force-all` after adding register lines.

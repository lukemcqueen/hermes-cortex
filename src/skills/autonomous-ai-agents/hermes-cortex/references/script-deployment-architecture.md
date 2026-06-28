# Hermes Cortex Script Deployment Architecture

## Directory Roles

| Directory | Purpose | Managed by |
|-----------|---------|-----------|
| `~/hermes-cortex/` | Git repo — source of truth for all scripts | `git pull` → `cortex-update.sh` |
| `~/.hermes-cortex/scripts/` | Canonical runtime location | `cortex-update.sh` register map (`HERMES_HOME=${HOME}/.hermes-cortex`) |
| `~/.hermes/scripts/` | Hermes Agent cron resolution | Symlinks → `~/.hermes-cortex/scripts/` |

## Deployment Flow

```
Repo source (src/scripts/ or src/loop-governance/)
    ↓  cortex-update.sh --force-all (via register() lines)
~/.hermes-cortex/scripts/<file>
    ↓  manual symlink (done once per new file)
~/.hermes/scripts/<file>  (symlink)
    ↓  cron scheduler resolves via .resolve()
Script runs
```

## Adding a New Script

1. Create the script in the repo under `src/scripts/` or `src/loop-governance/`
2. Add a `register()` line in `src/scripts/cortex-update.sh`:
   ```bash
   register "src/scripts/my-script.py" "${HERMES_HOME}/scripts/my-script.py"
   ```
3. Deploy via cortex-update:
   ```bash
   bash ~/hermes-cortex/src/scripts/cortex-update.sh --force-all
   ```
4. Create symlink for cron resolution:
   ```bash
   ln -sf ~/.hermes-cortex/scripts/my-script.py ~/.hermes/scripts/my-script.py
   ```
5. If it's a cron script, register in `install-hermes-crons.sh`:
   ```bash
   create_cron "my-cron" "0 */6 * * *" "my-script.py" "" "" "" "origin" "" "true"
   ```

## Symlink Cleanup (Done June 2026)

- 42 duplicate files in `~/.hermes/scripts/` replaced with symlinks to `~/.hermes-cortex/scripts/`
- 8 orphaned cortex scripts copied from repo to `~/.hermes-cortex/scripts/` and symlinked back
- 18 non-cortex files left as regular files (Hermes-native scripts like `auto-save-sessions.py`, `hermes-update.sh`, gbrain scripts)

## Pitfalls

- **Do NOT `cp` directly to `~/.hermes/scripts/`** — always use cortex-update then symlink. Direct copies create stale duplicates that drift from the source.
- **`cortex-update.sh --force-all` requires `~/.hermes-cortex/bin/` to exist** — if missing, the `offline_knowledge` symlink fails and `set -e` stops the entire update. Fix: `mkdir -p ~/.hermes-cortex/bin` before running.
- **The cron scheduler resolves scripts from `HERMES_HOME/scripts/`** which is `~/.hermes/scripts/`. It follows symlinks. The `install-hermes-crons.sh` script existence check uses `~/.hermes-cortex/scripts/`.
- **New register lines added to cortex-update.sh require `--force-all`** to deploy on an existing install (delta mode skips files with matching commit hashes).

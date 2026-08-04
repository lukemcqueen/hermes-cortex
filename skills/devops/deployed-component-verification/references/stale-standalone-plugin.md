# Stale Standalone Plugin Directory

## The Pattern

A plugin was previously deployed as a standalone copy with `chattr +i`
immutability. Later, a symlink was created to the repo source — but the
old immutable files *inside* the standalone directory were never removed.
Since the symlink replaces the *directory entry*, not the *file contents*,
Hermes loads the old stale copy instead of the repo source.

Discovered July 2026 — the governance enforcer plugin had both a fresh
symlink AND old immutable `__init__.py`/`plugin.yaml`/`README.md` files
from a prior deployment that were never cleaned up.

## Detection

```bash
# A symlinked plugin directory should NOT contain files directly
# If it shows files (not just the -> symlink arrow), stale copy
ls -la ~/.hermes/plugins/<name>/

# Iterate all plugins
for plugin in ~/.hermes/plugins/*/; do
    name=$(basename "$plugin")
    if [ ! -L "$plugin" ] && [ -f "$plugin/__init__.py" ]; then
        echo "STANDALONE: $plugin"
    elif [ -L "$plugin" ] && [ -f "$plugin/__init__.py" ]; then
        echo "STALE FILES inside symlink: $plugin"
        ls -la "$plugin"
    fi
done
```

## Fix

```bash
# 1. Unlock immutable files (ORCHESTRATOR-ONLY token — non-orch agents: request via Moses)
sudo hermes-plugin-lock unlock --orchestrator

# 2. Remove stale directory
rm -rf ~/.hermes/plugins/<name>

# 3. Fresh symlink to repo source
ln -sf ~/hermes-cortex/plugins/<source-name> ~/.hermes/plugins/<name>

# 4. Re-deploy (converts symlink to locked copy)
bash ~/hermes-cortex/ops/scripts/cortex-update.sh --force-all
```

## Prevention

Before deploying plugin updates, check for stale standalone files:

```bash
for p in ~/.hermes/plugins/*/; do
    if [ -L "${p%/}" ] && [ -f "$p/__init__.py" ]; then
        echo "STALE: $p has files despite being a symlink"
    fi
done
```

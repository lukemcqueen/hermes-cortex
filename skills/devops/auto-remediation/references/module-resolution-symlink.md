# Module Resolution Symlink Fix — Reference

## Signal

In `hermes cron list` output, a `no-agent` script deployed under `~/steadfaste-fleet/` shows:

```
Last run: ... error: Script exited with code 1
stdout:
[offline-code-index] Index rebuild failed
Traceback (most recent call last):
  File ".../offline_code.py", line 33, in <module>
    from hermes_paths import ensure_scripts_path
ModuleNotFoundError: No module named 'hermes_paths'
```

The script adds `~/.steadfaste-fleet/scripts/` to `sys.path` first, then imports from `hermes_paths`, but that directory only contains cortex-deployed scripts (symlinks into `~/steadfaste-fleet/ops/scripts/`) — not the shared Hermes modules.

## Root Cause

Hermes shared modules (`hermes_paths.py`, `hermes_models.py`, `hermes_tz.py`, `platform_utils.py`) live in `~/.hermes/scripts/`. Scripts deployed via `~/steadfaste-fleet/ops/offline/` or `~/.steadfaste-fleet/scripts/` add the cortex scripts dir to `sys.path` but not the Hermes scripts dir. The import fails because the module isn't in either location the code checks.

## Fix

Symlink the 4 shared modules from `~/.hermes/scripts/` into `~/.steadfaste-fleet/scripts/`:

```bash
cd ~/.steadfaste-fleet/scripts
ln -sf ~/.hermes/scripts/hermes_paths.py .
ln -sf ~/.hermes/scripts/hermes_models.py .
ln -sf ~/.hermes/scripts/hermes_tz.py .
ln -sf ~/.hermes/scripts/platform_utils.py .
```

## Verification

```bash
# 1. Verify symlinks exist
ls -la ~/.steadfaste-fleet/scripts/hermes_paths.py  # should show -> ~/.hermes/scripts/hermes_paths.py

# 2. Run the failing command (the cron script or its wrapper)
~/.hermes/bin/offline_code index  # should start embedding instead of crashing with ImportError

# 3. Syntax check on any further layers
python3 -m py_compile ~/steadfaste-fleet/ops/offline/offline_code.py && echo "syntax OK"
```

## When NOT to symlink

- If the module is versioned differently in the two locations (e.g. a cortex-specific fork of a Hermes module), symlinking could mask real version drift. Check that the `.hermes/scripts/` version is the authoritative copy.
- If the script explicitly overrides `sys.path` with a *different* directory than `~/.steadfaste-fleet/scripts/`, trace where it's looking and symlink there instead, or update the script's `sys.path` logic.
- If the import is genuinely missing from both locations (not a path issue), install the package properly via `uv pip install` or `pip install` in the script's active venv.

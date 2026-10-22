# Cron Script Symlink & Module Issues

## Self-Referencing Symlinks from rsync -a

**Problem:** After cortex-update.sh --force-all deploys scripts to
~/.hermes-cortex/scripts/, syncing to ~/.hermes/scripts/ with rsync -a
preserves symlinks as-is. When the symlink target path doesn't resolve
correctly, it creates self-referencing symlinks like
hermes_tz.py pointing to itself. Python errors with
'Too many levels of symbolic links' and imports fail with
ModuleNotFoundError.

**Detection:**
  find ~/.hermes/scripts/ -xtype l        # broken/self-ref symlinks
  find ~/.hermes/scripts/ -type l -ls     # all symlinks

**Fix:**
  cp -rL ~/.hermes-cortex/scripts/ ~/.hermes/scripts/  # dereference
  # Or fix individual files:
  rm -f ~/.hermes/scripts/hermes_tz.py
  cp ~/hermes-cortex/ops/scripts/hermes_tz.py ~/.hermes/scripts/
  # Same for hermes_models.py, platform_utils.py, hermes_paths.py

## Python ModuleNotFoundError in no_agent Cron Scripts

Cron scripts import sibling modules with bare names:
  from platform_utils import service_running
  from hermes_tz import format_timestamp
  from hermes_models import load_models_env
  from state_tracker import StateTracker

These fail when:
1. The sibling module is a self-referencing symlink (see above)
2. The sibling module is absent from ~/.hermes/scripts/
3. The script lacks sys.path.insert(0, script_dir) before imports

**Fix for missing sys.path (service-recovery.py had this bug):**
  _SCRIPT_DIR = Path(__file__).parent
  if str(_SCRIPT_DIR) not in sys.path:
      sys.path.insert(0, str(_SCRIPT_DIR))

**Verification:**
  python3 -c "import sys; sys.path.insert(0, '/home/esther/.hermes/scripts'); from hermes_tz import format_timestamp; print('OK')"

## cortex-doctor + grep = Safety Filter Block

Running cortex-doctor.py | grep triggers the terminal safety filter.
Run doctor raw without piping to grep, then scan the output visually.
# Stale Deploy Cleanup Procedure

## The Problem

`cortex-update.sh` uses `register()` to map repo source files to deploy
destinations. When a `register()` line is removed (file renamed, deleted,
or consolidated), the deployed copy stays on disk at the old path as an
orphan. Over time these accumulate — 34 orphans were found in one scan
(2026-07-23), totaling ~135KB of stale scripts.

## Detection

### Via Doctor (recommended)

```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py 2>&1 | grep -E "Stale deploy|Deploy source missing"
```

The doctor's `check_stale_deploys()` function:
1. Parses every `register()` call from cortex-update.sh
2. Resolves `${CORTEX_DEPLOY_HOME}` and `${HOME}` in destination paths
3. Scans `~/.hermes-cortex/scripts/` for `.py` and `.sh` files not in any mapping
4. Reports each orphan as a WARN with file path and size

Also checks:
- **Missing source files** — register() references a file that no longer exists in repo (FAIL)
- **Symlinks** — deployed file is a symlink instead of a real copy (WARN)

### Via Update Script

After any deploy, `clean_stale_deploys()` auto-runs:
```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh
```

Or manually:
```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh --clean-stale
bash ~/hermes-cortex/ops/scripts/cortex-update.sh --dry-run
```

## Fix

### Auto-fix (scripts/ directory only)

The auto-cleanup scans `~/.hermes-cortex/scripts/` for `.py` and `.sh` files
not in any `register()` destination. Removed files are logged.

### Manual cleanup (other deploy targets)

Some deploy targets are NOT auto-scanned:
- `~/.hermes-cortex/dashboard/` — dashboard service files
- `~/.hermes-cortex/bus/` — bus service files
- `~/.config/systemd/user/` — Linux systemd units
- `~/Library/LaunchAgents/` — macOS launchd plists

For these, check and remove manually:
```bash
# Check what's in the deploy dir vs what's registered
grep "CORTEX_DEPLOY_HOME.*dashboard" ~/hermes-cortex/ops/scripts/cortex-update.sh
grep "CORTEX_DEPLOY_HOME.*bus" ~/hermes-cortex/ops/scripts/cortex-update.sh
ls ~/.hermes-cortex/dashboard/
ls ~/.hermes-cortex/bus/
```

## Prevention

When you remove a `register()` line from cortex-update.sh:
1. Run `cortex-update.sh` to trigger auto-cleanup
2. Run the doctor to confirm no stale warnings remain
3. If removing a systemd unit or launchd plist, check `systemctl --user` or
   `launchctl list` for stale service entries too

## History

- **2026-07-23:** 14 stale register entries removed from cortex-update.sh
  (bus-sensor.py ×2, orch-install-bus.sh, change-readiness.sh, inbox-sensor.py,
  inbox-depth-watchdog.sh, cortex-bus-monitor.sh, inbox_watcher.py, mcp-inbox-proxy,
  agent-inbox server+plist, old offline_code_index_cron.sh path)
- **34 orphan files** detected in `~/.hermes-cortex/scripts/` after cleanup
- Auto-cleanup and doctor check added to prevent recurrence

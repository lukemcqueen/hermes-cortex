# Stale Deploy Cleanup & Auto-Doctor

## Problem

When a `register()` line is removed from `cortex-update.sh`, the deployed
copy stays on disk at `~/.hermes-cortex/scripts/`. Over time, these orphan
files accumulate. Similarly, after install/update, agents don't know if
their deployment is actually healthy.

## Solutions Added (2026-07-23)

### 1. Auto-Cleanup After Every Deploy

**File:** `ops/scripts/cortex-update.sh` — `clean_stale_deploys()` function

Runs automatically at the end of every deploy. Scans
`~/.hermes-cortex/scripts/` for `.py` and `.sh` files not in any
`register()` destination, then removes them.

```bash
# Manual invocation
bash ops/scripts/cortex-update.sh --clean-stale

# Dry-run (preview without deleting)
bash ops/scripts/cortex-update.sh --dry-run cortex-update.sh
```

### 2. Doctor Stale Deploy Detection

**File:** `cortex_doctor/checks.py` — `check_stale_deploys()` function

Runs in full doctor mode (not quick mode). Reports:
- Files in deploy dir not in any register() mapping → WARN
- register() source files that don't exist → FAIL
- Deploy files that are symlinks instead of copies → WARN

```bash
python3 ops/scripts/manage/cortex-doctor.py 2>&1 | grep "Stale deploy"
```

### 3. Auto-Doctor After Install & Update

**install.sh** — runs `cortex-doctor.py --quiet` after installation completes
(before final cleanup).

**cortex-update.sh** — runs `cortex-doctor.py --quiet` after update finishes
(after service verify, stale cleanup, cron install, governance lock cleanup).

Both use `|| true` so warnings never block the install/update.

### 4. Doctor --quick Mode

A fast subset of checks (35 checks vs 42 full) for quick health verification.
Includes: repo status, crons, scripts, services, system, config, governance,
install footprint. Skips: skills manifest, nginx config, stale deploys.

```bash
python3 ops/scripts/manage/cortex-doctor.py --quick
```

## Architecture

The doctor was modularized into `cortex_doctor/` package (8 modules):
- `config.py` — paths, constants, dynamic registries, AGENT_ROLE detection
- `results.py` — Results class
- `helpers.py` — run_bg, curl, helpers
- `checks.py` — all 14 check functions (role-aware)
- `fix.py` — apply_fixes auto-remediation
- `bus_alert.py` — bus alert dispatch
- `cli.py` — main entry point with arg parsing
- `__init__.py` — package exports

The old `cortex-doctor.py` is now a 34-line shim. To add a new check:
1. Create a `def check_xxx(res):` function in `checks.py`
2. Add to `all_checks` list in `cli.py`

# Stale sys.path.insert after `runtime/` → `core/` restructure

## What happened

The `runtime/` directory was removed from hermes-cortex and the module tree
moved to `core/`. Three cron scripts still had `sys.path.insert(0, ".../runtime")`,
causing import failures:

| Script | Cron job | Symptoms |
|--------|----------|----------|
| `workflow-sla-watchdog.py` | `workflow-sla-watchdog` | Script exit 1, traceback on import |
| `workflow-router.py` | `workflow-router` | Script exit 1, traceback on import |
| `workflow-dispatcher.py` | `workflow-dispatcher` | Script exit 1, traceback on import |

All three shared identical structure:

```python
import sys
sys.path.insert(0, "~/hermes-cortex/runtime")   # ← stale
from agent_bus.workflow.sla_watchdog import main            # ← module still exists, path was wrong
```

## Fix

In each file, changed the path string from `runtime` to `core`:

```python
sys.path.insert(0, "~/hermes-cortex/core")   # ← corrected
```

## Files patched

### Upstream (repo source)
- `hermes-cortex/ops/scripts/bus/workflow-sla-watchdog.py`
- `hermes-cortex/ops/scripts/bus/workflow-router.py`
- `hermes-cortex/ops/scripts/bus/workflow-dispatcher.py`

### Deployed (runtime)
- `~/.hermes-cortex/scripts/workflow-sla-watchdog.py`
- `~/.hermes-cortex/scripts/workflow-router.py`
- `~/.hermes-cortex/scripts/workflow-dispatcher.py`

## Verification

1. **Bare script run** — each script exit 0 (silent watchdog = all clear)
2. **Scheduler run** — `cronjob(action='run', job_id=...)` for each job
3. **last_status confirmed** — all three show `"ok"` in the job list

## Lesson

When a repo restructure renames a directory that Python scripts reference
via `sys.path.insert`, every script that injects the old path must be
found and updated. The scan pattern is:

```
search_files(pattern='hermes-cortex/runtime')
search_files(pattern='sys.path.insert.*runtime')
```

Both the repo source and the deployed copy must be patched. The repo
source comes first (upstream before one-off). Scheduler `cronjob(action='run')`
updates the internal `last_status` that watchdogs and doctors read —
bare script execution does not.

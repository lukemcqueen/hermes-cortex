# Doctor Self-Staleness Check (2026-07-23)

## Problem

When agents run the doctor, it checks the *deployed* version. If the repo has a newer version of the doctor (or any check), the doctor runs against stale code and misses issues — or doesn't have the latest fixes (like the enhanced bus E2E check).

## Solution

Added `_check_self_stale(res)` to `cortex_doctor/checks.py`:

```python
def _check_self_stale(res):
    deployed = Path(__file__).resolve()
    repo_source = CORTEX_REPO / "ops/scripts/manage/cortex_doctor/checks.py"
    if repo_source.is_file() and repo_source.stat().st_mtime > deployed.stat().st_mtime:
        res.add("Doctor version", "WARN",
                "Running older version — repo source is newer",
                "Run: cortex-update.sh --force-all")
    else:
        res.add("Doctor version", "PASS", "Deployed version matches repo")
```

Called at the top of `check_services()`.

## Stale Detection in Action

When the deployed doctor is older than the repo:
```
⚠️ Doctor version — Running older version — repo source is newer
  Run: cortex-update.sh --force-all
```

When up to date:
```
✅ Doctor version — Deployed version matches repo
```

## Companion: Enhanced Bus E2E

The `_check_bus_e2e` function was also expanded this session to 5 sub-checks:

| Check | What it tests |
|-------|--------------|
| Bus config (URL) | CORTEX_BUS_URL is set |
| Bus config (fallback) | CORTEX_BUS_FALLBACK_URL is set |
| Bus health | health endpoint responds ok |
| Bus self (send→read→archive) | Full cycle on own inbox |
| Bus stuck msgs | PGMQ API: stuck processing messages in own inbox |
| Bus handler | agent-message-handler.py exists |

# health-vector.py Schema Migration — 8 → 9 Elements

Migrated 2026-07-01 on Moses server.

## The Problem

`health-vector.py` had a `SERVICE_MAP` docstring referencing 9 elements (resources, services, no_errored_crons, no_stale_crons, nginx, ollama, mycortex, disk_ok, mycortex_sources_ok) but the actual `CHECK_FUNCTIONS` list contained only the old 8 check functions (nginx, ollama, mycortex, cortex-dashboard, langfuse-web, langfuse-worker, docker, hermes-gateway). This created a dangerous sync failure: the doc claimed 9-element support, the code returned 8, and downstream pollers misdiagnosed every index.

## Three Places That Must Stay in Sync

When migrating the schema, update ALL three:

| # | Location | What to change | Verification |
|---|----------|----------------|-------------|
| 1 | `SERVICE_MAP` (top-level doc comment, ~line 9) | Add/remove element names to match target | Read the comment — does it list the correct elements? |
| 2 | `CHECK_FUNCTIONS` (function list, near bottom) | Add/remove function references in same order as SERVICE_MAP | `len(CHECK_FUNCTIONS)` must equal target count |
| 3 | `--check` labels (in `main()`) | Update the labels list to match | `python3 health-vector.py --check` must show correct names |

## Migration Steps (8 → 9, as performed)

### 1. Add new check functions

Add these above `CHECK_FUNCTIONS`:

```python
def check_resources() -> int:
    """resources: disk and memory within thresholds."""
    ...

def check_services() -> int:
    """services: key services running (nginx, ollama, legacy autopilot)."""
    ...

def check_no_errored_crons() -> int:
    """no_errored_crons: 1 if no 'error:' in hermes cron list."""
    ...

def check_no_stale_crons() -> int:
    """no_stale_crons: 1 if no cron has 'never run' status."""
    ...

def check_disk_ok() -> int:
    """disk_ok: disk usage below 90%."""
    ...

def check_mycortex_sources_ok() -> int:
    """mycortex_sources_ok: legacy autopilot or process running."""
    ...
```

See the repo source at `~/hermes-cortex/ops/scripts/health-vector.py` for the full implementations with platform-aware checks.

### 2. Update CHECK_FUNCTIONS list

Replace old 8-element list with new 9-element list:

```python
CHECK_FUNCTIONS = [
    check_resources,
    check_services,
    check_no_errored_crons,
    check_no_stale_crons,
    check_nginx,
    check_ollama,
    check_mycortex,
    check_disk_ok,
    check_mycortex_sources_ok,
]
```

**Do NOT** keep orphan check functions (check_cortex_dashboard, check_langfuse_web, etc.) in the list — they are dead code until the schema includes them again.

### 3. Update --check labels

```python
labels = ["resources", "services", "no_errored_crons",
           "no_stale_crons", "nginx", "ollama", "mycortex",
           "disk_ok", "mycortex_sources_ok"]
```

### 4. Copy, restart, verify

```bash
cp ~/hermes-cortex/ops/scripts/health-vector.py ~/.hermes/scripts/health-vector.py
systemctl --user restart health-vector
sleep 2
curl -s http://127.0.0.1:8905/
# Should return {"v":[1,1,-1,-1,1,1,1,1,1], "h":"moses", "t":...}
# Expected: 9 elements; some -1 values expected (errored/stale crons)
python3 ~/.hermes/scripts/health-vector.py --check
# Should show correct labels matching each vector index
```

### 5. Commit to repo

```bash
cd ~/hermes-cortex
git add ops/scripts/health-vector.py
git commit -m "fix: align health-vector.py CHECK_FUNCTIONS with 9-element schema"
git push origin main
```

## Verification

After migration:
- `curl` returns exactly 9 elements
- `--check` output labels match SERVICE_MAP doc
- `orch-health-report.py` / `orch-fleet-watchdog.py` pollers correctly report service names
- Agent-registry.json health_vector_map matches

## Common mistakes

- **Updating only the docstring** — the code still returns old length
- **Forgetting --check labels** — human-readable output shows wrong names
- **Leaving orphan check functions** — dead code that misleads future maintainers
- **Not restarting the service** — old process continues serving stale vector
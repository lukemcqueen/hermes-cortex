# Remediation Pipeline — Script Map

All 6 scripts in the auto-remediation pipeline, their deployed paths, repo paths, and roles.

## Script Inventory

| Script | Size | Deployed (runtime) | Repo (source) | Schedule | Role |
|--------|------|--------------------|---------------|----------|------|
| `remediation-sensor.py` | ~20KB | `~/.hermes/scripts/` | `ops/scripts/health/` | `*/5 * * * *` | Detect issues, output JSON to cron output dir |
| `service-recovery.py` | ~13KB | `~/.hermes/scripts/` | `ops/scripts/health/` | `*/5 * * * *` | Restart failed systemd services, check critical services |
| `agent-remediate-apply.py` | ~9KB | `~/.hermes/scripts/` | `ops/scripts/agent/` | `*/10 * * * *` | Apply deterministic fixes from sensor output |
| `agent-apply-fixes.py` | ~11KB | `~/.hermes/scripts/` | `ops/scripts/agent/` | `*/10 * * * *` | Read remediation markers, search offline corpus, apply fixes |
| `inbox-sensor.py` | ~6KB | `~/.hermes/scripts/` | `ops/scripts/inbox/` | `*/10 * * * *` | Monitor inbox for new messages from peer agents |
| `inbox-flag.py` | ~4KB | `~/.hermes/scripts/` | `ops/scripts/inbox/` | `*/10 * * * *` | Flag remediation markers for agent-fixer to process |
| `inbox-depth-watchdog.sh` | ~1KB | `~/.hermes/scripts/` | **purged** (commit `218d5de`) | `*/1 * * * *` | Check bus inbox depth, silent when empty; recreated port 8903 + CORTEX_BUS_TOKEN auth |

## Pipeline Flow

```
remediation-sensor.py (every 5m)
  │  Detects: missing scripts, git issues, disk/memory pressure,
  │  service down, nginx issues, gbrain health, SSL certs, cron errors
  │  Output: JSON to ~/.hermes/cron/output/<job-id>/
  ▼
agent-remediate-apply.py (every 10m)
  │  Reads latest sensor output
  │  Applies deterministic fixes (nginx, service restart, disk cleanup)
  │  Skips unrecognized types (left for LLM-driven agent-fixer)
  │  Deduplicates via ~/.hermes/state/remediate-seen.txt
  ▼
agent-fixer (LLM-driven cron, hourly via auto-remediation skill)
  │  Handles complex issues the deterministic script can't fix
  │  Uses auto-remediation skill's 3-phase workflow
  ▼
inbox-sensor.py + inbox-flag.py (every 10m)
  │  Detect peer-agent messages needing remediation
  │  Write markers to ~/.hermes/state/remediate/
  ▼
agent-apply-fixes.py (every 10m)
  │  Reads markers, searches offline code corpus
  │  Applies known fix patterns, marks done
```

## Gitignore Context

The repo's `.gitignore` has `ops/scripts/` as a blanket ignore at line 101, with specific `!` exceptions for tracked files. When adding new scripts to the repo:

```bash
# Check which scripts are exempted
grep '!ops/scripts' ~/hermes-cortex/.gitignore

# Force-add new scripts
cd ~/hermes-cortex && git add -f ops/scripts/<subdir>/<new-script>.py
```

Current exceptions for pipeline scripts:
- `!ops/scripts/agent/orch-fleet-watchdog.py`
- `!ops/scripts/agent/contact-moses.sh`
- `!ops/scripts/health/service-recovery.py`
- `!ops/scripts/inbox/inbox-sensor.py`
- `!ops/scripts/inbox/inbox-flag.py`
- `!ops/scripts/inbox/inbox-depth-watchdog.sh` ← file purged from repo in commit 218d5de; exception is stale

## Script Status Notes

| Script | Status |
|--------|--------|
| `inbox-depth-watchdog.sh` | Source purged from repo in commit `218d5de` ("purge stale agent-inbox references — bus is the only messaging system"). Cron entry still active (`*/1 * * * *`). Recreated at deployed path only with updated bus config (port 8903, CORTEX_BUS_TOKEN auth). Stale cron entry not yet cleaned up upstream. |

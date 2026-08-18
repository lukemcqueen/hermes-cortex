---
name: cron-filesystem-fallback
description: "Read cron job definitions and execution history from filesystem when cronjob CLI is unavailable. Platform-agnostic fallback for cron mode, restricted approval, or limited shell contexts."
version: 1.0.0
category: devops
---

# Cron Status — Filesystem Fallback

## When to use

The `cronjob action='list'` CLI tool may be unavailable in restricted
execution contexts (cron mode, limited shell, approval restrictions).
Read cron state directly from the filesystem instead.

## Data sources

| What | Path | Format |
|------|------|--------|
| Job definitions + status | `~/.hermes/cron/jobs.json` | JSON array under `"jobs"` key |
| Execution history | `~/.hermes/cron/executions.db` | SQLite3 table `executions` |

## Reading job definitions (jobs.json)

Each job object contains these key fields:

- `id` — job UUID
- `name` — human-readable name (e.g. `agent-daily-bible-reading`)
- `last_status` — `"ok"`, `"error"`, or null — **the most recent run result**
- `last_error` — error string or null
- `last_run_at` — ISO 8601 timestamp
- `schedule.display` — cron expression (e.g. `"0 1 * * *"`)
- `script` — relative path resolved under `~/.hermes/scripts/`
- `no_agent` — `true` = watchdog script, `false` = LLM-driven
- `deliver` — `"origin"` (delivers to creator) or `"local"` (logs only)
- `state` — `"scheduled"`, `"paused"`, etc.
- `enabled` — boolean

**Filter for issues:** look for `last_status != "ok"` or `last_error != null`.

## Reading execution history (executions.db)

Table schema:

```sql
CREATE TABLE executions (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  source TEXT NOT NULL,
  process_id TEXT NOT NULL,
  pid INTEGER NOT NULL,
  process_started_at INTEGER,
  status TEXT CHECK(status IN ('claimed','running','completed','failed','unknown')),
  claimed_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  error TEXT
);
```

Query recent failures:

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('$HOME/.hermes/cron/executions.db')
cur = db.execute(\"SELECT job_id, status, started_at, error FROM executions WHERE status='failed' ORDER BY started_at DESC LIMIT 10\")
for r in cur.fetchall(): print(f'{r[0]}: {r[1]} | {r[2][:19]} | err={r[3][:80]}')
db.close()
"
```

## Cross-referencing both sources

A job may show `last_status: "ok"` in jobs.json (latest run succeeded)
but have historic failures in executions.db. This means the job
self-recovered — note it but don't re-fix.

**Order of operations:**
1. Read `jobs.json` — filter for current failures
2. Query `executions.db` — check for historic failures
3. If a job self-recovered between checks, report: "N previous failures
   (self-healed, no action needed)"
4. Only act on jobs with current `last_status != "ok"`

## Platform-aware health checks (companion to Phase 3)

| Check | Linux | macOS |
|-------|-------|-------|
| Disk | `df -h /` | `df -h /` |
| Memory | `free -h` or `/proc/meminfo` | `vm_stat` or `memory_pressure` |
| User services | `systemctl --user status <name>` | `launchctl list <name>` |
| Docker | `docker ps --format '{{.Names}} {{.Status}}'` | same |
| Cortex Doctor | `python3 ~/.hermes/scripts/cortex-doctor.py` | same |
| Ollama | `curl -s http://localhost:11434/api/tags` | same |
| Agent Bus | `curl -s http://localhost:8905/health` | same |

## Pitfalls

- **jobs.json is the authoriative latest state.** executions.db may have
  stale entries that were never cleaned up. Always trust jobs.json for
  "is it broken NOW?" and executions.db for "has it been broken recently?"
- **The cronjob CLI tool is preferred** when available — filesystem reads
  are the fallback, not the default.
- **executions.db schema may vary** across Hermes versions. Always
  `PRAGMA table_info(executions)` to confirm column names before querying.
- **No SQLite3 CLI?** Use Python's `sqlite3` stdlib module — it ships with
  every Python installation.
- **Zombie `running` rows:** after a hung LLM cron run, executions.db may
  keep a row stuck `running` with no live process. The job's claim TTL is
  300s; a manual `hermes cron run` during that window is a no-op (returns
  RC=0 but creates no new execution row). Check `hermes cron runs <job>`
  / executions.db, not the exit code, to see whether a trigger actually
  fired.
- **Stale job def after `hermes cron edit`:** the gateway/ticker may hold
  an in-memory copy of the job def (loaded at startup or last tick), so a
  `hermes cron run` immediately after an edit can still execute with the
  OLD model/provider. Verify with a fresh tick or next scheduled run; the
  scheduler re-reads jobs.json each tick (`cron/scheduler.py` run_one_job:
  "no in-memory cache"), but manual `run` claims race the refresh.
- **`last_status: null` is not an error:** a job deployed after its last
  scheduled slot (or one that hasn't hit its first slot yet) shows null
  status/run times — check the schedule before flagging it.
- **Cron model/provider drift:** an LLM cron configured with a model the
  provider doesn't host (e.g. `deepseek` on `custom:ollama-local` which
  only has `qwen2.5-coder:3b`) 404s instantly, falls back, 400s, then hangs
  until the 600s idle kill. Cross-check `jobs.json` model/provider against
  `curl -s localhost:11434/api/tags` (or the provider's model list). Fix:
  `hermes cron edit <job_id> --model <real> --provider <real>`. Full
  recipe: `references/cron-model-drift.md`.

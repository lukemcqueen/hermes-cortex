---
name: cron-cost-tracking
version: 1.0.0
description: SQLite-backed per-run token usage and cost tracking for Hermes cron jobs. Deploys cost_store.py and patches scheduler.py / cronjob_tools.py.
tags: [cron, cost, tokens, observability, hermes]
related_skills: [hermes-agent, cortex-update]
---

# Cron Cost Tracking

Records per-run token usage (input, output, cache) and estimated cost for every Hermes cron job into a SQLite database at `~/.hermes/cron/cron-costs.db`.

## Architecture

```
run_job() ──┐
            ├─ no_agent → record_run(tokens=0, cost=$0)
            ├─ LLM ok   → record_run(agent.session_*_tokens)
            └─ failure  → record_run(partial tokens, status="failure")
                        ↓
              cron-costs.db (SQLite WAL, ~/.hermes/cron/)
                        ↓
              cronjob(action='list') → includes last_run_cost + total_cost per job
              cronjob(action='costs') → aggregate stats across all jobs
```

## Files

| File | Location | Purpose |
|------|----------|---------|
| `cost_store.py` | `~/.hermes/hermes-agent/cron/` | SQLite store module |
| `scheduler.py` | `~/.hermes/hermes-agent/cron/` | **Patched** — 3 hooks to capture cost data |
| `cronjob_tools.py` | `~/.hermes/hermes-agent/tools/` | **Patched** — cost facade + costs action |
| `install-cron-cost-tracking.py` | `~/.hermes-cortex/scripts/` | Deployment/status/uninstall script |

## Deployment

```bash
# Apply patches and deploy cost_store.py
python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py

# Check status
python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py --status

# Re-apply after hermes update (force overwrites)
python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py --force

# Remove all patches and cost_store.py
python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py --uninstall
```

## Post-Update Recovery

After `hermes update --yes`, Hermes replaces its own source directory and the patches are lost. Re-run:

```bash
python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py --force
```

This can be added as a post-update hook or cron job.

## Querying Costs

```bash
# List all crons with cost data
hermes cron list
# → each job includes last_run_cost and total_cost fields

# Aggregate costs across all jobs
cronjob(action='costs')

# Single job costs
cronjob(action='costs', job_id='ee20583ee947')
```

## Cost Columns

| Field | Source | Description |
|-------|--------|-------------|
| `input_tokens` | `agent.session_input_tokens` | Prompt tokens |
| `output_tokens` | `agent.session_output_tokens` | Completion tokens |
| `cache_read_tokens` | `agent.session_cache_read_tokens` | Cache hit tokens |
| `cache_write_tokens` | `agent.session_cache_write_tokens` | Cache written tokens |
| `api_calls` | `agent.session_api_calls` | API call count |
| `estimated_cost_usd` | `agent.session_estimated_cost_usd` | Cost from provider pricing |
| `model` | job config | Model used |
| `provider` | job config | Provider used |

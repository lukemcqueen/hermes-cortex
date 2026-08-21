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
| `input_tokens` | `agent.session_input_tokens` | **Cache-MISS prompt tokens** (not total — see below) |
| `output_tokens` | `agent.session_output_tokens` | Completion tokens |
| `cache_read_tokens` | `agent.session_cache_read_tokens` | Cache hit tokens |
| `cache_write_tokens` | `agent.session_cache_write_tokens` | Cache-written (miss) tokens |
| `api_calls` | `agent.session_api_calls` | API call count |
| `estimated_cost_usd` | `agent.session_estimated_cost_usd` | Cost from provider pricing |
| `model` | job config | Model used |
| `provider` | job config | Provider used |
| `rate_version` | `RATE_VERSION` | Pricing schedule that produced `estimated_cost_usd` |

## ⚠️ Token semantics (do not unify with usage_audit)

`cron-costs.db`'s `input_tokens` is **already the cache-MISS portion**
(`usage_pricing.py: input_tokens = max(0, prompt_total - hit - write)`).
So `miss = input_tokens + cache_write_tokens`.

`usage_audit.jsonl`'s `prompt_tokens` is **TOTAL** (hit + miss), so there
`miss = max(prompt - hit, 0)`. The two stores price the same run differently
by design — keep them separate.

## Rate versioning & re-pricing (O1-S1, 2026-08-22)

Every row is stamped with the pricing schedule that produced its cost
(`rate_version`, default `2026-08-16` = DeepSeek hike). Rows recorded under
older pricing can be re-priced at current rates:

```bash
# Dry-run (no writes)
python3 ~/.hermes/hermes-agent/cron/cost_store.py --reprice --dry-run

# Apply (re-prices all rows not already at RATE_VERSION)
python3 ~/.hermes/hermes-agent/cron/cost_store.py --reprice

# Only the last N days
python3 ~/.hermes/hermes-agent/cron/cost_store.py --reprice --days 7
```

Current rates (USD/1M, mirror orch-daily-cost-report.py): hit `$0.007`,
miss `$0.22`, out `$0.66`, peak (01–04 & 06–10 UTC) ×2.

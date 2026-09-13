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

## Provider estimate is STALE — DB recomputes at local rates (O1-S3, 2026-08-26)

The scheduler passes `agent.session_estimated_cost_usd`, which comes from
hermes-agent's OWN pricing table (`usage_pricing.py`, snapshot 2026-07) — for
deepseek-v4-flash that is the **pre-hike schedule** (in $0.14 / out $0.28 /
hit $0.0028) and understates real spend by **~2.1–2.5×** (verified 2026-08-26:
63 rows cost $0.88 → $2.24 after reprice). Since the rate_version column
existed, every row was stamped `2026-08-16` while actually priced at the stale
table, so the old reprice guard skipped them all.

Fix (deployed in `cost_store.py`): `record_run()` ignores the provider estimate
and recomputes `estimated_cost_usd` from the token columns at the LOCAL
`RATE_VERSION` schedule (`_compute_cost`, same math as
`orch-daily-cost-report.py`). `reprice_runs()` guard is now a consistency check
(`abs(stored - recomputed) < 1e-4` → skip) instead of a version-only check, so
it self-heals rows recorded under any stale estimate. Apply with
`install-cron-cost-tracking.py --force` (source of truth:
`~/hermes-cortex/ops/scripts/cost_store.py`, copied to
`~/.hermes-cortex/scripts/`, deployed to `~/.hermes/hermes-agent/cron/`).

Caveat: the report (`orch-daily-cost-report.py`) recomputes from
`usage_audit.jsonl` and was ALWAYS correct; only the DB store (and
`cronjob(action='costs')` / `last_run_cost`) was understated. Interactive
`state.db` sessions still use the stale provider estimate — unaffected by this
fix.

⚠️ **DEPLOYED ≠ LOADED — a gateway restart is required to activate the fix.**
The scheduler imports `cost_store` lazily but Python caches the module in
`sys.modules` from the FIRST run after gateway start. A gateway started
BEFORE the fix was copied to `~/.hermes/hermes-agent/cron/cost_store.py`
keeps calling the OLD `record_run` (stale provider estimate) until
restarted. Verified 2026-08-26 (9befa548): esther gateway pid started
Aug 24, fix deployed Aug 26 08:26, rows at 10:51 KST STILL stale
(stored $0.006581 vs local-rate $0.028042); `--reprice` healed them.
Restart: `systemctl --user restart hermes-gateway` (user unit; restart
kills running cron sessions — schedule it, don't run it from inside a
cron job). After restart, run `cost_store.py --reprice` once to heal rows
recorded while the old module was loaded. Detection:
`fleet-hygiene.py cost-store` (repo ops/scripts/manage/) checks both the
deployed markers AND the latest-row math in one probe.

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

## ⚠️ Pitfalls that kill crons fleet-wide (learned the hard way)

**The audit write must never raise — it is inside the job's try block.**
`_FireAudit.write()` runs after a *successful* agent run; if it raises, the
outer `except` calls `write()` again (which raises again) and the exception
escapes `run_job`, so the job is reported **failed even though the agent
succeeded**. Symptom: `'_FireAudit' object has no attribute '<x>'` and 3+ failed
runs in a row on every LLM cron of that host.

**Hosts diverge on the injected attribute name** — an earlier patcher build wrote
`self.agent = agent`, a hand-edited install has `self._agent`. The snippet and
the init line must be normalized to ONE name *before* the snippet is inserted;
otherwise the fix for one host is the breakage for another. `_repair_audit_cache()`
now does this (normalize → remove the broken pair → collapse duplicates) and
`--status` prints a `BAD` line instead of reporting the audit split as OK.

**Diagnose in one command:**
```bash
f=~/.hermes/hermes-agent/cron/scheduler.py
grep -c 'getattr(self.agent' "$f"     # >0 on the broken variant
grep -n 'self\.agent = agent\|self\._agent = agent' "$f"   # which name the init sets
```

**Never hand-edit the injected snippet in the deployed copy.** The next
`cortex-update.sh` re-injects it (and a stale hand edit is what produced the
duplicate pairs). Fix the patcher in the repo, deploy, let the repair step run.

**`py_compile` is not enough — run the patcher through the real deploy.**
A repair step that used `re.subn` without `import re` passed every static check
and crashed only when `cortex-update.sh` executed it, turning the deploy-sync
gate red. The verification that counts is the deploy itself.

**Recovery for an already-broken host:** run `cortex-update.sh` (it deploys the
patcher and runs it) — the repair step heals the file in place. Then confirm:
`grep -c 'getattr(self.agent' <scheduler.py>` → 0, and fire the affected job with
`cronjob action='run' job_id=<id>` (a manual run is what refreshes `last_status`).

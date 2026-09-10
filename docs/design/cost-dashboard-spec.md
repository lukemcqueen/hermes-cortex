# Cost Dashboard Spec — fleet cost vs $10/day target + review queue depth (slice 8d7e1560)

Task: esther backlog slice 8d7e1560-4d97-4119-b3a0-3b3f22614fb9 [1/2] · Author: Esther · 2026-09-11
Scope: **spec only, no implementation** (parent story c579ef95: "Fleet cost under $10/day avg + halve review queue").

## 1. Metrics

| ID | Metric | Definition | Target / threshold |
|---|---|---|---|
| M1 | daily_cost | SUM(cron_runs.estimated_cost_usd) grouped by date(run_time), per agent-host | avg over trailing 7d < $10 |
| M2 | weekly_cost_7d_avg | 7-day rolling average of M1 | < $10; alert > $10, page > $15 |
| M3 | per_agent_daily | M1 split by agent (from agent-registry.json on moses) | no agent > $4/day (40% share) |
| M4 | per_job_daily | grouped by job_id; join cron job names via local crontab | top 3 jobs listed on dashboard |
| M5 | review_queue_depth | count of loop-governance loop_cycles with status='PENDING' + open review slices in tasks DB | trend ↓ toward baseline; alert if depth does not decrease week-over-week |
| M6 | cost_trend_delta | M2 vs previous 7-day window | > +20% WoW = warning |

## 2. Data sources

- **Authoritative cost DB:** `moses:~/.hermes/cron/cron-costs.db` (table `cron_runs`: run_time, input_tokens, output_tokens, cache_read/write_tokens, estimated_cost_usd, model, provider, rate_version). Access via `ssh mosesaaron` — the local per-host mirror is a **stale REPORTS mirror; never query it for fleet totals**.
- Verified live on 2026-09-11: schema confirmed (no `agent` column — agent identity must come from per-host job_id mapping or agent-registry.json); moses DB has 2,263 rows, all-time sum **$0.38** (well under target — deepseek-v4-flash pricing at RATE_VERSION 2026-08-16: hit $0.007/M, miss $0.22/M, out $0.66/M, 2.0× peak mult 01-04 & 06-10 UTC).
- Per-host cost DBs: each agent's `~/.hermes/cron/cron-costs.db`; fleet collector iterates hosts via ssh (moses is the aggregation point; gisu currently DOWN — see §5).
- **Review queue:** `moses:~/.hermes-cortex/data/loop-governance.db` table `loop_cycles` (status column) + tasks DB pending slices.
- **Output sink:** esther Victoria Metrics VM, docker `victoria-metrics` on **:14005** (verified live, HTTP 401 = auth-gated write). Push via `vmeter`/`prometheus` remote-write with `VICTORIA_METRICS_FALLBACK_URL` honored.

## 3. Alert thresholds

| Condition | Action |
|---|---|
| M2 (7d avg) > $10 | warning in daily cron report |
| M2 > $15 for 2 consecutive days | page Luke (Telegram) |
| M3 per-agent > $4/day | warning, name agent + top job |
| M6 WoW delta > +20% | warning with top-3 growing jobs |
| M5 depth flat or ↑ for 2 weeks | warning, list oldest pending review slices |
| gisu host unreachable during collection | "COULD NOT VERIFY gisu" — never silently skip |

## 4. Output format (fleet dashboard :14005)

- Push gauges per scrape: `fleet_cost_daily_usd{agent=…}`, `fleet_cost_7d_avg_usd`, `fleet_review_queue_depth`, `fleet_cost_wow_delta_pct`.
- Daily summary block in `orch-daily-cost-report.py` delivery: 7d avg, per-agent bars, top 3 jobs, queue depth trend.
- Dashboard labels follow agent-registry names (esther, moses, joseph, kustos, titus, gisu).

## 5. Known gaps / blockers to flag in implementation

1. **cron_runs has no agent column** — fleet attribution needs either (a) per-host collection (each host's own DB = that agent), or (b) a job_id→agent mapping table. Recommend (a): per-host ssh sweep, one row per host, tag with agent name. gisu rows currently uncollectable (host down since ~Sep 5, task 52dfe25e).
2. **Stale rates** — rows with old `rate_version` understate cost until `cost_store.py --reprice` runs (O1-S3, task dd583dfe: gateways cache old cost_store until restart). Dashboard must label M2 with data coverage caveat when any host has unrepriced rows.
3. **Provider estimates** are estimates (DeepSeek rate card), not invoices — dashboard footer states this.
4. Cache semantics: cron-costs `input_tokens` is ALREADY cache-miss portion; do not re-derive like usage_audit.jsonl (cost_store.py note).

## 6. Implementation sketch (for slice [2/2] — NOT in this task)

Collector script `fleet-cost-dashboard.py` on moses: ssh sweep per-host cron-costs.db + loop-governance.db → vm remote-write to esther:14005 → daily Telegram block appended to existing cost report cron. Hourly cadence acceptable; daily is sufficient.

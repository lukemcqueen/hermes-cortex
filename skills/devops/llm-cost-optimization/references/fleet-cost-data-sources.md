# Fleet cost data sources — where each number lives (verified 2026-08-21)

Reconciling a fleet LLM bill requires knowing which store holds which slice of
the truth. This is the map from the 2026-08-21 HC gaps party.

## The four stores

| Store | Path | Covers | Caveats |
|-------|------|--------|---------|
| `usage_audit.jsonl` | `~/.hermes/cron/` | Per **cron-run** tokens (prompt/completion, model, ts) | Cron-only (job_id present). `prompt_tokens` is **cumulative across turns** — a 150-iteration session re-sends growing context each call, so "26.4M prompt" ≠ one giant call (1M context cap makes that impossible). No cache split unless the cron-cost-tracking patch was extended. |
| `cron-costs.db` | `~/.hermes/cron/` | Per-run estimated cost (SQLite `cron_runs`) | Only fills while the scheduler patch is applied — rots on every `hermes update` (seam rot). Stored prices go stale after provider hikes (was June-July data on Titus). |
| `state.db` → `sessions` | `~/.hermes/` | **Per-session** tokens + cost, **all sources** (telegram/cli/subagent/cron) | **The interactive 70% lives here.** Columns: input/output/cache_read/cache_write tokens, reasoning_tokens, api_call_count, estimated_cost_usd, actual_cost_usd, cost_status, source, end_reason. Written live per turn. Cron rows are `cron_<jobid>_<ts>`. |
| `state.db` → `messages` | `~/.hermes/` | Per-message content | `token_count` is NULL in practice — do NOT try to reconstruct cost from messages; the sessions table is the reliable source. |

## Reading the sessions table correctly

```sql
-- interactive spend (excludes cron rows)
SELECT source, COUNT(*), ROUND(SUM(COALESCE(estimated_cost_usd,0)),2)
FROM sessions
WHERE source != 'cron' AND started_at >= <utc_epoch>
GROUP BY source ORDER BY 3 DESC;
```

⚠️ **Timezone trap:** `started_at` is epoch (`time.time()`, UTC-based). A naive
`datetime.utcnow() - timedelta(...)` then `.timestamp()` misreads the naive UTC
as LOCAL (+8.6h on KST hosts) and old sessions leak into the window. Build the
cutoff with an explicit tz:

```python
from datetime import datetime, timedelta, timezone
cutoff_ts = int((datetime.utcnow() - timedelta(days=N))
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .replace(tzinfo=timezone.utc).timestamp())
```

## What the 2026-08-21 reconciliation showed

- Esther (1 of 6 hosts): ~$0.83/day total — cron $0.38 + interactive $0.45
  (7-day, cache-aware, current post-hike rates). ×6 hosts ≈ $5/day, HALF the
  $10 budget.
- The user's billing page said $15-20/day → the gap is unproven from one host's
  data. Candidates: Titus interactive (4× Esther's message volume), other hosts,
  or under-counted session cost. The daily digest (`orch-daily-cost-report.py`)
  reconciles against billing over ~3 days.
- The "giant 26M-token runs" are ~99% cache-read → ~$0.29/run, NOT a bloat
  emergency. The real per-run cost is OUTPUT tokens from long iteration loops
  (90-145K out/run × $0.66/M). Raise `agent.max_turns` to let jobs finish rather
  than forcing manual session reset + summary paste (Luke 2026-08-21: the
  iteration cap was causing exactly the handholding he wanted gone).
- Peak-hour analysis must check `no_agent` first: all 19 peak-KST crons were
  no_agent scripts (zero API cost) — peak pricing only applies to LLM calls.
  Off-peak rescheduling only matters for LLM-driven jobs.

## Daily digest

`orch-daily-cost-report.py` (repo: `ops/scripts/manage/`, deployed to
`~/.hermes-cortex/scripts/`, cron `orch-daily-cost-report` 08:00 KST, no_agent):
aggregates usage_audit + cron-costs.db + sessions table into one Telegram
message. Shows total $, per-category (cron/session/subagent), cache-hit %,
peak-run count, top jobs, and **coverage %** (missing sources shown as GAPS,
never zeros — a cost report that hides missing data is worse than no report).

⚠️ Redactor gotcha: `agent/redact.py` treats `Tokens:` as a secret field name
(`_SECRET_CFG_NAMES` includes `token`) and masks the value as `***` in cron
delivery. Label the line `Tokens →` (or `Prompt/Comp:`) instead — verified fix.

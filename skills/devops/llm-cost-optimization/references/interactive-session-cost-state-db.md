# Interactive session cost — reading state.db (O7-S1, 2026-08-21)

## The discovery

The "invisible 70% interactive surface" was never a capture problem. Hermes
already persists per-session token + cost data LIVE (per turn, not only at
finalize) in the `sessions` table of `~/.hermes/state.db` — for telegram,
cli, and subagent sources. The daily cost report simply wasn't reading it.

Verified on Esther (2026-08-21): 14-day interactive totals read straight from
the table matched the provider-billing scale. Titus's state.db carries the
same schema (his message-level `token_count` is NULL, but the session-level
row is populated — the session row is the reliable source, NOT the messages
table).

## Columns (sessions table)

`id`, `source` (telegram/cli/cron/subagent/...), `started_at`, `ended_at`,
`end_reason`, `message_count`, `api_call_count`, `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_write_tokens`,
`reasoning_tokens`, `estimated_cost_usd`, `actual_cost_usd`, `cost_status`,
`cost_source`, `billing_provider`, `model`, `title`.

Rows update per turn (ended_at NULL while live) — a report can read yesterday's
sessions any time, no finalize hook needed.

## Reference query

```sql
SELECT source,
       ROUND(SUM(COALESCE(estimated_cost_usd,0)),2) AS cost_usd,
       SUM(input_tokens) AS fresh_in,
       SUM(cache_read_tokens) AS cache_read
FROM sessions
WHERE source != 'cron' AND started_at >= ?
GROUP BY source ORDER BY 3 DESC;
```

Cutoff: use `time.time() - days*86400` (epoch) — NOT
`datetime.utcnow().timestamp()` which misreads naive-UTC as local and drifts
~8.6h on KST hosts.

## Shape of interactive sessions (measured, Esther 14d)

- Median 128 API calls/session, max 487; median 109K output tokens/session.
- End reason: `session_reset` for 41/42 — every session dies by reset, paying
  a fresh cold start next time.
- Interactive cache-read dominates by volume (~99% hit) — cheap at hit price.
- The real cost driver is OUTPUT tokens (thinking) + the 95K incompressible
  floor (system 67K + schemas 28K) re-sent per call.

## Why this matters

- `usage_audit.jsonl` is job_id-keyed (cron-only) — it can NEVER show
  interactive spend. The sessions table is the only complete source.
- A daily digest should union cron (usage_audit + cron-costs.db) with
  interactive (sessions table) — otherwise the biggest number stays invisible.
- Don't build a "session-end capture hook" — Hermes already does it. The gap
  is read-side only.

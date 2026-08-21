# Session Telemetry & Reporting Pitfalls (2026-08-21, O1-S2/O7-S1)

Session-specific detail behind the llm-cost-optimization playbook: how the
fleet's interactive (non-cron) spend is actually stored, and three traps hit
while building the daily cost digest.

## Interactive cost is in state.db `sessions` — not in usage_audit

`usage_audit.jsonl` is job_id-keyed and cron-only. The interactive surface
(telegram/cli/subagent sessions — often ~70% of a fleet's bill) lives in the
`sessions` table of `~/.hermes/state.db`. Verified 2026-08-21 on Esther and
Titus:

- Columns present: `input_tokens`, `output_tokens`, `cache_read_tokens`,
  `cache_write_tokens`, `reasoning_tokens`, `estimated_cost_usd`,
  `actual_cost_usd`, `cost_status`, `cost_source`, `billing_provider`,
  `billing_mode`, `model`, `source`, `ended_at`, `end_reason`, `api_call_count`,
  `message_count`, `tool_call_count`.
- **Live per turn**: a running session has `ended_at = NULL` and the token/cost
  fields are already populated (checked mid-session: cost=$0.35, 523K input,
  82M cache-read while still open). No session-end hook needed to capture cost.
- Per-message `token_count` in the `messages` table is NULL on every host —
  content is stored, tokens are not. The per-SESSION aggregates are the only
  real token data.
- All-time Esther sample: telegram $24.07 vs cron $10.15 vs cli $0.60 vs
  subagent $0.39. Last 7d: telegram $2.79 / cli $0.18 / subagent $0.06.

Query the digest uses:

```sql
SELECT source, COUNT(*), ROUND(SUM(COALESCE(estimated_cost_usd,0)),2),
       ROUND(SUM(COALESCE(input_tokens,0))/1e6,1),
       ROUND(SUM(COALESCE(cache_read_tokens,0))/1e6,1)
FROM sessions
WHERE source != 'cron' AND started_at >= ?
GROUP BY source ORDER BY 3 DESC;
```

A 7-day interactive sample showed 6M fresh input vs **613M cache-read (~99% hit
on interactive)** — the interactive surface is expensive by VOLUME, not by miss
rate.

## Trap 1 — sessions.started_at is epoch; naive-UTC .timestamp() is wrong

`sessions.started_at` stores `time.time()` (UTC-based epoch). Building the
cutoff as a naive UTC datetime and calling `.timestamp()` misreads it as LOCAL
time — an 8.6-hour shift on KST hosts that silently mis-filters sessions by
~9 hours. Correct form:

```python
cutoff_ts = int(cutoff.replace(tzinfo=timezone.utc).timestamp())
```

Regression-test with an old-session row (e.g. 9 days back) that MUST be
excluded — the bug otherwise passes because the new row is included either way.

## Trap 2 — the secret redactor masks "Tokens: <value>"

`~/.hermes/hermes-agent/agent/redact.py` treats `Tokens:` as a secret field
name — `_SECRET_CFG_NAMES` includes `token`, so `Tokens: 85M in / 0.6M out`
gets its value masked to `***` by `redact_sensitive_text()`. This fires in the
cron delivery path (the saved output file literally contains `***`). The value
alone (`85M`) passes; the `Tokens:` prefix triggers it.

Fix: use a label that isn't a secret-key name — `Tokens → 85M` verified to
pass. Add a regression test asserting the literal number survives.

Diagnostic recipe (verify any cron-number masking):

```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.hermes/hermes-agent')
from agent.redact import redact_sensitive_text
print(redact_sensitive_text('Tokens: 85M in / 0.6M out'))  # masked
print(redact_sensitive_text('Tokens → 85M in / 0.6M out')) # clean
"
```

## Trap 3 — cost-store patch seam rots silently

`install-cron-cost-tracking.py` patches scheduler.py / cronjob_tools.py and
deploys cost_store.py into the Hermes source tree. Every `hermes update`
replaces that tree — the patches and store vanish. Verified: `--status` showed
9× MISS on Esther and cron-costs.db had only 2 days of rows while the fleet was
billing $15–20/day. A sparse cost DB is the symptom of a dead patch, not low
spend. Run `--status` before trusting cost data; wire auto-reapply into the
post-update hook.

## Report design (what the digest learned)

- Coverage % is a first-class field: missing sources show as GAPS, never as
  zeros (fake-precise numbers are worse than no numbers).
- $ before/after comparisons are confounded (Aug-16 price hike + model
  migration happened together) — use token/cache-hit metrics as primary, $ as
  secondary.
- A no_agent cron whose script output IS the report costs zero LLM tokens.

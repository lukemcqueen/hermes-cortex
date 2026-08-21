# DeepSeek Cache Economics — verified mechanics & numbers (2026-08-21)

Source: api-docs.deepseek.com (pricing + kv_cache/thinking_mode guides), fetched
2026-08-21. Cross-checked against Luke's actual billing page.

## Pricing (deepseek-v4-flash, USD per 1M tokens)

| Component | Before Aug-16-2026 | After (current) | Multiplier |
|-----------|-------------------|-----------------|------------|
| Cache-hit input | $0.0028 | $0.007 | 2.5× |
| Cache-miss input | $0.14 | $0.22 | 1.57× |
| Output | $0.28 | $0.66 | **2.36×** |
| Peak hours (01–04, 06–10 UTC) | — | 2× all rates | 2× |

deepseek-v4-pro: hit $0.022 / miss $0.66 / out $1.98 off-peak. v4-flash
context 1M, max output 384K. The hike went live ~2026-08-16 16:00 UTC and
roughly doubled Luke's fleet bill ($8 → $15–20/day).

**Cache-hit vs miss spread: $0.22 / $0.007 = 31×.** This is THE cost lever.
A 26.4M-token run: $0.18 at 98% hit, ~$5.81 at all-miss.

## Cache mechanics (from the official kv_cache guide)

- Enabled by default; automatic. Each request constructs a disk cache.
- **Prefix matching:** a cache hit requires the prefix to FULLY match a
  persisted prefix unit. Sliding-window attention means each cached prefix is
  an independent complete unit.
- Prefix units are persisted at request boundaries (end of user input, end of
  model output) and when a common prefix is detected across requests.
- TTL: "usually within a few hours to a few days" after last use. Weekly jobs
  often expire between runs.
- Cache construction takes seconds — first request after a change misses, then
  identical prefixes hit.
- API exposes `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` per
  request (usage object). Hermes exposes them as `agent.session_cache_read_tokens`
  / `session_cache_write_tokens`.

## Thinking mode (from the thinking_mode guide)

- Enabled by DEFAULT with effort **high**. Toggle (OpenAI format):
  `{"thinking": {"type": "enabled/disabled"}}` or `reasoning_effort: none`
  (Anthropic format `reasoning: {effort: none}` also disables).
- Effort mapping: low→medium, high→high, xhigh→high, max→max.
- **Thinking tokens bill as OUTPUT and never cache.** Measured: a normal
  session burned 55K thinking vs 9K answer tokens (6×). Firing the same cron
  with `reasoning_effort: none` cut completion tokens 12,829 → 5,881 (−54%).
- Hermes cron knob: `hermes cron edit <id> --reasoning-effort none` (valid:
  none, minimal, low, medium, high, xhigh, max, ultra; empty clears).

## The 31× math (why cache-hit rate dominates)

Esther's fleet, 13 days: 650M prompt / 5.5M completion tokens (118:1 ratio).
- All-miss: 650M × $0.22/M ≈ $143 → $11/day on one host's crons
- 90% hit: 650M × (0.9×0.007 + 0.1×0.22) ≈ $18.4 → $1.4/day
- Output: 5.5M × $0.66 ≈ $3.6 total — noise next to input.

## Prompt_tokens are cumulative, not per-call

usage_audit's `prompt_tokens` sums every API call in the run. A "26.4M-token
run" = ~100+ turns of growing context re-sent (1M context cap makes a single
26M call impossible). Per-turn floor on this fleet ≈ 67K (skills index 15.8K,
tool schemas 28K, SOUL 3.9K, AGENTS 2.7K, platform instructions ~15K).

## Session-continuation model (verified arithmetic)

System 67K, avg new content/turn 6.3K, hit $0.007/M, miss $0.22/M.
Correct cache-aware model: history re-sends are HITS; only new content misses;
system prompt cold once per session.

| Pattern | Cost | Note |
|---------|------|------|
| 1×150 turns | $0.79 | 70M history tokens at hit price |
| 3×50 turns | $0.48 | 3 cold system starts |
| 5×30 turns | $0.45 | 5 cold system starts |
| 1×150 with bust every 10 turns | $2.39 | churn = 3× the stable case |

## Fleet-specific findings (2026-08-21 audit)

- 14/17 agent crons were pinned to `deepseek-chat` (retired 2026-07-24) — the
  canonical source (ops/install/cron-manifest.yaml) still had it; live
  `hermes cron edit` edits were reverted by the next cortex-update.
- 12% of cron runs landed in peak (2×) hours.
- Interactive sessions (Titus) ≈ 70% of weekday spend and were invisible to
  cost tracking (usage_audit is job_id-keyed, cron-only).
- cron-costs.db had 2 days of data on Esther (patch rotted on a hermes update)
  and old pricing on Moses — no rate-version column.

## Absorbed from llm-cost-engineering's deepseek-cache-cost-mechanics.md (2026-08-22)

- **Output includes thinking tokens** in the pricing above ($0.66/M off-peak,
  $1.32/M peak). Thinking is never cached.
- Peak pricing applies to ALL rates: hit $0.014, miss $0.44, output $1.32
  per 1M during 01:00–04:00 & 06:00–10:00 UTC.
- **Where the split is recorded:** usage_audit.jsonl did NOT record the cache
  split; cron-costs.db has cache_read/cache_write columns (patch-derived).
  Always check which store actually captured the field before trusting it.

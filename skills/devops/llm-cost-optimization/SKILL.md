---
name: llm-cost-optimization
description: "Cut LLM API spend: cache-hit rate, thinking mode, telemetry."
version: 1.1.0
category: devops
platforms: [linux, macos]
aliases:
  - llm-cost-engineering
metadata:
  hermes:
    tags: [cost, cache, tokens, llm, deepseek, observability, spending]
    related_skills: [cron-cost-tracking, cron-cost-scheduling]
---

# LLM Cost Optimization

Class-level playbook for reducing LLM API spend on a fleet of agents. Built from
the 2026-08-21 HC gaps party (Luke's fleet: $8/day pre-hike → $15–20/day after
DeepSeek's Aug-16-2026 price increase; target <$10/day).
Consolidated 2026-08-22: absorbed llm-cost-engineering (pricing mechanics,
audit reading, installer pitfalls, verification).

## The core insight: cache-hit rate IS the cost

For DeepSeek v4-flash (and most providers with automatic prefix caching), the
price spread between cache-hit and cache-miss input tokens is **~31×**
($0.007/M hit vs $0.22/M miss off-peak). Output tokens are a distant second
driver. Every cost conversation starts with: **what is the cache-hit rate, and
is the prefix stable?**

| Scenario (50M prompt tokens/day) | $/day |
|----------------------------------|-------|
| 95% cache hit | ~$1.2 |
| 80% cache hit | ~$4.5 |
| 70% cache hit | ~$8.5 |
| 50% cache hit | ~$13.6 |

## Cache mechanics (provider-agnostic rules)

1. **Prefix-based, automatic.** A request hits cache only if its prefix fully
   matches a persisted prefix unit. No config to enable; the API reports the
   split (`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`).
2. **TTL is hours-to-days** after last use. Weekly jobs often go cold between
   runs; daily/hourly jobs stay warm.
3. **Cache construction takes seconds** — the first request after any change is
   a miss, then identical prefixes hit. Model migration = cold cache for ~1 run.
4. **The prefix is the system prompt + prior conversation.** ANY byte change in
   the system prompt (memory write, skill load, dynamic content, timestamp)
   busts the entire prefix — all history re-bills at miss price.
5. **`prompt_tokens` in audit logs is cumulative across turns**, not per-call.
   A 26M-token "run" is a long session (100+ turns re-sending growing context),
   not a single giant call — 1M context limits make single calls impossible.

## The five levers (ranked)

1. **Byte-stable system prompt** (biggest lever). Write memory at session end,
   never mid-session; keep skills-index ordering stable; no timestamps/random
   content in the system prompt; move dynamic content to the END of the prompt
   so the stable prefix keeps caching.
2. **One long session per domain, not many short ones.** Turn N+1 reuses
   turns 1..N as its prefix → ~100% hit after the first turn (see
   session-continuation economics below). Splitting work across tiny sessions
   resets the prefix every time and pays the 67K system-prompt cold start again.
3. **Keep cron prompts + skill lists stable.** Don't edit hot jobs casually;
   hourly jobs stay warm all day only if prompt and skill set don't churn.
4. **Measure the split per run.** `usage_audit.jsonl` should carry
   `cache_read_tokens`/`cache_write_tokens`; without the split every cost claim
   is a guess. Verify capture is actually LOADED (gateway restart), not just
   patched on disk — see the deployed≠loaded pitfall.
5. **Off-peak scheduling** (2× peak pricing on DeepSeek: 01:00–04:00 &
   06:00–10:00 UTC). Real but small — ~$1/day ceiling on a fleet; never move
   daytime-service or overnight-orchestrator crons; cadence consistency beats
   the specific hour (moving a cron can bust its prefix cache).

## Thinking mode bills as OUTPUT

Thinking/reasoning tokens are output-priced and NEVER cached. On a thinking
model, reasoning can be 6× the answer text (55K thinking vs 9K answer in a
normal session). **Disable thinking on mechanical jobs** (`reasoning_effort:
none` on dreams, briefings, prunes, eval) — verified −54% output tokens on the
same job. Keep it on reasoning-heavy work (orchestrator decisions, diagnosis,
evaluation). Pin via the cron manifest so it survives deploys, not just live
jobs.json (live edits get reverted by cortex-update).

## Session-continuation economics (same session vs new)

Same-session continuation is CHEAPER and better, because re-sent history is a
cache hit (~31× cheaper than fresh content):

| Pattern | Cost (modeled) |
|---------|----------------|
| 1×150 turns (same session) | $0.79 |
| 3×50 turns (3 sessions) | $0.48 |
| 5×30 turns (5 sessions) | $0.45 |

The long session costs only ~$0.30 more and that gap is history re-sends at hit
price — the cheapest thing you can buy. The real enemies:

1. **Cache busts** (memory write mid-session, skill load, dynamic system
   prompt): one bust every 10 turns turns $0.79 into $2.39 (3×).
2. **The system prompt is a per-session tax** (67K on this fleet): fewer
   sessions = fewer cold starts. Shrinking it (skills index, tool schemas)
   lowers the tax on every session.
3. **Thinking tokens are the same either way** — session structure doesn't
   affect them; only `reasoning_effort: none` does.

Rule: keep one session while the topic is coherent AND the prefix stays stable.
Start fresh only on a context switch or when the session is so large that
compaction/rewrites fire (those bust cache worse than a fresh start).

## Reading usage_audit.jsonl (what the numbers actually mean)

- `prompt_tokens` per run is CUMULATIVE across turns — a 26M-token "prompt" is a
  long session re-sending growing context, NOT one 26M-token call (context cap
  makes that impossible).
- The audit has NO cache split unless the cron-cost-tracking patch was extended —
  cache hit/miss is the single most important missing field; add it first.
- Interactive/subagent spend never lands in usage_audit (job_id only) — the
  biggest wallet share (Titus ~70%) is invisible until session capture exists
  (see `references/interactive-session-cost-state-db.md` — state.db sessions
  table has interactive tokens+cost live).

## Cost telemetry requirements

- Per-run cache-hit/miss split (the API returns it; store it).
- Per-host AND per-category (cron/session/subagent) aggregation — interactive
  sessions are often the biggest surface and the least tracked.
- Coverage % in reports: missing hosts/fields show as GAPS, never as zeros.
  Fake-precise numbers are worse than no numbers.
- Rate-version the pricing table: mixing old-rate history with new creates a
  fake "spike". Token-normalized metrics, with $ as a secondary view — any
  $ before/after comparison is confounded by price changes + model migrations.
- Reconcile the daily report against the provider billing page weekly.

## Procedure

1. **Get the ground truth** — ask the user for the billing-page number (avg/peak
   per day) and the target. Never trust a computed estimate over the bill.
2. **Measure before optimizing** — per-run cost is uncomputable without the
   cache-hit/miss split. Check cron-costs.db has data AND current prices (rate
   drift makes stored costs lie). Add cache capture to usage_audit if missing.
3. **Find the cache hit rate** — the 31× lever dominates everything. If you can't
   measure it, you can't rank any fix (a 26M-token run = $0.18 hit vs $5.81 miss).
4. **Attack in order:** cache discipline → thinking-mode off on mechanical jobs →
   off-peak re-timing → model migration → session compaction.
5. **Control for confounds** — price hikes and model migrations in the same window
   contaminate any $ before/after. Use token/cache-hit metrics as primary, $ as
   secondary.
6. **Report coverage %** — a cost report must show missing hosts/fields as gaps,
   never as zeros. Fake-precise numbers are worse than no numbers.

## Pitfalls

- **Deployed ≠ loaded.** Patching scheduler.py on disk doesn't affect the
  running gateway (long-lived daemon). Verify by firing a cheap cron and
  reading its audit line, not by grepping the file.
- **Live job edits get reverted.** `hermes cron edit --model/--reasoning-effort`
  writes jobs.json, but the next cortex-update re-registers crons from the
  source of truth (cron-manifest.yaml / install-crons.sh). Fix the SOURCE first,
  then the live jobs — or your "migration" silently reverts. The manifest and
  the installer's pin function must both change (14-cron deepseek-chat→v4-flash
  migration reverted exactly this way, 2026-08-21).
- **Cost-store patches rot on every `hermes update`.** Auto-reapply via a
  post-update hook (`install-cron-cost-tracking.py --force`); a missing
  cost_store.py shows as 9× MISS in --status. 2 days of data out of 13 seen
  2026-08-21.
- **cron-costs.db understated ~2× until O1-S3 (2026-08-26).** The provider
  estimate (`session_estimated_cost_usd`) uses hermes-agent's stale
  pre-hike pricing table for v4-flash (in 0.14/out 0.28/hit 0.0028 vs local
  0.22/0.66/0.007). Fixed in cost_store.py: record_run recomputes at the local
  schedule, reprice guard is now consistency-based (self-heals stale rows).
  The daily REPORT was always correct (recomputes from usage_audit); only the
  DB store under-reported. See cron-cost-tracking skill.
- **Installer patch index drift.** install-cron-cost-tracking.py splits patches
  at hardcoded indices ([:3]/[3:]); adding scheduler patches shifts the boundary
  and the new patches get applied to cronjob_tools.py. Update the slice boundary
  when adding patches. Its FAIL message ("marker not found") actually means the
  `old` text wasn't found — verify the real file state, not the installer's word.
- **Peak-by-design jobs.** Some crons (bus overnight, orch lifecycle) are peak BY
  DESIGN; re-timing them defeats their purpose. Never move daytime-service or
  overnight-orchestrator jobs.
- **Don't build a MAX_COST cap on unmeasured data.** A sane cap set against
  today's bloat kills legitimate jobs (a 26M-token run is $0.18 at hit rates).
  Measure first, cap later (per-job p95 + headroom).
- **cache_write_tokens=0 on every row = capture gap, not 100% hit rate (2026-08-29).**
  cron-costs.db shows `cache_write_tokens` 0 for ALL 4828 rows, so the naive
  `hit% = read/(read+write)` reads a fake 100%. Root cause is UPSTREAM
  (hermes-agent `agent/usage_pricing.py`): the cache_read side maps DeepSeek's
  top-level `prompt_cache_hit_tokens` (line ~1373) but the cache_write fallback
  chain (~1385–1400) checks only `details.cache_write_tokens`,
  `cache_creation_input_tokens`, `response_usage.cache_write_tokens` — NEVER
  DeepSeek's complementary `prompt_cache_miss_tokens`. Since
  `prompt_tokens = hit + miss`, the miss tokens land in `input_tokens` and the
  cost math stays correct (`miss = input + write`); only the hit-rate metric
  lies. **True hit rate = read/(read+input_tokens)** — measured 93–99% across
  all cron jobs (7-day window, 2026-08-29), so the system-prompt prefix IS
  byte-stable. Upstream fix candidate: add `prompt_cache_miss_tokens` to the
  cache_write fallback chain (task `orch-upstream-cache-write-fix`).

## Verification

- Cache-hit % visible per job/session (was unmeasurable before the split existed).
- Daily fleet cost report reconciles to the billing page within ±10% (documented
  scope: interactive sessions may be excluded).
- After a thinking-mode change: output tokens per run drop measurably; job output
  still parses per its output contract.
- After a model migration: cold-cache spike decays to plateau over 3-7 days; zero
  job failures; per-job hit-rate climbs to 60-90%+.

## References

- `references/deepseek-cache-economics.md` — canonical DeepSeek pricing table,
  cache rules, thinking-mode switch (absorbed llm-cost-engineering's
  deepseek-cache-cost-mechanics.md 2026-08-22).
- `references/opencode-relay-pricing.md` — opencode zen/go relay pricing:
  mirrors DeepSeek direct exactly (no markup; 4.4%+$0.30 card rail only),
  and the free-tier reality (NO free deepseek as of 2026-08-31 —
  deepseek-v4-flash-free listed but "Model is unavailable"; no pro-free).
- `references/fleet-cost-data-sources.md` — where each fleet cost number lives
  (audit files, DBs, billing page) — from llm-cost-engineering.
- `references/fleet-cost-levers-verified.md` — session-verified lever results.
- `references/daemon-restart-peak-pins-2026-08-21.md` — restart-gap and peak-pin
  session detail.
- `references/interactive-session-cost-state-db.md` — state.db sessions table as
  the interactive-cost source.
- `references/session-telemetry-reporting.md` — session-specific detail behind
  the playbook.

# ADR-0001: DeepSeek Model Contract + Pricing

- Status: accepted
- Date: 2026-08-24
- Author: Esther (facts verified from `ops/scripts/cost_store.py` +
  `~/.hermes-cortex/.env`)

## Context

Every LLM call in the fleet goes through DeepSeek. The pricing schedule
changed on 2026-08-16 (a ~2x hike on cache-miss), and the fleet's cost
model (cache-hit ratio, peak multipliers, per-job tracking) depends on
getting the contract exactly right. Fresh sessions kept re-deriving the
numbers from memory — which drifts.

## Decision

**Provider/model contract (env var NAMES — values live in `.env`):**

- Provider: `DEEPSEEK` (via `LLM_CRON_PROVIDER` in env)
- Main model: `deepseek-v4-flash` (via `LLM_CRON_MODEL`)
- Embedding: `nomic-embed-text:v1.5` (local Ollama, `EMBEDDING_MODEL`)
- Judge: `JUDGE_MODEL` env

**Pricing (USD per 1M tokens, source `ops/scripts/cost_store.py`):**

| Token class | USD/1M |
|---|---|
| Cache-hit input | $0.007 |
| Cache-miss input | $0.22 |
| Output | $0.66 |
| Peak multiplier (01:00–04:00 & 06:00–10:00 UTC) | 2× |

**Cost formula** (cost_store.py): input = prompt_total − hit − write;
output billed at $0.66/1M; peak hours double the total.

## Consequences

- **Cache-hit is the #1 cost lever**: a 98% hit rate vs 50% is ~$0.007 vs
  ~$0.11 per 1M input — a 15x spread. Prompt-stability work (byte-stable
  system prompts, no per-turn reordering) directly attacks this.
- **Thinking bills as output** — reasoning tokens are priced at output
  rates, so lean thinking configs matter.
- Pre-2026-08-16 rows in cron-costs.db used the older (cheaper) schedule;
  cost reports must note the baseline shift (O1-S1).
- The `MAX_COST` preflight guard (ADR-0002) is built on these numbers.

## References

- `ops/scripts/cost_store.py` (authoritative pricing constants)
- `docs/setup-reference.md` (run-type cost table)
- `~/.hermes-cortex/.env` (values — never committed)

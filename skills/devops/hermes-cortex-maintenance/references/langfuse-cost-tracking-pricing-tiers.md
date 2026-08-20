# Langfuse Cost Tracking — Pricing Tiers, Backfill, Verification (3.206+/3.207+)

Discovered 2026-08-11 while adding cost tracking to a self-hosted Langfuse
stack upgraded 3.206.0 → 3.207.0. **The repo's `docs/troubleshooting.md` §23
SQL is stale for 3.206+** — it inserts into `public.models` with legacy
`input_price`/`output_price` columns, which the worker no longer reads.

## Root fact: cost comes from `prices` + `pricing_tiers`, not `models.input_price`

In Langfuse 3.206+, the ingestion worker resolves cost via Prisma's
`model.Price` relation (`pricing_tiers` → `prices` table). A model row with
only `input_price`/`output_price` set produces `cost_details = {}` and
`total_cost = NULL` — **silently, no error**. Always verify with a test
generation before trusting the UI.

## The three inserts (model → tier → prices)

Prices are **per-token USD**. DeepSeek V4 Flash: $0.14/1M input = 0.00000014,
$0.28/1M output = 0.00000028.

```sql
-- 1. Model (project_id NULL = global, applies to all projects)
INSERT INTO public."models" (id, model_name, match_pattern, input_price, output_price, unit, tokenizer_config)
VALUES (gen_random_uuid()::text, 'deepseek-v4-flash', '(?i)^(deepseek-v4-flash)$', 0.00000014, 0.00000028, 'TOKENS', NULL)
ON CONFLICT DO NOTHING;

-- 2. Pricing tier (id MUST be <model_id>_tier_default — mirrors built-ins)
INSERT INTO public.pricing_tiers (id, model_id, name, is_default, priority, conditions)
SELECT id || '_tier_default', id, 'Standard', true, 0, '[]'::jsonb
FROM public.models WHERE model_name = 'deepseek-v4-flash'
ON CONFLICT DO NOTHING;

-- 3. Price rows — usage_type 'input'/'output' ONLY. NO 'total' row.
INSERT INTO public.prices (id, model_id, usage_type, price, project_id, pricing_tier_id)
SELECT gen_random_uuid()::text, m.id, ut.usage_type, ut.price, NULL, m.id || '_tier_default'
FROM public.models m
CROSS JOIN (VALUES ('input', 0.00000014::numeric), ('output', 0.00000028::numeric)) AS ut(usage_type, price)
WHERE m.model_name = 'deepseek-v4-flash'
ON CONFLICT DO NOTHING;
```

⚠️ **Never add a `total` price row.** When `usage_details` carries
input+output AND total, the worker prices all three and total is
double-counted (1500 tokens × 0.00000042 = $0.00063 instead of the correct
$0.00028). Built-in models (e.g. gpt-4o) have no `total` row either.

## Refresh the model-match cache (mandatory after any pricing change)

The worker caches model matches in Redis (`model-price-tiers:<project>:<model>`
keys) plus a local 10s TTL cache. A cached NOT_FOUND token survives a plain
worker restart — without clearing Redis, new prices stay invisible.

```bash
RP=$(grep LANGFUSE_REDIS_AUTH ~/langfuse/.env | cut -d= -f2-)
docker exec langfuse-redis-1 redis-cli -a "$RP" --scan --pattern 'model-*' \
  | xargs -r docker exec langfuse-redis-1 redis-cli -a "$RP" DEL
docker restart langfuse-langfuse-worker-1
```

## Backfill historical generations (ClickHouse mutation)

Ingestion only prices NEW traces. Existing rows need an async mutation (track
via `system.mutations`, poll `is_done=1`):

```sql
ALTER TABLE observations
UPDATE
  cost_details = map(
    'input',  toDecimal128(usage_details['input']  * 0.00000014, 12),
    'output', toDecimal128(usage_details['output'] * 0.00000028, 12)
  ),
  total_cost = toDecimal128(
    usage_details['input'] * 0.00000014 + usage_details['output'] * 0.00000028, 12
  )
WHERE type = 'GENERATION' AND provided_model_name = 'deepseek-v4-flash' AND total_cost IS NULL
  AND (has(usage_details, 'input') OR has(usage_details, 'output'));
```

- Rows with `usage_details = {}` are correctly left NULL (nothing to price).
- Result sanity check: `sum(total_cost)` should equal
  `sum(usage_details['input'])*0.00000014 + sum(usage_details['output'])*0.00000028`
  within per-row rounding (~$0.0002 on a $9 stack).
- After the mutation, OTLP-ingested rows may show populated `cost_details`
  but NULL `total_cost` column — the API derives totalCost from cost_details
  on read, so the UI is fine; a second mutation adding `cost_details['total']`
  makes the aggregate exact.

## Verification: query ClickHouse, not the API list endpoint

The public observations list endpoint loosely applies `trace_id` filters —
it returns your own live session's rows instead. Verify by exact name:

```bash
docker exec langfuse-clickhouse-1 clickhouse-client -q \
  "SELECT name, usage_details, cost_details, total_cost FROM observations WHERE name='cost-verify3';"
```

**API field names in 3.206+:** `costDetails`, `calculatedInputCost`,
`calculatedOutputCost`, `calculatedTotalCost` — NOT the legacy `totalCost`.
Dashboard code must read `calculatedTotalCost` first, then `totalCost`, then
fall back to local `_MODEL_PRICING`.

**`/api/public/traces` requires `fromTimestamp` in 3.207+** — returns 400
`InvalidRequestError: fromTimestamp is required` without it. The dashboard's
`_lf()` helper already appends a 7-day window; direct curl tests must add it.

## ClickHouse schema quirks (25.5)

- `traces` time column is `timestamp`, NOT `start_time`; `observations` uses
  `start_time`.
- No `events` table in this version — it's `event_log`.
- `mapGet` function does not exist — use bracket syntax `usage_details['input']`.
- Docker exec + heredoc psql silently swallows input — write SQL to a file and
  use `docker exec -i <container> psql ... < file.sql`.

## Deploy layout note (luke-server)

`~/langfuse/clickhouse-config.d/` is root-owned (no sudo) — the deployed
compose mounts from `~/langfuse/clickhouse-config-writable/` instead. Sync
config changes there, keep `chmod 644` (ClickHouse runs non-root, `:ro`
mounts must be world-readable). The repo compose pins Langfuse 3.207.0 while
deployed was 3.206.0 — after `cp` from repo, adjust only the mount paths to
`clickhouse-config-writable/`, then `docker compose down && up -d` (restart
does NOT re-read configs/images).

## Dashboard pricing (ops/services/dashboard/server.py)

`_MODEL_PRICING` was wrong: `deepseek-v4-flash` was priced at
$0.15/$0.60 per 1M (1.5e-7/6.0e-7) — real rate is **$0.14/$0.28 per 1M**
(1.4e-7/2.8e-7). The dashboard falls back to this dict when the Langfuse API
returns no cost, so a stale rate silently under/over-states spend.

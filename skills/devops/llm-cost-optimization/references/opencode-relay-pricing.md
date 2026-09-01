# OpenCode Relay (zen/go) Pricing & Free-Tier Reality

Verified 2026-08-31 against live `https://opencode.ai/zen/v1/models` and
`https://opencode.ai/docs/zen/` (plus the fleet's own `cost_store.py`).

## The headline: zen relay charges EXACTLY DeepSeek's own rates

There is **no opencode markup on DeepSeek models**. The zen relay passes the
model through at cost. The only cost difference vs calling `api.deepseek.com`
direct is the payment rail.

| Model | Off-peak (USD/1M) | Peak (USD/1M) |
|---|---|---|
| DeepSeek V4 Flash | in 0.22 / out 0.66 / cache-hit 0.007 | 0.44 / 1.32 / 0.014 |
| DeepSeek V4 Pro | in 0.66 / out 1.98 / hit 0.022 | 1.32 / 3.96 / 0.044 |

Same peak window as direct DeepSeek: 01:00–04:00 & 06:00–10:00 UTC (×2).

These match the fleet's canonical `cost_store.py` constants
(RATE_VERSION 2026-08-16: PRICE_HIT 0.007, PRICE_MISS 0.22, PRICE_OUT 0.66,
PEAK_MULT 2.0) exactly. So cost math does NOT need a per-provider table when
routing through the relay.

## The real differences (none of them per-token price)

1. **Payment rail** — OpenCode passes credit-card fees along at cost:
   4.4% + $0.30 per transaction. Negligible on ~$0.006 cron runs; only matters
   if you reload small amounts frequently.
2. **Provider diversity** — the real value of an opencode-zen fallback: a
   DIFFERENT backend serving the same model. If DeepSeek's own API is down or
   rate-limited, the relay still serves deepseek-v4-flash. A fallback to the
   same provider is useless — this is why the chain
   `deepseek → opencode-zen` beats `deepseek → deepseek-alt-key`.
3. **The only actual "free"** — `opencode-free` (keyless, empty Authorization,
   base_url https://opencode.ai/zen/v1). Free-tier models are $0, but see below.

## Free-tier reality (2026-08-31): NO free deepseek

- Live `/zen/v1/models` still lists `deepseek-v4-flash-free`, but a real
  chat completion returns
  `{"error":{"type":"server_error","message":"...Model is unavailable."}}`
  — the promo ended; curated models.py says delisted/401s.
- **There is no `deepseek-v4-pro-free` at all** (checked live).
- Free tier currently serves: `x-preview-f-free` (Ox Alpha), `hy3-free`,
  `laguna-s-2.1-free`, `ling-3.0-flash-fin-free`, `mimo-v2.5-free`,
  `muse-spark-1.2-contributor-free`, `nemotron-3-ultra-free`,
  `nemotron-3.5-lightning-free`, `deepseek-v4-flash-free` (listed but dead).

**Consequence for config:** making `opencode-free`/`deepseek-v4-flash-free`
the primary is fine ONLY with a working fallback chain — every run falls
through to fallback 1 until the promo returns. Verify live before claiming a
free model works: `curl -s https://opencode.ai/zen/v1/models` for the list,
then a real one-token completion for availability (a listed model can still
be "Model is unavailable").

## Provider quick reference

| Provider | Alias | Auth | Base URL |
|---|---|---|---|
| `opencode-free` | `free`, `opencode_free` | keyless (empty Authorization header) | https://opencode.ai/zen/v1 |
| `opencode-zen` | `opencode`, `zen` | `OPENCODE_ZEN_API_KEY` in ~/.hermes/.env | https://opencode.ai/zen/v1 |
| `opencode-go` | `go`, `opencode-go-sub` | `OPENCODE_GO_API_KEY` | https://opencode.ai/zen/go/v1 |

DeepSeek models route via `chat_completions` api_mode on both relays.

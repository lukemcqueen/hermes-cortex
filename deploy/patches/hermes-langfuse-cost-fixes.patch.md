# Langfuse Cost/Spend Integration — Changes Made

## Files Modified

### 1. `~/.hermes/hermes-agent/plugins/observability/langfuse/__init__.py`
**Bug**: `on_post_llm_call` handler expected `response` to be an SDK object with `.usage` attribute, but `post_api_request` hook passes a dict payload. `getattr(dict, "usage", None)` returns None → empty usage/cost.

**Fix**: Added `isinstance(response, dict)` check at the top of the usage-extraction logic. When `response` is a dict, read usage from the separate `usage` kwarg (CanonicalUsage summary dict) or `response["usage"]` fallback. SDK object path preserved via `elif response is not None`.

### 2. `~/.hermes/hermes-agent/agent/usage_pricing.py`
Added model pricing entries under both `("[model name]")` and `("[provider name]")` providers:
- Input: $3.00/1M tokens (cache miss)
- Output: $1.45/1M tokens
- Cache read: $0.0028/1M tokens (cache hit)

### 3. `~/.hermes-cortex/dashboard/server.py`
**Bug**: `_lf("/observations?limit=200")` → Langfuse API caps at 100 items per page, returns HTTP 400. Dashboard silently receives None → empty observation data.

**Fix**: Changed to `limit=100`.

### 4. `~/.hermes-cortex/dashboard/static/index.html`
- Added `.cyan` stat card color for spend display
- Added `.cost` CSS class for per-model cost column (green mono)
- Updated `renderStats()` to show "Total Spend" or "Tokens" stat card (6th position)
- Updated `renderModels()` to show per-model cost in model usage list

## Verifying

After the next Hermes LLM interaction (new session):
1. Langfuse observations will contain `usageDetails` with input/output tokens
2. Langfuse observations will contain `totalCost` with computed cost
3. Dashboard /api/langfuse → model_usage will show token counts and costs
4. Dashboard frontend cost trend card will populate with daily spend

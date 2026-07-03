# Decimal & JSON Handling in FastAPI (Python 3.12+ / ACME)

## Root Cause

Python 3.12's `json.JSONEncoder` does not handle `Decimal` — `TypeError: Object of type Decimal is not JSON serializable`. SQLAlchemy returns `Decimal` from PostgreSQL `NUMERIC` columns (sum, aggregates, raw column reads). FastAPI serializes Pydantic response models via `json.dumps()` internally, hitting this error at endpoint response time.

## Three-Layer Fix Strategy

### Layer 1: Global JSONEncoder monkey-patch (catch-all for API responses)

Place this early in `main.py` (before `FastAPI()` construction):

```python
import json
from decimal import Decimal

def _json_default(obj: object) -> object:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    raise TypeError

json.JSONEncoder.default = _json_default  # type: ignore[method-assign]
```

This patches ALL `json.dumps()` calls globally — FastAPI response serialization, Starlette's `JSONResponse`, and any manual `json.dumps()` in the same process. No need for custom response classes or per-call `default=` arguments.

**Trade-off:** `float(Decimal('999999999.99'))` loses ~5-6 digits of precision at ~10^15. For KRW (BIGINT up to ~10^14 max), float is accurate to 56+ bits → well within safe range for Korean-Won amounts (₩1 = 1 unit in BIGINT, ₩9 quadrillion max before precision loss). If precision beyond 15 significant digits matters, this is the wrong approach.

### Layer 2: Decimal→int at query boundary (for arithmetic)

When query results feed into arithmetic operations, `Decimal * float` throws `TypeError` in Python 3.12. Convert at the query boundary:

```python
# BEFORE (crashes):
total = aggregated[0] if aggregated and aggregated[0] is not None else 0
# total is Decimal, then: int(total * (1.0 + growth_pct)) → TypeError

# AFTER (safe):
total = int(aggregated[0]) if aggregated and aggregated[0] is not None else 0
# total is int, all math works
```

Do this wherever `func.sum()` results or raw `Column(Numeric)` values enter service/route logic. Applies to: distribution amounts, deduction rates, royalty totals, any `sa_func.sum()` in queries.

### Layer 3: JSON storage (DB write path)

When storing dicts as JSON text columns, avoid `json.dumps(data, default=str)` — that converts Decimals to strings like `"10000000"`, polluting the stored data with string-typed numbers.

```python
# BAD — stores Decimal as string:
json.dumps(form_data, default=str)

# GOOD — stores Decimal as float (reversible):
json.dumps(form_data, default=lambda o: float(o) if isinstance(o, Decimal) else str(o))
```

## Detection

Run any test that exercises an endpoint returning monetary values. The error signature is always:

```
TypeError: Object of type Decimal is not JSON serializable
```

For arithmetic errors:

```
TypeError: unsupported operand type(s) for *: 'decimal.Decimal' and 'float'
```

## Files Affected in ACME Royalty

| Fix | Where | When |
|---|---|---|
| Global monkey-patch | `apps/api/main.py` | Layer 1 |
| Decimal→int at queries | `services/forecasting.py` | Layer 2 |
| Decimal→int at queries | `routers/regulatory_filings.py` | Layer 2 + Layer 3 |
| default=str → Decimal-aware | `routers/regulatory_filings.py` | Layer 3 |

## Test Verification

Run the affected test files to confirm fix:

```bash
cd apps/api && set -a && source ../../.env && set +a && PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_reconciliation.py \
  tests/test_forecasting.py \
  tests/test_regulatory_filings.py \
  -v --no-header -q
```

Should report 45+ passing with zero Decimal errors.

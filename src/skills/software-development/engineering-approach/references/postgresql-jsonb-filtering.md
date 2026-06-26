# PostgreSQL JSONB Filtering Pitfall

When filtering on JSONB columns in SQLAlchemy, avoid `.astext` attribute access in production queries.

## The Problem

```python
# ❌ This crashes in SQLAlchemy sync endpoints
query.filter(AuditEvent.event_metadata["purpose"].astext == "royalty_calculation")
```

Error: `AttributeError: Neither 'BinaryExpression' object nor 'Comparator' object has an attribute 'astext'`

The `.astext` accessor works in raw PostgreSQL but fails when wrapped in SQLAlchemy's expression system, especially inside sync FastAPI endpoints run via `run_in_threadpool`.

## The Solution

Filter in Python after loading:

```python
# ✅ Load then filter in Python (cross-db compatible)
events = query.all()
if purpose:
    events = [e for e in events if e.event_metadata and e.event_metadata.get("purpose") == purpose]
```

This is safe because:
- Audit event queries are typically bounded by date range (already indexed)
- The Python filter is O(n) on a small result set (hundreds, not millions)
- Works identically across PostgreSQL, SQLite, and other backends

## When to Use Raw JSONB Filtering

If you need server-side JSONB filtering for large datasets:

```python
# Use SQLAlchemy's JSON path operators instead
from sqlalchemy import cast, String
query.filter(
    cast(AuditEvent.event_metadata["purpose"], String) == "royalty_calculation"
)
```

Or use PostgreSQL's `@>` containment operator:

```python
query.filter(
    AuditEvent.event_metadata.op("@>")({"purpose": "royalty_calculation"})
)
```

## Session Context

This pattern emerged during Epic 6 (PIPA audit report) implementation in acme-royalty. The audit report endpoint filters `AuditEvent` records by purpose stored in JSONB `event_metadata`. The `.astext` approach crashed; Python filtering resolved it.

## Related

- `backend-api-test-patterns.md` — async pytest fixtures for FastAPI
- `backend-api-domain-patterns.md` — AuditLog patterns

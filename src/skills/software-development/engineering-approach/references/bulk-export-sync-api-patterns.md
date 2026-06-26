# Bulk Export & Sync API Pattern

Cross-system integration pattern for one ACME app to expose data to other apps (e.g., acme-works → acme-metadata, acme-royalty, acme-ipi, acme-av).

## Architecture

```
Other ACME app (consumer)
    ↓ HTTP GET (Bearer auth)
Export endpoint → ExportService → AsyncSession → PostgreSQL
    ↓ Response
JSON collection | NDJSON stream | CSV download
```

## Endpoint Design

```
GET /api/export                    — Discover all entities + available formats
GET /api/export/{entity}           — Paginated JSON collection (cursor-based)
GET /api/export/{entity}/stream    — NDJSON streaming (chunked transfer)
GET /api/export/{entity}/csv       — CSV download (Content-Disposition: attachment)
GET /api/export/{entity}/count     — Row count for planning
```

All endpoints accept:
- `?cursor_ts=<ISO8601>&cursor_id=<uuid>` — stable keyset pagination
- `?since=<ISO8601>` — incremental sync (rows updated after timestamp)
- `?limit=<int>` — page size (default 1000, max 5000)

## Cursor-Based Pagination (composite cursor)

Cursor = `(updated_at, id)` composite key. This is stable across inserts and updates, unlike offset-based pagination which can skip or duplicate rows when data changes mid-query.

### Implementation

```python
async def export_works(
    cursor_ts: Optional[datetime] = None,
    cursor_id: Optional[UUID] = None,
    since: Optional[datetime] = None,
    limit: int = 1000,
    db: AsyncSession,
) -> tuple[list[dict], Optional[tuple[datetime, UUID]]]:
    query = select(Work).order_by(Work.updated_at, Work.id).limit(limit + 1)

    if since:
        query = query.where(Work.updated_at >= since)
    if cursor_ts and cursor_id:
        query = query.where(
            or_(
                Work.updated_at > cursor_ts,
                and_(Work.updated_at == cursor_ts, Work.id > cursor_id),
            )
        )

    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = (last.updated_at, last.id)
    else:
        next_cursor = None

    return [row_to_dict(r) for r in rows], next_cursor
```

### Response headers

```http
Link: </api/export/works?cursor_ts=2026-06-01T12:00:00&cursor_id=uuid>; rel="next"
X-Total-Count: 15000
```

## NDJSON Streaming

Best for large datasets (10K+ rows). Each line is a self-contained JSON object. The consumer reads line-by-line with no memory limit.

### Implementation

```python
async def stream_export(entity: str, since: datetime, db: AsyncSession):
    async with db.begin():
        cursor_ts, cursor_id = None, None
        while True:
            rows, next_cursor = await export_func(
                cursor_ts, cursor_id, since, limit=1000, db=db
            )
            for row in rows:
                yield json.dumps(row, default=str) + "\n"
            if not next_cursor:
                break
            cursor_ts, cursor_id = next_cursor
```

Returns `Content-Type: application/x-ndjson` with `Transfer-Encoding: chunked`.

### Consumer side (bash)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://works.client-domain.com/api/export/works/stream?since=2026-01-01" \
  | while IFS= read -r line; do
      echo "$line" | jq '.code, .title'
    done
```

## CSV Download

```python
@router.get("/export/{entity}/csv")
async def export_csv(entity: str, since: datetime = None, db: AsyncSession = Depends(get_db)):
    rows, _ = await export_all(entity, since, db)
    if not rows:
        return Response(content="", media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=empty.csv"})

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={entity}-{date.today()}.csv"},
    )
```

## Entity Serialization

Each entity class needs a `to_export_dict()` method that returns a flat dict with ISO8601 dates and string UUIDs:

```python
def to_export_dict(self) -> dict:
    return {
        "id": str(self.id),
        "code": self.code,
        "title": self.title,
        "status": self.status.value if self.status else None,
        "created_at": self.created_at.isoformat() if self.created_at else None,
        "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        # ... other fields ...
    }
```

For entities with related data (works → creators, contracts → territories), include a nested array or a flat representation depending on the consumer's needs.

## Format Negotiation

Accept header or `?format=` query param:

| Param | Accept header | Content-Type | Use case |
|-------|--------------|--------------|----------|
| `format=json` | `application/json` | `application/json` | Simple paginated page |
| `format=ndjson` | `application/x-ndjson` | `application/x-ndjson` | Streaming, large datasets |
| `format=csv` | `text/csv` | `text/csv` | Spreadsheet download |

## Auth for Machine-to-Machine

JWT (user session) is wrong for service-to-service. Options:

1. **API keys** — store in `api_keys` table, scoped to specific entities
2. **Service accounts** — dedicated users with minimal permissions
3. **Shared secret + HMAC** — lightweight, no DB hit per request

For v1, the simplest approach is API key auth middleware:

```python
@router.get("/export/{entity}")
async def export(
    entity: str,
    x_api_key: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if not x_api_key or not await validate_api_key(x_api_key, entity, db):
        raise HTTPException(401, "Invalid or unauthorized API key")
    ...
```

## When to Use This Pattern

- Another ACME app needs to read data from this app (metadata, av, royalty, ipi consumers)
- External system needs a one-time data dump or daily sync
- You need stable pagination across large, changing datasets
- You need to serve 10K+ rows without OOM on either side

## Pitfalls

1. **ORM entity to dict serialization is the perf bottleneck** for large exports. Each row triggers lazy loads for relationships. Use explicit joins + `row_to_dict()` or `selectinload()` with throttled chunks.
2. **Timezones** — all timestamps should be UTC. The consumer converts to local time. Always use `datetime.utcnow()` or `datetime.now(timezone.utc)` for `since` comparisons.
3. **Soft-deleted rows** — decide whether to include them. Use `where(deleted_at.is_(None))` unless the consumer needs deletion awareness.
4. **Cursor drift** — if `updated_at` has sub-second precision truncation (e.g., microseconds rounded to seconds), multiple rows can share the same timestamp. The composite cursor `(updated_at, id)` handles this correctly.
5. **Rate limiting on export endpoints** — add a rate limiter for export endpoints that is higher than the standard API limit but not unlimited. A malicious consumer with a valid key can pull the entire dataset repeatedly.
6. **Parameter binding in raw SQL** — `?limit=` in the query string gets consumed by Starlette as a route param if not explicitly handled. Endpoints must declare `limit: int = Query(1000)` not as a path param.

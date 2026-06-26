# FastAPI CRUD Security Patterns

Layered security model for protecting CRUD endpoints in a FastAPI + SQLAlchemy application. These patterns were applied to the acme-works project's anti-abuse overhaul (C1, C2, C3, M1, M4).

## Layer 1: Authentication — `require_active_user`

Every endpoint that returns data must first verify the caller is authenticated.

**Pattern — per-endpoint:**
```python
from app.auth.deps import require_active_user

@router.get("/items")
async def list_items(
    ...,
    _: None = Depends(require_active_user),
):
```

**Pattern — router-wide (applies to all endpoints):**
```python
router = APIRouter(
    prefix="/api/items",
    dependencies=[Depends(require_active_user)],
)
```

**Do NOT use `get_current_user` for protection** — it returns `User | None` silently. Only `require_active_user` raises 401. This mistake causes endpoints to return data to unauthenticated clients.

## Layer 2: Authorization — `require_permission`

Mutations (POST, PATCH, DELETE) need role-based permission checks matching the RBAC matrix.

**Pattern:**
```python
from app.auth.deps import require_permission

@router.post("/items")
async def create_item(
    data: ItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("items", "create")),
):
```

The `current_user` parameter is also needed for audit logging (see Layer 5).

**Permission matrix** (example from acme-works rbac.py):
| Resource | SUPERADMIN | MANAGER | ADMIN | PUBLISHER | MEMBER | VIEWER |
|---|---|---|---|---|---|---|
| works | create/read/update/delete/manage | create/read/update/delete | create/read/update | read | read | read |
| creators | same as works | same as works | same as works | read | read | read |
| members | same as works | same as works | same as works | read | read | — |
| publishers | same as works | same as works | same as works | read | — | — |

## Layer 3: Rate Limiting

### Global middleware — tier-based sliding window

A `BaseHTTPMiddleware` applies rate limits by path prefix. Each tier has its own request count per sliding window (60s):

| Tier | Limit/min | Paths |
|---|---|---|
| search | 60 | `/api/search/*` |
| crud | 120 | Most `/api/` paths |
| import | 10 | `/api/cwr/*`, `/api/imports/*` |
| auth | 20 | `/api/auth/*` |
| **membership** | **10** | `/api/membership/*` |
| default | 60 | Fallback |

**Tier routing** — match the most specific prefix first, fall through to generic:
```python
def _tier_for_path(path: str) -> str:
    if path.startswith("/api/search"):   return "search"
    if path.startswith("/api/auth"):     return "auth"
    if path.startswith("/api/membership/"): return "membership"
    if path.startswith(("/api/cwr", "/api/imports")): return "import"
    if path.startswith("/api/health"):   return "default"  # exempt
    if path.startswith("/api/"):         return "crud"
    return "default"
```

### Per-endpoint — specific endpoints with tighter limits

For unauthenticated / sensitive endpoints, use a Redis-backed async rate limiter:

```python
RATE_LIMIT = RateLimitConfig(max_requests=5, window_seconds=3600)  # 5/hr

if not await check_rate_limit_async(f"key:{ip}", RATE_LIMIT, redis_client):
    raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

**Architecture:**
- `RateLimitConfig` dataclass (max_requests, window_seconds)
- `check_rate_limit_async(key, config, redis)` — Redis ZSET sliding window, falls back to in-memory
- `check_rate_limit(key, config)` — synchronous in-memory fallback (backward compat)

**Login brute-force protection:** 10 attempts per 15 minutes per IP. Critical because login is unauthenticated and a high-value target.

## Layer 4: File Upload Validation

Accepting file uploads without validation is a vector for resource exhaustion and malicious content. Validate before processing:

```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"text/plain", "application/octet-stream", ""}
MAGIC_BYTES = b"HDR"  # CWR files start with HDR

async def _validate_upload(file: UploadFile) -> str:
    # 1. Content-Type check
    ct = (file.content_type or "").lower().split(";")[0].strip()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(400, detail="Invalid Content-Type")

    # 2. Magic bytes — read only first bytes
    header = await file.read(len(MAGIC_BYTES))
    if header != MAGIC_BYTES:
        raise HTTPException(400, detail="Invalid file header")

    # 3. Read rest with size limit
    rest = await file.read()
    content = header + rest
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, detail=f"File too large ({len(content)} bytes)")

    # 4. Decode
    return content.decode("utf-8-sig", errors="strict")
```

**Note:** Reading in two steps (magic bytes then rest) works with FastAPI's `UploadFile` because the internal `SpooledTemporaryFile` supports seeking. After validation, the full content is returned as a string — the caller doesn't need to read again.

## Layer 5: Audit Logging

Every mutation endpoint must record who changed what. Wire `AuditService` into each mutation handler:

**Create pattern:**
```python
obj = await crud.create(db, data)
await AuditService.record_create(
    db=db, table_name="items", record_id=obj.id,
    new_data=AuditService._serialize(obj),
    user_id=current_user.id,
)
await db.commit()  # commit the audit entry
```

**Update pattern (capture before/after):**
```python
old = await crud.get(db, id)
old_data = AuditService._serialize(old)
updated = await crud.update(db, id, data)
await AuditService.record_changes(
    db=db, table_name="items", record_id=id,
    old_data=old_data,
    new_data=AuditService._serialize(updated),
    user_id=current_user.id,
)
await db.commit()
```

**Delete pattern:**
```python
old = await crud.get(db, id)
old_data = AuditService._serialize(old)
await crud.delete(db, id)
await AuditService.record_delete(
    db=db, table_name="items", record_id=id,
    old_data=old_data,
    user_id=current_user.id,
)
await db.commit()
```

**Key detail:** `crud.create/update/delete` call `db.commit()` internally, so the audit call happens AFTER the CRUD commit. The `await db.commit()` after `AuditService.record_*()` commits the audit entry in a new transaction.

**Type hint fix:** `AuditService._serialize` should return `dict` not `dict | None`:
```python
@staticmethod
def _serialize(obj: Any) -> dict:
    if obj is None:
        return {}
    ...
```

## Layer 6: Input Sanitization

Search endpoints pass user input directly into `LIKE '%q%'` queries. Escaping `%` and `_` is essential to prevent wildcard injection:

```python
def sanitize_search_query(q: str, max_length: int = 64) -> str:
    q = q.strip()[:max_length]
    q = q.replace("%", r"\%").replace("_", r"\_")
    return q
```

Apply in:
- **Global search endpoint** — before passing to search service
- **CRUD search methods** — before building `ilike(f"%{q}%")` patterns
- **API Query params** — use `max_length` in FastAPI's `Query()`: `q: str = Query(None, max_length=64)`

## Pitfalls

- **`get_current_user` is NOT auth** — it silently returns None. Only `require_active_user` raises 401. The contracts router had this bug on its list endpoint.
- **Rate limiter middleware matching order matters** — `/api/membership/` must be checked before the generic `/api/` → `"crud"` fallback or membership endpoints get 120/min instead of 10/min.
- **File upload: reading twice from UploadFile** — after `await file.read(3)`, the internal cursor is at byte 3. `await file.read()` reads the rest starting from byte 3. Concatenate: `content = header + rest`.
- **`db.commit()` inside CRUD base** — the CRUD base `create/update/delete` methods call `commit()` internally. To record audit entries after the mutation, you must call `db.commit()` again in the router (starts a new transaction for the audit entry).
- **Search sanitization at multiple layers** — sanitize at the API entry point (Query max_length) AND at the data access layer (escape wildcards in LIKE patterns). Single-layer protection is leaky.
- **Honeypot field name** — Pydantic v2 treats fields starting with `_` as private. Name your honeypot field `honey` not `_honey`.

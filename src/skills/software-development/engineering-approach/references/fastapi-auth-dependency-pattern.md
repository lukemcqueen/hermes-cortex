# FastAPI Auth Dependency Gotcha: `Depends(get_db)` vs `request.app.state`

## The Problem

Custom auth dependencies that need DB access often start with `request.app.state.db_session`:

```python
# WRONG — breaks test fixture overrides
async def require_service_key(request: Request) -> None:
    result = await request.app.state.db_session.execute(...)
```

This fails in tests because the test suite overrides `get_db` via `app.dependency_overrides`, but `request.app.state` isn't affected by that override. Tests fail with:
```
AttributeError: 'State' object has no attribute 'db_session'
```

## The Fix

Use standard FastAPI dependency injection — the auth dependency itself accepts `Depends(get_db)`:

```python
async def resolve_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    # DB lookup works because db is injected through the normal override-able path
    result = await db.execute(
        select(ApiKey).where(ApiKey.expires_at > now)
    )
    for db_key in list(result.scalars().all()):
        if verify_api_key(api_key, db_key.key_hash):
            return
    raise HTTPException(status_code=401, detail="Invalid API key")
```

## Root Cause

`app.dependency_overrides[get_db]` only intercepts endpoints/routers that declare `Depends(get_db)`. If the auth dependency creates its own engine connection or accesses `request.app.state`, the override is bypassed entirely.

## Applies To

Any custom FastAPI dependency (`Depends(...)`) that touches the database directly:
- API key validation dependencies
- Service-to-service token verifiers
- Feature-flag checkers that read from DB
- Custom permission resolvers that query user roles

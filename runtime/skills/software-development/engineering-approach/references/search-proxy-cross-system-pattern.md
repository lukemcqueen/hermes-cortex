# Search Proxy / Cross-System API Proxy Pattern

Real-time HTTP proxy from one ACME app to another, with path mapping, auth forwarding, and response transformation. Used when acme-website's search needs to query acme-works's works endpoint in real-time.

## Architecture

```
Browser → Next.js rewrite → acme-website API → acme-works API
  :13001       /api/* → api:8000     proxy transforms      :13202
```

- Browser hits acme-website's Next.js web server (port 13001)
- Next.js rewrites `/api/:path*` to the acme-website API (port 8000, service name `api`)
- The API's proxy forwards to acme-works (port 13202, via `host.docker.internal`)
- Response is transformed before returning to the frontend

## Service-to-Service Auth

acme-works endpoints require auth. Two options:

### Option A: Service API Key (X-API-Key header)

Preferred for automated/programmatic access where no user session context exists:

```python
# acme-works auth/deps.py
from fastapi import Header, HTTPException
from src.config import settings

async def require_service_or_user(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    token: str | None = Depends(optional_bearer),
):
    if x_api_key and x_api_key in settings.API_KEYS:
        # Return a synthetic system user for audit purposes
        return SystemUser(name="acme-website sync", role="superadmin")
    if token:
        return await get_current_user(token)
    raise HTTPException(401)
```

### Option B: JWT Bearer forwarding

Use when the caller has a user context and wants to preserve it. Forward the Authorization header through the proxy.

## Proxy Implementation

### Route Mapping

The proxy maps frontend-facing paths to backend service paths:

| Frontend path | Backend path | Notes |
|--------------|-------------|-------|
| `/api/search/songs/autocomplete?q=...` | `/api/works?q=...&page_size=N` | Autocomplete → list with small page_size |
| `/api/search/songs?q=...&page=N&page_size=N` | `/api/works?q=...&page=N&page_size=N` | Paginated search, param names may differ |
| `/api/search/songs/{id}` | `/api/works/{id}` | Detail lookup |
| `/api/search/members?q=...` | `/api/members?q=...` | Member search (exact path match) |

### Response Transformation

acme-works uses **snake_case** fields (Python convention). The frontend (TypeScript) expects **camelCase**. Transform at the proxy layer:

```python
def _to_camel_case(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])

def _transform_work(item: dict) -> dict:
    """Convert a acme-works WorkListRead to a frontend WorkSearchResult."""
    return {
        "id": item["id"],
        "title": item.get("title", ""),
        "titleKo": item.get("title_ko", ""),
        "iswc": item.get("iswc"),
        "isrc": item.get("isrc", ""),
        "writers": item.get("creators", []),  # creators from list view
        "publishers": item.get("publishers", []),
        "genre": item.get("genre", ""),
        "status": item.get("status", ""),
        "registrationDate": item.get("created_at"),
        "thumbnail": item.get("thumbnail"),
    }
```

For autocomplete, the expected shape is `SearchResult[]` (flat list):

```python
@router.get("/songs/autocomplete")
async def autocomplete(q: str, page_size: int = 8):
    result = await _proxy_request("works", {"q": q, "page_size": page_size})
    items = result.get("items", [])
    return [
        {
            "id": w["id"],
            "title": w.get("title", ""),
            "type": "work",
            "matchField": "title",
        }
        for w in items
    ]
```

### Auth Forwarding

Add the service API key header to proxied requests:

```python
async def _proxy_request(path: str, params: dict | None = None) -> dict:
    url = f"{settings.ACME_WORKS_API_URL}/api/{path}"
    headers = {"X-API-Key": settings.ACME_WORKS_API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()
```

### Error Handling

Failures should NOT propagate as 500s to the frontend. Return empty results on any upstream failure:

```python
try:
    result = await _proxy_request(...)
except httpx.TimeoutException:
    logger.warning("upstream timeout for %s", url)
    return []
except httpx.HTTPStatusError as e:
    logger.warning("upstream %d for %s: %s", e.response.status_code, url, e.response.text[:200])
    return []
except httpx.RequestError as e:
    logger.warning("upstream connection error for %s: %s", url, str(e))
    return []
```

## Configuration

### acme-website `.env` / compose environment

```yaml
services:
  api:
    environment:
      ACME_WORKS_API_URL: "http://host.docker.internal:13202"  # works API
      ACME_WORKS_API_KEY: "dev-..."  # must match acme-works SERVICE_API_KEY
```

### Router registration

```python
# main.py
from src.routers import search
app.include_router(search.router, prefix="/api/search", tags=["search"])
```

## Pitfalls

- **Next.js builds embed `NEXT_PUBLIC_API_URL` at build time** — use Docker build args, not runtime `environment:`. See `references/nextjs-standalone-docker-patterns.md` for the Dockerfile + compose pattern.
- **Docker service names vs host ports** — inside the API container, the proxy URL must be `host.docker.internal:13202` (or the Docker service name for same-network services). `localhost:13202` or `http://api:8000` won't work because the API container is not the acme-works service.
- **Param name mismatches** — acme-works works API uses `page_size`, not `per_page`. Always check the upstream service's query parameter names before wiring.
- **Empty results ≠ broken** — an upstream with no data returns `{"items":[],"total":0,...}`. The proxy should pass this through correctly as `[]` or `PaginatedResponse` with empty items.
- **Httpx client lifecycle** — avoid creating a new `AsyncClient` per request in hot paths. Prefer a shared client or at minimum set a reasonable timeout (10s) to avoid hanging during upstream outages.

# Server-Rendered Console Pattern (FastAPI + Jinja2)

Pattern for building analyst/admin console UIs in ACME projects that use
FastAPI server-rendered templates (acme-matching), NOT Next.js SPA apps
(which use a different pattern — see `references/fullstack-feature-workflow.md`).

## Architecture

```
Browser          Web App (FastAPI)              API (FastAPI)
────────         ────────────────              ──────────────
Page load ──→    _api(GET /api/v1/...)   ──→   GET /api/v1/...
                 Returns rendered HTML
                 (Jinja2 template)

JS fetch  ──→    /fraud-alerts/{id}/status ──→  PUT /api/v1/...
(PUT)            (proxies via httpx)
```

- The web app is itself a FastAPI app with Jinja2 templates
- Data fetches happen server-side via `_api()` (httpx to the internal API)
- Mutations (status updates) require a **PUT proxy route** because `_api()` is GET-only

## Template Structure

### List Page (`templates/<entity>.html`)

```html
{% extends "base.html" %}
{% block title %}Title — Site{% endblock %}
{% block content %}
<h1>Title</h1>

<form class="filters" method="get" action="/<entity>">
  <select name="field1">
    <option value="">All</option>
    {% for opt in options %}
    <option value="{{ opt }}" {% if filters.field1 == opt %}selected{% endif %}>{{ opt }}</option>
    {% endfor %}
  </select>
  <input type="text" name="q" placeholder="Search..." value="{{ filters.q or '' }}">
  <button type="submit">Filter</button>
  {% if any_active_filter %}
  <a href="/<entity>" style="padding:8px 12px;color:#94a3b8;">Clear</a>
  {% endif %}
</form>

{% if error %}
<div class="error-state">...</div>
{% elif items %}
<table>...</table>
<div class="pagination">...</div>
{% else %}
<div class="empty">No items found</div>
{% endif %}
{% endblock %}
```

### Detail Page (`templates/<entity>_detail.html`)

Structure:
1. **Back link** — `← Back to ...`
2. **Header** with action buttons (inline JS that does `fetch(PUT)`)
3. **Stats grid** — key metrics in `.stat-card` elements
4. **Detail grid** — two-column `.detail-card` layout for field breakdowns
5. **Sectional content** — tables or cards for sub-items (evidence, lineage, history)
6. **Status action buttons** — only shown when status allows editing

### Base template extensions

Add to `base.html`:
```html
<a href="/<entity>" class="{% if active == '<entity>' %}active{% endif %}">Page Name</a>
```

Badge CSS:
```css
.badge-new { background: #1e3a5f; color: #93c5fd; }
.badge-red { background: #7f1d1d; color: #fca5a5; }
.badge-orange { background: #7c2d12; color: #fdba74; }
```

## Route Patterns (`main.py`)

### GET list with filters
```python
@app.get("/<entity>", response_class=HTMLResponse)
async def entity_list(
    page: int = Query(1, ge=1),
    status: str = Query(""),
    field2: str = Query(""),
):
    params: dict[str, str] = {"page": str(page), "size": str(PAGE_SIZE)}
    if status: params["status"] = status
    if field2: params["field2"] = field2

    data = await _api(f"/api/v1/<entity>", params)
    items = _extract_items(data)
    error = data.get("error") if isinstance(data, dict) and "error" in data else None

    filters = {"status": status, "field2": field2}
    return _t("<entity>.html", items=items, filters=filters, page=page, error=error, active="<entity>")
```

### GET detail with sub-resources
```python
@app.get("/<entity>/{item_id}", response_class=HTMLResponse)
async def entity_detail(item_id: int):
    data = await _api(f"/api/v1/<entity>/{item_id}")
    item = data if isinstance(data, dict) and "id" in data else None

    sub_data = await _api(f"/api/v1/<entity>/{item_id}/sub-resource")
    sub_items = sub_data.get("sub_items", []) if sub_data else []

    error = None if item else f"Item #{item_id} not found"
    return _t("<entity>_detail.html", item=item, sub_items=sub_items, error=error, active="<entity>")
```

### PUT proxy for status mutations
```python
@app.put("/<entity>/{item_id}/status")
async def entity_status_update(
    item_id: int,
    status: str = Query(..., pattern=r"^(valid|statuses)$"),
    notes: str = Query(""),
):
    async with httpx.AsyncClient() as c:
        url = f"{API_BASE}/api/v1/<entity>/{item_id}/status"
        params: dict[str, str] = {"status": status}
        if notes: params["notes"] = notes
        try:
            r = await c.put(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            from fastapi.responses import JSONResponse
            detail = str(e)
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                pass
            return JSONResponse(
                status_code=e.response.status_code if hasattr(e, "response") and e.response else 502,
                content={"detail": detail},
            )
```

## JS Action Button Pattern (detail page)

```html
{% block head_extra %}
<script>
async function updateStatus(itemId, status) {
  if (!confirm(`Set item #${itemId} to "${status}"?`)) return;
  const notes = prompt('Notes (optional):');
  try {
    const r = await fetch(`/<entity>/${itemId}/status?status=${status}&notes=${encodeURIComponent(notes || '')}&decided_by=analyst`, { method: 'PUT' });
    if (r.ok) window.location.reload();
    else { const data = await r.json(); alert('Error: ' + (data.detail || 'Unknown')); }
  } catch (e) { alert('Network error: ' + e.message); }
}
</script>
{% endblock %}
```

Only render buttons when item status permits editing:
```
{% if item.status == 'new' or item.status == 'under_review' %}
<button onclick="updateStatus({{ item.id }}, 'action_1')">Action 1</button>
<button onclick="updateStatus({{ item.id }}, 'action_2')">Action 2</button>
{% endif %}
```

## Mock Data Strategy (conftest.py)

Server-rendered templates are tested via `TestClient` with a mocked `_api()` function.
The mock intercepts `httpx` calls at the `_api()` level (not the transport level).

### Structure
```python
# Sample data functions
def _sample_items() -> dict:
    return {"items": [{"id": 1, ...}, {"id": 2, ...}]}

def _sample_single_item() -> dict:
    return {"id": 1, ...}

def _sample_sub_resource() -> dict:
    return {"sub_items": [...]}

# URL → response mapping (for exact path matches)
_API_ROUTES: dict[str, dict] = {
    "/api/v1/items": _sample_items(),
    "/api/v1/items/1": _sample_single_item(),
    "/api/v1/items/1/sub": _sample_sub_resource(),
}

# Mock _api function
async def _mock_api(path: str, params: dict[str, str] | None = None) -> dict | list | None:
    if path.startswith("/api/v1/items/"):
        route = _API_ROUTES.get(path)
        if route: return route
        return {"items": []} if path.count("/") == 3 else {"sub_items": []}
    if path == "/api/v1/items":
        items = _sample_items()["items"]
        if params and params.get("page"):
            page = int(params["page"])
            size = int(params.get("size", "20"))
            items = items[(page - 1) * size : page * size]
        return {"items": items}
    return {"items": []}
```

### Fixtures
```python
@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with patch("app.main._api", side_effect=_mock_api):
        with TestClient(app) as c:
            yield c

@pytest.fixture
def api_failing() -> Generator[TestClient, None, None]:
    with patch("app.main._api", return_value=None):
        with TestClient(app) as c:
            yield c

@pytest.fixture
def api_empty() -> Generator[TestClient, None, None]:
    mock = AsyncMock(return_value={"items": []})
    with patch("app.main._api", mock):
        with TestClient(app) as c:
            yield c
```

## Test Coverage Checklist

### List page
- [ ] Renders with data
- [ ] Shows item attributes (IDs, badges, scores)
- [ ] Each filter dimension works (no crash)
- [ ] Clear filter link appears when filters active
- [ ] Pagination controls present
- [ ] API down: graceful fallback, no crash
- [ ] Empty results: "No items" message

### Detail page
- [ ] Renders with data
- [ ] Shows key stats (score, risk, type, status)
- [ ] Shows entity identifiers (publisher, work IDs)
- [ ] Shows timeline (created/updated)
- [ ] Sub-resources render (evidence, lineage)
- [ ] Action buttons present for editable statuses
- [ ] Not found: error state
- [ ] Invalid ID: 422

### Status mutations
- [ ] Invalid status → 422 validation error

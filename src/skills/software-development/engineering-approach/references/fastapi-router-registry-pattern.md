# FastAPI Router Registry Pattern

Replaces 35+ individual `app.include_router(...)` calls in `main.py` with a single `register_routers(app)` call backed by a declarative data structure.

## The Pattern

Create `app/routers/registry.py`:

```python
from dataclasses import dataclass
from fastapi import APIRouter, FastAPI

# Import every router
from app.routers import health, works, creators, ...
from app.routers.admin.audit import router as admin_audit_router
from app.routers import import_ as import_router


@dataclass
class _RouterEntry:
    router: APIRouter
    prefix: str = ""
    tags: list[str] | None = None


_ROUTERS: list[_RouterEntry] = [
    _RouterEntry(health.router, prefix="/api"),
    _RouterEntry(works.router, prefix="/api"),
    _RouterEntry(membership_router, prefix="/api/membership", tags=["membership"]),
    _RouterEntry(admin_audit_router, prefix="/api"),
    _RouterEntry(publisher_portal_router, prefix="/api/v1"),
    # ...
]


def register_routers(app: FastAPI) -> None:
    for entry in _ROUTERS:
        kwargs = {"router": entry.router, "prefix": entry.prefix}
        if entry.tags is not None:
            kwargs["tags"] = entry.tags
        app.include_router(**kwargs)
```

Then in `main.py`:

```python
from app.routers.registry import register_routers
register_routers(app)   # 1 line replaces 35
```

## Benefits

- Single file to add/remove/modify router registrations
- Eliminates 35-line import + registration block from `main.py`
- Prefixes and tags are explicit and visible at a glance
- Easy to reorder or group routers

## When to Use

- Any FastAPI project with >5 routers
- During `main.py` cleanup / router reorganization

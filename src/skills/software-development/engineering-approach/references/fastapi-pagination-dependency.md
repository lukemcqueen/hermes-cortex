# FastAPI Pagination Dependency Pattern

Extracts the `skip = (page - 1) * page_size` / `pages = max(1, ...)` boilerplate from every list endpoint into a single injectable dependency.

## The Pattern

```python
# app/lib/pagination.py
from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar

from fastapi import Query

if TYPE_CHECKING:
    from app.schemas import PaginatedResponse

T = TypeVar("T")


class PaginationParams:
    """FastAPI dependency that extracts pagination query parameters.

    Usage:
        @router.get("")
        async def list_items(
            pagination: PaginationParams = Depends(),
            db: AsyncSession = Depends(get_db),
        ):
            items, total = await crud.search(db, skip=pagination.skip,
                                              limit=pagination.page_size)
            return pagination.response(items, total)
    """

    def __init__(
        self,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.skip = (page - 1) * page_size

    def response(self, items: list[T], total: int) -> PaginatedResponse[T]:
        pages = max(1, (total + self.page_size - 1) // self.page_size)
        return PaginatedResponse(
            items=items, total=total, page=self.page,
            page_size=self.page_size, pages=pages,
        )
```

## Before/After

**Before** — every list endpoint manually computes skip/pages:
```python
@router.get("", response_model=PaginatedResponse[WorkListRead])
async def list_works(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * page_size
    items, total = await crud.search(db, skip=skip, limit=page_size)
    pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(items=items, total=total, page=page,
                             page_size=page_size, pages=pages)
```

**After** — one-line pagination dependency:
```python
@router.get("", response_model=PaginatedResponse[WorkListRead])
async def list_works(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    items, total = await crud.search(db, skip=pagination.skip,
                                     limit=pagination.page_size)
    return pagination.response(items, total)
```

## When to Use

- Every list endpoint that returns a `PaginatedResponse`
- New endpoints and refactoring existing ones

## Migration Scope

In acme-works, 21 list endpoints across 16 router files were refactored in one pass. Search for `skip = (page - 1)` to find stragglers.

---
language: python
tags: [api, web, pattern, util]
title: FastAPI App with Auto-Docs
description: FastAPI application skeleton with Pydantic models, GET/POST endpoints, path and query parameters, automatic OpenAPI docs, and dependency injection.
source: pattern
---

```python
from typing import Optional

from fastapi import FastAPI, Query, Path, Depends, HTTPException
from pydantic import BaseModel, Field

# ------------------------------------------------------------------ #
# Models
# ------------------------------------------------------------------ #
class Item(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Item name")
    price: float = Field(..., gt=0, description="Price must be positive")
    in_stock: bool = True
    tags: list[str] = []

class ItemResponse(Item):
    id: int

    model_config = {"from_attributes": True}

# ------------------------------------------------------------------ #
# App & in-memory store
# ------------------------------------------------------------------ #
app = FastAPI(
    title="Example API",
    version="1.0.0",
    description="A sample FastAPI app showcasing routing, validation, and auto docs.",
)
store: dict[int, ItemResponse] = {}
counter: int = 0

def get_next_id() -> int:
    global counter
    counter += 1
    return counter

# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #
@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello from FastAPI"}

@app.get("/items/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: int = Path(..., ge=1, description="The item ID"),
) -> ItemResponse:
    if item_id not in store:
        raise HTTPException(status_code=404, detail="Item not found")
    return store[item_id]

@app.get("/items", response_model=list[ItemResponse])
def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    min_price: Optional[float] = Query(None, gt=0),
) -> list[ItemResponse]:
    items = list(store.values())
    if min_price is not None:
        items = [it for it in items if it.price >= min_price]
    return items[skip : skip + limit]

@app.post("/items", response_model=ItemResponse, status_code=201)
def create_item(item: Item) -> ItemResponse:
    item_id = get_next_id()
    new = ItemResponse(id=item_id, **item.model_dump())
    store[item_id] = new
    return new

# ------------------------------------------------------------------ #
# Run with: fastapi dev fastapi-app.py
# Auto-docs at http://127.0.0.1:8000/docs
# ------------------------------------------------------------------ #

```

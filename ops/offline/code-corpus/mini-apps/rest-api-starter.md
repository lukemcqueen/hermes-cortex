---
title: REST API Starter Template
description: Production-ready REST API starter with FastAPI, async SQLAlchemy, Alembic migrations, Pydantic schemas, CRUD endpoints with pagination, error handling middleware, health check, Docker Compose, and pytest fixtures.
language: python
tags: [rest, api, starter, fastapi, template]
---

# REST API Starter Template

A production-ready REST API starter template with FastAPI, async SQLAlchemy, Alembic migrations, Pydantic schemas, comprehensive error handling, health checks, Docker Compose, and pytest fixtures.

## Quick Start

```bash
# Clone and run
docker compose up --build

# Or locally
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Open API docs
open http://localhost:8000/docs
```

## Project Structure

```
rest-api-starter/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, middleware, lifespan
│   ├── config.py                # Settings from env vars
│   ├── database.py              # Async SQLAlchemy engine / session
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py              # Declarative base + mixins
│   │   └── item.py              # Example model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py            # Pagination, error schemas
│   │   └── item.py              # Item CRUD schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── items.py             # CRUD router
│   │   └── health.py            # Health check
│   ├── services/
│   │   ├── __init__.py
│   │   └── item.py              # Business logic layer
│   └── middleware/
│       ├── __init__.py
│       └── error_handler.py     # Global exception handler
├── migrations/
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│       └── 0001_create_items.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Fixtures: async client, DB session
│   ├── test_health.py
│   └── test_items.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── Makefile
```

## Configuration

### `app/config.py`

```python
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "REST API Starter"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/app"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/app"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Pagination defaults
    default_page_size: int = 20
    max_page_size: int = 100

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
```

## Database

### `app/database.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency that provides an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

## Models

### `app/models/base.py`

```python
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, DateTime, func
from app.database import Base


class TimestampMixin:
    """Mixin adding created_at / updated_at columns."""
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BaseModel(Base, TimestampMixin):
    """Abstract base model with auto-increment PK and timestamps."""
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
```

### `app/models/item.py`

```python
from sqlalchemy import Column, String, Boolean, Float, Text
from app.models.base import BaseModel


class Item(BaseModel):
    __tablename__ = "items"

    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, default="")
    price = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
```

## Schemas

### `app/schemas/common.py`

```python
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, List, Optional

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
    field_errors: Optional[dict] = None


class SuccessResponse(BaseModel):
    message: str
    data: Optional[dict] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    database: str = "connected"
```

### `app/schemas/item.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = ""
    price: Optional[float] = Field(default=0.0, ge=0)
    is_active: Optional[bool] = True


class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ItemResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    price: float
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

## Services (Business Logic)

### `app/services/item.py`

```python
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple

from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate


class ItemService:
    """Business logic layer for Item CRUD."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        active_only: bool = True,
        search: Optional[str] = None,
    ) -> Tuple[List[Item], int]:
        """List items with pagination and optional filters."""
        query = select(Item)

        if active_only:
            query = query.where(Item.is_active == True)

        if search:
            query = query.where(Item.title.ilike(f"%{search}%"))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Get paginated results
        query = query.order_by(Item.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_by_id(self, item_id: int) -> Optional[Item]:
        """Get a single item by ID."""
        result = await self.db.execute(select(Item).where(Item.id == item_id))
        return result.scalar_one_or_none()

    async def create(self, data: ItemCreate) -> Item:
        """Create a new item."""
        item = Item(**data.model_dump())
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def update(self, item: Item, data: ItemUpdate) -> Item:
        """Update an existing item (partial update)."""
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete(self, item: Item) -> None:
        """Soft-delete by deactivating, or hard-delete."""
        item.is_active = False
        await self.db.flush()
```

## Routers

### `app/routers/health.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint that verifies database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(status="ok", version="1.0.0", database=db_status)
```

### `app/routers/items.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.item import ItemCreate, ItemUpdate, ItemResponse
from app.schemas.common import PaginatedResponse, PaginationParams
from app.services.item import ItemService

router = APIRouter(prefix="/items", tags=["items"])


async def get_item_service(db: AsyncSession = Depends(get_db)) -> ItemService:
    return ItemService(db)


@router.get("/", response_model=PaginatedResponse[ItemResponse])
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    active_only: bool = Query(True),
    service: ItemService = Depends(get_item_service),
):
    """List items with pagination and optional search."""
    items, total = await service.list(
        page=page, page_size=page_size, active_only=active_only, search=search
    )
    return PaginatedResponse.create(
        items=[ItemResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, service: ItemService = Depends(get_item_service)):
    """Get a single item by ID."""
    item = await service.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemResponse.model_validate(item)


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate,
    service: ItemService = Depends(get_item_service),
):
    """Create a new item."""
    item = await service.create(data)
    return ItemResponse.model_validate(item)


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    data: ItemUpdate,
    service: ItemService = Depends(get_item_service),
):
    """Update an existing item (partial)."""
    item = await service.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item = await service.update(item, data)
    return ItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, service: ItemService = Depends(get_item_service)):
    """Delete (soft-deactivate) an item."""
    item = await service.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await service.delete(item)
    return None
```

## Middleware / Error Handling

### `app/middleware/error_handler.py`

```python
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global catch-all exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions with consistent format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": f"HTTP_{exc.status_code}"},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors with field-level details."""
    field_errors = {}
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        field_errors[field] = error["msg"]

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "error_code": "VALIDATION_ERROR",
            "field_errors": field_errors,
        },
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle database errors gracefully."""
    logger.error(f"Database error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database error", "error_code": "DB_ERROR"},
    )
```

### `app/main.py`

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import engine, Base
from app.routers import items, health
from app.middleware.error_handler import (
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup, clean up on shutdown."""
    logger.info(f"Starting {settings.app_name}...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")
    yield
    await engine.dispose()
    logger.info("Engine disposed")


app = FastAPI(
    title=settings.app_name,
    description="Production-ready REST API starter with async SQLAlchemy, Alembic, and pytest.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)

# Routers
app.include_router(health.router)
app.include_router(items.router, prefix=settings.api_prefix)
```

## Alembic Migrations

### `migrations/env.py`

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base

# Import all models so Alembic can detect them
from app.models.item import Item  # noqa

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### `migrations/versions/0001_create_items.py`

```python
"""Create items table

Revision ID: 0001
Revises:
Create Date: 2025-01-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("price", sa.Float(), server_default="0.0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_items_title"), "items", ["title"])
    op.create_index(op.f("ix_items_id"), "items", ["id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_items_title"), table_name="items")
    op.drop_index(op.f("ix_items_id"), table_name="items")
    op.drop_table("items")
```

### `migrations/alembic.ini`

```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql://postgres:postgres@localhost:5432/app

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

## Tests

### `tests/conftest.py`

```python
import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator

from app.database import Base, get_db
from app.main import app

# Use SQLite for tests (fast, isolated)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated DB session per test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client with overridden DB dependency."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

### `tests/test_health.py`

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test the health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_check_database_connected(client: AsyncClient):
    """Health check should report database status."""
    response = await client.get("/health")
    data = response.json()
    assert data["database"] in ("connected", "disconnected")
```

### `tests/test_items.py`

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_item(client: AsyncClient):
    """Create an item and verify response."""
    response = await client.post(
        "/api/v1/items/",
        json={"title": "Test Item", "description": "A test item", "price": 9.99},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Item"
    assert data["price"] == 9.99
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_items_empty(client: AsyncClient):
    """List items when database is empty."""
    response = await client.get("/api/v1/items/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["pages"] == 1


@pytest.mark.asyncio
async def test_list_items_with_data(client: AsyncClient):
    """List items after creating some."""
    # Create two items
    await client.post("/api/v1/items/", json={"title": "Item A", "price": 10.0})
    await client.post("/api/v1/items/", json={"title": "Item B", "price": 20.0})

    response = await client.get("/api/v1/items/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_item(client: AsyncClient):
    """Get a single item by ID."""
    create_resp = await client.post(
        "/api/v1/items/", json={"title": "Get Me", "price": 5.0}
    )
    item_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/items/{item_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Get Me"


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient):
    """Get a nonexistent item returns 404."""
    response = await client.get("/api/v1/items/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"


@pytest.mark.asyncio
async def test_update_item(client: AsyncClient):
    """Update an item's title and price."""
    create_resp = await client.post(
        "/api/v1/items/", json={"title": "Original", "price": 1.0}
    )
    item_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/v1/items/{item_id}",
        json={"title": "Updated", "price": 2.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated"
    assert data["price"] == 2.0


@pytest.mark.asyncio
async def test_partial_update_item(client: AsyncClient):
    """Update only the title, price should remain."""
    create_resp = await client.post(
        "/api/v1/items/", json={"title": "Partial", "price": 15.0}
    )
    item_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/v1/items/{item_id}",
        json={"title": "Partially Updated"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Partially Updated"
    assert data["price"] == 15.0  # Not changed


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient):
    """Delete (soft-deactivate) an item."""
    create_resp = await client.post(
        "/api/v1/items/", json={"title": "Delete Me", "price": 0.0}
    )
    item_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/items/{item_id}")
    assert response.status_code == 204

    # Item should now be inactive (not in active-only list)
    list_resp = await client.get("/api/v1/items/")
    ids = [item["id"] for item in list_resp.json()["items"]]
    assert item_id not in ids


@pytest.mark.asyncio
async def test_search_items(client: AsyncClient):
    """Search items by title."""
    await client.post("/api/v1/items/", json={"title": "Python Programming"})
    await client.post("/api/v1/items/", json={"title": "JavaScript Guide"})
    await client.post("/api/v1/items/", json={"title": "Python for Data Science"})

    response = await client.get("/api/v1/items/?search=Python")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    titles = [item["title"] for item in data["items"]]
    assert "Python Programming" in titles
    assert "Python for Data Science" in titles
    assert "JavaScript Guide" not in titles


@pytest.mark.asyncio
async def test_pagination(client: AsyncClient):
    """Verify pagination works."""
    for i in range(25):
        await client.post("/api/v1/items/", json={"title": f"Item {i}", "price": float(i)})

    # Page 1 (default 20)
    page1 = await client.get("/api/v1/items/")
    assert page1.json()["total"] == 25
    assert len(page1.json()["items"]) == 20
    assert page1.json()["pages"] == 2

    # Page 2
    page2 = await client.get("/api/v1/items/?page=2")
    assert len(page2.json()["items"]) == 5
    assert page2.json()["page"] == 2


@pytest.mark.asyncio
async def test_validation_error(client: AsyncClient):
    """Creating an item with empty title should fail."""
    response = await client.post("/api/v1/items/", json={"title": ""})
    assert response.status_code == 422
    data = response.json()
    assert "field_errors" in data
    assert "title" in str(data["field_errors"])


@pytest.mark.asyncio
async def test_item_not_active_in_list(client: AsyncClient):
    """Soft-deleted items should not appear in active-only list."""
    create = await client.post("/api/v1/items/", json={"title": "Temporary", "price": 1.0})
    item_id = create.json()["id"]

    await client.delete(f"/api/v1/items/{item_id}")

    # Active-only list (default) should not include it
    resp = await client.get("/api/v1/items/")
    assert item_id not in [i["id"] for i in resp.json()["items"]]
```

## Docker

### `Dockerfile`

```dockerfile
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: app
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/app
      DATABASE_URL_SYNC: postgresql://postgres:postgres@db:5432/app
      DEBUG: "false"
    depends_on:
      db:
        condition: service_healthy
    command: >
      sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"

volumes:
  pgdata:
```

## Makefile

```makefile
.PHONY: help install dev migrate test docker-up docker-down lint format

help:
	@echo "install   - Install dependencies"
	@echo "dev       - Run dev server with hot reload"
	@echo "migrate   - Run Alembic migrations"
	@echo "migrate-create - Create a new migration"
	@echo "test      - Run tests"
	@echo "docker-up - Start Docker Compose"
	@echo "docker-down - Stop Docker Compose"
	@echo "lint      - Run linter"
	@echo "format    - Format code"

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt 2>/dev/null || true

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(message)"

test:
	python -m pytest tests/ -v --asyncio-mode=auto

docker-up:
	docker compose up --build

docker-down:
	docker compose down

lint:
	ruff check app/ tests/

format:
	ruff format app/ tests/
```

## Requirements

### `requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.35
asyncpg==0.30.0
alembic==1.13.0
pydantic==2.9.0
pydantic-settings==2.5.0
psycopg2-binary==2.9.9
aiosqlite==0.20.0
```

### `requirements-dev.txt`

```
pytest==8.3.0
pytest-asyncio==0.24.0
httpx==0.27.0
ruff==0.6.0
```

## Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v --asyncio-mode=auto
```

## Key Patterns Demonstrated

- **Async SQLAlchemy** — `async_sessionmaker`, `AsyncSession`, `select()` with `await`
- **Alembic migrations** — async `env.py`, auto-generation, upgrade/downgrade
- **Pydantic v2** — `model_validate`, `model_dump(exclude_unset=True)`, `Field`
- **CRUD with pagination** — page/page_size, total count, search filter
- **Service layer** — business logic separated from routes
- **Generic paginated response** — `PaginatedResponse[T]` with Generic
- **Error handling** — global, HTTP, validation, and DB exception handlers
- **Dependency injection** — async DB session, service factory
- **Lifespan events** — async create_all/dispose
- **Comprehensive pytest** — fixtures, async client, DB isolation
- **Soft-delete** — `is_active` flag instead of hard DELETE
- **Docker Compose** — PostgreSQL + API with health checks
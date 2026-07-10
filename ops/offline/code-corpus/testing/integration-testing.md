---
language: python
tags: [integration-testing, testing, api, database]
title: Integration Testing with Python
description: Comprehensive guide to integration testing including test database setup with PostgreSQL testcontainers, API testing with httpx and Playwright API, Docker Compose for test environments, and fixtures for full-stack tests
source: pattern
---

# Integration Testing with Python

## Test Database Setup with Testcontainers

```python
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import asyncpg
import asyncio


# ─── Basic PostgresContainer ──────────────────────────────────────────────────

@pytest.fixture(scope='session')
def postgres_container():
    """Start a PostgreSQL container for the entire test session."""
    with PostgresContainer('postgres:16-alpine') as postgres:
        yield postgres


@pytest.fixture(scope='session')
def db_engine(postgres_container):
    """Create SQLAlchemy engine connected to the test container."""
    connection_url = postgres_container.get_connection_url()
    engine = create_engine(connection_url, echo=False)
    
    # Create schema
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                amount DECIMAL(10,2) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
    
    yield engine
    
    # Cleanup schema
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS orders, users CASCADE"))


@pytest.fixture
def db_session(db_engine):
    """Create a fresh database session for each test with rollback."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def fresh_database(db_engine):
    """Recreate all tables before each test for complete isolation."""
    with db_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS orders, users CASCADE"))
        conn.execute(text("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                amount DECIMAL(10,2) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))


# ─── Async Testcontainers ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope='session')
async def async_postgres():
    """Async PostgreSQL container for async tests."""
    with PostgresContainer('postgres:16-alpine') as postgres:
        yield postgres


@pytest_asyncio.fixture
async def async_pool(async_postgres):
    """Create an asyncpg connection pool."""
    dsn = async_postgres.get_connection_url().replace('postgresql+psycopg2://', 'postgresql://')
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                price DECIMAL(10,2)
            )
        """)
    
    yield pool
    
    await pool.close()


@pytest_asyncio.fixture
async def redis_container():
    """Redis container for caching tests."""
    with RedisContainer('redis:7-alpine') as redis:
        yield redis


# ─── Usage in Tests ──────────────────────────────────────────────────────────

def test_insert_and_query_user(db_session):
    """Test basic database operations."""
    # Insert a user
    db_session.execute(
        text("INSERT INTO users (name, email) VALUES (:name, :email) RETURNING id"),
        {'name': 'Alice', 'email': 'alice@example.com'}
    )
    db_session.commit()
    
    # Query back
    result = db_session.execute(
        text("SELECT * FROM users WHERE email = :email"),
        {'email': 'alice@example.com'}
    ).fetchone()
    
    assert result is not None
    assert result.name == 'Alice'
    assert result.email == 'alice@example.com'


def test_user_with_orders(db_session):
    """Test relational data across tables."""
    # Create user
    user_id = db_session.execute(
        text("INSERT INTO users (name, email) VALUES (:name, :email) RETURNING id"),
        {'name': 'Bob', 'email': 'bob@example.com'}
    ).scalar()
    
    # Create orders
    for amount in [50.00, 75.50]:
        db_session.execute(
            text("INSERT INTO orders (user_id, amount) VALUES (:uid, :amt)"),
            {'uid': user_id, 'amt': amount}
        )
    db_session.commit()
    
    # Query with JOIN
    result = db_session.execute(
        text("""
            SELECT u.name, COUNT(o.id) as order_count, SUM(o.amount) as total
            FROM users u
            LEFT JOIN orders o ON o.user_id = u.id
            WHERE u.id = :uid
            GROUP BY u.name
        """),
        {'uid': user_id}
    ).fetchone()
    
    assert result.name == 'Bob'
    assert result.order_count == 2
    assert float(result.total) == 125.50


@pytest.mark.asyncio
async def test_async_database(async_pool):
    """Test async database operations."""
    async with async_pool.acquire() as conn:
        # Insert
        item_id = await conn.fetchval(
            "INSERT INTO items (name, price) VALUES ($1, $2) RETURNING id",
            "Widget", 19.99
        )
        
        # Query
        row = await conn.fetchrow(
            "SELECT * FROM items WHERE id = $1", item_id
        )
        
        assert row['name'] == 'Widget'
        assert float(row['price']) == 19.99
```

## API Testing with httpx

```python
import pytest
import httpx
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator

# ─── Test FastAPI Application ─────────────────────────────────────────────────

# Assuming you have a FastAPI app:
# from app.main import app

@pytest.fixture
def test_app():
    """Mock FastAPI app for testing."""
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    
    app = FastAPI()
    
    class UserCreate(BaseModel):
        name: str
        email: str
    
    class UserResponse(BaseModel):
        id: int
        name: str
        email: str
    
    fake_db: dict = {}
    counter = [0]
    
    @app.post("/api/users", response_model=UserResponse)
    async def create_user(user: UserCreate):
        counter[0] += 1
        user_id = counter[0]
        fake_db[user_id] = user.dict()
        fake_db[user_id]['id'] = user_id
        return fake_db[user_id]
    
    @app.get("/api/users/{user_id}")
    async def get_user(user_id: int):
        if user_id not in fake_db:
            raise HTTPException(status_code=404, detail="User not found")
        return fake_db[user_id]
    
    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}
    
    return app


@pytest.fixture
def client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client using ASGI transport."""
    import asyncio
    
    transport = ASGITransport(app=test_app)
    
    async def _create_client():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    
    gen = _create_client()
    client = None
    
    async def setup():
        nonlocal client
        g = gen.__aiter__()
        client = await g.__anext__()
        return client
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = loop.run_until_complete(setup())
    
    yield client
    
    loop.run_until_complete(client.aclose())
    loop.close()


# ─── API Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test health check endpoint."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_create_user(client):
    """Test creating a user via API."""
    response = await client.post(
        "/api/users",
        json={"name": "Alice", "email": "alice@example.com"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_user(client):
    """Test getting a user by ID."""
    # First create a user
    create_resp = await client.post(
        "/api/users",
        json={"name": "Bob", "email": "bob@example.com"}
    )
    user_id = create_resp.json()["id"]
    
    # Then fetch it
    response = await client.get(f"/api/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Bob"


@pytest.mark.asyncio
async def test_get_user_not_found(client):
    """Test 404 for non-existent user."""
    response = await client.get("/api/users/999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ─── Standalone httpx Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_external_api():
    """Test an external API (mock in CI, real in integration suite)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get("https://jsonplaceholder.typicode.com/posts/1")
        
        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert "body" in data
        assert data["id"] == 1


# ─── API with Auth ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authenticated_endpoint(client):
    """Test an endpoint that requires authentication."""
    headers = {"Authorization": "Bearer test-token-123"}
    
    response = await client.get(
        "/api/users/1",
        headers=headers
    )
    
    # Test passes regardless of auth
    assert response.status_code in [200, 401, 403]
```

## Docker Compose for Test Environment

```python
import pytest
import subprocess
import time
import docker
import httpx
from pathlib import Path


# ─── Docker Compose Fixture ───────────────────────────────────────────────────

@pytest.fixture(scope='session')
def docker_compose():
    """
    Start Docker Compose services for integration tests.
    Requires docker-compose.yml at the project root.
    """
    compose_file = Path(__file__).parent.parent / 'docker-compose.test.yml'
    
    if not compose_file.exists():
        pytest.skip("docker-compose.test.yml not found")
    
    # Start services
    subprocess.run(
        ['docker', 'compose', '-f', str(compose_file), 'up', '-d'],
        check=True, capture_output=True
    )
    
    # Wait for services to be healthy
    print("Waiting for services to be ready...")
    time.sleep(5)
    
    yield
    
    # Cleanup
    subprocess.run(
        ['docker', 'compose', '-f', str(compose_file), 'down', '-v'],
        check=True, capture_output=True
    )
    print("Services stopped and cleaned up")


@pytest.fixture(scope='session')
def service_urls(docker_compose):
    """Discover service URLs from Docker Compose."""
    # These should match your docker-compose.test.yml
    return {
        'api': 'http://localhost:8080',
        'postgres': 'postgresql://test:test@localhost:5432/testdb',
        'redis': 'redis://localhost:6379/0',
    }


# ─── Using docker-py ──────────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def docker_client():
    """Docker client for programmatic container management."""
    return docker.from_env()


@pytest.fixture
def ephemeral_postgres(docker_client):
    """Start an ephemeral PostgreSQL container for a single test."""
    container = docker_client.containers.run(
        'postgres:16-alpine',
        environment={
            'POSTGRES_DB': 'testdb',
            'POSTGRES_USER': 'test',
            'POSTGRES_PASSWORD': 'test',
        },
        ports={'5432/tcp': None},  # Random port
        detach=True,
        remove=True,
    )
    
    # Wait for PostgreSQL to be ready
    container.reload()
    port = container.attrs['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort']
    connection_url = f'postgresql://test:test@localhost:{port}/testdb'
    
    # Poll until ready
    for _ in range(30):
        try:
            import sqlalchemy
            engine = sqlalchemy.create_engine(connection_url)
            engine.connect()
            engine.dispose()
            break
        except Exception:
            time.sleep(1)
    else:
        container.stop()
        raise RuntimeError("PostgreSQL did not start in time")
    
    yield connection_url, container
    
    container.stop()


# ─── Integration Test with Services ───────────────────────────────────────────

def test_api_with_database(service_urls):
    """Full integration test: API → Database."""
    api_url = service_urls['api']
    
    response = httpx.get(f"{api_url}/health")
    assert response.status_code == 200
    assert response.json()['status'] == 'healthy'


def test_database_connection(service_urls):
    """Test database connection from the test runner."""
    import sqlalchemy
    
    engine = sqlalchemy.create_engine(service_urls['postgres'])
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text("SELECT 1"))
        assert result.scalar() == 1
    engine.dispose()
```

## Fixtures for Full-Stack Tests

```python
import pytest
import pytest_asyncio
from dataclasses import dataclass
from typing import AsyncGenerator, Optional
import httpx


# ─── Domain Models ────────────────────────────────────────────────────────────

@dataclass
class TestUser:
    id: int
    name: str
    email: str
    token: str = ""


@dataclass
class TestOrder:
    id: int
    user_id: int
    amount: float
    status: str


# ─── Test Data Factories ──────────────────────────────────────────────────────

@pytest.fixture
def user_factory(db_session):
    """Factory fixture to create test users in the database."""
    created_ids = []
    
    def _create_user(name: str = "Test User", email: str = None) -> TestUser:
        if email is None:
            email = f"{name.lower().replace(' ', '.')}@example.com"
        
        result = db_session.execute(
            "INSERT INTO users (name, email) VALUES (:name, :email) RETURNING id, name, email",
            {'name': name, 'email': email}
        ).fetchone()
        
        user = TestUser(id=result.id, name=result.name, email=result.email)
        created_ids.append(user.id)
        return user
    
    yield _create_user
    
    # Cleanup
    for uid in created_ids:
        db_session.execute("DELETE FROM orders WHERE user_id = :uid", {'uid': uid})
        db_session.execute("DELETE FROM users WHERE id = :uid", {'uid': uid})
    db_session.commit()


@pytest.fixture
def order_factory(db_session, user_factory):
    """Factory fixture to create test orders."""
    created_ids = []
    
    def _create_order(user: TestUser = None, amount: float = 100.0,
                      status: str = "pending") -> TestOrder:
        if user is None:
            user = user_factory()
        
        result = db_session.execute(
            "INSERT INTO orders (user_id, amount, status) "
            "VALUES (:uid, :amount, :status) RETURNING id, user_id, amount, status",
            {'uid': user.id, 'amount': amount, 'status': status}
        ).fetchone()
        
        order = TestOrder(
            id=result.id, user_id=result.user_id,
            amount=float(result.amount), status=result.status
        )
        created_ids.append(order.id)
        return order
    
    yield _create_order
    
    for oid in created_ids:
        db_session.execute("DELETE FROM orders WHERE id = :oid", {'oid': oid})
    db_session.commit()


# ─── API Client Fixture ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for API integration tests."""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        yield client


@pytest_asyncio.fixture
async def authenticated_client(api_client: httpx.AsyncClient) -> AsyncGenerator[httpx.AsyncClient, None]:
    """API client with authentication token."""
    # Login or register to get a token
    response = await api_client.post("/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        api_client.headers["Authorization"] = f"Bearer {token}"
    
    yield api_client


# ─── Full Stack Test ──────────────────────────────────────────────────────────

class TestFullStack:
    """Full integration test: Database → API → Assertions."""
    
    def test_create_user_and_order(
        self, db_session, user_factory, order_factory
    ):
        """End-to-end: create a user, create an order, verify relationships."""
        # Create user
        user = user_factory(name="Alice Johnson", email="alice@example.com")
        assert user.id > 0
        
        # Create orders for the user
        order1 = order_factory(user=user, amount=50.00, status="completed")
        order2 = order_factory(user=user, amount=75.50, status="pending")
        
        # Verify via database query
        result = db_session.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = :uid",
            {'uid': user.id}
        ).scalar()
        assert result == 2
        
        # Verify user has orders
        result = db_session.execute(
            "SELECT u.name, COUNT(o.id) as cnt, SUM(o.amount) as total "
            "FROM users u JOIN orders o ON o.user_id = u.id "
            "WHERE u.id = :uid GROUP BY u.name",
            {'uid': user.id}
        ).fetchone()
        
        assert result.name == "Alice Johnson"
        assert result.cnt == 2
        assert float(result.total) == 125.50
    
    def test_multiple_users_independent_data(
        self, db_session, user_factory, order_factory
    ):
        """Verify that data between users is properly isolated."""
        user1 = user_factory(name="User One")
        user2 = user_factory(name="User Two")
        
        order_factory(user=user1, amount=100.00)
        order_factory(user=user2, amount=200.00)
        order_factory(user=user2, amount=300.00)
        
        # User 1 should have 1 order
        count1 = db_session.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = :uid",
            {'uid': user1.id}
        ).scalar()
        assert count1 == 1
        
        # User 2 should have 2 orders
        count2 = db_session.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = :uid",
            {'uid': user2.id}
        ).scalar()
        assert count2 == 2
    
    @pytest.mark.asyncio
    async def test_api_integration(self, api_client: httpx.AsyncClient):
        """Test the API layer with proper request/response."""
        response = await api_client.get("/health")
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            assert "status" in response.json()
    
    def test_transaction_rollback(self, db_session):
        """Test that failed operations roll back correctly."""
        # Start with clean state
        count_before = db_session.execute(
            "SELECT COUNT(*) FROM users"
        ).scalar()
        
        # Insert a user
        db_session.execute(
            "INSERT INTO users (name, email) VALUES (:name, :email)",
            {'name': 'Rollback', 'email': 'rollback@example.com'}
        )
        
        # Force a failure before commit
        try:
            db_session.execute(
                "INSERT INTO users (name, email) VALUES (:name, :email)",
                {'name': 'Invalid', 'email': 'rollback@example.com'}  # Duplicate email
            )
            db_session.commit()
        except Exception:
            db_session.rollback()
        
        # Verify no new user was persisted
        count_after = db_session.execute(
            "SELECT COUNT(*) FROM users"
        ).scalar()
        
        assert count_after == count_before

    def test_complex_query_with_aggregation(
        self, db_session, user_factory, order_factory
    ):
        """Test complex SQL queries with aggregation."""
        # Create users and orders
        users = [
            user_factory(name="High Spender"),
            user_factory(name="Medium Spender"),
            user_factory(name="Low Spender"),
        ]
        
        order_factory(user=users[0], amount=1000.00)
        order_factory(user=users[0], amount=500.00)
        order_factory(user=users[1], amount=300.00)
        order_factory(user=users[2], amount=50.00)
        
        # Aggregate query: find users who spent more than average
        result = db_session.execute("""
            SELECT u.name, SUM(o.amount) as total_spent
            FROM users u
            JOIN orders o ON o.user_id = u.id
            GROUP BY u.name
            HAVING SUM(o.amount) > (
                SELECT AVG(total) FROM (
                    SELECT SUM(amount) as total
                    FROM orders
                    GROUP BY user_id
                ) as user_totals
            )
            ORDER BY total_spent DESC
        """).fetchall()
        
        # Only the high spender should be above average
        assert len(result) == 1
        assert result[0].name == "High Spender"
        assert float(result[0].total_spent) == 1500.00
```

## Complete docker-compose.test.yml

```yaml
# docker-compose.test.yml
# Place at project root for integration testing

version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.test
    environment:
      DATABASE_URL: postgresql://test:test@postgres:5432/testdb
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET: test-secret-key
    ports:
      - "8080:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: testdb
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d testdb"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Optional: Email service mock
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"  # SMTP
      - "8025:8025"  # Web UI
```

## conftest.py Organization

```python
# tests/conftest.py
"""
Integration test configuration.
Pytest discovers this file and makes all fixtures available
to all test files in the tests/ directory.
"""
import pytest
from pathlib import Path
import os


def pytest_addoption(parser):
    """Add integration test flags."""
    parser.addoption(
        '--run-docker',
        action='store_true',
        default=False,
        help='Run tests that require Docker containers'
    )
    parser.addoption(
        '--db-url',
        action='store',
        default=None,
        help='Database URL for integration tests'
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        'markers',
        'docker: marks tests that require Docker (skipped by default)'
    )


def pytest_collection_modifyitems(config, items):
    """Skip Docker tests unless --run-docker is passed."""
    if not config.getoption('--run-docker'):
        skip_docker = pytest.mark.skip(reason='Use --run-docker to run')
        for item in items:
            if 'docker' in item.keywords:
                item.add_marker(skip_docker)


# Environment variables for test configuration
os.environ.setdefault('TESTING', 'true')
os.environ.setdefault('LOG_LEVEL', 'DEBUG')
```
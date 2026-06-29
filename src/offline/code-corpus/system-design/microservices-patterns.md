---
title: Microservices Patterns
description: Microservice architecture patterns including service discovery, API gateway, circuit breaker, saga (choreography vs orchestration), event sourcing, CQRS, sidecar pattern, and health checks.
language: python
tags: [system-design, microservices, architecture, patterns]
---

# Microservices Patterns

## Overview

Microservices decompose a monolith into independently deployable services. This snippet covers the essential patterns for building resilient, observable, and scalable microservice systems.

---

## Service Discovery

Services need to find each other at runtime. Two approaches:

### Client-Side Discovery (with Consul)

```python
import requests
import random
from typing import Optional

class ConsulServiceDiscovery:
    """Discover service instances from Consul."""

    def __init__(self, consul_host: str = "localhost", consul_port: int = 8500):
        self.base_url = f"http://{consul_host}:{consul_port}/v1"

    def get_service_url(self, service_name: str, path: str = "") -> Optional[str]:
        resp = requests.get(
            f"{self.base_url}/health/service/{service_name}?passing=true"
        )
        resp.raise_for_status()
        instances = resp.json()

        if not instances:
            return None

        # Pick a healthy instance at random
        instance = random.choice(instances)
        address = instance["Service"]["Address"]
        port = instance["Service"]["Port"]
        return f"http://{address}:{port}{path}"

    def register_service(
        self,
        service_name: str,
        service_id: str,
        port: int,
        health_check_url: str,
    ) -> None:
        payload = {
            "ID": service_id,
            "Name": service_name,
            "Address": self._get_private_ip(),
            "Port": port,
            "Check": {
                "HTTP": health_check_url,
                "Interval": "10s",
                "Timeout": "5s",
            },
        }
        requests.put(
            f"{self.base_url}/agent/service/register",
            json=payload,
        )
```

### Server-Side Discovery (via API Gateway)

The API Gateway (or a load balancer) handles routing; services don't know each other's addresses.

---

## API Gateway

Single entry point that routes to internal services, handles auth, rate limiting, and aggregation.

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import asyncio

app = FastAPI(title="API Gateway")

# Route mapping
ROUTES = {
    "/api/users": "http://user-service:8001",
    "/api/orders": "http://order-service:8002",
    "/api/payments": "http://payment-service:8003",
}

RATE_LIMITS: dict[str, int] = {}
MAX_REQUESTS_PER_MINUTE = 100

async def proxy_request(backend_url: str, request: Request) -> JSONResponse:
    """Forward request to backend service."""
    path = request.url.path
    query = request.url.query
    target_url = f"{backend_url}{path}"
    if query:
        target_url += f"?{query}"

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                timeout=30.0,
            )
            return JSONResponse(
                content=resp.json() if resp.text else {},
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

@app.api_route("/api/{service:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway_handler(service: str, request: Request):
    # 1. Authentication
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")
    await verify_token(token)

    # 2. Rate limiting
    client_ip = request.client.host
    if RATE_LIMITS.get(client_ip, 0) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    RATE_LIMITS[client_ip] = RATE_LIMITS.get(client_ip, 0) + 1

    # 3. Route resolution
    for prefix, backend in ROUTES.items():
        if request.url.path.startswith(prefix):
            return await proxy_request(backend, request)

    raise HTTPException(status_code=404, detail="Route not found")
```

---

## Circuit Breaker

Prevents cascading failures by failing fast when a downstream service is unhealthy.

```python
import time
import asyncio
from enum import Enum
from functools import wraps

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing; reject immediately
    HALF_OPEN = "half_open" # Testing if service recovered

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_requests = 0

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                # Move to half-open to test
                self.state = CircuitState.HALF_OPEN
                self.half_open_requests = 0
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_requests >= self.half_open_max_requests:
                raise CircuitBreakerOpenError("Circuit breaker is HALF_OPEN (at capacity)")

        try:
            self.half_open_requests += 1
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    def _on_success(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_requests = 0

    def _on_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

class CircuitBreakerOpenError(Exception):
    pass

# Usage
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=15)

async def fetch_orders(user_id: str) -> list:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://order-service:8002/orders/{user_id}")
        resp.raise_for_status()
        return resp.json()

# Wrap with circuit breaker
async def safe_fetch_orders(user_id: str) -> dict:
    try:
        return await breaker.call(fetch_orders, user_id)
    except CircuitBreakerOpenError:
        # Fallback — return cached data or empty response
        return {"fallback": True, "orders": []}
```

---

## Saga Pattern

A saga is a sequence of local transactions with compensating actions for rollback.

### Choreography (Event-Driven)

Each service publishes events and listens for events. No central coordinator.

```python
# Order Service
async def create_order(user_id: str, items: list, total: float) -> str:
    order_id = str(uuid.uuid4())
    # 1. Create order in PENDING state
    await db.execute(
        "INSERT INTO orders (id, user_id, items, total, status) VALUES (%s, %s, %s, %s, 'PENDING')",
        (order_id, user_id, json.dumps(items), total),
    )
    # 2. Publish event — other services react
    await event_bus.publish("order.created", {
        "order_id": order_id,
        "user_id": user_id,
        "total": total,
    })
    return order_id

# Payment Service (reactive)
async def on_order_created(event: dict) -> None:
    order_id = event["order_id"]
    try:
        # Process payment
        await payment_provider.charge(event["user_id"], event["total"])
        await event_bus.publish("payment.completed", {"order_id": order_id})
    except Exception:
        # Compensating action
        await event_bus.publish("payment.failed", {"order_id": order_id})

# Inventory Service (reactive)
async def on_payment_completed(event: dict) -> None:
    order_id = event["order_id"]
    await db.execute("UPDATE orders SET status = 'CONFIRMED' WHERE id = %s", (order_id,))
    await event_bus.publish("inventory.reserved", {"order_id": order_id})

# Order Service (compensating)
async def on_payment_failed(event: dict) -> None:
    order_id = event["order_id"]
    await db.execute("UPDATE orders SET status = 'FAILED' WHERE id = %s", (order_id,))
```

### Orchestration (Central Coordinator)

A saga orchestrator tells each service what to do and handles compensation.

```python
class OrderSagaOrchestrator:
    """Central coordinator for the order saga."""

    async def execute(self, user_id: str, items: list, total: float) -> str:
        order_id = None
        try:
            # Step 1: Create order
            order_id = await self._create_order(user_id, items, total)

            # Step 2: Reserve inventory
            await self._reserve_inventory(order_id, items)

            # Step 3: Process payment
            await self._process_payment(order_id, user_id, total)

            # Step 4: Confirm order
            await self._confirm_order(order_id)

            return order_id

        except Exception as exc:
            print(f"[SAGA FAILED] {exc}")
            await self._compensate(order_id)
            raise

    async def _compensate(self, order_id: str | None) -> None:
        if order_id is None:
            return
        # In reverse order
        await self._reverse_payment(order_id)
        await self._release_inventory(order_id)
        await self._cancel_order(order_id)

    async def _create_order(self, user_id: str, items: list, total: float) -> str:
        # Call order service
        pass

    async def _cancel_order(self, order_id: str) -> None:
        # Compensating action for step 1
        pass

    # ... other steps and compensations
```

---

## Event Sourcing

Store state changes as a sequence of events rather than current state.

```python
import json
from datetime import datetime

class EventStore:
    """Append-only event store."""

    async def append_event(
        self,
        aggregate_id: str,
        event_type: str,
        data: dict,
        version: int,
    ) -> None:
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO events (aggregate_id, version, event_type, data, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (aggregate_id, version, event_type, json.dumps(data), datetime.utcnow()),
            )

    async def get_events(self, aggregate_id: str) -> list[dict]:
        async with pool.connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM events WHERE aggregate_id = %s ORDER BY version",
                aggregate_id,
            )
            return [dict(row) for row in rows]

    def rebuild_state(self, events: list[dict]) -> dict:
        """Replay events to reconstruct current state."""
        state = {"balance": 0, "status": "active"}
        for event in events:
            if event["event_type"] == "account.created":
                state["account_id"] = event["data"]["account_id"]
                state["owner"] = event["data"]["owner"]
            elif event["event_type"] == "money.deposited":
                state["balance"] += event["data"]["amount"]
            elif event["event_type"] == "money.withdrawn":
                state["balance"] -= event["data"]["amount"]
            elif event["event_type"] == "account.closed":
                state["status"] = "closed"
        return state

# Schema
"""
CREATE TABLE events (
    id           BIGSERIAL PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    version      INT NOT NULL,
    event_type   TEXT NOT NULL,
    data         JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(aggregate_id, version)
);
CREATE INDEX idx_events_aggregate ON events(aggregate_id);
"""
```

---

## CQRS (Command Query Responsibility Segregation)

Separate read and write models for different optimization.

```python
from pydantic import BaseModel

# --- WRITE SIDE (Commands) ---

class CreateOrderCommand(BaseModel):
    user_id: str
    items: list[dict]
    shipping_address: str

class CommandHandler:
    """Handles commands — validates business rules, emits events."""

    def __init__(self, event_store: EventStore, event_bus):
        self.event_store = event_store
        self.event_bus = event_bus

    async def handle_create_order(self, cmd: CreateOrderCommand) -> str:
        order_id = str(uuid.uuid4())
        await self.event_store.append_event(
            order_id,
            "order.created",
            cmd.model_dump(),
            version=1,
        )
        await self.event_bus.publish("order.created", {"order_id": order_id})
        return order_id

# --- READ SIDE (Queries) ---

class ReadModelUpdater:
    """Subscribes to events and updates denormalized read models."""

    async def on_order_created(self, event: dict) -> None:
        # Update a materialized view / read-optimized table
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO order_summaries (order_id, user_id, total, status)
                VALUES (%s, %s, %s, 'pending')
                """,
                (event["order_id"], event["user_id"], event["total"]),
            )

class OrderQueryService:
    """Fast reads against denormalized data."""

    async def get_order_summary(self, order_id: str) -> dict:
        async with pool.connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM order_summaries WHERE order_id = %s",
                order_id,
            )
            return dict(row) if row else None

    async def list_recent_orders(self, user_id: str, limit: int = 20) -> list[dict]:
        async with pool.connection() as conn:
            rows = await conn.fetch(
                "SELECT * FROM order_summaries WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                user_id,
                limit,
            )
            return [dict(r) for r in rows]
```

---

## Sidecar Pattern

Run auxiliary processes alongside the main service in the same pod/container.

```python
# sidecar_config.yaml (for Kubernetes sidecar containers)
"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-service
spec:
  template:
    metadata:
      labels:
        app: my-service
    spec:
      containers:
        - name: main-app
          image: my-service:latest
          ports:
            - containerPort: 8080
        - name: sidecar
          image: envoyproxy/envoy:v1.28-latest
          ports:
            - containerPort: 9901  # admin
            - containerPort: 10000 # proxy
          volumeMounts:
            - name: envoy-config
              mountPath: /etc/envoy
      volumes:
        - name: envoy-config
          configMap:
            name: envoy-config
"""

# Example sidecar responsibilities:
# - Service mesh proxy (Envoy, Linkerd)
# - Log shipper (Filebeat, Fluentd)
# - Metrics exporter (Prometheus sidecar)
# - Config reloader
# - TLS termination
```

---

## Health Checks

Every service should expose health endpoints for orchestration and monitoring.

```python
from fastapi import FastAPI
from pydantic import BaseModel
import psycopg2

app = FastAPI()

class HealthStatus(BaseModel):
    status: str
    version: str
    uptime: float
    dependencies: dict[str, str]

@app.get("/health")
async def health() -> HealthStatus:
    deps = {}

    # Check database
    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        deps["database"] = "healthy"
    except Exception as exc:
        deps["database"] = f"unhealthy: {exc}"

    # Check Redis
    try:
        await cache.ping()
        deps["redis"] = "healthy"
    except Exception as exc:
        deps["redis"] = f"unhealthy: {exc}"

    overall = "healthy" if all(v == "healthy" for v in deps.values()) else "degraded"
    status_code = 200 if overall == "healthy" else 503

    return HealthStatus(
        status=overall,
        version="1.2.3",
        uptime=time.time() - START_TIME,
        dependencies=deps,
    )

@app.get("/ready")
async def readiness() -> dict:
    """Readiness probe — true only when the service can accept traffic."""
    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        return {"ready": True}
    except Exception:
        return JSONResponse(
            content={"ready": False},
            status_code=503,
        )
```

### Kubernetes Probe Config

```yaml
# In your Deployment spec
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 15

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10

startupProbe:
  httpGet:
    path: /health
    port: 8080
  failureThreshold: 30
  periodSeconds: 10
```

---

## Key Takeaways

- **Service Discovery** (Consul/ETCD/K8s DNS) — services find each other without hardcoded addresses.
- **API Gateway** — single entry point for auth, routing, rate limiting.
- **Circuit Breaker** — fail fast when downstream is down; retry after recovery.
- **Saga** — distributed transactions with compensating actions (choreography for decoupling, orchestration for control).
- **Event Sourcing + CQRS** — powerful combo for audit trails and read/write optimization.
- **Sidecar** — push cross-cutting concerns (logging, metrics, proxy) out of the main process.
- **Health Checks** — essential for orchestration (Kubernetes probes) and monitoring.

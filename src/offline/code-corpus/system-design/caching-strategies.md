---
title: Caching Strategies
description: Redis caching patterns (cache-aside, write-through, write-behind), cache invalidation (TTL, LRU, event-driven), Redis commands, and CDN caching headers.
language: python
tags: [system-design, caching, redis, cdn, performance]
---

# Caching Strategies

## Overview

Caching is a technique that stores frequently accessed data in a high-speed storage layer so future requests can be served faster. This snippet covers Redis-backed caching strategies, invalidation techniques, and CDN-level HTTP caching.

---

## Cache-Aside (Lazy Loading)

The application checks the cache first. On a miss, it loads data from the database, stores it in the cache, and returns it.

```python
import redis.asyncio as aioredis
import json
from typing import Optional, Any

cache = aioredis.from_url("redis://localhost:6379", decode_responses=True)

async def get_user(user_id: str) -> dict[str, Any]:
    cache_key = f"user:{user_id}"

    # Check cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        print(f"[CACHE HIT] {cache_key}")
        return json.loads(cached)

    # Cache miss — load from database (simulated)
    print(f"[CACHE MISS] {cache_key}")
    user = await _fetch_user_from_db(user_id)  # your DB call
    if user is None:
        raise ValueError("User not found")

    # Populate cache with TTL
    await cache.setex(cache_key, 300, json.dumps(user))
    return user
```

**Pros:** Only caches what is requested; resilient to cache failures.
**Cons:** Cache miss penalty (three trips for a cold start); stale data until TTL expires.

---

## Write-Through

Writes go through the cache to the database. The cache is always consistent with the DB for writes.

```python
async def update_user(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    cache_key = f"user:{user_id}"

    # Write to database first
    updated = await _update_user_in_db(user_id, data)

    # Then update cache synchronously
    await cache.setex(cache_key, 300, json.dumps(updated))
    return updated
```

**Pros:** Cache is always fresh for written data; no stale-read window after a write.
**Cons:** Write latency increases (two sequential writes); caches data that may never be read.

---

## Write-Behind (Write-Back)

Writes go to the cache immediately and are asynchronously flushed to the database.

```python
import asyncio
from collections import deque

write_buffer: deque[tuple[str, dict[str, Any]]] = deque()

async def write_behind_update(user_id: str, data: dict[str, Any]) -> None:
    cache_key = f"user:{user_id}"
    # Write to cache immediately
    await cache.setex(cache_key, 600, json.dumps(data))
    # Queue for eventual DB write
    write_buffer.append((cache_key, data))

async def flush_buffer(batch_size: int = 50) -> None:
    """Background task: flush queued writes to DB periodically."""
    while True:
        batch = []
        while write_buffer and len(batch) < batch_size:
            batch.append(write_buffer.popleft())

        for cache_key, data in batch:
            user_id = cache_key.split(":", 1)[1]
            await _update_user_in_db(user_id, data)

        await asyncio.sleep(5)  # flush every 5 seconds
```

**Pros:** Very low write latency; excellent for write-heavy workloads.
**Cons:** Risk of data loss if cache fails before flush; more complex recovery.

---

## Cache Invalidation Strategies

### 1. TTL-Based (Time-To-Live)

```python
# Set with TTL — Redis auto-evicts when expired
await cache.setex("session:abc123", 900, session_data)  # 15 min

# Or set then expire separately
await cache.set("temp:xyz", "value")
await cache.expire("temp:xyz", 60)  # expire in 60s
```

Best for data that naturally becomes stale (sessions, API responses).

### 2. LRU Eviction

Configured at the Redis level — when memory is full, least-recently-used keys are evicted.

```
# redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru
```

### 3. Event-Driven Invalidation

```python
import aioredis
from typing import Callable

pubsub = cache.pubsub()

async def subscribe_to_invalidation(channel: str = "cache:invalidate") -> None:
    await pubsub.subscribe(channel)
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        key_to_invalidate = message["data"]
        await cache.delete(key_to_invalidate)
        print(f"[INVALIDATED] {key_to_invalidate}")

async def invalidate_on_update(entity_type: str, entity_id: str) -> None:
    """Call this from write endpoints to broadcast invalidation."""
    await cache.publish("cache:invalidate", f"{entity_type}:{entity_id}")
```

---

## Redis Commands Reference

| Command | Example | Purpose |
|---------|---------|---------|
| `SET` | `SET user:1 '{"name":"Alice"}'` | Store a key |
| `GET` | `GET user:1` | Retrieve a key |
| `EXPIRE` | `EXPIRE user:1 300` | Set TTL in seconds |
| `SETEX` | `SETEX user:1 300 '...'` | Atomic SET + EXPIRE |
| `TTL` | `TTL user:1` | Check remaining TTL |
| `DEL` | `DEL user:1` | Remove a key |
| `EXISTS` | `EXISTS user:1` | Check if key exists |
| `MSET` | `MSET user:1 '...' user:2 '...'` | Set multiple keys |
| `KEYS` | `KEYS user:*` | List keys (avoid in prod — use SCAN) |
| `SCAN` | `SCAN 0 MATCH user:*` | Safe key iteration |

---

## CDN Caching Headers

```python
from fastapi import FastAPI, Response
from datetime import datetime, timedelta
import hashlib

app = FastAPI()

@app.get("/api/products/{product_id}")
async def get_product(product_id: str, response: Response):
    product = await _fetch_product(product_id)
    data = json.dumps(product)

    # Cache-Control — tells CDN/browser how long to cache
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=60"

    # ETag — content-based fingerprint for conditional requests
    etag = hashlib.md5(data.encode()).hexdigest()
    response.headers["ETag"] = f'"{etag}"'

    # Last-Modified — timestamp-based freshness
    response.headers["Last-Modified"] = product["updated_at"].strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

    return product


@app.get("/api/check-etag")
async def check_etag(product_id: str, request_etag: str | None = None):
    product = await _fetch_product(product_id)
    current_etag = hashlib.md5(json.dumps(product).encode()).hexdigest()

    if request_etag == current_etag:
        # Client has fresh data — return 304 Not Modified
        return Response(status_code=304)

    return {"data": product, "etag": current_etag}
```

### Key CDN Headers

| Header | Example | Purpose |
|--------|---------|---------|
| `Cache-Control` | `public, max-age=3600` | Directives for caching duration |
| `ETag` | `"33a64df551425fcc55e4..."` | Content version fingerprint |
| `Last-Modified` | `Mon, 12 Jul 2025 10:00:00 GMT` | Timestamp of last change |
| `Expires` | `Expires: Thu, 01 Dec 2025 16:00:00 GMT` | Deprecated; use Cache-Control |
| `Surrogate-Control` | `max-age=86400` | CDN-specific (Akamai, Fastly) |

---

## Combined Pattern: Cache-Aside with CDN

```python
@app.get("/api/v2/products/{product_id}")
async def get_product_v2(product_id: str, response: Response):
    # Try Redis first
    cache_key = f"product:{product_id}"
    cached = await cache.get(cache_key)
    if cached:
        data = json.loads(cached)
        response.headers["X-Cache"] = "HIT"
    else:
        # Miss — fetch from origin DB
        data = await _fetch_product_from_db(product_id)
        await cache.setex(cache_key, 300, json.dumps(data))
        response.headers["X-Cache"] = "MISS"

    # Set CDN headers so edge caches can serve this
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["ETag"] = hashlib.md5(json.dumps(data).encode()).hexdigest()
    return data
```

---

## Key Takeaways

- **Cache-aside** is the most common and robust pattern for read-heavy apps.
- **Write-through** sacrifices write speed for read consistency.
- **Write-behind** optimizes write throughput at the cost of potential data loss.
- **TTL** is the simplest invalidation; **LRU** manages memory pressure; **event-driven** gives fine-grained control.
- **CDN + Redis** creates a multi-layer cache hierarchy that can handle massive traffic.

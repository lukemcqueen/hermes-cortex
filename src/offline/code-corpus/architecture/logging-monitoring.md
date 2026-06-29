---
language: python
tags: [architecture, logging, monitoring, observability]
title: Logging and Monitoring
description: Structured JSON logging, log levels, centralized logging, correlation IDs, metrics, and health check endpoints
source: pattern
---

```python
# === STRUCTURED JSON LOGGING ===

import structlog
import logging
from datetime import datetime, timezone

# Configure structlog for JSON output
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Application-wide logger
logger = structlog.get_logger("myapp")

# Usage — all log output is JSON
logger.info("user_registered", user_id="abc123", email="user@example.com", signup_source="web")

# Output:
# {"event": "user_registered", "user_id": "abc123", "email": "user@example.com",
#  "signup_source": "web", "level": "info", "logger": "myapp",
#  "timestamp": "2026-06-29T10:30:00.123456+00:00"}
```

```python
# === LOG LEVELS AND SENSIBLE DEFAULTS ===

# config/logging.py
import os
import logging

LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

def get_log_level() -> int:
    """Deterministic log level from environment or default to INFO."""
    raw = os.getenv("LOG_LEVEL", "INFO").upper()
    return LOG_LEVEL_MAP.get(raw, logging.INFO)

# Level usage guidelines:
# DEBUG    — Detailed info for diagnosing problems (request payloads, SQL queries)
# INFO     — Key lifecycle events (service start/stop, user registration, order placed)
# WARNING  — Something unexpected but non-critical (rate limit approaching, deprecated API used)
# ERROR    — Operation failed, needs investigation (DB connection failed, third-party API error)
# CRITICAL — Application can't continue (out of disk, config validation failed on startup)

# Never log:
# - Passwords, tokens, API keys, or secrets at any level
# - PII (Personal Identifiable Information) in production logs
# - Full database dumps or large binary payloads
```

```python
# === CORRELATION IDS (trace requests across services) ===

import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a correlation ID propagated through logs."""

    HEADER_NAME = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        # Accept incoming correlation ID or generate one
        correlation_id = request.headers.get(
            self.HEADER_NAME,
            str(uuid.uuid4()),
        )

        # Bind to structlog context for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        # Pass to downstream services via response headers
        response = await call_next(request)
        response.headers[self.HEADER_NAME] = correlation_id
        return response

# Register on FastAPI app
# app.add_middleware(CorrelationIDMiddleware)

# Forward to downstream services in outgoing HTTP calls
import httpx

async def call_downstream():
    correlation_id = structlog.contextvars.get_contextvars().get("correlation_id")
    async with httpx.AsyncClient() as client:
        await client.get(
            "https://internal-api/orders",
            headers={"X-Correlation-ID": correlation_id},
        )
```

```python
# === CENTRALIZED LOGGING CONFIGURATION ===

# logging_config.py — single source of truth for all loggers
import structlog
import logging
import sys

def configure_logging(env: str = "development") -> None:
    """Centralized logging setup. Call once at application startup."""

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if env == "development"
        else structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            *shared_processors,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set root logger level
    root_logger = logging.getLogger()
    root_logger.setLevel(get_log_level())

    # Suppress noisy third-party loggers in production
    if env != "development":
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("aiosqlite").setLevel(logging.WARNING)
```

```python
# === METRICS (Prometheus + structured logging) ===

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import FastAPI, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time

# Define metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

ACTIVE_REQUESTS = Gauge(
    "http_requests_active",
    "Currently active requests",
)

DB_CONNECTION_POOL_SIZE = Gauge(
    "db_connection_pool_size",
    "Database connection pool size",
)

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ACTIVE_REQUESTS.inc()
        start = time.monotonic()

        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.monotonic() - start
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code if 'response' in dir() else 500,
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
            ).observe(duration)
            ACTIVE_REQUESTS.dec()

# Metrics endpoint (usually protected/not exposed publicly)
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")
```

```python
# === HEALTH CHECK ENDPOINTS ===

from fastapi import FastAPI, Response
from dataclasses import dataclass, field, asdict
from enum import Enum
import json

class HealthStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

@dataclass
class HealthCheck:
    status: HealthStatus = HealthStatus.PASS
    version: str = "1.0.0"
    release_id: str = ""
    checks: dict = field(default_factory=dict)

    def add_check(self, name: str, status: HealthStatus, output: str | None = None):
        entry = {"status": status.value}
        if output:
            entry["output"] = output
        self.checks[name] = entry
        if status == HealthStatus.FAIL:
            self.status = HealthStatus.FAIL
        elif status == HealthStatus.WARN and self.status != HealthStatus.FAIL:
            self.status = HealthStatus.WARN

# Startup health
health = HealthCheck(
    version="1.0.0",
    release_id="git-sha-abc123",
)

@app.get("/health")
async def health_check():
    hc = HealthCheck(version=health.version, release_id=health.release_id)

    # Check database connectivity (example)
    try:
        await db.execute("SELECT 1")
        hc.add_check("database", HealthStatus.PASS)
    except Exception as exc:
        hc.add_check("database", HealthStatus.FAIL, str(exc))

    # Check Redis (example)
    try:
        await redis.ping()
        hc.add_check("redis", HealthStatus.PASS)
    except Exception as exc:
        hc.add_check("redis", HealthStatus.FAIL, str(exc))

    # Check disk space (example)
    import shutil
    usage = shutil.disk_usage("/")
    if usage.free / usage.total < 0.05:
        hc.add_check("disk", HealthStatus.WARN, f"Only {usage.free / (1024**3):.1f}GB free")

    status_code = 200 if hc.status == HealthStatus.PASS else (503 if hc.status == HealthStatus.FAIL else 200)
    return Response(
        content=json.dumps(asdict(hc)),
        status_code=status_code,
        media_type="application/health+json",
    )

# Readiness probe (is the app ready to serve traffic?)
@app.get("/ready")
async def readiness():
    return {"status": "ok"}
```

```python
# === COMPLETE BOOTSTRAP EXAMPLE ===
# app/main.py — ties everything together

from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_client import start_http_server

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    configure_logging(env=os.getenv("APP_ENV", "development"))
    logger = structlog.get_logger("myapp")
    logger.info("application_starting", version="1.0.0")

    # Start Prometheus metrics server (non-blocking, separate port)
    start_http_server(port=8001)

    yield

    # Shutdown
    logger.info("application_stopping")

app = FastAPI(lifespan=lifespan)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(MetricsMiddleware)
```
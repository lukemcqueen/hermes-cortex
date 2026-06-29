---
language: python
tags: [architecture, errors, error-handling, patterns]
title: Error Handling Strategies
description: Result types, error hierarchies, typed errors, centralized error handling, and middleware patterns across languages
source: pattern
---

```python
# === PATTERN 1: Result Type (Railway Oriented Programming) ===

from __future__ import annotations
from dataclasses import dataclass
from typing import Generic, TypeVar, Callable
from enum import Enum

T = TypeVar('T')
E = TypeVar('E')

@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

@dataclass(frozen=True)
class Err(Generic[E]):
    error: E

type Result[T, E] = Ok[T] | Err[E]

# Usage
def divide(a: float, b: float) -> Result[float, str]:
    if b == 0:
        return Err("division by zero")
    return Ok(a / b)

def sqrt(x: float) -> Result[float, str]:
    if x < 0:
        return Err("negative input")
    return Ok(x ** 0.5)

# Railway — chain operations that short-circuit on error
result = divide(10, 2)
match result:
    case Ok(value):
        squared = sqrt(value)
        match squared:
            case Ok(v):    print(f"Result: {v}")
            case Err(e):   print(f"Error: {e}")
    case Err(e):
        print(f"Error: {e}")

# TODO: real `and_then` / `map` would make chaining cleaner
```

```python
# === PATTERN 2: Typed Error Hierarchy ===

from enum import IntEnum

class ErrorCode(IntEnum):
    NOT_FOUND = 1001
    VALIDATION_ERROR = 1002
    UNAUTHORIZED = 1003
    FORBIDDEN = 1004
    RATE_LIMITED = 1005
    INTERNAL = 5000

class AppError(Exception):
    """Base application error with machine-readable code."""
    def __init__(self, message: str, code: ErrorCode, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(message)

class NotFoundError(AppError):
    def __init__(self, entity: str, entity_id: str):
        super().__init__(
            message=f"{entity} with id '{entity_id}' not found",
            code=ErrorCode.NOT_FOUND,
            details={"entity": entity, "entity_id": entity_id},
        )

class ValidationError(AppError):
    def __init__(self, field: str, reason: str):
        super().__init__(
            message=f"Validation failed for '{field}': {reason}",
            code=ErrorCode.VALIDATION_ERROR,
            details={"field": field, "reason": reason},
        )

class UnauthorizedError(AppError):
    def __init__(self, reason: str = "Authentication required"):
        super().__init__(message=reason, code=ErrorCode.UNAUTHORIZED)

# Usage
def get_user(user_id: str) -> User:
    user = repository.find(user_id)
    if user is None:
        raise NotFoundError("User", user_id)
    return user
```

```python
# === PATTERN 3: Centralized Error Handler (FastAPI style) ===

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# Register a global exception handler for all AppErrors
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=_http_status_for(exc.code),
        content={
            "error": {
                "code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
                "request_id": request.headers.get("X-Request-ID", ""),
            }
        },
    )

def _http_status_for(code: ErrorCode) -> int:
    match code:
        case ErrorCode.NOT_FOUND:       return 404
        case ErrorCode.VALIDATION_ERROR: return 422
        case ErrorCode.UNAUTHORIZED:    return 401
        case ErrorCode.FORBIDDEN:       return 403
        case ErrorCode.RATE_LIMITED:    return 429
        case _:                         return 500
```

```python
# === PATTERN 4: Middleware-Based Error Handling ===

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import logging
import traceback

logger = logging.getLogger(__name__)

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except AppError as exc:
            logger.warning(
                "App error: %s [code=%s, details=%s]",
                exc.message, exc.code, exc.details,
            )
            return JSONResponse(
                status_code=_http_status_for(exc.code),
                content={"error": {"code": exc.code.value, "message": exc.message}},
            )
        except Exception as exc:
            logger.exception("Unhandled exception: %s", exc)
            return JSONResponse(
                status_code=500,
                content={"error": {"code": 5000, "message": "Internal server error"}},
            )

# Register on app
app.add_middleware(ErrorHandlingMiddleware)
```

```python
# === PATTERN 5: Graceful Degradation (Circuit Breaker) ===

import asyncio
from enum import Enum, auto

class CircuitState(Enum):
    CLOSED = auto()      # Normal operation
    OPEN = auto()        # Failing — reject requests immediately
    HALF_OPEN = auto()   # Testing if service has recovered

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time: float | None = None

    async def call(self, fn, fallback=None):
        if self._state == CircuitState.OPEN:
            if asyncio.get_event_loop().time() - self._last_failure_time > self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
            else:
                return fallback() if fallback else None

        try:
            result = await fn()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
            return result
        except Exception:
            self._failure_count += 1
            self._last_failure_time = asyncio.get_event_loop().time()
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
            return fallback() if fallback else None
```

```python
# === PATTERN 6: Alternative — Rust-style Result with monadic operations ===

from __future__ import annotations
from typing import Generic, TypeVar, Callable

T = TypeVar('T')
U = TypeVar('U')
E = TypeVar('E')
F = TypeVar('F')

class Result(Generic[T, E]):
    """A minimal monadic Result type."""
    def __init__(self, value: T | None = None, error: E | None = None):
        self._is_ok = error is None
        self._value = value
        self._error = error

    @staticmethod
    def ok(value: T) -> Result[T, E]:
        return Result(value=value)

    @staticmethod
    def err(error: E) -> Result[T, E]:
        return Result(error=error)

    def is_ok(self) -> bool:
        return self._is_ok

    def is_err(self) -> bool:
        return not self._is_ok

    def unwrap(self) -> T:
        if self._is_ok:
            return self._value
        raise ValueError(f"Called unwrap on error: {self._error}")

    def unwrap_or(self, default: T) -> T:
        return self._value if self._is_ok else default

    def map(self, fn: Callable[[T], U]) -> Result[U, E]:
        if self._is_ok:
            return Result.ok(fn(self._value))
        return Result(err=self._error)

    def and_then(self, fn: Callable[[T], Result[U, F]]) -> Result[U, E | F]:
        if self._is_ok:
            return fn(self._value)
        return Result(err=self._error)

    def map_err(self, fn: Callable[[E], F]) -> Result[T, F]:
        if self._is_err:
            return Result(err=fn(self._error))
        return Result.ok(self._value)

# Usage
def parse_int(s: str) -> Result[int, str]:
    try:
        return Result.ok(int(s))
    except ValueError:
        return Result.err(f"'{s}' is not an integer")

def double(x: int) -> Result[int, str]:
    return Result.ok(x * 2)

result = (
    parse_int("42")
    .map(lambda x: x + 1)
    .and_then(double)
)
print(result.unwrap())  # 86
```
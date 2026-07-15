---
name: error-handling
version: 1.0.0
category: software-development
description: >
  Error handling patterns and idioms: structured exceptions, graceful
  degradation, retry strategies, circuit breakers, user-facing error
  messages, and failure domain boundaries across Python and web apps.
tags: [error-handling, exceptions, resilience, retry, robustness]
related_skills: [systematic-debugging, logging-patterns, change-test-loop, engineering-approach]
---

# Error Handling Patterns

## When to Use

Load this skill when:
- Writing code that calls external services, filesystems, or databases
- Designing API error responses
- Implementing retry or fallback logic
- Reviewing code for error-handling correctness
- Any task involving user input validation

## Core Principles

### 1. Fail Fast vs. Fail Gracefully

| Approach | When to use | Example |
|----------|-------------|---------|
| **Fail fast** | Pre-condition violation, invalid config, missing dependency | Raise immediately on startup if DB unreachable |
| **Fail gracefully** | External service down, transient error, non-critical path | Return degraded result, log, alert |

**Rule:** Don't catch what you can't handle. If you can't recover, let it
propagate to a global handler.

### 2. Error Types and Their Responses

| Error type | Response | Examples |
|-----------|----------|----------|
| **Validation** | Return 400 with field-level errors | Missing field, bad format, out of range |
| **Authentication** | Return 401, no details | Invalid token, expired session |
| **Authorization** | Return 403, no details | Insufficient permissions |
| **Not found** | Return 404, minimal details | Resource doesn't exist |
| **Conflict** | Return 409, what conflicted | Duplicate, version mismatch, stale data |
| **Rate limited** | Return 429 with Retry-After header | Too many requests |
| **Internal** | Return 500, no internals exposed | DB connection lost, unexpected null |
| **Service unavailable** | Return 503, no internals | Downstream dependency down |

**Never expose internals to the client.** Log the full error server-side,
return a safe message to the user.

### 3. Python Exception Patterns

**Custom exception hierarchy:**
```python
class AppError(Exception):
    """Base for all application errors."""
    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.code = code or "UNKNOWN"
        self.details = details or {}

class NotFoundError(AppError):
    code = "NOT_FOUND"

class ValidationError(AppError):
    code = "VALIDATION"

class ExternalServiceError(AppError):
    code = "EXTERNAL_ERROR"
```

**Precise exception types — never bare `except:`:**
```python
# BAD — catches KeyboardInterrupt, SystemExit, everything
try:
    ...
except:
    pass

# GOOD — specific, recoverable
try:
    result = api.call()
except (ConnectionError, TimeoutError) as e:
    raise ExternalServiceError(f"API unreachable: {e}") from e
except ApiError as e:
    raise ValidationError(e.message, details=e.errors) from e
```

**Exception chaining (`raise ... from e`):**
```python
try:
    user = db.query(User).filter_by(id=user_id).one()
except NoResultFound as e:
    raise NotFoundError(f"User {user_id} not found") from e
```

### 4. Web API Error Format (RFC 7807 / Problem Details)

```json
{
    "type": "https://example.com/errors/validation",
    "title": "Validation Error",
    "status": 422,
    "detail": "Email address is already registered",
    "instance": "/api/v1/users",
    "errors": {
        "email": ["already_taken", "must_be_unique"]
    }
}
```

**Implementation (FastAPI):**
```python
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "type": "https://example.com/errors/validation",
            "title": "Validation Error",
            "status": 422,
            "detail": "Request validation failed",
            "instance": str(request.url),
            "errors": {e["loc"][-1]: e["msg"] for e in exc.errors()},
        },
    )
```

### 5. Retry Pattern

**Recommended library:** `tenacity` — battle-tested, handles jitter, async, and edge cases.

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=lambda retry_state: logger.warning("retry_attempt",
        extra={"func": retry_state.fn.__name__, "attempt": retry_state.attempt_number,
               "next_delay_s": retry_state.next_action.sleep}),
)
def fetch_data(url: str) -> dict:
    response = requests.get(url, timeout=5.0)
    response.raise_for_status()
    return response.json()
```

**Manual implementation (no dependencies):**
```python
import time
from functools import wraps

def retry(max_attempts=3, base_delay=1.0, backoff=2.0, exceptions=(ConnectionError, TimeoutError)):
    """Retry on transient failures with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = base_delay * (backoff ** (attempt - 1))
                        # Add jitter: ±25% random spread
                        import random
                        delay *= 1 + random.uniform(-0.25, 0.25)
                        logger.warning("retry_attempt",
                            extra={"func": func.__name__, "attempt": attempt, "next_delay_s": delay})
                        time.sleep(delay)
                    else:
                        logger.error("retry_exhausted",
                            extra={"func": func.__name__, "attempts": max_attempts})
            raise last_exception
        return wrapper
    return decorator
```

**Jitter is critical.** Without jitter, multiple retrying clients synchronize
(thundering herd). Add ±25% random spread to every delay.

**When to retry:**
- ✅ Network errors, timeouts, rate limits (429)
- ❌ Validation errors (4xx client errors)
- ❌ Authentication failures (won't succeed on retry)
- ❌ Business logic errors (won't change)

**What to log on each retry:** attempt number, delay, remaining attempts.

### 6. Circuit Breaker Pattern (for production services)

When a downstream service is failing, stop trying for a while.

**Recommended library:** `pybreaker` or `resilient-circuit` (supports PostgreSQL for distributed state).

```python
from pybreaker import CircuitBreaker

breaker = CircuitBreaker(fail_max=5, reset_timeout=30)

@breaker
def call_external_api(payload: dict) -> dict:
    response = requests.post("https://api.partner.com/charge",
                             json=payload, timeout=10.0)
    response.raise_for_status()
    return response.json()

def handle_payment(order_id: str, amount: float):
    try:
        result = call_external_api({"order_id": order_id, "amount": amount})
        return {"status": "success", "transaction": result}
    except pybreaker.CircuitBreakerError:
        # Circuit is open — queue for retry instead of failing
        queue_payment_for_retry(order_id, amount)
        return {"status": "queued", "retry_in_s": 30}
    except Exception as e:
        logger.error("payment_failed", extra={"order_id": order_id, "error": str(e)})
        raise
```

**Manual implementation (no dependencies):**
```python
import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — don't call
    HALF_OPEN = "half_open" # Testing if recovered

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0

    def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise ServiceUnavailableError("Circuit breaker open")

        try:
            result = func(*args, **kwargs)
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
            raise
```

### 7. Error Classification (TRANSIENT / FATAL / DEGRADED)

Not all errors are equal. Classify before deciding how to handle:

```python
from enum import Enum

class ErrorType(Enum):
    TRANSIENT = "transient"   # Retry (network timeout, 503, 429)
    FATAL = "fatal"           # Fail fast (validation, auth, 400)
    DEGRADED = "degraded"     # Fallback (3rd party down, feature unavailable)

class ErrorClassifier:
    @staticmethod
    def classify(exception) -> ErrorType:
        if isinstance(exception, (TimeoutError, ConnectionError)):
            return ErrorType.TRANSIENT
        if isinstance(exception, (ValidationError, PermissionError)):
            return ErrorType.FATAL
        if isinstance(exception, ThirdPartyDownError):
            return ErrorType.DEGRADED
        return ErrorType.FATAL  # Default: safe

def handle_error(exception):
    error_type = ErrorClassifier.classify(exception)
    if error_type == ErrorType.TRANSIENT:
        return retry_with_backoff(lambda: raise_or_return(exception))
    elif error_type == ErrorType.FATAL:
        raise exception
    elif error_type == ErrorType.DEGRADED:
        return fallback_response()
```

### 8. Fallback Routing (Stripe pattern)

When primary service fails, try an alternative:

```python
def process_payment(amount: float, currency: str) -> dict:
    """Try primary processor, fall back to secondary."""
    providers = [
        ("stripe", stripe_charge),
        ("paypal", paypal_charge),
        ("local_fallback", manual_hold_charge),
    ]
    last_error = None
    for provider_name, provider_fn in providers:
        try:
            result = provider_fn(amount, currency)
            logger.info("payment_processed",
                extra={"provider": provider_name, "amount": amount})
            return result
        except Exception as e:
            logger.warning("payment_fallback",
                extra={"provider": provider_name, "error": str(e)})
            last_error = e
            continue
    raise PaymentFailedError("All providers failed") from last_error
```


### 10. Graceful Degradation

When a non-critical dependency fails, degrade instead of crashing:

```python
def get_recommendations(user_id: str) -> list:
    """Return recommendations. If ML service is down, return popular items."""
    try:
        return ml_service.recommend(user_id, top_n=5)
    except ExternalServiceError:
        logger.warning("recommendation_service_down, falling back to popular")
        return db.query(Product).order_by(Product.popularity.desc()).limit(5).all()
```

**Pattern:** Try primary → log failure → return degraded result.

### 8. Timeouts Everywhere

Every external call needs a timeout:

```python
# Python requests
response = requests.get(url, timeout=5.0)  # Seconds

# Database
cursor.execute("SET statement_timeout = 5000")  # PostgreSQL ms

# HTTP server
# uvicorn: --timeout-keep-alive 30 --timeout-graceful-shutdown 120
```

**Without timeouts:** a hanging dependency hangs your entire service.

### 9. Panic / Global Handler

```python
import sys
import logging

logger = logging.getLogger(__name__)

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Last-resort handler for uncaught exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("unhandled_exception",
        extra={"type": exc_type.__name__, "message": str(exc_value)})

sys.excepthook = global_exception_handler
```

## Anti-Patterns

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| `except: pass` | Swallows every error — undebuggable |
| `except Exception as e: print(e)` | In production, print goes nowhere useful |
| Returning error strings | Callers can't distinguish error from data |
| Catching and re-raising same type | Adds no value, obscures original trace |
| No timeout on external calls | Hangs entire process on network stall |
| Logging sensitive data in errors | Passwords/keys in error logs = security incident |

## Verification

```python
# Test that error responses follow the schema
response = client.post("/api/users", json={"email": "invalid"})
assert response.status_code == 422
data = response.json()
assert "title" in data
assert "errors" in data
assert isinstance(data["errors"], dict)
```

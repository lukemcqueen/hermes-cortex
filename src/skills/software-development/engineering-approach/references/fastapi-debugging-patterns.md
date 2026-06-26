# FastAPI Debugging Patterns

Recurring debugging patterns specific to FastAPI + Python 3.12+ async middleware.

## ValueError in Sync Endpoint → ExceptionGroup Crash

### Symptom

A synchronous FastAPI endpoint raises `ValueError`, and instead of returning a 500 response, the request crashes with an unhandled `ExceptionGroup`:

```
ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    | ValueError: 'original' is not a valid RightType
```

The traceback shows the error propagating through `starlette.middleware.base.BaseHTTPMiddleware`, with the final exception wrapped in an `ExceptionGroup` by `anyio`.

### Root Cause

When a sync endpoint raises `ValueError`, the `ExceptionMiddleware` in the async middleware stack doesn't find a registered handler for `ValueError` (it only handles `HTTPException` and `WebSocketException` by default). The unhandled exception propagates through the `BaseHTTPMiddleware`'s `collapse_excgroups` context manager, which wraps individual exceptions in an `ExceptionGroup` for `anyio` compatibility. FastAPI's error handling is then unable to unwrap the ExceptionGroup, resulting in a 500 crash rather than a controlled error response.

### Fix

Wrap the endpoint body in a `try/except ValueError` block and raise `HTTPException`:

```python
@router.post("/calculate", response_model=WorkDistributionOut)
def calculate_distribution(body: CalculateRequest) -> WorkDistributionOut:
    try:
        result = calculate_work_distribution(...)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return WorkDistributionOut(...)
```

### Prevention

- Any sync endpoint that calls domain validation functions (which may raise `ValueError`) MUST wrap the call in try/except.
- Use `HTTPException` (not `ValueError`) for all user-facing error paths in endpoints.
- Validate input at the Pydantic schema layer whenever possible — Pydantic validation errors are caught by FastAPI's built-in `RequestValidationError` handler and return 422 correctly.

### Related patterns

- **Async endpoints** do NOT have this issue — FastAPI's `async def` endpoint handler catches `ValueError` correctly and returns 500. This issue is specific to sync (`def`) endpoints behind async middleware.
- **Pydantic field validation** (using `@field_validator` or type annotations) is the safest place for input validation — errors are caught before the endpoint runs.

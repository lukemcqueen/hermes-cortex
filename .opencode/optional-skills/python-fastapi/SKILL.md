---
name: python-fastapi
description: |
  Build, refactor, and test FastAPI services using typed Pydantic models,
  clean architecture, and pytest.

  Triggers when user mentions:
  - "fastapi"
  - "pydantic model"
  - "api endpoint"
  - "python refactor"
  - "pytest"
---

# Python + FastAPI

## Purpose
Create, refactor, and test FastAPI code that is:
- strongly typed (Pydantic)
- modular (services)
- production-ready (secure, performant)

---

## Inputs
- Feature request OR existing code
- Optional: failing test, bug, or performance issue

---

## Output (STRICT ORDER)

1. **Code** (complete, runnable)
2. **Explanation** (≤3 sentences)
3. **Tests** (pytest, success + failure + edge cases)

---

## Workflow (STRICT)

1. Identify intent (feature, refactor, bug, test)
2. Define/adjust Pydantic schemas FIRST
3. Keep route handlers minimal
4. Move logic to services (`app/services`)
5. Use dependency injection for:
   - DB
   - auth
   - config
6. Add/update tests alongside code
7. Validate types (`mypy`) and lint (`ruff`)
8. Keep output minimal and deterministic

---

## Architecture Rules (MANDATORY)

### Routes (FastAPI)
- Thin: request/response only
- No business logic
- Use explicit response models

Example:
```python
@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, service: OrderService = Depends()):
    return service.create(payload)
```

---

### Schemas (Pydantic)

* Separate:

  * `Create`
  * `Update`
  * `Response`
* Use strict typing

Example:

```python
from pydantic import BaseModel

class OrderCreate(BaseModel):
    item_id: int
    quantity: int
```

---

### Services (REQUIRED for complexity)

Use when:

* multi-step logic
* DB operations
* external APIs

Pattern:

```python
class OrderService:
    def __init__(self, db):
        self.db = db

    def create(self, payload):
        # business logic
        return ...
```

---

### Dependency Injection

Use `Depends()` for:

* DB sessions
* authentication
* shared services

---

## Testing (MANDATORY)

Use `pytest`

### Rules

* Test behavior, not implementation
* Cover:

  * success
  * failure
  * edge cases

### Example

```python
def test_create_order(client):
    res = client.post("/orders", json={"item_id": 1, "quantity": 2})
    assert res.status_code == 201
```

---

## Refactoring Guidelines

* Remove duplication first
* Extract services before adding complexity
* Keep functions ≤20 lines
* Replace large conditionals with clear logic
* Keep types explicit

---

## Security Rules (STRICT)

* Validate ALL input via Pydantic
* Never trust request data
* Sanitize external inputs
* Use proper auth dependencies
* Avoid leaking internal errors

---

## Performance (ENTERPRISE)

* Use async for I/O-bound tasks
* Avoid N+1 queries
* Use pagination for large data
* Cache where needed (Redis, etc.)
* Move heavy tasks to background workers

---

## Commands (REFERENCE)

```bash
pytest -q
uvicorn app.main:app --reload
ruff check .
mypy .
```

---

## Anti-Patterns (AVOID)

* Business logic in routes
* Untyped code
* Skipping tests
* Large monolithic files
* Blocking I/O in async routes
* Returning raw dicts instead of models

---

## Examples

### Example 1

User: "refactor this fastapi endpoint"

→ Extract service, add schema, add tests

---

### Example 2

User: "add new api endpoint"

→ Create:

* route
* schema
* service
* pytest

---

## Goal

Produce **clean, typed, testable FastAPI code** that:

* scales to production
* is easy to refactor
* passes strict validation
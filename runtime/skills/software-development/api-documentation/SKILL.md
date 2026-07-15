---
name: api-documentation
version: 1.0.0
category: software-development
description: >
  API documentation standards and tooling: OpenAPI/Swagger specs,
  endpoint descriptions, request/response schemas, error documentation,
  authentication docs, changelogs, and generation tooling.
tags: [api, openapi, swagger, documentation, specs]
related_skills: [product-requirements, engineering-approach, code-review]
---

# API Documentation Standards

## When to Use

Load this skill when:
- Designing a new API endpoint or service
- Writing OpenAPI/Swagger specs
- Reviewing API documentation for completeness
- Setting up documentation generation tooling
- Onboarding new API consumers

## Core Principles

### 1. Document Before Implementation

Write the API spec before writing the code. This surfaces design issues
early and gives both frontend and backend a contract to work against.

**Workflow:** Spec → Review → Implement → Verify spec matches code.

### 2. Complete Endpoint Documentation

Every endpoint MUST document:

| Field | Required | Example |
|-------|----------|---------|
| `summary` | Always | "Create a new user account" |
| `description` | Always | "Registers a new user with email and password. Sends verification email." |
| `operationId` | Always | `createUser` |
| `tags` | Category | `["Users", "Authentication"]` |
| `parameters` | If applicable | Path params, query params |
| `requestBody` | If applicable | Schema + content type |
| `responses` | Always | At minimum: success + all error codes |
| `security` | If applicable | Auth scheme required |

**Good example:**
```yaml
paths:
  /users:
    post:
      summary: Create a new user account
      description: |
        Registers a new user with email and password.
        Sends a verification email to the provided address.
        Rate limited to 10 requests per minute per IP.
      operationId: createUser
      tags: [Users]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateUserRequest'
      responses:
        '201':
          description: User created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UserResponse'
        '400':
          description: Validation error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '409':
          description: Email already registered
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '429':
          description: Rate limit exceeded
```

### 3. Schema Definitions

Use `$ref` to avoid duplication. Every reusable type gets its own schema:

```yaml
components:
  schemas:
    User:
      type: object
      required: [id, email, name]
      properties:
        id:
          type: string
          format: uuid
          description: Unique user identifier
          example: "550e8400-e29b-41d4-a716-446655440000"
        email:
          type: string
          format: email
          description: User's email address
          example: "user@example.com"
        name:
          type: string
          description: Display name
          minLength: 1
          maxLength: 100
          example: "Jane Doe"
        createdAt:
          type: string
          format: date-time
          description: ISO 8601 timestamp
```

**Schema rules:**
- Every field gets `type`, `description`, and `example`
- `required` lists mandatory fields
- `nullable: true` for optional nullable fields
- `minLength`/`maxLength` for strings
- `minimum`/`maximum` for numbers
- `enum` for fixed values

### 4. Document All Error Responses

Every endpoint's error responses MUST be documented:

```yaml
responses:
  '400':
    description: Validation error — request body is malformed or missing required fields
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ErrorResponse'
        example:
          type: https://example.com/errors/validation
          title: Validation Error
          status: 400
          detail: "email: must be a valid email address"
  '401':
    description: Authentication required — missing or invalid API key
  '403':
    description: Forbidden — insufficient permissions
  '404':
    description: Resource not found
  '429':
    description: Rate limit exceeded — retry after the Retry-After header
  '500':
    description: Internal server error — the request may be retried
  '503':
    description: Service temporarily unavailable — maintenance or overload
```

### 5. Authentication Documentation

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |
        JWT token obtained from POST /auth/login.
        Include as: `Authorization: Bearer <token>`
        Tokens expire after 24 hours.

security:
  - BearerAuth: []
```

### 6. Python Tooling

**FastAPI (auto-generates OpenAPI from type hints):**
```python
from pydantic import BaseModel, EmailStr
from fastapi import FastAPI, HTTPException, status

app = FastAPI(
    title="User API",
    version="1.0.0",
    description="User management API with email verification",
)

class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8)

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    created_at: str

@app.post("/users", response_model=UserResponse, status_code=201,
          summary="Create a new user account",
          responses={
              400: {"model": ErrorResponse, "description": "Validation error"},
              409: {"model": ErrorResponse, "description": "Email already registered"},
          })
async def create_user(body: CreateUserRequest):
    """Registers a new user. Sends verification email."""
    ...
```

### 7. Changelog / Versioning

```
# API Changelog

## 2026-07-15 — v2.1.0
### Added
- `GET /users/:id/activity` — returns recent user activity
- `sort` and `filter` query params on `GET /users`

### Changed
- `POST /users` now sends verification email (was sync, now async)
- Rate limit increased from 10/min to 30/min

### Deprecated
- `GET /users/search` — replaced by `GET /users?q=:query`
  Scheduled removal: 2026-10-15

### Fixed
- `PATCH /users/:id` now correctly returns 404 for non-existent users
```

**Versioning strategy:**
- URL path: `v1/`, `v2/` — simple, explicit
- Header: `Accept: application/vnd.api+json;version=2` — no URL pollution
- Never: just "latest" — consumers need stability

### 8. Rate Limits & Pagination

Document rate limits in the endpoint description:

```yaml
x-rate-limit:
  limit: 1000
  window: hour
  scope: per-user
```

Document pagination on list endpoints:

```yaml
parameters:
  - name: cursor
    in: query
    schema:
      type: string
    description: |
      Cursor for pagination. Pass the `next_cursor` value from the
      previous response. Omit for the first page. Cursors expire
      after 10 minutes.
  - name: limit
    in: query
    schema:
      type: integer
      default: 20
      maximum: 100
    description: Maximum items per page (1-100).

responses:
  '200':
    content:
      application/json:
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                $ref: '#/components/schemas/User'
            next_cursor:
              type: string
              nullable: true
              description: Pass as ?cursor= to get the next page. null = last page.
```

## Tooling

| Tool | Language | Output |
|------|----------|--------|
| FastAPI | Python | Auto-generates OpenAPI 3.1; `/docs` (Swagger UI) and `/redoc` |
| drf-spectacular | Python | OpenAPI 3.0 from Django REST Framework |
| OpenAPI Generator | Any | SDKs, server stubs, client libs from spec |
| Swagger Editor | — | Web UI for editing specs with live preview |
| Spectral | — | Linter for OpenAPI specs (enforce conventions) |
| Redocly CLI | — | Bundle, lint, preview OpenAPI specs |

## Verification

```bash
# Validate OpenAPI spec
npx @redocly/cli lint openapi.yaml

# Check spec is valid against OpenAPI 3.1 schema
npx swagger-cli validate openapi.yaml

# Generate server stub and verify it compiles
npx @openapitools/openapi-generator-cli generate \
  -i openapi.yaml -g python-fastapi -o /tmp/stub
```

## Anti-Patterns

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| "Docs are in the code comments" | Code comments aren't discoverable by consumers |
| Documenting only success responses | Consumers don't know how to handle errors |
| No examples | Consumers can't tell what valid data looks like |
| Out-of-date spec | Worse than no spec — actively misleading |
| Too much text | Be concise; let the schema do the talking |
| No rate limit docs | Consumers get surprised by 429s |
| Versionless API | Breaking changes break all consumers at once |

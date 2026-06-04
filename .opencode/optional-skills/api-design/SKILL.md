---
name: api-design
description: |
  Design and review APIs with clear resources, validation, auth boundaries,
  stable contracts, error shapes, pagination, and idempotency.

  Triggers when user mentions:
  - "api design"
  - "endpoint"
  - "route handler"
  - "rest api"
  - "request validation"
  - "api contract"
---

# API Design

## Purpose
Create APIs that are:
- predictable
- secure
- versionable
- easy to test
- safe for clients

---

## Output (STRICT ORDER)

1. **API Contract**
2. **Implementation Notes**
3. **Tests / Verification**

---

## API Contract Format

```md
## Endpoint
<METHOD> <path>

## Purpose
What this endpoint does

## Auth
Required role/permission

## Request
Params/body/query

## Response
Status + response shape

## Errors
Status + error shape

## Notes
Pagination, idempotency, rate limits, compatibility
```

---

## Core Rules

* Use clear resource names
* Use correct HTTP methods
* Validate all request inputs
* Return explicit status codes
* Keep response shapes stable
* Never leak internal exceptions
* Enforce auth server-side
* Version or preserve public contracts

---

## HTTP Method Rules

```txt
GET     → read
POST    → create/action
PUT     → replace
PATCH   → partial update
DELETE  → delete
```

Rules:

* GET must not mutate data
* risky writes should be idempotent when possible
* destructive actions require clear authorization

---

## Status Codes

Use explicit codes:

```txt
200 OK                  → successful read/update
201 Created             → created resource
202 Accepted            → async job accepted
204 No Content          → successful delete/no body
400 Bad Request         → malformed request
401 Unauthorized        → not logged in/auth missing
403 Forbidden           → authenticated but not allowed
404 Not Found           → resource not found or hidden
409 Conflict            → state/version conflict
422 Unprocessable Entity → validation failed
429 Too Many Requests   → rate limited
500 Internal Error      → unexpected server failure
```

---

## Request Validation

Validate:

* path params
* query params
* body fields
* enum values
* dates
* pagination limits
* nested objects

Treat all client input as untrusted.

---

## Response Shape

Prefer stable envelope when project uses one:

```json
{
  "data": {},
  "meta": {}
}
```

For errors:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "Validation failed",
    "fields": {
      "email": ["is required"]
    }
  }
}
```

Rules:

* keep error codes stable
* avoid stack traces
* do not expose internal class names
* do not return unnecessary PII

---

## Auth / Authorization

For every endpoint define:

* who can call it
* what resource scope applies
* whether tenant/account boundaries apply
* whether ownership must be checked

Never trust client-provided role, user_id, account_id, or tenant_id without server validation.

---

## Pagination / Filtering

Required for list endpoints that can grow.

Rules:

* enforce max page size
* use stable ordering
* document filters
* avoid unbounded queries

Example:

```txt
GET /orders?page=1&per_page=25&status=pending
```

---

## Idempotency

Use idempotency keys for risky or retryable writes:

* payments
* order creation
* external API calls
* job enqueueing
* destructive actions

Pattern:

```txt
Idempotency-Key: <client-generated-key>
```

---

## Compatibility Rules

* do not remove fields without versioning
* do not change meaning of fields silently
* additive changes are safest
* version breaking changes
* document deprecations

---

## Security Rules

* enforce auth before data access
* validate input before processing
* rate-limit sensitive endpoints
* never leak internals
* log safely without secrets/PII
* use CSRF protection for browser sessions

---

## Testing Rules

Every endpoint should test:

* success
* validation failure
* unauthorized
* forbidden
* not found
* edge case

For risky writes, test:

* retry/idempotency behavior
* transaction rollback
* duplicate submission

---

## Enterprise Checks

Consider:

* audit logging for sensitive actions
* observability: request IDs, metrics, errors
* backward compatibility
* tenant isolation
* rate limiting
* async job status endpoint if long-running

---

## Anti-Patterns

Avoid:

* vague endpoint names
* POST for simple reads
* GET with side effects
* unstable response shapes
* raw exception messages
* missing auth checks
* unbounded list responses
* hidden breaking changes
* trusting client IDs blindly

---

## Final Report

```md
## API Design Result
pass | needs changes

## Contract
- method/path:
- request:
- response:
- errors:

## Security
- auth:
- data exposure:

## Verification
- tests:

## Notes
Compatibility, risks, follow-ups
```

---

## Goal

Produce APIs that are secure, stable, documented, testable, and safe for enterprise clients.
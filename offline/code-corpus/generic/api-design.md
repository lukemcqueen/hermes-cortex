---
language: generic
tags: [api, web, pattern]
title: REST API Design Patterns
description: RESTful API conventions: URLs, status codes, pagination, errors, versioning.
source: reference
---

```generic
# REST API Design Patterns

## URL Structure
```
GET    /api/resource          # List all
GET    /api/resource/:id      # Get one
POST   /api/resource          # Create
PUT    /api/resource/:id      # Replace
PATCH  /api/resource/:id      # Partial update
DELETE /api/resource/:id      # Delete
```

## HTTP Status Codes
- `200 OK` — Success
- `201 Created` — Resource created
- `204 No Content` — Deletion success
- `400 Bad Request` — Invalid input
- `401 Unauthorized` — No auth
- `403 Forbidden` — No permission
- `404 Not Found` — Resource missing
- `409 Conflict` — Duplicate/stale
- `422 Unprocessable` — Validation errors
- `429 Too Many Requests` — Rate limit
- `500 Internal Server Error` — Server fault

## Pagination
```
GET /api/items?page=2&per_page=50

Response:
{
  "data": [...],
  "meta": {
    "page": 2,
    "per_page": 50,
    "total": 1024,
    "total_pages": 21
  }
}
```

## Error Response
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Name is required",
    "details": [
      {"field": "name", "message": "must not be empty"}
    ]
  }
}
```

## Versioning
- URL: `/api/v1/resource`
- Header: `Accept: application/vnd.app.v2+json`

```

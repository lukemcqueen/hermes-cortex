---
language: yaml
tags: [documentation, api, openapi, rest]
title: OpenAPI / API Documentation Guide
description: OpenAPI/Swagger spec structure, endpoint descriptions, request/response schemas, error documentation, and rate limits
source: pattern
---

# OpenAPI / API Documentation Guide

A well-documented API follows the OpenAPI 3.1 specification. Every endpoint should describe:

- What it does (summary + description)
- Request parameters (path, query, headers, body)
- Response schemas (status code, body shape)
- Error responses (status codes, error payload)
- Authentication and rate limits

Below is a complete OpenAPI snippet for a hypothetical User API.

```yaml
openapi: "3.1.0"
info:
  title: User Management API
  version: "1.0.0"
  description: |
    Create, read, update, and delete user accounts.
    Base URL: `https://api.example.com/v1`
  contact:
    name: API Support
    email: support@example.com
  license:
    name: MIT
    url: https://opensource.org/licenses/MIT

servers:
  - url: https://api.example.com/v1
    description: Production server
  - url: https://staging.api.example.com/v1
    description: Staging server

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |
        Obtain a token via `POST /auth/login`. Include as `Authorization: Bearer <token>`.

  schemas:
    Error:
      type: object
      required: [error, status]
      properties:
        error:
          type: string
          description: Machine-readable error code.
          example: "rate_limit_exceeded"
        message:
          type: string
          description: Human-readable explanation.
          example: "Too many requests. Retry after 30 seconds."
        status:
          type: integer
          example: 429

    User:
      type: object
      required: [id, name, email]
      properties:
        id:
          type: string
          format: uuid
          description: Unique user identifier.
          example: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        name:
          type: string
          minLength: 1
          maxLength: 120
          example: "Alice Johnson"
        email:
          type: string
          format: email
          example: "alice@example.com"
        role:
          type: string
          enum: [user, admin, moderator]
          default: user
        created_at:
          type: string
          format: date-time
          example: "2026-06-15T14:30:00Z"

    CreateUserRequest:
      type: object
      required: [name, email]
      properties:
        name:
          type: string
          example: "Alice Johnson"
        email:
          type: string
          format: email
          example: "alice@example.com"
        role:
          type: string
          enum: [user, admin, moderator]
          default: user

    UserList:
      type: object
      required: [data, pagination]
      properties:
        data:
          type: array
          items:
            $ref: "#/components/schemas/User"
        pagination:
          type: object
          properties:
            page:
              type: integer
              example: 1
            per_page:
              type: integer
              example: 25
            total:
              type: integer
              example: 142

paths:
  /users:
    get:
      summary: List all users
      description: Retrieve a paginated list of user accounts.
      operationId: listUsers
      security:
        - BearerAuth: []
      parameters:
        - name: page
          in: query
          required: false
          schema:
            type: integer
            default: 1
            minimum: 1
          description: Page number.
        - name: per_page
          in: query
          required: false
          schema:
            type: integer
            default: 25
            maximum: 100
          description: Items per page.
        - name: role
          in: query
          required: false
          schema:
            type: string
            enum: [user, admin, moderator]
          description: Filter by role.
      responses:
        "200":
          description: A paginated list of users.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/UserList"
        "401":
          $ref: "#/components/responses/Unauthorized"
        "429":
          $ref: "#/components/responses/RateLimited"

    post:
      summary: Create a new user
      description: Register a new user account.
      operationId: createUser
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateUserRequest"
      responses:
        "201":
          description: User created successfully.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/User"
        "400":
          description: Validation error.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
        "409":
          description: Email already exists.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
        "429":
          $ref: "#/components/responses/RateLimited"

  /users/{userId}:
    get:
      summary: Get a user by ID
      operationId: getUserById
      security:
        - BearerAuth: []
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
            format: uuid
          description: The user's unique ID.
      responses:
        "200":
          description: User details.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/User"
        "404":
          description: User not found.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"

components:
  responses:
    Unauthorized:
      description: Missing or invalid authentication token.
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/Error"
          example:
            error: "unauthorized"
            message: "Provide a valid Bearer token in the Authorization header."
            status: 401

    RateLimited:
      description: Rate limit exceeded.
      headers:
        X-RateLimit-Remaining:
          schema:
            type: integer
          description: Number of requests remaining in the current window.
        X-RateLimit-Reset:
          schema:
            type: integer
          description: Unix timestamp when the rate limit resets.
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/Error"
          example:
            error: "rate_limit_exceeded"
            message: "Too many requests. Retry after 30 seconds."
            status: 429
```

## Error Documentation Best Practices

- Use **consistent error schemas** across all endpoints (same shape: `error`, `message`, `status`)
- Include **machine-readable codes** (`error`) for programmatic handling and **human-readable messages** for debugging
- Document every error status code per endpoint (`400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`)
- For validation errors, include a `details` array pointing to the specific field

## Rate Limits

| Scope     | Limit              | Window  | Headers                                     |
|-----------|--------------------|---------|---------------------------------------------|
| Per-user  | 100 requests        | 1 min   | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` |
| Per-IP    | 1000 requests       | 1 hour  |                                             |

Respond with `429 Too Many Requests` and a `Retry-After` header when exceeded.

## Documentation Principles

- **Every endpoint needs** a summary, description, operationId, and full request/response schema
- **Document all error codes** — not just the happy path
- **Use `$ref`** to share schemas instead of duplicating them
- **Version your API** in the URL path (`/v1/`, `/v2/`)
- **Keep examples realistic** — test that they match the schema
--- Full content (truncated) ---
---
name: rest-graphql-debug
description: "Debug REST/GraphQL APIs: status codes, auth, schemas, repro."
version: 1.2.0
author: eren-karakus0
license: MIT
metadata:
  hermes:
    tags: [api, rest, graphql, http, debugging, testing, curl, integration]
    category: software-development
    related_skills: [systematic-debugging, test-driven-development]
---

# API Testing & Debugging

Drive REST and GraphQL diagnosis through Hermes tools — `terminal` for `curl`, `execute_code` for Python `requests`, `web_extract` for vendor docs. Isolate the failing layer before guessing at the fix.

## When to Use

- API returns unexpected status or body
- Auth fails (401/403 after token refresh, OAuth, API key)
- Works in Postman but fails in code
- Webhook / callback integration debugging
- Building or reviewing API integration tests
- Rate limiting or pagination issues

Skip for UI rendering, DB query tuning, or DNS/firewall infra (escalate).

## Core Principle

**Isolate the layer, then fix.** A 200
... [truncated]
--- End skill ---
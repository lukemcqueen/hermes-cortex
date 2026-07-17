--- Full content (truncated) ---
---
name: canvas
description: Canvas LMS integration — fetch enrolled courses and assignments using API token authentication.
version: 1.0.0
author: community
license: MIT
platforms: [linux, macos, windows]
prerequisites:
  env_vars: [CANVAS_API_TOKEN, CANVAS_BASE_URL]
metadata:
  hermes:
    tags: [Canvas, LMS, Education, Courses, Assignments]
---

# Canvas LMS — Course & Assignment Access

Read-only access to Canvas LMS for listing courses and assignments.

## Scripts

- `scripts/canvas_api.py` — Python CLI for Canvas API calls

## Setup

1. Log in to your Canvas instance in a browser
2. Go to **Account → Settings** (click your profile icon, then Settings)
3. Scroll to **Approved Integrations** and click **+ New Access Token**
4. Name the token (e.g., "Hermes Agent"), set an optional expiry, and click **Generate Token**
5. Copy the token and add to `~/.hermes/.env`:

```
CANVAS_API_TOKEN=your_token_here
CANVAS_BASE_URL=https://yourschool.instructure.com
```

The base URL is whatever 
... [truncated]
--- End skill ---
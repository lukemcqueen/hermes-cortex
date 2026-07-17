--- Full content (truncated) ---
---
name: env-aware-compose-wrapper
category: devops
description: >
  Build an env-aware `_compose()` wrapper for `./run` CLI scripts that
  requires an explicit environment variable (e.g. APP_ENV), halts with
  instructions if unset, and shows a prominent env banner on every Docker
  invocation. Supports dev/stage/prod with separate compose override files
  and env files.
tags: [docker, compose, environment, devops, cli, run-script]
version: 2
---

# Env-Aware Compose Wrapper

## When to Use

You maintain or are building a `./run` CLI script that orchestrates Docker Compose
across multiple environments (dev, stage, prod). The operator must explicitly
declare their target and see it clearly in every command's output.

## Pattern

The `./run` script gains:

1. **Explicit env var required** — no silent default. Halts with a boxed error
   and instructions if not set (e.g. `export APP_ENV=dev|stage|prod`).
2. **`_compose()` wrapper** — replaces every bare `docker compose` call.
   Selects
... [truncated]
--- End skill ---
--- Full content (truncated) ---
---
name: unified-cli-script
version: 1.0.0
description: >-
  Design a unified ./run CLI script for multi-environment Docker Compose
  deployments. Covers the _compose() wrapper, CLIENT_ENV requirement,
  prominent env display, compose override files, and git hook compatibility.
triggers:
  - user asks to update ./run for env support
  - user asks to make CLI env-aware
  - user asks to halt with instructions when config missing
  - user says 'scripts should halt if no env set'
  - creating or modifying a unified CLI script for monorepo Docker workflows
---

# Unified CLI Script (`./run`)

Pattern for building a single `./run` CLI that works across `dev`, `stage`, and `prod` environments via Docker Compose override files.

## Architecture

```
./run                    → unified entry point
docker-compose.yml       → base compose file (shared config)
docker-compose.stage.yml → stage overrides
docker-compose.prod.yml  → production overrides
.env                     → dev environment varia
... [truncated]
--- End skill ---
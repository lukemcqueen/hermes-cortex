---
name: local-config-drift-diagnostics
aliases: [config-drift-diagnostics]
version: 1.0.0
category: devops
description: >-
  Container configs stale? Compare vs source in 3 locations.
author: Gisu
license: MIT
platforms: [linux, darwin]
---

# Config Drift Diagnostics

## When to Use

A Docker container is failing with auth errors (401, JDBC password failure)
and you suspect the config inside doesn't match the source `.env` or templates.

## The Pattern

```
.env → envsubst → generated configs → Dockerfile COPY → container image
```

A stale image is the most common drift source: `.env` or templates updated,
`generate-configs` re-run, but image never rebuilt.

## 3-Location Comparison

```bash
# (1) What the container has
docker exec <c> grep key /path/to/config.properties

# (2) What build SHOULD produce
grep key generated/.../config.properties

# (3) What .env says
grep VARIABLE .env
```

| Result | Interpretation |
|--------|---------------|
| (1)≠(2) | Image built from stale generated — rebuild |
| (2)≠(3) | `generate-configs` not re-run — regenerate first |
| All match | Problem is elsewhere |

## Timeline Check

```bash
stat generated/.../config.properties
docker inspect <c> --format '{{.Created}}'
```

Config generated AFTER container created = stale image.

## Fix

```bash
cd <project>
source .env
./run generate-configs
./run build <service>
docker compose up -d <service>
```

## Verification

```bash
docker exec <c> grep key /path/to/config.properties
curl ...   # returns non-401?
```

## Common Variants

| Variant | Symptom | Fix |
|---------|---------|-----|
| DB password | JDBC auth failure | regenerate + rebuild |
| API key | 401 on API calls | regenerate + rebuild |
| Wrong env | Prod creds on stage | Set MWI_ENVIRONMENT + rebuild |

## Anti-Patterns

- Editing config inside a running container — rebuild wipes it
- Mounting host configs as bind mount — creates deploy drift
- `docker compose up -d` without `--build` — does NOT rebuild

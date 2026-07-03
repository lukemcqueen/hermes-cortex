# Dockerfile Permission Safety Net

## Problem

`write_file` creates files with 600 (owner-only) permissions on macOS. When these files are baked into a Docker image and the container runs as a non-root user, Python raises `PermissionError: [Errno 13] Permission denied` at import time because the container user can't read the file.

This affects:
- Migration files (`alembic/versions/*.py`) — Alembic can't read them, revision chain breaks, "No heads found" on every restart
- Router files (`app/routers/*.py`) — FastAPI can't import routes
- Model files (`app/models/*.py`) — SQLAlchemy can't define tables
- Schema files (`app/schemas/*.py`) — Pydantic models are inaccessible
- Test files — pytest can't discover tests
- Any `.py` file created via `write_file` that ends up in a Docker build context

## Two-Part Fix

### Part 1: Fix permissions at source level

Before every Docker build, run:
```bash
find apps -type f \( -name '*.py' -o -name '*.json' -o -name '*.yaml' -o -name '*.toml' \) \
  -not -perm -o=r -exec chmod 644 {} + 2>/dev/null
```

This ensures the build context files are world-readable before COPY into the image.

### Part 2: Add a Dockerfile safety net (belt AND suspenders)

Add a `chmod` fallback after all `COPY` instructions in the Dockerfile:

```dockerfile
# After all COPY instructions — safety net for write_file 600-permission files
RUN chmod -R 644 /app/app/*.py /app/alembic/versions/*.py 2>/dev/null; \
    chmod +x /app/entrypoint.sh && chown -R myuser:myuser /app/
```

**Why both?** Part 1 fixes the source files. Part 2 catches any files that were missed (created between the `find chmod` and the build, or from a different source). But see the Docker caching pitfall below.

## Docker Caching Pitfall

**`COPY app/ app/` caches on file CONTENT, not file PERMISSIONS.**

If you run Part 1 (`chmod 644`) and then `docker compose build api`, the COPY layer is REUSED from the previous build because the file content (bytes) is identical — only metadata changed. Docker computes cache keys from SHA256 content hashes, not from permission bits.

**Fix:** Always use `--no-cache` after a `chmod` fix:
```bash
docker compose build --no-cache api
docker compose up -d api
```

Without `--no-cache`, the old 600-permission files stay in the image regardless of your source-level `chmod`.

## Verification

```bash
# Check for remaining 600 files in source
find apps -type f -name '*.py' -not -perm -o=r

# Check for remaining 600 files inside the running container
docker exec api find /app -type f -name '*.py' -not -perm -o=r

# Verify Alembic can read migration files
docker exec api .venv/bin/python3 -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
config = Config('alembic.ini')
script = ScriptDirectory.from_config(config)
heads = script.get_heads()
print('Heads:', heads)
"
# Expected: exactly one head, no warnings
```

## References

- `engineering-approach` SKILL.md → `write_file permission pitfall` section (the original finding)
- `docker-compose-common-issues` SKILL.md → `Docker COPY layer caches on file CONTENT, not file metadata` section (the Docker caching behavior)

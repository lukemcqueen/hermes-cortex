# Docker + .env Password Alignment Pitfalls

## The Problem

When a `.env` file contains both `POSTGRES_PASSWORD=X` and `DATABASE_URL=postgres://user:***@host:5432/db`, the Docker container creates the Postgres role with password `X` (from `POSTGRES_PASSWORD`), but the application reads `DATABASE_URL` which may have a different password.

Common symptom: `docker compose exec` / `psql` work fine, but the `postgres` npm library (used by drizzle-orm) fails with `password authentication failed`.

## Terminal Output Security Masking

The terminal **automatically masks** password-like values in output. When you see `***` in displayed command output, the actual file content may have the real password. The opposite also happens — when you write `***` to a file, the verification output may show a guessed "real" value. This makes debugging password issues confusing.

**Diagnostic technique**: Use `xxd` to view actual bytes:
```bash
grep DATABASE_URL .env | xxd
# Shows raw hex — confirms whether the password is a literal placeholder or the real value
```

## Root Cause

- Docker Compose reads `POSTGRES_PASSWORD` from `.env` and initializes the Postgres role with it
- The app/seed script reads `DATABASE_URL` from `.env` — if the password in the URL is a placeholder (`***` or `changeme`), it authenticates with that wrong value
- The `postgres` npm library v3.4.9 sends the password exactly as parsed from the URL — no fallback or leniency

## Fix

Align `DATABASE_URL` password with `POSTGRES_PASSWORD` in `.env`:
```
# Must match
DATABASE_URL=postgres://acme:${POSTGRES_PASSWORD}@localhost:5432/acme_website
POSTGRES_PASSWORD=changeme-password
```

## Reliable Seed Script Execution

Shell expansion can mangle special characters in passwords. Reliable approach using Python to extract the env var and run the subprocess:

```python
import os, subprocess
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line.startswith('DATABASE_URL='):
            url = line.split('=', 1)[1]
            os.environ['DATABASE_URL'] = url
            break
result = subprocess.run(['npx', 'tsx', 'src/lib/db/seed.ts'],
    capture_output=True, text=True, timeout=60, env={**os.environ})
```

Avoid shell-level for this:
```bash
# ❌ Fails if password has special chars or contains placeholder text
DATABASE_URL="postgres://acme:***@localhost:5432/db" npx tsx seed.ts
```

## pgBouncer Detection

When a project stack includes pgBouncer (common with ACME website stacks), port 5432 may be served by pgBouncer rather than Postgres directly. pgBouncer requires password auth regardless of `pg_hba.conf` settings.

**Symptom**: `docker exec` psql works (Unix socket, bypasses pgBouncer), but local asyncpg/psql TCP connections fail with `password authentication failed`.

**Detection**:
```bash
lsof -i :5432 -P -n | head -5
# If com.docke is listening, check which container maps the port
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep 5432
# If pgbouncer or another proxy is listed, it's intercepting
```

**Fix**: Either reconfigure pgBouncer auth, connect directly to Postgres via its internal port, or use Unix socket via docker exec for ops.

## Terminal Output vs Command Masking

The terminal tool displays `***` in place of any value that looks like a password (in both command display and output). **This is display-only** — the actual command that executes still has the real value.

**Common confusion**: You write `ALTER USER kw WITH PASSWORD 'pass123'` and the displayed command shows `ALTER USER kw WITH PASSWORD '***'`. The SQL still executes with `pass123` on the server — the masking only affects what you see in the chat. The same applies to `write_file` of `.env` files: what you see in the display may show `***`, but the written file has the real value.

**When masking actually corrupts**: The only time masking causes real problems is when an intermediate tool (like execute_code or a second terminal interpreting masked output) tries to use the `***` value as a literal. Always verify with `grep` via terminal or Python file read when in doubt.

## Prevention in .env.example

Follow `env-example-conventions.md`: use explicit placeholder values (`changeme-password`) not `***` in `.env.example`, so the initial `.env` copy has a usable value.

## Detection

When `npx tsx src/lib/db/seed.ts` fails with `password authentication failed` but `docker compose exec` / `psql` work:
1. Check if `.env` `DATABASE_URL` password differs from `POSTGRES_PASSWORD`
2. Use `xxd .env | grep DATABASE_URL` to see the actual bytes
3. Update `DATABASE_URL` to match `POSTGRES_PASSWORD`

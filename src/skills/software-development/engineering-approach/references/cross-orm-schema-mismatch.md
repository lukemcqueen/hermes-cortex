# Cross-ORM Schema Mismatch Debugging (FastAPI + Next.js)

The acme-website project shares the same PostgreSQL tables between **two ORMs**: SQLAlchemy (FastAPI backend) and Drizzle (Next.js frontend). When column definitions diverge, authentication or data access can fail silently. Some mismatches produce different symptoms depending on which ORM's operation fails.

## Symptoms

| Symptom | Likely root cause |
|---|---|
| Login form returns "Connection error" or "Invalid credentials" despite correct email/password | Drizzle server action's SQL INSERT/UPDATE fails (e.g. `login_attempts` column mismatch, `admins.hashed_password` missing) |
| FastAPI `/api/auth/login` works but login form does not | Issue in Next.js layer — Drizzle schema vs DB columns, or server action catches error silently |
| Login succeeds but every page link redirects to login page | Session cookie created but Drizzle `getSessionAdmin()` query returns null — session token lookup fails in Drizzle ORM, or web container has stale code |
| You can log in, navigate 1-2 pages, then get redirected to login | Session `expiresAt` or `absoluteExpiresAt` column missing/null in DB, or session token column has wrong type |

## Diagnosis

### 1. Isolate the layer

First determine if the issue is in the FastAPI layer or the Next.js layer:

```bash
# Test FastAPI login directly
curl -X POST http://localhost:13001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@client-domain.com","password":"admin123"}' \
  -c /tmp/cookies.txt

# Test session validation
curl http://localhost:13001/api/auth/me -b /tmp/cookies.txt
```

If FastAPI login + session validation work, the issue is in the Next.js layer. If they fail, start with the SQLAlchemy models and Alembic migrations.

### 2. Check both ORM schemas against actual DB columns

```sql
\d admins
\d sessions
\d login_attempts
\d <other shared tables>
```

Compare against:
- **Drizzle schema:** `apps/web/src/lib/db/schema.ts`
- **SQLAlchemy model:** `apps/api/src/models/__init__.py`

### 3. Common drifts found in acme-website

| Table | SQLAlchemy (Alembic) | Drizzle (Next.js schema.ts) | Actual DB (after fix) |
|---|---|---|---|
| `admins` | `password_hash` | `hashed_password` | `hashed_password` |
| `admins` | (missing) | `last_login_at` timestamptz | `last_login_at` timestamptz |
| `sessions` | `id` varchar(128) PK (=token) | `id` serial PK, separate `session_token` varchar | `id` serial PK, `session_token` varchar unique |
| `sessions` | (missing) | `absolute_expires_at` timestamptz | `absolute_expires_at` timestamptz |
| `login_attempts` | `ip_address` varchar(45) | `ip_hash` varchar(64) | `ip_hash` varchar(64) |
| `login_attempts` | `attempted_at` timestamptz | `created_at` timestamptz | `created_at` timestamptz |
| `login_attempts` | `email` NOT NULL | `email` nullable (Drizzle inserts without email on failed attempts) | `email` nullable |

### 4. "Login works but every link redirects to login page" — deeper diagnosis

This is the trickiest symptom. The login form submits, calls the API, creates a session in the DB, sets the cookie — but subsequent page navigation doesn't find the session. Two things must both pass:

**Layer A — Middleware:** `apps/web/src/middleware.ts` calls FastAPI `/api/auth/me` with the session cookie. If this returns 401 → redirect to login.

**Layer B — AdminGuard + getSessionAdmin:** Every admin page is wrapped in `AdminGuard.tsx` which calls `getSessionAdmin()` from `login/actions.ts`. That function does a direct Drizzle query:

```typescript
// getSessionAdmin() — login/actions.ts (simplified)
const session = await db.query.sessions.findFirst({
  where: eq(sessions.sessionToken, cookieStore.get('session_token')?.value),
  with: { admin: true }
});
if (!session || session.expiresAt < now || session.absoluteExpiresAt < now) return null;
```

If `getSessionAdmin()` returns `null`, `AdminGuard` redirects to login immediately — regardless of whether the middleware passed.

**Common causes of getSessionAdmin() returning null:**

1. **Drizzle session_token column missing** — `eq(sessions.sessionToken, ...)` maps to SQL column `session_token`. If the column doesn't exist, Drizzle throws, the catch block returns null.
2. **Drizzle session_token column exists but is empty** — FastAPI creates sessions with `session_token=<uuid>` but Drizzle looks up the cookie value. If the session was created before the column existed, it has NULL session_token and can never be found.
3. **Web container has stale code** — acme-website's web container bakes the Next.js build into the Docker image. After fixing column names, the web container must be **rebuilt** (`docker compose up -d web --build`). Stale code runs the old Drizzle schema and never sees the new columns.
4. **Drizzle camelCase→snake_case mapping** — Drizzle by default maps `sessionToken` → `session_token`, `expiresAt` → `expires_at`, `absoluteExpiresAt` → `absolute_expires_at`. If the DB column names don't match the expected mapping (e.g., DB has `expires_at` but Drizzle also expects `expires_at` — they match), the query silently returns null.

**Diagnosing Layer B (Drizzle query failure):**

Since `getSessionAdmin()` has a `catch` block that returns `null`, errors are invisible. To debug, temporarily log the error:

```typescript
// TEMPORARY DEBUG — add before the catch (null) return
console.error('getSessionAdmin error:', error);
// Or in dev mode, throw instead of catching
throw error;
```

Or add a debug endpoint that runs the same query and returns the raw result.

## Fix Pattern

### 1. Align the DB (direct ALTER TABLE)

```sql
-- Admins
ALTER TABLE admins RENAME COLUMN password_hash TO hashed_password;
ALTER TABLE admins ADD COLUMN last_login_at timestamptz;

-- Sessions: migrate from varchar PK to serial + session_token
-- (only if no active sessions exist; otherwise, preserve existing sessions)
ALTER TABLE sessions ADD COLUMN session_token varchar(255);
ALTER TABLE sessions ADD COLUMN absolute_expires_at timestamptz;
CREATE SEQUENCE sessions_id_seq OWNED BY sessions.id;
ALTER TABLE sessions ALTER COLUMN id SET DEFAULT nextval('sessions_id_seq');
ALTER TABLE sessions ALTER COLUMN id TYPE integer USING id::integer;  -- if id was varchar
CREATE UNIQUE INDEX sessions_session_token_idx ON sessions(session_token);

-- login_attempts
ALTER TABLE login_attempts ADD COLUMN ip_hash varchar(64);
ALTER TABLE login_attempts ADD COLUMN created_at timestamptz;
ALTER TABLE login_attempts ALTER COLUMN email DROP NOT NULL;
-- Backfill existing rows
UPDATE login_attempts SET ip_hash = encode(sha256(COALESCE(ip_address, '')::bytea), 'hex');
UPDATE login_attempts SET created_at = COALESCE(attempted_at, now());
ALTER TABLE login_attempts ALTER COLUMN ip_hash SET NOT NULL;
ALTER TABLE login_attempts ALTER COLUMN created_at SET NOT NULL;
```

### 2. Update SQLAlchemy models (`models/__init__.py`)

- Rename model field: `password_hash` → `hashed_password`
- Add new fields: `last_login_at`, `session_token`, `absolute_expires_at`
- Fix type mismatches: `sessions.id` needs to be `Integer` not `String(128)`

### 3. Update all code referencing old columns

- `auth.py`: `admin.password_hash` → `admin.hashed_password`
- `auth.py`: `Session.id == session_token` → `Session.session_token == session_token`
- `auth.py`: Session creation `id=token` → `session_token=token`
- `auth.py`: `Session.expires_at` — verify Drizzle expects `expiresAt` → SQL column `expires_at` (this mapping works by default if the column exists)

### 4. Create Alembic migration

Manually write the migration file representing the delta. The DB already has the changes applied directly, so:

- Write the migration that *would* transform head→new state
- Copy it into the container: `docker compose cp <source> api:<target>`
- Stamp: `alembic stamp <revision>`

### 5. Rebuild BOTH containers

After column alignment, both containers need the new code:

```bash
# API container — picks up renamed model fields, updated auth router
docker compose up -d api --build

# Web container — picks up updated Drizzle schema, server actions
docker compose up -d web --build
```

The web container is often missed because it's not the "auth service." But its server actions (`getSessionAdmin`, login form) use Drizzle queries that operate on the same tables. Stale web code = Drizzle queries with old column names → silent failures.

### 6. Verify both layers

```bash
# Layer A — FastAPI auth
curl -X POST http://localhost:13001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@client-domain.com","password":"admin123"}' \
  -c /tmp/cookies.txt
curl http://localhost:13001/api/auth/me -b /tmp/cookies.txt
# Should return user JSON

# Layer B — Web session validation (using the same cookie)
curl http://localhost:13001/en/admin -b /tmp/cookies.txt
# Should return admin page HTML, not a redirect to /login
```

## Root cause summary

The dual-ORM setup has **three** sources of truth for column names:

| Source | Location |
|---|---|
| SQLAlchemy model | `apps/api/src/models/__init__.py` |
| Drizzle schema | `apps/web/src/lib/db/schema.ts` |
| Actual database | PostgreSQL (via Alembic migrations) |

A mismatch between any two produces silent failures because both ORMs catch SQL errors and return null/default instead of crashing.

## Third-ORM Variation: Rust sqlx vs SQLAlchemy

The `alembic_version` table is created by SQLAlchemy/Alembic migrations and uses `version_num` as its single column. A **Rust binary** using `sqlx` to query this table must use `SELECT version_num`, not `SELECT version`:

```rust
// ❌ Wrong — column "version" does not exist
sqlx::query_as("SELECT version FROM alembic_version")

// ✅ Correct — matches SQLAlchemy's column name
sqlx::query_as("SELECT version_num FROM alembic_version")
```

**Symptom:** Batch container starts, connects to PostgreSQL successfully, then fails with:
```
Error: failed to query alembic_version table – does the schema exist?
Caused by:
    0: error returned from database: column "version" does not exist
    1: column "version" does not exist
```

**Root cause:** SQLAlchemy's Alembic creates the `alembic_version` table with column `version_num` (varchar(32)), not `version`. A non-Python tool (Rust sqlx, Go pgx, raw SQL) that queries `version` will fail. The error message says "does the schema exist?" which is misleading — the schema exists, the column name is wrong.

**Fix:** Change the Rust query to use `version_num`, then rebuild the batch Docker image (`docker compose build batch`).

**Prevention checklist for Rust/Kotlin/Go batch processors:**
- [ ] Verify all column names match SQLAlchemy model definitions, not assumptions
- [ ] Pay special attention to `alembic_version` — its column name is `version_num`
- [ ] For ENUM columns, ensure the Rust type matches SQLAlchemy's ENUM values (case-sensitive)
- [ ] Test against a real PostgreSQL instance with actual migrations applied — not a mock or test DB

## ACME Website Auth Architecture

```
Browser
  │
  ├─► POST /en/login (Next.js server action)
  │   ├─► Drizzle: INSERT INTO sessions (session_token, admin_id, expires_at, ...)
  │   ├─► Sets cookie: session_token=<uuid>
  │   └─► Returns result (success/error displayed on page)
  │
  ├─► GET /en/admin/* (page request)
  │   ├─► middleware.ts — calls FastAPI /api/auth/me with cookie
  │   │   ├─► FastAPI validates session_token → returns user or 401
  │   │   └─► If 401 → redirect to /login (before page renders)
  │   │
  │   └─► layout.tsx — calls getSessionAdmin() (Drizzle query)
  │       ├─► Drizzle: SELECT ... FROM sessions JOIN admins WHERE session_token = <cookie>
  │       ├─► If null → AdminGuard redirects to /login
  │       └─► If valid → renders admin page
  │
  └─► FastAPI auth endpoints (for API consumers, not web login)
      └─► POST /api/auth/login → POST /api/auth/me → POST /api/auth/logout
```

Both layers (middleware FastAPI check + AdminLayout Drizzle check) must pass for the page to render. If either fails, the user gets redirected to login.

## Docker Container Note

The acme-website API container bakes code into the Docker image (no volume mount). Migration files created on the host aren't visible inside the container. Use:

```bash
docker compose cp apps/api/alembic/versions/<file> api:/app/alembic/versions/<file>
```

Then `docker compose exec -T api python -m alembic stamp <revision>`.

**Both containers must be rebuilt** after schema-related code changes:

```bash
docker compose up -d api web --build
```

The web container runs its own Drizzle queries. Stale web code = silent Drizzle failures even if the API container is up-to-date.

## Prevention

- When adding a new shared table or column, check both ORM schemas before running migrations
- Run `\d tablename` to verify the actual DB state matches both ORM definitions
- If both ORMs need to share a table, define column names in SQLAlchemy explicitly with `mapped_column("db_column_name", ...)` to match Drizzle's convention, or vice versa
- After any schema change affecting shared tables, rebuild BOTH containers — not just the API
- Every login_attempts failure should log the column mismatch (currently errors are silently swallowed by the catch block)
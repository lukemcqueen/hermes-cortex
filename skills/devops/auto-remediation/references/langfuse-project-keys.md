# Langfuse Project API Keys

## Failure Signal

`llm-judge-scorer` scripts fail with:

```
ERROR: Could not read Langfuse project keys
```

or

```
FileNotFoundError: [Errno 2] No such file or directory: '/home/esther/.hermes-cortex/.env'
```

## Root Cause

The `.env` symlink at `~/.hermes-cortex/.env` → `~/langfuse/.env` only contains Langfuse **deployment** secrets (SALT, SECRET_KEY, CLICKHOUSE_PASSWORD, etc.) — NOT **project** API keys.

The script needs:
- `HERMES_LANGFUSE_PUBLIC_KEY` or `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`
- `HERMES_LANGFUSE_SECRET_KEY` or `LANGFUSE_INIT_PROJECT_SECRET_KEY`

## Diagnosis

```bash
grep -E 'HERMES_LANGFUSE_(PUBLIC|SECRET)_KEY' ~/.hermes-cortex/.env
# If empty → keys not configured
```

## Resolution (manual — no auto-fix)

1. Open Langfuse at `http://localhost:3000`
2. Sign in (initial admin credentials from docker-compose)
3. Navigate to **Settings → API Keys**
4. Generate a new key pair (public + secret)
5. Add to `~/.hermes/hermes-cortex.env` (NOT the docker-compose env):

```
HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx
HERMES_LANGFUSE_SECRET_KEY=sk-lf-xxxxx
HERMES_LANGFUSE_BASE_URL=http://localhost:3000
```

Or add directly to `~/.hermes-cortex/.env` (the file the scripts read).

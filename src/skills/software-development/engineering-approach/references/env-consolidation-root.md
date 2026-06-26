# Root .env Consolidation

When moving from per-app `.env` (e.g. `apps/api/.env`) to a single project root `.env`.

## Why

- Single source of truth for all env vars across API, web, Docker, seed scripts
- `./run` CLI sources root `.env` at startup via `set -a; source .env; set +a`
- Docker Compose reads `.env` from project root by default

## Steps

1. **Set values in root `.env`** — include all vars previously scattered across `apps/api/.env`, `apps/web/.env.local`, etc.

2. **Quote values with spaces** — `APP_NAME="ACME Works"` not `APP_NAME=ACME Works`. Necessary because `source .env` evaluates as shell commands; unquoted values with spaces produce `command not found` errors in `./run`.

3. **Update API config to read from root** — in `apps/api/app/config.py`:

   ```python
   from pathlib import Path
   ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent  # apps/api/app/config.py -> project root
   ENV_FILE = ROOT_DIR / ".env"

   class Settings(BaseSettings):
       model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")
   ```

   **Important**: Exactly 4 `.parent` calls from `apps/api/app/config.py`. One fewer or more resolves to wrong directory.

4. **Remove old per-app `.env`** — delete `apps/api/.env` and `apps/web/.env.local` after confirming root `.env` is read correctly.

5. **Verify** — use the venv Python:
   ```bash
   cd /path/to/project && apps/api/.venv/bin/python3 -c "
   import sys; sys.path.insert(0, 'apps/api')
   from app.config import settings
   print(settings.database_url)  # Should match root .env
   "```

## Compatibility

- **Pydantic-settings v2**: `env_file` resolves relative to CWD when using a relative path. Using an absolute path (`Path(__file__).resolve() / ...`) avoids cwd-dependence.
- **Docker Compose**: reads `.env` from project root automatically — no config change needed.
- **`./run`**: sources root `.env` via `set -a; source .env; set +a` before any command — vars become environment variables.

## Pitfalls

- **Terminal masking**: When writing root `.env` with `write_file`, password values that look sensitive may be displayed as `***`. The actual file content is correct — verify with `grep` or Python `open()`.
- **Existing env vars take precedence**: pydantic-settings reads env_file first, but environment variables override file values. If a stale `DATABASE_URL` is set in the shell, it will override the `.env` value.
- **`source .env` is not `export`**: The `set -a` / `set +a` wrapper in `./run` converts sourced vars to exported env vars. Without it, sourced vars are only shell variables and won't be inherited by subprocesses.

# .env.example Conventions

These conventions apply to writing and maintaining `.env.example` files.

## Secret Placeholder Style

**Use explicit placeholder values, not `***`.**

✅ Good:
```
POSTGRES_PASSWORD=changeme-password
MEILI_MASTER_KEY=changeme-master-key
```

❌ Avoid:
```
POSTGRES_PASSWORD=***
MEILI_MASTER_KEY=***
```

Rationale: Explicit placeholders signal the format/length the real value should have. `***` is ambiguous — it could mean "paste your value here" or "this was redacted" or "the value is hidden". A readable placeholder tells the developer what kind of value goes there.

## What to Include

- **Every env var** referenced in `docker-compose.yml` as `${VAR_NAME}` — either with a default (ports, `development` mode) or an explicit placeholder for secrets.
- **Comment annotations** for non-obvious vars explaining what they control, e.g.:
  ```
  # Web app uses this to reach the API backend.
  # Local dev: http://localhost:${API_PORT}/api/v1
  # Production: https://client-domain.com/api/v1
  NEXT_PUBLIC_API_URL=http://localhost:8981/api/v1
  ```
- **Port numbers** that differ from the default (e.g. postgres is 5438, not 5432) — so the developer knows the local mapping matches the compose file.

## What NOT to Include

- Real secrets, tokens, or production credentials
- Developer-local paths or machine-specific config
- Values that change per-deployment environment (those belong in a different `.env` per env)

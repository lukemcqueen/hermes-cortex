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
   Selects the override file + env file for the current `APP_ENV` and prints
   a prominent banner showing the active environment.

## Implementation

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── Environment gate ─────────────────────────────────────────────
APP_ENV="${APP_ENV:-}"
if [[ -z "$APP_ENV" ]]; then
  cat >&2 <<'EOF'
╔══════════════════════════════════════════════════════════════╗
║  APP_ENV is not set.                                         ║
║                                                              ║
║  Run:  export APP_ENV=dev     # or stage, prod               ║
║  Then re-run ./run <command>                                 ║
╚══════════════════════════════════════════════════════════════╝
EOF
  exit 1
fi

case "$APP_ENV" in
  dev|stage|prod) ;;
  *) echo "Invalid APP_ENV: $APP_ENV (expected dev|stage|prod)" >&2; exit 1 ;;
esac

# ── Prominent banner ───────────────────────────────────────────
echo "▸▸▸ ENV: $APP_ENV — compose files: docker-compose.yml + docker-compose.$APP_ENV.yml"

# ── _compose() wrapper ─────────────────────────────────────────
_compose() {
  local args=(-f docker-compose.yml)
  [[ -f "docker-compose.$APP_ENV.yml" ]] && args+=(-f "docker-compose.$APP_ENV.yml")
  [[ -f ".env.$APP_ENV" ]] && args+=(--env-file ".env.$APP_ENV")
  echo "» docker compose ${args[*]} $*"
  docker compose "${args[@]}" "$@"
}

# ── Commands ───────────────────────────────────────────────────
case "${1:-}" in
  up)   shift; _compose up -d "$@" ;;
  down) shift; _compose down "$@" ;;
  logs) shift; _compose logs -f "$@" ;;
  ps)   _compose ps ;;
  exec) shift; _compose exec "$@" ;;
  *)
    echo "Usage: ./run <up|down|logs|ps|exec> [args]" >&2
    exit 1
    ;;
esac
```

## File Layout

```
./run                        → unified entry point (above)
docker-compose.yml           → base compose (shared config)
docker-compose.stage.yml     → stage overrides
docker-compose.prod.yml      → production overrides
.env                         → dev defaults
.env.stage                   → stage secrets/overrides
.env.prod                    → prod secrets/overrides
```

## Rules

- **Every `docker compose` invocation goes through `_compose()`** — never call
  `docker compose` directly in the script. One place to change compose behavior.
- **The banner prints on every command** — the operator always sees which
  environment they're touching. No "I thought this was prod" incidents.
- **No silent default** — omitting `APP_ENV` is an error with instructions,
  never a quiet fallback to dev. Predictability beats convenience.
- **Secret env files** (`.env.stage`, `.env.prod`) stay out of git —
  `.gitignore` them.

## Verification

```bash
# No env → halts with instructions
APP_ENV= ./run up; echo "exit=$?"        # expect exit=1 + boxed message

# Valid env → banner + compose command
APP_ENV=dev ./run up                     # expect "ENV: dev" banner

# Invalid env → rejected
APP_ENV=qa ./run up; echo "exit=$?"      # expect exit=1 + invalid message
```

## Related
- `unified-cli-script` — the full `./run` CLI design this wrapper belongs to
- `project-run-scripts` — canonical `./run` template

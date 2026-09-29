#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  ./run — canonical single CLI entrypoint for this project
#
#  Source: ops/scripts/project-run-scripts/templates/run.sh
#  (hermes-cortex project-run-scripts skill — canonical template).
#  Customize: PROJECT_ROOT paths, service names, env defaults,
#  test runners. Keep the command contract identical across repos
#  so a developer switching projects never re-learns the interface.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── PROJECT_ROOT detection ───────────────────────────────────
# Resolve the repo root (where .env / compose files live) from this
# script's own location. Works whether `run` is at the root or nested.
SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

# ── Source .env (if present) ─────────────────────────────────
# Optional config overrides. NEVER let a missing .env kill the script.
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

# ── Color helpers ────────────────────────────────────────────
RESET='\033[0m'; BOLD='\033[1m'; RED='\033[0;31m'
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
info()  { echo -e "${GREEN}✓${RESET} $*"; }
ok()    { echo -e "${GREEN}ok${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

# ── Defaults ─────────────────────────────────────────────────
# Override in .env or when invoking: ./run up POSTGRES_USER=foo
POSTGRES_USER="${POSTGRES_USER:-app}"
POSTGRES_DB="${POSTGRES_DB:-app}"
API_DIR="${API_DIR:-app}"          # Python/FastAPI source dir (for alembic)
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
# Non-Docker projects (standalone Go tools, scripts) may set COMPOSE_OPTIONAL=1
# to skip the docker lifecycle commands entirely — see cmd_up.
COMPOSE_OPTIONAL="${COMPOSE_OPTIONAL:-0}"

# ── Help ─────────────────────────────────────────────────────
show_help() {
  cat <<'EOF'
Usage: ./run <command> [args]

Docker lifecycle:
  up [svc...]        Start environment (detached)
  down               Stop environment
  restart [svc]      Down then Up (full restart), or restart one service
  logs [-f] [svc]    Tail logs (--tail=50)
  build [--no-cache] [svc...]   Build images (aborts on multi Alembic head)
  ps                 List running containers
  health             Check service health

Services:
  exec <svc> <cmd>   Run a command in a container
  pgsql [-c "SQL"]   Interactive psql (non-interactive with -c)

Dev:
  pip [args]         Run pip inside the venv
  dev:api            Run the API dev server
  dev:web            Run the web dev server

Test:
  test               Run all tests
  test:api           Run API tests (pytest)
  test:web           Run web tests (vitest)

Database:
  db:reset           Drop → create → migrate → seed
  migrate            Apply pending Alembic migrations (fail-fast on multi head)
  check:alembic      Inline migration-head check
  seed               Load seed data

Lint / clean:
  lint               Run all linters
  fmt                Check formatting
  fmt:fix            Auto-fix formatting
  clean              Remove build artifacts (.venv node_modules .next __pycache__)
  rebuild            clean + up + build

Utility:
  help               Show this help
EOF
}

# ── Helpers ──────────────────────────────────────────────────
activate_venv() {
  if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.venv/bin/activate"
  elif command -v python3 >/dev/null 2>&1; then
    : # system python; no venv to activate
  else
    error "No .venv and no python3 — cannot run Python commands."
    exit 1
  fi
}

_pytest_runner() {
  activate_venv
  python3 -m pytest "$@"
}

_alembic_runner() {
  activate_venv
  python3 -m alembic "$@"
}

# ── Alembic head integrity — fail-fast, never auto-merge ─────
# Static check script lives at $PROJECT_ROOT/scripts/check-alembic-heads.py.
# If present it is preferred; the inline check is the portable fallback.
_check_alembic_heads() {
  if [[ -f "$PROJECT_ROOT/scripts/check-alembic-heads.py" ]]; then
    if ! python3 "$PROJECT_ROOT/scripts/check-alembic-heads.py" "$PROJECT_ROOT/$API_DIR/alembic/versions" 2>&1; then
      error "Build aborted: fix Alembic migration heads before building."
      return 1
    fi
    return 0
  fi
  # Fallback — inline head count via alembic.
  local HEADS
  HEADS=$(_alembic_runner heads 2>/dev/null | wc -l | tr -d ' ')
  if [[ -z "$HEADS" || "$HEADS" -ne 1 ]]; then
    error "${HEADS:-0} migration heads detected. Expected exactly 1."
    error "Run 'alembic heads' to see them, then create a merge revision."
    return 1
  fi
  return 0
}

# ── Docker lifecycle ─────────────────────────────────────────
has_compose() {
  [[ -f "$PROJECT_ROOT/$COMPOSE_FILE" ]] || [[ "$COMPOSE_OPTIONAL" == "1" ]]
}

cmd_up() {
  if ! has_compose; then
    warn "No $COMPOSE_FILE found (or COMPOSE_OPTIONAL=1) — skipping Docker up."
    return 0
  fi
  info "Starting Docker environment..."
  (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" up -d --remove-orphans "$@")
  ok "Environment up"
}

cmd_down() {
  [[ -f "$PROJECT_ROOT/$COMPOSE_FILE" ]] || { warn "No compose file — nothing to down."; return 0; }
  info "Stopping Docker environment..."
  (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" down --remove-orphans "$@")
  ok "Environment down"
}

cmd_restart() {
  if [[ $# -gt 0 ]]; then
    info "Restarting service(s): $*"
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" restart "$@")
    return 0
  fi
  cmd_down
  cmd_up
}

cmd_logs() {
  if [[ $# -eq 0 ]]; then
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" logs --tail=50)
  elif [[ "$1" == "-f" ]]; then
    shift
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" logs --tail=50 -f "$@")
  else
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" logs --tail=50 "$@")
  fi
}

cmd_build() {
  # Pre-check: abort on multiple Alembic heads before building.
  if ! _check_alembic_heads; then
    return 1
  fi
  local no_cache=""
  local services=()
  for arg in "$@"; do
    if [[ "$arg" == "--no-cache" ]]; then
      no_cache="--no-cache"
    else
      services+=("$arg")
    fi
  done
  if [[ ${#services[@]} -eq 0 ]]; then
    info "Building all Docker images..."
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" build ${no_cache:+"$no_cache"})
  else
    info "Building Docker image(s): ${services[*]}"
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" build ${no_cache:+"$no_cache"} "${services[@]}")
  fi
  ok "Build complete"
}

cmd_ps() {
  (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" ps)
}

cmd_health() {
  # Loop over compose services and report status. Customize per service.
  (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" ps --format 'table {{.Name}}\t{{.Status}}')
  info "Health check complete (customize cmd_health for per-service probes)."
}

cmd_exec() {
  [[ $# -ge 2 ]] || { error "Usage: ./run exec <svc> <cmd>"; exit 1; }
  local svc="$1"; shift
  (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" exec -T "$svc" "$@")
}

cmd_pgsql() {
  # Dual-mode: interactive by default, non-interactive with -c.
  if [[ "${1:-}" == "-c" ]]; then
    shift
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@")
  else
    (cd "$PROJECT_ROOT" && docker compose -f "$COMPOSE_FILE" exec -it postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@")
  fi
}

# ── Dev commands ─────────────────────────────────────────────
cmd_pip() {
  activate_venv
  python3 -m pip "$@"
}

cmd_dev_api() {
  activate_venv
  info "Starting API dev server..."
  # Customize: adjust host/port/reload flags to match the framework.
  exec uvicorn "$API_DIR.main:app" --reload --host 0.0.0.0 --port "${API_PORT:-8000}"
}

cmd_dev_web() {
  info "Starting web dev server..."
  exec pnpm --dir "$PROJECT_ROOT" dev
}

# ── Test commands ────────────────────────────────────────────
cmd_test() {
  cmd_test_api
  cmd_test_web
}

cmd_test_api() {
  info "Running API tests..."
  _pytest_runner -q
}

_cleanup_vitest() {
  # Orphaned vitest workers accumulate and block ports.
  pkill -f "vitest" 2>/dev/null || true
}

_run_vitest() {
  _cleanup_vitest
  (cd "$PROJECT_ROOT" && pnpm test "$@")
  _cleanup_vitest
}

cmd_test_web() {
  info "Running web tests..."
  _run_vitest
}

# ── Database commands ────────────────────────────────────────
cmd_db_reset() {
  warn "Dropping and recreating the database..."
  cmd_pgsql -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";"
  cmd_pgsql -c "CREATE DATABASE \"$POSTGRES_DB\";"
  cmd_migrate
  cmd_seed
  ok "Database reset complete"
}

cmd_migrate() {
  info "Applying Alembic migrations..."
  if ! _check_alembic_heads; then
    return 1
  fi
  _alembic_runner upgrade head
  ok "Migrations applied"
}

cmd_check_alembic() {
  if [[ -f "$PROJECT_ROOT/scripts/check-alembic-heads.py" ]]; then
    python3 "$PROJECT_ROOT/scripts/check-alembic-heads.py" "$PROJECT_ROOT/$API_DIR/alembic/versions"
  else
    # Inline head check — on-demand, no bundled script required.
    python3 - <<'EOF'
from alembic.config import Config
from alembic.script import ScriptDirectory
import sys
config = Config("alembic.ini")
script = ScriptDirectory.from_config(config)
heads = script.get_heads()
if len(heads) != 1:
    print(f"✗ {len(heads)} Alembic heads detected: {heads}")
    print("  Fix: alembic merge heads -m 'merge' (or rebase your branch).")
    sys.exit(1)
print(f"✓ single head: {heads[0]}")
EOF
  fi
}

cmd_seed() {
  activate_venv
  info "Loading seed data..."
  python3 -m app.seed
  ok "Seed loaded"
}

# ── Lint / format ────────────────────────────────────────────
cmd_lint() {
  activate_venv
  info "Running linters..."
  python3 -m ruff check "$PROJECT_ROOT"
  # Add rubocop / eslint / go vet per stack.
}

cmd_fmt() {
  activate_venv
  python3 -m ruff format --check "$PROJECT_ROOT"
}

cmd_fmt_fix() {
  activate_venv
  python3 -m ruff format "$PROJECT_ROOT"
}

# ── Clean / rebuild ──────────────────────────────────────────
cmd_clean() {
  warn "Removing build artifacts..."
  rm -rf "$PROJECT_ROOT/.venv" "$PROJECT_ROOT/node_modules" "$PROJECT_ROOT/.next" \
    "$PROJECT_ROOT/__pycache__" "$PROJECT_ROOT/.pytest_cache"
  find "$PROJECT_ROOT" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
  ok "Clean complete"
}

cmd_rebuild() {
  cmd_clean
  cmd_up
  cmd_build
  ok "Rebuild complete"
}

# ── Main dispatch ────────────────────────────────────────────
main() {
  local cmd="${1:-help}"
  shift 2>/dev/null || true
  case "$cmd" in
    up)          cmd_up "$@" ;;
    down)        cmd_down "$@" ;;
    restart)     cmd_restart "$@" ;;
    logs)        cmd_logs "$@" ;;
    build)       cmd_build "$@" ;;
    ps)          cmd_ps ;;
    health)      cmd_health ;;
    exec)        cmd_exec "$@" ;;
    pgsql)       cmd_pgsql "$@" ;;
    pip)         cmd_pip "$@" ;;
    dev:api)     cmd_dev_api ;;
    dev:web)     cmd_dev_web ;;
    test)        cmd_test ;;
    test:api)    cmd_test_api ;;
    test:web)    cmd_test_web ;;
    db:reset)    cmd_db_reset ;;
    migrate)     cmd_migrate ;;
    check:alembic) cmd_check_alembic ;;
    seed)        cmd_seed ;;
    lint)        cmd_lint ;;
    fmt)         cmd_fmt ;;
    fmt:fix)     cmd_fmt_fix ;;
    clean)       cmd_clean ;;
    rebuild)     cmd_rebuild ;;
    help|-h|--help) show_help ;;
    *) error "Unknown command: $cmd"; echo; show_help; exit 1 ;;
  esac
}

main "$@"

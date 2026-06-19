#!/bin/bash
# <Project Name> — Unified CLI
# Usage: ./run <command>
#
# DEFINITIVE CANONICAL TEMPLATE — Every project must follow this interface.
# Customize: PROJECT_ROOT paths, service names, DB credentials, test commands.
# Run `chmod +x run && ./run help` to verify.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load .env ──────────────────────────────────────────
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
    # CORS_ORIGINS is JSON with quotes that bash strips on source.
    # Let pydantic-settings read it from .env file directly.
    unset CORS_ORIGINS 2>/dev/null || true
fi

# ── Colors ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

# ── Paths (CUSTOMIZE per project) ──────────────────────
API_DIR="$PROJECT_ROOT/apps/api"
WEB_DIR="$PROJECT_ROOT/apps/web"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"

# ── Defaults (CUSTOMIZE per project) ───────────────────
POSTGRES_USER="${POSTGRES_USER:-app}"
POSTGRES_DB="${POSTGRES_DB:-app}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

# ══════════════════════════════════════════════════════════
# HELP
# ══════════════════════════════════════════════════════════

show_help() {
    cat <<EOF
<Project Name> — Unified CLI

Usage: ./run <command>

Docker:
  up                  Start all services (detached)
  down                Stop all services
  restart [svc]       Restart all (down+up), or a single service
  ps                  List running containers
  logs [-f] [svc]     Show logs (--tail=50, -f to follow)
  build [--no-cache] [svc]  Build Docker images
  health              Check health of all services
  exec <svc> <cmd>    Run command in container
  pgsql [-c "SQL"]    Interactive psql, or run SQL (./run pgsql -c "SELECT 1")

Dev:
  pip                 Set up Python venv + install deps
  dev:api             Start API dev server (uvicorn --reload)
  dev:web             Start web dev server (next/vite dev)

Test:
  test                Run all tests (api + web)
  test:api [args]     Run API tests (pytest [args])
  test:web [args]     Run web tests (vitest [args])
  test:unit [args]    Run unit tests (fast, no DB)
  test:infra [args]   Run infrastructure integration tests

Database:
  migrate             Apply pending Alembic migrations (self-heals multi-head)
  db:reset            Drop → create → migrate → seed
  seed                Load seed data
  check:alembic       Verify single Alembic head

Lint:
  lint                Run all linters
  fmt                 Check formatting
  fmt:fix             Fix formatting in place

Utility:
  clean               Remove build artifacts (.venv, node_modules, .next, __pycache__)
  help                Show this help

Examples:
  ./run up
  ./run pip
  ./run build --no-cache
  ./run test:api -k "test_health" --tb=short
  ./run pgsql -c "SELECT count(*) FROM users"
  ./run logs -f api
EOF
}

# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

activate_venv() {
    if [ -d "$API_DIR/.venv" ]; then
        source "$API_DIR/.venv/bin/activate"
        # Re-source .env so PORT vars are available inside the venv shell
        if [ -f "$PROJECT_ROOT/.env" ]; then
            set -a; source "$PROJECT_ROOT/.env"; set +a
        fi
        unset CORS_ORIGINS 2>/dev/null || true
    else
        error "No venv found. Run: ./run pip"
        exit 1
    fi
}

_pytest_runner() {
    cd "$API_DIR"
    activate_venv
    unset CORS_ORIGINS 2>/dev/null || true
    PYTHONPATH=. python -m pytest "$@"
}

_alembic_runner() {
    cd "$API_DIR"
    activate_venv
    PYTHONPATH=. alembic "$@"
}

# ── Vitest cleanup (include in repos with web tests) ──
_cleanup_vitest() {
    sleep 1
    local pid cwd
    for pid in $(pgrep -f 'vitest' 2>/dev/null || true); do
        cwd=$(lsof -p "$pid" -d cwd -Fn 2>/dev/null | grep '^n/' | sed 's/^n//' || true)
        if [ -n "$cwd" ] && [[ "$cwd" == "$PROJECT_ROOT"* ]]; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    sleep 0.5
    for pid in $(pgrep -f 'vitest' 2>/dev/null || true); do
        cwd=$(lsof -p "$pid" -d cwd -Fn 2>/dev/null | grep '^n/' | sed 's/^n//' || true)
        if [ -n "$cwd" ] && [[ "$cwd" == "$PROJECT_ROOT"* ]]; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
}

_run_vitest() {
    local dir="$1"; shift
    cd "$dir"
    if command -v pnpm &>/dev/null; then
        pnpm test "$@"
    else
        npm test "$@"
    fi
    _cleanup_vitest
}

# ══════════════════════════════════════════════════════════
# DOCKER COMMANDS
# ══════════════════════════════════════════════════════════

cmd_up() {
    info "Starting Docker environment..."
    # Remove orphaned containers that block name reuse (Pattern B: explicit names)
    for name in postgres redis api web; do
        if docker ps -a --format '{{.Names}}' | grep -q "^$name$"; then
            docker rm -f "$name" 2>/dev/null || true
        fi
    done
    docker compose up -d --remove-orphans
    ok "Docker started — http://localhost:${WEB_PORT:-3000}"
}

cmd_down() {
    info "Stopping Docker environment..."
    docker compose down --remove-orphans
    ok "Docker stopped"
}

cmd_restart() {
    if [ $# -eq 0 ]; then
        info "Restarting all Docker containers (down + up)..."
        cmd_down
        cmd_up
    else
        info "Restarting Docker container(s): $*"
        docker compose restart "$@"
        ok "Restarted: $*"
    fi
}

cmd_ps() {
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
}

cmd_logs() {
    docker compose logs --tail=50 "$@"
}

cmd_build() {
    local no_cache=""
    local services=()
    for arg in "$@"; do
        if [[ "$arg" == "--no-cache" ]]; then
            no_cache="--no-cache"
        else
            services+=("$arg")
        fi
    done
    if [ ${#services[@]} -eq 0 ]; then
        info "Building all Docker images..."
        docker compose build ${no_cache:+"$no_cache"}
    else
        info "Building Docker image(s): ${services[*]}"
        docker compose build ${no_cache:+"$no_cache"} "${services[@]}"
    fi
    ok "Build complete"
}

cmd_health() {
    info "Checking service health..."
    echo ""

    local ALL_HEALTHY=true

    if docker compose ps 2>/dev/null | grep -q 'STATUS'; then
        echo "=== Docker Services ==="
        docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
        echo ""

        for svc in postgres redis api web; do
            local STATUS
            STATUS=$(docker compose ps --format json 2>/dev/null | grep "\"$svc\"" | grep -o '"healthy"' || true)
            if [ -z "$STATUS" ]; then
                local RUNNING
                RUNNING=$(docker compose ps --format json 2>/dev/null | grep "\"$svc\"" | grep -o '"running"' || true)
                if [ -n "$RUNNING" ]; then
                    warn "$svc: running (not yet healthy)"
                    ALL_HEALTHY=false
                else
                    error "$svc: not running"
                    ALL_HEALTHY=false
                fi
            else
                ok "$svc: healthy"
            fi
        done
        echo ""
    else
        error "Docker Compose not running (run: ./run up)"
        ALL_HEALTHY=false
    fi

    echo "=== Connectivity ==="
    if docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" &>/dev/null; then
        ok "PostgreSQL: connected (${POSTGRES_USER}@${POSTGRES_DB})"
    else
        error "PostgreSQL: connection failed"
        ALL_HEALTHY=false
    fi

    if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        ok "Redis: connected"
    else
        error "Redis: connection failed"
        ALL_HEALTHY=false
    fi

    if curl -sf --max-time 3 "http://localhost:${API_PORT}/health" &>/dev/null; then
        ok "API: http://localhost:${API_PORT}/health"
    else
        warn "API: not reachable (expected if dev server not running)"
    fi

    local WEB_CODE
    WEB_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:${WEB_PORT}" 2>/dev/null || echo "000")
    if [ "$WEB_CODE" != "000" ]; then
        ok "Web: http://localhost:${WEB_PORT} (HTTP $WEB_CODE)"
    else
        warn "Web: not reachable"
    fi
    echo ""

    if [ "$ALL_HEALTHY" = true ]; then
        ok "All services healthy"
    else
        warn "Some services have issues (see above)"
        exit 1
    fi
}

cmd_exec() {
    if [ $# -lt 2 ]; then
        error "Usage: ./run exec <service> <command...>"
        exit 1
    fi
    local service="$1"; shift
    docker compose exec -T "$service" "$@"
}

cmd_pgsql() {
    if [ "${1:-}" = "-c" ]; then
        shift
        docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
    else
        docker compose exec -it postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
    fi
}

# ══════════════════════════════════════════════════════════
# DEV COMMANDS
# ══════════════════════════════════════════════════════════

cmd_pip() {
    info "Setting up Python environment..."
    cd "$API_DIR"

    # Detect suitable Python version
    local PYTHON=""
    for candidate in python3.13 python3.12 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12; do
        if command -v "$candidate" &>/dev/null && "$candidate" --version &>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    done
    [ -z "$PYTHON" ] && PYTHON="python3"

    if [ ! -d ".venv" ]; then
        $PYTHON -m venv .venv
    fi
    source .venv/bin/activate

    if command -v uv &>/dev/null; then
        uv pip install -e ".[dev]" 2>&1 | grep -v "^\[notice\]" || true
    elif [ -f "pyproject.toml" ]; then
        pip install -e ".[dev]" --quiet
    elif [ -f "requirements.txt" ]; then
        pip install -r requirements.txt --quiet
    fi
    ok "Python environment ready"
}

cmd_dev_api() {
    info "Starting API dev server on port ${API_PORT}..."
    cd "$API_DIR"
    activate_venv
    exec uvicorn app.main:app --reload --host "${API_HOST:-0.0.0.0}" --port "${API_PORT}"
}

cmd_dev_web() {
    info "Starting web dev server on port ${WEB_PORT}..."
    cd "$WEB_DIR"
    if command -v pnpm &>/dev/null; then
        exec pnpm dev --port "${WEB_PORT}" --host 0.0.0.0
    else
        exec npm run dev -- --port "${WEB_PORT}"
    fi
}

# ══════════════════════════════════════════════════════════
# TEST COMMANDS
# ══════════════════════════════════════════════════════════

cmd_test() {
    info "Running all tests..."
    echo ""
    echo "=== API Tests ==="
    cmd_test_api -v --tb=short 2>&1 | tail -20 || true
    echo ""
    echo "=== Web Tests ==="
    cmd_test_web 2>&1 | tail -20 || true
    echo ""
    ok "All tests complete"
}

cmd_test_api() {
    info "Running API tests..."
    _pytest_runner tests/ -v "$@"
}

cmd_test_web() {
    info "Running web tests..."
    _run_vitest "$WEB_DIR"
}

cmd_test_unit() {
    info "Running unit tests (no DB required)..."
    _pytest_runner tests/ -v \
        --ignore=tests/test_integration \
        --ignore=tests/test_infrastructure \
        -x -q "$@"
}

cmd_test_infra() {
    info "Running infrastructure integration tests..."
    _pytest_runner tests/test_infrastructure/ -v "$@"
}

# ══════════════════════════════════════════════════════════
# DATABASE COMMANDS
# ══════════════════════════════════════════════════════════

cmd_migrate() {
    info "Applying Alembic migrations..."
    local HEADS
    HEADS=$(_alembic_runner heads 2>/dev/null | wc -l)
    if [ "$HEADS" -gt 1 ]; then
        warn "Detected $HEADS migration heads — auto-merging..."
        local HEAD_REVS
        HEAD_REVS=$(_alembic_runner heads | grep -oE '^[a-f0-9]+')
        local FIRST SECOND
        FIRST=$(echo "$HEAD_REVS" | head -1)
        SECOND=$(echo "$HEAD_REVS" | tail -1)
        if [ -n "$FIRST" ] && [ -n "$SECOND" ] && [ "$FIRST" != "$SECOND" ]; then
            _alembic_runner merge -m "auto-merge branches" "$FIRST" "$SECOND"
            ok "Auto-merged migration heads"
        fi
    fi
    _alembic_runner upgrade head
    ok "Migrations applied"
}

cmd_db_reset() {
    info "Resetting database..."
    echo "  Dropping database..."
    docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE);"
    echo "  Creating database..."
    docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
        -c "CREATE DATABASE \"$POSTGRES_DB\";"
    echo "  Running migrations..."
    cmd_migrate
    ok "Database reset complete"
}

cmd_seed() {
    info "Loading seed data..."
    cd "$API_DIR"
    activate_venv

    # Preferred patterns (pick one, remove others):
    # (a) Python seed module
    PYTHONPATH=. python -m app.seed
    # (b) YAML content loader
    # PYTHONPATH=. python -m scripts.seed_content "$@"
    # (c) Docker exec (for production)
    # docker compose exec -T api python -m app.seed

    ok "Seed complete"
}

cmd_check_alembic() {
    info "Checking Alembic migrations..."
    local HEADS
    HEADS=$(_alembic_runner heads 2>/dev/null | wc -l)
    if [ "$HEADS" -gt 1 ]; then
        warn "Multiple heads detected ($HEADS). Run './run migrate' to auto-merge."
        return 1
    elif [ "$HEADS" -eq 0 ]; then
        warn "No migration heads found — no migrations applied yet."
        return 0
    else
        ok "Single migration head"
    fi
}

# ══════════════════════════════════════════════════════════
# LINT COMMANDS
# ══════════════════════════════════════════════════════════

cmd_lint() {
    info "Running linters..."

    # Python lint
    if command -v ruff &>/dev/null || [ -f "$API_DIR/.venv/bin/ruff" ]; then
        cd "$API_DIR"
        activate_venv
        python -m ruff check app/ tests/ && ok "Python lint passed"
    else
        warn "ruff not installed. Run: ./run pip"
    fi

    # Node/TS lint
    if [ -f "$WEB_DIR/package.json" ]; then
        cd "$WEB_DIR"
        if command -v pnpm &>/dev/null; then
            pnpm lint 2>/dev/null && ok "Web lint passed" || warn "Web lint had warnings"
        fi
    fi

    ok "Lint complete"
}

cmd_fmt() {
    info "Checking formatting..."
    cd "$API_DIR"
    activate_venv
    python -m ruff format . --check 2>&1
}

cmd_fmt_fix() {
    info "Fixing formatting..."
    cd "$API_DIR"
    activate_venv
    python -m ruff format . 2>&1
    ok "Formatting fixed"
}

# ══════════════════════════════════════════════════════════
# UTILITY COMMANDS
# ══════════════════════════════════════════════════════════

cmd_clean() {
    info "Cleaning build artifacts..."
    cd "$PROJECT_ROOT"

    echo "  Removing Python .venv..."
    rm -rf "$API_DIR/.venv" 2>/dev/null || true

    echo "  Removing __pycache__ and .pyc..."
    find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name '*.pyc' -delete 2>/dev/null || true

    echo "  Removing node_modules..."
    rm -rf "$WEB_DIR/node_modules/" 2>/dev/null || true
    find . -name node_modules -type d -prune -exec rm -rf {} + 2>/dev/null || true

    echo "  Removing build cache..."
    rm -rf "$WEB_DIR/.next" "$PROJECT_ROOT/.turbo" .pytest_cache .ruff_cache 2>/dev/null || true

    echo "  Removing test artifacts..."
    rm -rf htmlcov .coverage 2>/dev/null || true

    ok "Clean complete"
}

# ══════════════════════════════════════════════════════════
# ROUTING
# ══════════════════════════════════════════════════════════

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

CMD="$1"
shift

case "$CMD" in
    # Docker
    up)                cmd_up "$@" ;;
    down)              cmd_down "$@" ;;
    restart)           cmd_restart "$@" ;;
    ps)                cmd_ps "$@" ;;
    logs)              cmd_logs "$@" ;;
    build)             cmd_build "$@" ;;
    health)            cmd_health "$@" ;;
    exec)              cmd_exec "$@" ;;
    pgsql)             cmd_pgsql "$@" ;;

    # Dev
    pip)               cmd_pip "$@" ;;
    dev:api)           cmd_dev_api "$@" ;;
    dev:web)           cmd_dev_web "$@" ;;

    # Test
    test)              cmd_test "$@" ;;
    test:api)          cmd_test_api "$@" ;;
    test:web)          cmd_test_web "$@" ;;
    test:unit)         cmd_test_unit "$@" ;;
    test:infra)        cmd_test_infra "$@" ;;

    # Database
    migrate)           cmd_migrate "$@" ;;
    db:reset)          cmd_db_reset "$@" ;;
    seed)              cmd_seed "$@" ;;
    check:alembic)     cmd_check_alembic "$@" ;;

    # Lint
    lint)              cmd_lint "$@" ;;
    fmt)               cmd_fmt "$@" ;;
    fmt:fix)           cmd_fmt_fix "$@" ;;

    # Utility
    clean)             cmd_clean "$@" ;;
    help|--help|-h)    show_help ;;

    *)
        error "Unknown command: $CMD"
        echo "Run './run help' for available commands"
        exit 1
        ;;
esac
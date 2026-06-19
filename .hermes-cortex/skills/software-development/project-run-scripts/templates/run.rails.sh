#!/usr/bin/env bash
# <Rails Project> — Unified CLI
# Usage: ./run <command>
#
# Rails variant: function-based dispatch, rails-specific commands.
# Modeled on ioneent-website/run and koscap-mwi/run patterns.

set -o errexit
set -o pipefail

# ── Source .env ──────────────────────────────────────────
if [ -f .env ]; then
  source .env
fi

# ── Compose command detection ────────────────────────────
DC="${DC:-exec}"
TTY=""
if [[ ! -t 1 ]]; then
  TTY="-T"
fi

# ── Multi-compose support (uncomment if needed) ──────────
# F_MWEB="-f docker-compose.mweb.yml -p mweb"
# F_MWI="-f docker-compose.mwi.yml -p mwi"

_dc() {
  echo "docker compose ${*}"
  docker compose "${@}"
}

# ══════════════════════════════════════════════════════════
# Lifecycle
# ══════════════════════════════════════════════════════════

function up {
  docker compose up -d "${@}"
}

function down {
  docker compose down --remove-orphans "${@}"
}

function restart {
  down
  up
}

function build {
  docker compose build "${@}"
}

function logs {
  docker compose logs -f "${@}"
}

function ps {
  docker compose ps
}

# ══════════════════════════════════════════════════════════
# Container access
# ══════════════════════════════════════════════════════════

function exec_web {
  docker compose exec "${TTY}" web "${@}"
}

function bash_web {
  exec_web bash "${@}"
}

# ══════════════════════════════════════════════════════════
# Rails
# ══════════════════════════════════════════════════════════

function rails {
  ## Run Rails commands (e.g. ./run rails db:migrate)
  exec_web bundle exec rails "${@}"
}

function db:create {
  rails db:create
}

function db:migrate {
  rails db:migrate
}

function db:seed {
  rails db:seed
}

function db:reset {
  rails db:drop db:create db:migrate db:seed
}

# ══════════════════════════════════════════════════════════
# Dependencies
# ══════════════════════════════════════════════════════════

function bundle:install {
  docker compose run --rm web bundle install
}

function bundle:update {
  docker compose run --rm web bundle update --all "${@}"
  docker compose run --rm web bundle clean --force
  bundle:install
}

function yarn:install {
  _dc run --rm js yarn install 2>/dev/null || _dc run --rm web yarn install
}

function yarn:build {
  _dc run --rm js yarn build 2>/dev/null || _dc run --rm web yarn build
}

# ══════════════════════════════════════════════════════════
# Database
# ══════════════════════════════════════════════════════════

function psql {
  ## Open psql in the postgres container
  if [ "${1:-}" = "-c" ]; then
    shift
    docker compose exec -T postgres psql -U "${POSTGRES_USER:-app}" -d "${POSTGRES_DB:-app}" -c "$@"
  else
    docker compose exec -it postgres psql -U "${POSTGRES_USER:-app}" -d "${POSTGRES_DB:-app}" "${@}"
  fi
}

# ══════════════════════════════════════════════════════════
# Testing
# ══════════════════════════════════════════════════════════

function test {
  local spec_path="${1:-spec/}"
  echo "Running RSpec: $spec_path"
  _dc exec -e RAILS_ENV=test web bundle exec rspec "${spec_path}"
}

function test:setup {
  rails db:drop db:create db:migrate RAILS_ENV=test
}

# ══════════════════════════════════════════════════════════
# Maintenance
# ══════════════════════════════════════════════════════════

function clean {
  echo "clean: removing node_modules, app/assets/builds, tmp, public/assets"
  rm -rf node_modules/ app/assets/builds/* public/assets tmp/cache/assets .byebug_history
  echo "clean: done"
}

# ══════════════════════════════════════════════════════════
# Help
# ══════════════════════════════════════════════════════════

function help {
  printf "%s <task> [args]\n\n" "${0}"
  printf "Commands:\n"
  printf "  ./run up              Start all services\n"
  printf "  ./run down            Stop all services\n"
  printf "  ./run restart         Restart all services (down + up)\n"
  printf "  ./run build           Build images\n"
  printf "  ./run logs            Follow logs\n"
  printf "  ./run ps              List containers\n"
  printf "  ./run bash_web        Open bash in web container\n"
  printf "  ./run rails <cmd>     Run Rails command\n"
  printf "  ./run db:migrate      Run migrations\n"
  printf "  ./run db:seed         Seed database\n"
  printf "  ./run db:reset        Drop + create + migrate + seed\n"
  printf "  ./run test [path]     Run RSpec tests\n"
  printf "  ./run test:setup      Setup test database\n"
  printf "  ./run psql            Connect to PostgreSQL\n"
  printf "  ./run bundle:install  Install gems\n"
  printf "  ./run yarn:install    Install JS deps\n"
  printf "  ./run yarn:build      Build JS assets\n"
  printf "  ./run clean           Remove cache and generated files\n"
}

# ══════════════════════════════════════════════════════════
# Dispatch
# ══════════════════════════════════════════════════════════

TIMEFORMAT=$'\nTask completed in %3lR'
time "${@:-help}"
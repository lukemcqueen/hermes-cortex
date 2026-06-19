---
name: project-run-scripts
description: "DEFINITIVE canonical template for ./run — single bash CLI entrypoint covering Docker lifecycle, dev servers, testing, database management, linting, and utility commands. Applies to ANY tech stack: Python/FastAPI, Rails, Go, Node/Next.js, Rust. Every repo MUST have this file."
related_skills:
  - python-dependency-management
  - docker-compose-common-issues
trigger:
  - "creating a ./run script"
  - "adding a CLI to a project"
  - "standardizing project commands"
  - "setting up dev workflow"
  - "modeling after another project's run script"
  - "what commands should a ./run have"
  - "how to structure a ./run file"
  - "agents consistently create and update run file"
---

# Project Run Scripts — Canonical Specification

A single `./run` entrypoint MUST cover ALL common developer workflows. Every project — regardless of tech stack (Python, Rails, Go, Node, Rust) — MUST use the same command interface so a developer switching between repos never has to re-learn the entry point.

## Non-Negotiable Command Contract

Every `./run` MUST implement these commands with identical semantics:

| Command | Semantics | Implementation |
|---------|-----------|----------------|
| `./run up` | Start Docker environment (detached) | `docker compose up -d --remove-orphans` |
| `./run down` | Stop Docker environment | `docker compose down --remove-orphans` |
| `./run restart` | Down then Up (full restart) | `cmd_down && cmd_up` |
| `./run restart <svc>` | Restart single service | `docker compose restart <svc>` |
| `./run logs` | Show last 50 lines of logs | `docker compose logs --tail=50` |
| `./run logs -f` | Follow all logs | `docker compose logs --tail=50 -f` |
| `./run logs <svc>` | Tail logs for a service | `docker compose logs --tail=50 <svc>` |
| `./run build` | Build Docker images | `docker compose build` |
| `./run build --no-cache` | Build with no cache | `docker compose build --no-cache` |
| `./run build <svc>` | Build specific service | `docker compose build <svc>` |
| `./run ps` | List running containers | `docker compose ps` |
| `./run health` | Check health of all services | Loop over services + connectivity checks |
| `./run exec <svc> <cmd>` | Run command in container | `docker compose exec -T <svc> <cmd>` |
| `./run pgsql` | Interactive psql | `docker compose exec -it postgres psql -U <user> -d <db>` |
| `./run pgsql -c "SQL"` | Run SQL non-interactive | `docker compose exec -T postgres psql -U <user> -d <db> -c "SQL"` |
| `./run test` | Run all tests | Aggregates sub-test commands |
| `./run test:api` | Run API tests | pytest / rspec / go test |
| `./run test:web` | Run web tests | vitest / playwright |
| `./run lint` | Run all linters | ruff / rubocop / eslint |
| `./run db:reset` | Drop → create → migrate → seed | Via Docker psql or host |
| `./run migrate` | Apply pending migrations | alembic / rails / drizzle |
| `./run seed` | Load seed data | Python / pnpm / rails |
| `./run clean` | Remove all build artifacts | rm -rf .venv node_modules .next __pycache__ |
| `./run help` | Show help | |

### Variation policy

- **Non-Docker projects** (standalone Go tools, scripts): omit Docker commands, implement only test/lint/clean/help.  
- **No-compose projects** (simple services): fall back to individual `docker run` commands but still implement `up`/`down`/`logs`.  
- **Rails projects** MUST add `./run rails <cmd>`, `./run bundle:install`, `./run yarn:build`.  
- **Multi-compose projects** (e.g., koscap-mwi) MUST route service names to the correct compose file. Use a `case` dispatch in the build function.  
- **Platform dispatchers** (e.g., koscap-platform) use a root dispatcher + per-component `./run` scripts. Each component's `./run` implements the same interface above.

## Self-Healing Migrations

When running `./run migrate`, detect and auto-resolve multiple Alembic heads:

```bash
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
```

Also provide a `check:alembic` command that validates single head:

```bash
cmd_check_alembic() {
    info "Checking Alembic migrations..."
    local HEADS
    HEADS=$(_alembic_runner heads 2>/dev/null | wc -l)
    if [ "$HEADS" -gt 1 ]; then
        warn "Multiple heads detected ($HEADS). Run './run migrate' to auto-merge."
        return 1
    else
        ok "Single migration head"
    fi
}
```

## psql — Dual-Mode

Must support both interactive and non-interactive:

```bash
cmd_pgsql() {
    local user="${POSTGRES_USER:-app}"
    local db="${POSTGRES_DB:-app}"
    if [ "${1:-}" = "-c" ]; then
        shift
        docker compose exec -T postgres psql -U "$user" -d "$db" "$@"
    else
        docker compose exec -it postgres psql -U "$user" -d "$db" "$@"
    fi
}
```

## --no-cache Passthrough

Build must handle `--no-cache` mixed with service names:

```bash
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
}
```

## Template Structure

Every `./run` follows this structure:

```
1. shebang + set -euo pipefail
2. PROJECT_ROOT detection
3. Source .env
4. Color helpers (info/ok/warn/error)
5. show_help() — complete command list
6. activate_venv() + _pytest_runner() + _alembic_runner() helpers
7. Vitest cleanup (_cleanup_vitest + _run_vitest)
8. Docker commands (cmd_up through cmd_pgsql)
9. Dev commands (cmd_pip, cmd_dev_api, cmd_dev_web)
10. Test commands (cmd_test, cmd_test_api, etc.)
11. Database commands (cmd_db_reset, cmd_migrate, cmd_check_alembic, cmd_seed)
12. Lint/format commands (cmd_lint, cmd_fmt, cmd_fmt_fix)
13. Clean/rebuild commands (cmd_clean, cmd_rebuild)
14. Main case dispatch
```

## Canonical Template (replaces templates/run.sh)

The canonical template is at `/Users/luke/.hermes/skills/software-development/project-run-scripts/templates/run.sh` — it is the definitive starting point for every new project. Customize: PROJECT_ROOT paths, service names, env var defaults, test runner commands.

## Hermes Cortex Variant

For agent-only repos (hermes-cortex-style, no Docker, no database), use the minimal template at `templates/run.cortex.sh`.

## Vitest Cleanup (ALL repos with web tests)

Every repo with vitest tests MUST include `_cleanup_vitest` and `_run_vitest` functions. Orphaned vitest workers accumulate and block ports. Pattern (exact code in canonical template).

## Rainbow

When writing a `./run` for a repo that lacks one, or updating one that's incomplete:
1. Read the canonical template: `skill_view(name="project-run-scripts", file_path="templates/run.sh")`
2. Determine which tech stack(s) the project uses (Python/FastAPI? Rails? Go? Node?)
3. Customize: service names, env var defaults, test paths, db credentials
4. Remove irrelevant commands (e.g., remove `cmd_dev_web` if no frontend)
5. Add stack-specific commands (e.g., `rails` for Rails, `batch` for Rust)
6. Run `chmod +x run && ./run help` to verify

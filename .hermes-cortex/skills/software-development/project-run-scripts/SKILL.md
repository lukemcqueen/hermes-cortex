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
- **Rails projects** — use the **Taskfile pattern** (`time "${@:-help}"` + bare function names), NOT the bash case-dispatch template. See `references/taskfile-pattern.md` for how this dispatch mechanism works and how to add commands.
- **Rails projects** MUST add: `rails <cmd>`, `bundle:install`, `yarn:build`, `psql`, `test`, `migrate`, `seed`. Use `templates/run.rails.sh` for new Rails projects.
- **Multi-compose projects** (e.g., acme-mwi) MUST route service names to the correct compose file. Use a `case` dispatch in the build function.
- **Multi-compose projects** (e.g., acme-mwi) MUST route service names to the correct compose file. Use a `case` dispatch in the build function.
- **Platform dispatchers** (e.g., acme-platform) use a root dispatcher + per-component `./run` scripts. Each component's `./run` implements the same interface above.

## Migration Head Integrity — Fail-Fast, No Auto-Merge

Multiple Alembic heads MUST be resolved at PR/merge time — never at deploy or
container-start time. Auto-merging inside a container produces ephemeral state
that disappears on rebuild and masks genuine migration chain problems. It can
also generate corrupt merge files with `revision = None`, crashing every subsequent
Alembic operation with `TypeError: 'NoneType' object is not iterable`.

### Required Files

Every project with Alembic migrations MUST have these two files:

| File | Purpose | Provided by skill |
|------|---------|-------------------|
| `scripts/check-alembic-heads.py` | Static-analysis script: checks for multiple heads, validates revision ID length (max 32 chars) | `skill_view(name="project-run-scripts", file_path="scripts/check-alembic-heads.py")` — copy to your repo |
| `tests/test_migrations.py` | Pytest: asserts `len(script.get_heads()) == 1` at runtime | Template below — include in your test suite |

### Policy

| Layer | Behavior |
|-------|----------|
| **`./run build`** | Runs `check-alembic-heads.py` before building Docker images. Aborts on multi-head. |
| **`./run migrate`** | Validate single head before upgrade. Fail with instructions if >1 head. |
| **`./run check:alembic`** | Manual alias: runs `check-alembic-heads.py` on demand. |
| **`entrypoint.sh`** | Run `alembic upgrade head` directly. If multiple heads or corruption, fail loudly. |
| **CI (`test_migrations.py`)** | Assert `len(script.get_heads()) == 1`. Block deploy on divergence. |
| **Local dev** | Developer runs `alembic merge heads` or rebases before pushing. |

### `scripts/check-alembic-heads.py`

Copy this script from the skill's `scripts/` directory:

```bash
cp $(dirname $(skill_view name=project-run-scripts file_path=scripts/check-alembic-heads.py 2>/dev/null || echo "$HOME/.hermes/skills/software-development/project-run-scripts/scripts/check-alembic-heads.py"))/*.py scripts/
```

The script uses `re.DOTALL` to correctly parse multiline `down_revision` tuples
(e.g., merge revisions with two parents spread across multiple lines).

### `./run migrate` — Fail-Fast

```bash
cmd_migrate() {
    info "Applying Alembic migrations..."
    local HEADS
    HEADS=$(_alembic_runner heads 2>/dev/null | wc -l)
    if [ "$HEADS" -ne 1 ]; then
        error "$HEADS migration heads detected. Expected exactly 1."
        error "Run 'alembic heads' to see them, then create a merge revision."
        return 1
    fi
    _alembic_runner upgrade head
    ok "Migrations applied"
}
```

### `entrypoint.sh` — Direct, No Auto-Heal

```bash
echo "[1/3] Checking Alembic migrations..."
PYTHONPATH=. alembic upgrade head 2>&1 || {
    rc=$?
    echo "  ✗ Alembic migration failed (exit $rc)."
    echo "  Possible causes: multiple heads, corrupt merge revision, stale migration file."
    echo "  Action: rebase your branch, resolve heads locally, and rebuild."
    exit $rc
}
echo "  ✓ Migrations up to date"
```

### CI Test — `tests/test_migrations.py`

```python
from alembic.config import Config
from alembic.script import ScriptDirectory

def test_single_migration_head():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"Expected 1 Alembic head, found {len(heads)}: {heads}. "
        "Run `alembic merge heads -m 'merge'` or rebase your branch."
    )
```

### Auto-Merge Failure Mode (for context)

The old auto-merge pattern failed because:
1. `alembic merge heads` can generate a file with `revision: str | None = None`
2. Every subsequent `upgrade`/`heads`/`check` crashes with `TypeError: 'NoneType' object is not iterable`
3. The corrup file persists across container starts unless explicitly deleted
4. The entrypoint's `2>/dev/null || true` silently swallows the error, making it look like the DB is uninitialized

**Recovery from a broken auto-merge file inside a running container:**
```bash
docker compose exec api sh -c "rm -f /app/alembic/versions/*auto_merge* /app/alembic/versions/*merge*"
```

Then verify the root cause (migration chain fork, wrong `down_revision`, corrupt file).
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

### `--no-cache` Passthrough

Build must handle `--no-cache` mixed with service names, and MUST check Alembic migration integrity before building:

```bash
cmd_build() {
    # Pre-check: abort on multiple Alembic heads
    if ! python3 "$PROJECT_ROOT/scripts/check-alembic-heads.py" "$API_DIR/alembic/versions" 2>&1; then
        echo "✗ Build aborted: fix Alembic migration heads before building."
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

## Reference: Multi-Repo Audit

`references/multi-repo-audit-2026-06.md` documents the actual state of every `./run` file across all user repos as of June 2026 — what was changed, what was preserved, and which repos were skipped (and why). Consult this before updating an existing repo's `./run` to understand its specific structure.

## Hermes Cortex Variant

For agent-only repos (hermes-cortex-style, no Docker, no database), use the minimal template at `templates/run.cortex.sh`.

## Vitest Cleanup (ALL repos with web tests)

Every repo with vitest tests MUST include `_cleanup_vitest` and `_run_vitest` functions. Orphaned vitest workers accumulate and block ports. Pattern (exact code in canonical template).

## Rainbow (update workflow)

When writing a `./run` for a repo that lacks one, or updating one that's incomplete:
1. Read the canonical template: `skill_view(name="project-run-scripts", file_path="templates/run.sh")`
2. Determine which tech stack(s) the project uses (Python/FastAPI? Rails? Go? Node?)
3. Customize: service names, env var defaults, test paths, db credentials
4. Copy `scripts/check-alembic-heads.py` from the skill (see Migration Head Integrity section above) if the project uses Alembic
5. Remove irrelevant commands (e.g., remove `cmd_dev_web` if no frontend)
6. Add stack-specific commands (e.g., `rails` for Rails, `batch` for Rust)
7. Run `chmod +x run && ./run help` to verify

## Strategy: Rewrite vs Patch

Updating an existing `./run` across many repos requires a strategy:

- **Full rewrite** for files under 250 lines — safer than patching, preserves all custom commands in one pass. Write the file entirely from the template, preserving custom commands (test subdomains, search, backup, etc.).
- **Targeted patch** for files over 300 lines — use `patch(mode='replace')` on specific function bodies. Batch related patches with `execute_code` for speed.
- **Never use bundled dispatch** (e.g., `up|down|restart|build|logs|ps)` — this pattern prevents fixing individual commands like `restart` (should be down+up, not `docker compose restart`). Break them into individual cases.
- **Function boundary caution with patch** — patches that replace multi-line function bodies can accidentally consume/substring-match adjacent function definitions. If patch drops a neighboring function's `name() {`, revert by re-adding the definition line. Prefer full-file writes for functions over 8 lines to avoid this.

## Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|------|
| **Rails Taskfile pattern** — Rails repos use `time "${@:-help}"` + bare function names as commands (e.g., `function up {` called via `./run up`). They don't use case-dispatch with `cmd_` prefix. | Forcing case-dispatch conversion breaks the repo | Leave Rails Taskfile pattern repos alone. They already implement the standard Docker lifecycle commands as functions. Only add missing commands (pgsql, lint, migrate) as new functions, keeping the `time` dispatch. Use `run.rails.sh` template for new Rails projects. |
| **Custom compose variables** — Some repos (e.g., acme-metadata) define `DOCKER_COMPOSE="docker compose -p acme-metadata -f $COMPOSE_FILE"` and use `$DOCKER_COMPOSE` instead of raw `docker compose`. | Patching with `docker compose` literal breaks the command because the flag/format is wrong | Inspect how compose is called in `cmd_up()`. If it uses a variable, ALL docker compose calls in the file must preserve it. Use the same variable name when patching. |
| **Bundled dispatch** — `up|down|restart|build|logs|ps)` in a single case arm prevents fixing individual semantics | `./run restart` calls `docker compose restart` instead of down+up; `./run build` has no --no-cache | Break into individual cases: `up) ... ;; down) ... ;; restart) ... ;;` etc. |
| **psql vs pgsql naming** — Some repos (e.g., acme-matching) use `psql` and `psql:cmd` instead of `pgsql` | `./run pgsql` fails with "Unknown command" | Add `pgsql` as the canonical name with `pgsql) shift; cmd_pgsql "$@" ;;` AND keep `psql` as an alias pointing to the same function. The `pgsql` name is canonical across all repos. |
| **Self-healing migrate needs `_alembic_runner`** — The self-healing migrate function uses `_alembic_runner`, which requires `activate_venv` helper. | Repos without `_alembic_runner` or that run migrations inside Docker (via `docker compose exec -T api ...`) get errors | Check how db:reset runs migrations. If it uses `_alembic_runner` (local venv), mirror that. If it runs inside Docker, create cmd_migrate that also runs inside Docker. |
| **No-compose fallback** — Repos like example-website and ebm-website check `[ -f docker-compose.yml ]` and fall back to `docker run` individual containers | Standardizing the compose case breaks the no-compose fallback | Preserve the `HAS_DC` / `DC` variable pattern for repos that need compose-optional behavior. Only add new commands (lint, pgsql) inside the existing fallback structure. |

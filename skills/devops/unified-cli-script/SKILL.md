---
name: unified-cli-script
version: 1.0.0
description: >
  Design a unified ./run CLI script for multi-environment Docker Compose
  deployments. Covers the _compose() wrapper, CLIENT_ENV requirement,
  prominent env display, compose override files, and git hook compatibility.
triggers:
  - user asks to update ./run for env support
  - user asks to make CLI env-aware
  - user asks to halt with instructions when config missing
  - user says 'scripts should halt if no env set'
  - creating or modifying a unified CLI script for monorepo Docker workflows
---

# Unified CLI Script (`./run`)

Pattern for building a single `./run` CLI that works across `dev`, `stage`, and `prod` environments via Docker Compose override files.

## Architecture

```
./run                    → unified entry point
docker-compose.yml       → base compose file (shared config)
docker-compose.stage.yml → stage overrides
docker-compose.prod.yml  → production overrides
.env                     → dev environment variables (default)
.env.stage               → stage env overrides
.env.prod                → production env overrides
```

## Core Requirements

1. **Explicit env gate** — the script halts with clear instructions when
   `CLIENT_ENV` (or `APP_ENV`) is unset. No silent default to dev.
2. **`_compose()` wrapper** — single function that assembles
   `-f docker-compose.yml [-f docker-compose.<env>.yml] [--env-file .env.<env>]`
   and runs `docker compose`. Every command in the script routes through it.
3. **Prominent env banner** — each invocation prints which environment is
   active so operators can't mistake prod for dev.
4. **Subcommand dispatch** — `up`, `down`, `logs`, `ps`, `exec`, `build`,
   `restart`, `shell`, `test` (see `env-aware-compose-wrapper` for the
   concrete implementation).

## Git Hook Compatibility

The `./run` script is often invoked from git hooks (post-checkout,
post-merge, prepare-commit-msg). Two pitfalls:

- **Hooks run with a minimal environment** — `CLIENT_ENV` may be unset even
  though the developer "exported" it in their shell. The env gate must
  print instructions, not silently do nothing.
- **Interactive vs non-interactive** — a hook that calls `./run up` in a
  non-interactive context may hang on prompts. Keep hook-invoked commands
  non-interactive (`-d` for up, no TTY prompts) or guard with
  `[[ -t 0 ]]` checks.

Recommended hook pattern:

```bash
# post-checkout / post-merge — bring deps up after switching branches
export CLIENT_ENV=dev
./run up --detach 2>/dev/null || echo "⚠ ./run failed — set CLIENT_ENV and run manually"
```

## Env File Precedence

- `--env-file` values in compose: later `--env-file` flags override earlier ones;
  shell environment beats `--env-file` values.
- `.env` in the project root is loaded automatically by `docker compose`
  as defaults; the explicit `--env-file .env.<env>` overrides it per-environment.

## Verification Checklist

```bash
# 1. Gate works
./run up                              # must halt with instructions
CLIENT_ENV=dev ./run up               # must show banner + run

# 2. Correct override selection
CLIENT_ENV=prod ./run config | grep -c "prod"   # prod services present

# 3. Idempotent in hooks
CLIENT_ENV=dev ./run up --detach      # exits cleanly, no prompt hang
```

## Related
- `env-aware-compose-wrapper` — the `_compose()` wrapper implementation
- `project-run-scripts` — canonical `./run` template
- `docker-management` — general Docker operations

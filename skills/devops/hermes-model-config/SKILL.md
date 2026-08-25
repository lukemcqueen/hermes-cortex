---
name: hermes-model-config
description: "Use when sessions run the wrong model or config regresses."
version: 1.0.0
category: devops
author: Titus
license: MIT
platforms: [linux, macos]
---

# Hermes Model & Provider Config

**Trigger:** "sessions use the wrong model", "model is X but should be Y",
deepseek-chat/deepseek-flash questions, `⚠ Deprecated .env settings detected`
warning, cron model overrides, model.default regressions after `hermes update`.

## Fleet model convention (verified on the fleet owner's host, 2026-08-18)

- **Regular sessions = `deepseek-v4-flash`** — set in `config.yaml`
  `model.default` (provider `deepseek`, base_url `https://api.deepseek.com/v1`).
  Also encoded as `DEFAULT_MODEL=deepseek-v4-flash` in `~/.hermes-cortex/.env`.
- **`deepseek-chat` is LLM-cron-ONLY.** It must never be the session default.
  Crons pin it per-job: `"model": "deepseek-chat"` in `~/.hermes/cron/jobs.json`
  (see `LLM_CRON_MODEL=deepseek-chat` in `ops/scripts/install-crons.sh` and
  `ops/install/cron-manifest.yaml`). A config.yaml default of deepseek-chat is
  the regression symptom.

## Diagnose (in order)

1. **Truth for NEW sessions = config.yaml, not the banner.** Run
   `hermes config get model.default` (+ `model.provider`, `model.base_url`).
   The session banner snapshots the model at session START — a mid-session
   `hermes update` changes config underneath it (observed 2026-08-18: banner
   showed deepseek-v4-flash while config already said deepseek-chat).
2. **If config changed unexpectedly**, check
   `stat -f '%Sm %N' ~/.hermes/config.yaml` and `tail ~/.hermes/logs/update.log`
   — `hermes update` rewrites config.yaml AND ~/.hermes/.env in the same
   second. To rule out a migration, grep the key in
   `~/.hermes/hermes-agent/hermes_cli/config_migrations.py` (model.default had
   NO migration — it was a stale manual setting).
3. **Cron overrides:** `grep -n '"model"' ~/.hermes/cron/jobs.json` — per-job
   `model` field; `model_snapshot` records what it actually ran as. `no_agent`
   jobs (script-based) ignore `model` entirely.
4. **Check the whole repo for the convention:** `grep -rn '<model-id>'
   ~/hermes-cortex --include='*.sh' --include='*.yaml' --include='*.py'` —
   install scripts/manifests show the intended per-role model split.

## Fix

- `hermes config set model.default <model-id>` — **NEVER hand-edit
  config.yaml** (stray indent breaks the live gateway; hermes-agent hard
  invariant). `provider` / `base_url` are untouched by this command.
- No gateway restart needed: `_resolve_gateway_model` (gateway/run.py) reads
  `model.default` fresh per session from raw YAML.

## Verify end-to-end (mandatory)

1. Spawn a real one-shot: `hermes chat -q "Reply with exactly: OK"` — note the
   `Session:` id in output.
2. Confirm the recorded model:
   `sqlite3 ~/.hermes/state.db "SELECT id, model, billing_provider,
   billing_base_url FROM sessions WHERE id='<session-id>';"`
   ⚠️ sessions table has `model` + `billing_provider` — there is NO `provider`
   column; `billing_provider` is the provider.
3. Re-check the cron overrides still pin the cron-only model where intended.

## Deprecated .env settings warning

- The runtime warning comes from `warn_deprecated_cwd_env_vars`
  (hermes_cli/config.py) and checks **process env** for `MESSAGING_CWD` /
  `TERMINAL_CWD` — it can false-positive on Hermes's own launch-dir bridge
  (the message says "found in .env" even when the var came from Hermes).
- Authoritative check = `hermes doctor`, which scans the **.env file**
  (`hermes_cli/doctor.py` `_DEPRECATED_ENV_VARS`): `TERMINAL_CWD` →
  `terminal.cwd`, `MESSAGING_CWD` → `terminal.cwd`,
  `HERMES_TOOL_PROGRESS` / `HERMES_TOOL_PROGRESS_MODE` → `display.tool_progress`,
  `QQ_HOME_CHANNEL` / `QQ_HOME_CHANNEL_NAME` → `QQBOT_HOME_CHANNEL[_NAME]`.
- `hermes update` auto-comments deprecated .env entries. Check for ACTIVE
  leftovers with:
  `grep -nE '^(TERMINAL_CWD|MESSAGING_CWD|HERMES_TOOL_PROGRESS|HERMES_TOOL_PROGRESS_MODE|QQ_HOME_CHANNEL|QQ_HOME_CHANNEL_NAME)=' ~/.hermes/.env`
- Migration target `terminal.cwd` is PER-PROJECT: keep `terminal.cwd: .`
  (launch dir) on multi-project hosts. Do NOT set a global project path just
  to silence the warning.

## Pitfalls

- state.db sessions table: `billing_provider`, not `provider` (query error).
- The `.env` deprecated entry may already be commented by a recent `hermes
  update` — verify before "removing" anything; an empty grep result means the
  warning is already neutralized.
- model ids evolve: verify the exact id against
  `grep -n '"model"' ~/.hermes/cron/jobs.json` and `~/.hermes-cortex/.env`
  before assuming a shorthand ("deepseek-flash" = `deepseek-v4-flash`).

  2026-08-18 deepseek-chat regression: investigation trail + verification
  output.

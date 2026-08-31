# Env Var Name Registry

**NAMES ONLY — values live in the gitignored env files.** Two env files:

- `~/.hermes-cortex/.env` — the single fleet env file (canonical; 27 vars)
- `~/.hermes/.env` — Hermes agent env (credentials, telegram)

An agent needing a value reads it from the env file, never from this doc
or from memory. These names are the contract — never invent new names
without checking here first (Rule 11: never invent config or env names).

## ~/.hermes-cortex/.env (fleet)

| Env var | Purpose |
|---|---|
| `AGENT_NAME` | Agent identity (esther/moses/titus/...) — identity is env-derived ONLY, never hostname/USER fallback |
| `CODING_MODEL` | Coding task model |
| `CREATIVE_MODEL` | Creative/content model |
| `DEFAULT_MODEL` | Default fallback model |
| `JUDGE_MODEL` | Governance judge model |
| `EMBEDDING_MODEL` | Embedding model (local Ollama: nomic-embed-text:v1.5) |
| `LLM_CRON_MODEL` | Cron LLM model (deepseek-v4-flash) |
| `LLM_CRON_PROVIDER` | Cron LLM provider (deepseek) |
| `LLM_CRON_FALLBACK1_MODEL` | First cron fallback model (deepseek-v4-flash) |
| `LLM_CRON_FALLBACK1_PROVIDER` | First cron fallback provider (deepseek) |
| `LLM_CRON_FALLBACK2_MODEL` | Second cron fallback model (deepseek-v4-flash) |
| `LLM_CRON_FALLBACK2_PROVIDER` | Second cron fallback provider (opencode-zen) |
| `HERMES_CRON_TIMEOUT` | Cron timeout budget |
| `HERMES_TIMEZONE` | Fleet timezone (Asia/Seoul, KST) |
| `IS_ORCHESTRATOR` | Orchestrator flag (host-derived) |
| `IS_SERVER` | Server-mode flag |
| `CORTEX_BASE` | Cortex base path |
| `CORTEX_DOMAIN` | Fleet public domain (values never in repo) |
| `CORTEX_BASIC_AUTH` | Basic-auth credential pair |
| `CORTEX_BUS_URL` | Bus primary endpoint (env-first — see ADR history) |
| `CORTEX_BUS_FALLBACK_URL` | Bus fallback endpoint |
| `CORTEX_BUS_TOKEN` | Bus bearer token |
| `CORTEX_BUS_PG_*` (HOST/PORT/DB/USER/PASS) | Bus Postgres connection |
| `CORTEX_INBOX_URL` | Agent inbox v2 API base |
| `CORTEX_NGINX_PORT_PREFIX` | Nginx port prefixing |
| `ORCH_HEALTH_URLS` | Active orchestrator's health probe targets (failover watchdog) — lives in `~/.hermes/.env` (the file the gateway/cron reads), NOT `~/.hermes-cortex/.env` |
| `BACKUP_ORCH_HEALTH_URLS` | Standby orchestrator's health probe targets (failover watchdog) — `~/.hermes/.env` |

## ~/.hermes/.env (Hermes agent)

| Env var | Purpose |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API credential |
| `TELEGRAM_BOT_TOKEN` | Telegram bot credential |
| `TELEGRAM_ALLOWED_USERS` | Allowed Telegram user IDs |
| `TELEGRAM_HOME_CHANNEL` | Default delivery channel (Esther: Luke DM) |
| `TELEGRAM_API_BASE` | Telegram Bot API base URL for the messaging gateway (`msg-gateway.py`) |

## Rules

1. **Never hardcode a value that has an env var.** The bus URLs were
   over-scrubbed in the 2026-08-24 history rewrite because they were
   hardcoded in scripts — the fix moved them to env (commit `9a95ceb8`).
2. **Never invent a name** — survey this registry first.
3. **Auth-gated liveness** uses `CORTEX_BUS_URL` + token; `/health` alone
   is insufficient.

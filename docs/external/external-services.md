# External Services

**What exists outside the repo that an agent needs to know about. NAMES
and locations only — credentials/values live in the gitignored env files
or the service's own dashboard.**

| Service | What it's for | Credential location | Notes |
|---|---|---|---|
| DeepSeek API | All LLM inference (chat, cron, judge) | `~/.hermes/.env` → `DEEPSEEK_API_KEY` | Pricing contract: ADR-0001 |
| Telegram Bot API | All agent messaging (DM, cron delivery) | `~/.hermes/.env` → `TELEGRAM_BOT_TOKEN` | `TELEGRAM_HOME_CHANNEL` = default delivery target |
| Ollama (local) | Embeddings (`nomic-embed-text:v1.5`) | local service, no creds | Used by loop-governance cache + RAG |
| Agent Bus / Postgres | Fleet messaging (PGMQ over the bus) | `~/.hermes-cortex/.env` → `CORTEX_BUS_*` | v2 API policy: ADR-0003 |
| Agent Inbox | Threaded messaging with topic channels | `~/.hermes-cortex/.env` → `CORTEX_INBOX_URL` + `CORTEX_BUS_TOKEN` | v2 API: ADR-0003 |
| GitHub | hermes-cortex public repo | git credential helper | PII-free by policy |
| cron-costs DB | Per-run token/cost ledger | SQLite (`cron-costs.db`) | read by `orch-daily-cost-report.py` |
| loop-governance DB | Governance cycles | local SQLite | scored via loop-gov MCP |

## Payment processor

**Not yet configured.** The KAESA pre-order flow (client engagement) will
need a payment processor — the decision (processor choice, API keys,
webhook endpoints) will be recorded HERE as an ADR when chosen. No
payment credentials exist in any env file yet.

## Rules

- **No values in this file** — every credential is behind an env var name
  or a service dashboard.
- **Add new services here** when you wire them — a fresh session should
  never discover a third-party integration by reading code.
- **Payment processor selection** must be an ADR (context/decision/
  consequences), not just a config value.

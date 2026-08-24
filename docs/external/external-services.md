# External Services

**What exists outside the repo that an agent needs to know about. NAMES
and locations only — credentials/values live in the gitignored env files
or the service's own dashboard.**

| Service | What it's for | Credential location | Notes |
|---|---|---|---|
| DeepSeek API | All LLM inference (chat, cron, judge) | `~/.hermes/.env` → `DEEPSEEK_API_KEY` | Pricing contract: ADR-0001 |
| Telegram Bot API | All agent messaging (DM, cron delivery) | `~/.hermes/.env` → `TELEGRAM_BOT_TOKEN` | `TELEGRAM_HOME_CHANNEL` = default delivery target |
| Telegram Bot API (per-agent bridges) | Coding-agent inbox bridges (telegram-bridge.py) — each agent runs its OWN bot + OWN bus token | per-agent env (`~/.<agent>/.env` → `TELEGRAM_BOT_TOKEN` + `CORTEX_BUS_TOKEN`) | Per-agent tokens ONLY — never shared (Luke 2026-08-24). Rotate via `cortex-agent-manager.py rotate <agent>` |
| Ollama (local) | Embeddings (`nomic-embed-text:v1.5`) | local service, no creds | Used by loop-governance cache + RAG |
| Agent Bus / Postgres | Fleet messaging (PGMQ over the bus) | `~/.hermes-cortex/.env` → `CORTEX_BUS_*` | v2 API policy: ADR-0003 |
| Agent Inbox | Threaded messaging with topic channels | `~/.hermes-cortex/.env` → `CORTEX_INBOX_URL` + `CORTEX_BUS_TOKEN` | v2 API: ADR-0003 |
| GitHub | hermes-cortex public repo | git credential helper | PII-free by policy |
| cron-costs DB | Per-run token/cost ledger | SQLite (`cron-costs.db`) | read by `orch-daily-cost-report.py` |
| loop-governance DB | Governance cycles | local SQLite | scored via loop-gov MCP |

## Payment processor

**Framework policy (generic):** payment-processor selection for a client
engagement is a CLIENT/BUSINESS decision, documented in the private repo
(`~/hermes-cortex-private`), never the public framework. The public
framework ships no payment credentials, no processor integrations, and no
client-specific commerce details. When a processor is chosen for a
client, record it as a private ADR with the gating requirements
(merchant entity, local-wallet support, pre-order/escrow semantics).

## Rules

- **No values in this file** — every credential is behind an env var name
  or a service dashboard.
- **No client names or client-specific commerce details** — the public
  repo is framework-only; client decisions live in the private repo.
- **Add new services here** when you wire them — a fresh session should
  never discover a third-party integration by reading code.
- **Payment processor selection** for a client must be a PRIVATE ADR
  (context/decision/consequences), not just a config value.

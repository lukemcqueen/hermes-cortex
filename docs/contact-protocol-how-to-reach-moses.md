## Contact Protocol — How to Reach Moses

> **Role rule (canonical matrix in `docs/bus-architecture.md`):** Orchestrators
> (Moses, Esther) have the MCP client + HTTP client. Workers (Gisu, Joseph,
> Kustos, Titus) have the HTTP client ONLY — no MCP tools, no server.

| Channel | When | How |
|---------|------|-----|
| In-session (MCP) — **orchestrators only** | Have the agent-bus MCP tools loaded (Moses, Esther) | `inbox_send(to="moses", subject=..., body=...)` — see `docs/operations-reference.md`. The agent-bus MCP is orchestrator-only; workers do NOT have these tools and must not install them (the doctor WARNS). |
| Headless (HTTP) — **workers, scripts, crons** | Non-orchestrator agent or any script/cron | `bash ~/.hermes-cortex/scripts/contact-moses.sh "subject" "body" [priority]` (priority: normal/urgent/critical). Reads URL + auth from `~/.hermes-cortex/cortex-bus.conf` (fallback) or env vars. **Body must be a single line** — no raw newlines (breaks the JSON payload). |
| Python lib — **any script** | From Python (crons, workers, tooling) | `from lib.cortex_bus import bus_send; bus_send("inbox_moses", {"from": "<name>", "to": "moses", "subject": "...", "body": "..."})` — same API, with fallback support. |
| Raw curl | Debugging / one-off | `curl -u "$CORTEX_BASIC_AUTH" -X POST -H "Content-Type: application/json" -d '{"queue":"inbox_moses","message":{...}}' "$CORTEX_BUS_URL/api/pgmq/send"` — see `docs/operations-reference.md` |

> **Workers:** this HTTP channel is your ONLY bus access — keep it. You are NOT
> allowed to install `agent-bus-mcp.py` (orchestrator-only). See the role
> matrix at the top of `docs/bus-architecture.md`.

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-28T19:31:38.687301+00:00

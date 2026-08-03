## Contact Protocol — How to Reach Moses

| Channel | When | How |
|---------|------|-----|
| In-session (MCP) — **orchestrators only** | Have the agent-bus MCP tools loaded (Moses, Esther) | `inbox_send(to="moses", subject=..., body=...)` — see `docs/operations-reference.md`. The agent-bus MCP is orchestrator-only; workers do NOT have these tools. |
| Headless (HTTP) — **workers, scripts, crons** | Non-orchestrator agent or any script/cron | `bash ~/.hermes/scripts/contact-moses.sh "subject" "body" [priority]` (priority: normal/urgent/critical). Reads URL + auth from `~/.hermes-cortex/cortex-bus.conf`. |
| Python lib — **any script** | From Python (crons, workers, tooling) | `from lib.cortex_bus import bus_send; bus_send("inbox_moses", {"from": "<name>", "to": "moses", "subject": "...", "body": "..."})` — same API, with fallback support. |
| Raw curl | Debugging / one-off | `curl -u "$CORTEX_BASIC_AUTH" -X POST -H "Content-Type: application/json" -d '{"queue":"inbox_moses","message":{...}}' "$CORTEX_BUS_URL/api/pgmq/send"` — see `docs/operations-reference.md` |

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-28T19:31:38.687301+00:00

# MCP Servers for Loop Governance & Agent Inbox

Two MCP servers expose loop governance and agent inbox functionality as
structured tools. Both are written in Python using the `mcp` SDK (v1.26+).

## Registration

Both servers are pre-installed in `~/hermes-cortex/runtime/mcp-servers/`.
Register with Hermes:

```bash
hermes mcp add loop-governance --command python3 --args src/mcp-servers/loop-gov-mcp.py
hermes mcp add agent-inbox --command python3 --args src/mcp-servers/inbox-mcp.py
```

The `--args` flag MUST be the LAST option. Accept all tools when prompted.

## Loop Governance MCP (7 tools)

### `cycle_query`
Query scored cycles from the loop governance DB.

Arguments:
- `task_id` (str, optional) — Filter by task name (partial match)
- `min_score` (number, optional) — Minimum composite score
- `max_score` (number, optional) — Maximum composite score
- `limit` (int, default 10) — Max results
- `unreviewed` (bool) — Only cycles needing feedback

### `cycle_stats`
Summary statistics for the loop governance DB.

Arguments:
- `days` (int, default 30) — Lookback window

### `config_show`
Show current thresholds and weights from the runtime config file.

### `config_set`
Modify a threshold or weight. Safety bounds enforced:
- Max delta per change: 1.0
- Value range: 0–10

Arguments:
- `key` (str, required) — Dot-separated path like `thresholds.stop` or `weights.completeness`
- `value` (number, required) — New value

### `feedback_accept`
Mark a scored cycle's decision as correct (user_overrode=0).

Arguments:
- `cycle_id` (int, required)
- `note` (str, optional)

### `feedback_override`
Mark a scored cycle's decision as wrong (user_overrode=1).

Arguments:
- `cycle_id` (int, required)
- `correct_decision` (enum: STOP, LOOP, MOVE_ON, required)
- `note` (str, optional)

### `cache_search`
Search the session embedding cache for similar content.

Arguments:
- `query` (str, required) — Text to search for
- `top_k` (int, default 5) — Number of results

## Agent Inbox MCP (3 tools)

### `inbox_send`
Send a message to the agent inbox. Default `to=moses`, auto-CC `luke`.

Arguments:
- `subject` (str, required)
- `body` (str, required)
- `to` (str, default "moses") — Recipient or "all"
- `topic` (str, default "general")
- `priority` (enum: normal, urgent, critical)

### `inbox_read`
Read recent inbox messages, filtered by agent.

Arguments:
- `for_agent` (str) — Filter by recipient (checks to/cc fields)
- `topic` (str) — Filter by topic
- `limit` (int, default 10)
- `unread_only` (bool)

### `inbox_watch`
Poll the inbox directory for new messages addressed to this agent.

Arguments:
- `agent` (str, default auto-detect) — Agent name to check
- `since_id` (str) — Only messages newer than this filename

## Architecture Notes

- Both servers use stdio transport (communicate via stdin/stdout).
- The `--args` flag in `hermes mcp add` must be the LAST option.
- Tools appear in the agent's toolset on the NEXT session start (not current).
- The MCP SDK `asyncio.run(main())` pattern is required for the stdio transport.
- Both servers are registered in `~/.hermes/config.yaml` under `mcp_servers:`.

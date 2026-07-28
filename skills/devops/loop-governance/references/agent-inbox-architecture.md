# Agent Inbox Architecture

## Three-Repo Separation

| Repo | Purpose | Access |
|------|---------|--------|
| `hermes-cortex` (public) | Code, skills, docs | Everyone (public) |
| `private-data` (local) | Luke's + Amy's personal data | Luke + Amy only |

## Message Addressing (Legacy — File-Based Inbox)

The file-based `agent-inbox-private` (legacy, removed) repo has been replaced by the **Agent Bus (PGMQ)**. All agent-to-agent messages now flow through Postgres-backed queues via MCP tools (`inbox_send`, `inbox_read`, `inbox_watch`). The information below documents the legacy system for reference only.

## Message Addressing

Every message has `to` (primary recipients) and `cc` (carbon copy) fields.
The default `to` is `moses` — unknown senders route to the orchestrator.

| Scenario | `to` | `cc` | Who sees it |
|----------|------|------|-------------|
| Direct to Moses | `moses` (default) | `luke` (auto) | Moses + Luke |
| Public broadcast | `all` | `luke` (auto) | Everyone |
| Agent-to-agent | `titus` | `luke` (auto) | Titus + Luke |
| CC Moses too | `titus` | `luke, moses` | Titus + Luke + Moses |
| Skill-miner findings | `moses` (implied) | `luke` (auto) | Moses + Luke |

**Auto-CC rule:** Every message automatically includes `luke` in the CC field.
This is enforced server-side in `_write_message()` — the sender does not need
to specify it.

**Filtering:** `/api/inbox?for=agent` returns messages where:
- `to` is `all` (public), OR
- `to` includes the agent name, OR
- `cc` includes the agent name
Messages the agent sent or already read are excluded.

## Setup (Legacy — for reference only)

The file-based `agent-inbox-private` (legacy, removed) repo is no longer used. New agents should use the Agent Bus (PGMQ) instead:
- MCP tools: `inbox_send`, `inbox_read`, `inbox_watch`, `inbox_send_task`
- Backend: Postgres via gbrain database
- Setup: see `agent-bus` skill

## Storage (Legacy — File-Based)

The file-based inbox stored messages as markdown files with YAML frontmatter in `~/agent-inbox-private/inbox/`. This has been replaced by the Agent Bus (PGMQ) — Postgres-native message queues. No filesystem storage is used for the current inbox system.

## Sending Messages

### From agents (JSON API)
```bash
curl -sk -X POST http://localhost:8903/api/send \
  -H "Content-Type: application/json" \
  -d '{"from":"gisu","to":"moses","subject":"Status","body":"All nominal"}'
```

### From agents (MCP tool)
```python
inbox_send(subject="Status", body="All nominal", to="moses")
```

### From web UI (form)
Uses `POST /send` with form-encoded fields (from, to, cc, subject, body, topic).

### From skill-miner (auto)
The skill-miner defaults to `to=moses` (server-side default) with `topic=moses`.
No explicit `to` field needed — the server adds it automatically.

## MCP Servers

Two MCP servers interact with the inbox:

| Server | Tools | Purpose |
|--------|-------|---------|
| `agent-inbox` | `inbox_send`, `inbox_read`, `inbox_watch` | Read/send/watch the agent inbox |
| `loop-governance` | `cycle_query`, `cycle_stats`, `config_show`, `config_set`, `feedback_accept`, `feedback_override`, `cache_search` | Query DB, manage config, label cycles, search cache |

Register:
```bash
hermes mcp add agent-inbox --command python3 --args src/mcp-servers/inbox-mcp.py
hermes mcp add loop-governance --command python3 --args src/mcp-servers/loop-gov-mcp.py
```
## Cross-Machine Flow (Legacy)

This flow describes the old file-based inbox. The current system uses the Agent Bus (PGMQ) instead — MCP tools route through nginx to Postgres, eliminating file storage and git dependencies.

## Pitfalls (Legacy — File-Based Inbox)

1. **`to` defaults to `moses`, not `all`** — unknown senders route to the
   orchestrator. Use `to=all` explicitly to broadcast.
2. **Auto-CC is not visible in the compose form** — `luke` is always added
   server-side. The sender does not see it in their own message view.
3. **Topic vs `to`** — `topic` is for UI organization (general, development,
   moses, operations). `to` is for addressing. An agent's filtered inbox
   (`?for=agent`) checks `to` and `cc`, not `topic`.
4. **Thread replies** — reply messages inherit parent's `to` and `cc` from
   the thread metadata, not the parent message body.

> **The file-based inbox is legacy.** Current agent-to-agent messaging uses the Agent Bus (PGMQ). See `agent-bus` skill for the active system.

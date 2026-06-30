# Agent Inbox Setup — MCP-Based Messaging

The agent inbox allows cross-agent messaging. Messages are stored on the inbox
backend server and each agent polls for new messages using MCP tools.

## Architecture

```
Agent A (sends)              Agent B (polls)
       │                           │
       │  MCP tool: inbox_send     │  MCP tool: inbox_watch
       ▼                           ▼
┌─────────────────┐     ┌─────────────────┐
│   Inbox HTTP    │◄────│   Inbox MCP     │
│   Backend       │────►│   Server (local)│
│   (port 8903)   │     └─────────────────┘
└────────┬────────┘
         │ HTTPS via nginx (port 13004)
         │ Basic Auth
         ▼
   Remote agents poll
   via their local MCP
   server → inbox_watch
```

## Setup (for each agent)

Each agent running on a remote machine needs three things:

### 1. Inbox MCP Server in `~/.hermes/config.yaml`

The inbox MCP server must be enabled so the agent can call `inbox_watch`,
`inbox_read`, and `inbox_send` tools:

```yaml
agent-inbox:
  command: python3
  args:
    - ~/hermes-cortex/src/mcp-servers/inbox-mcp.py
  enabled: true
```

Verify it's registered:
```bash
hermes mcp list | grep agent-inbox
```

### 2. Auth Config at `~/.hermes/moses-inbox.conf`

```bash
cat > ~/.hermes/moses-inbox.conf << 'EOF'
MOSES_INBOX_URL="https://your-domain.com:13004"
MOSES_INBOX_AUTH="your-agent-name:your-password"
AGENT_NAME="your-agent-name"
EOF
chmod 600 ~/.hermes/moses-inbox.conf
```

Replace `your-agent-name` and `your-password` with credentials from Luke.

Test it:
```bash
# From the inbox MCP server's URL chain, the local backend is always
# reachable at http://127.0.0.1:8903 as last resort.
# Remote agents use https://your-domain.com:13004 with auth.
curl -sk -u "your-agent-name:your-password" \
  https://your-domain.com:13004/api/inbox?unread_only=true
```

### 3. Poll Cron (LLM-Driven)

The agent needs a cron job that regularly checks for new messages. Create it
once on the agent's machine:

```bash
hermes cron create --name process-mcp-agent-inbox-messages \
  --model "deepseek/deepseek-v4-flash" \
  --provider "openrouter" \
  --schedule "0 6-23 * * *" \
  --prompt "Check the agent inbox for new messages via inbox-watch MCP tool (mcp_agent_inbox_inbox_watch). If new messages are found, read (mcp_agent_inbox_inbox_read) and process using the Inbox Message Decision Framework: assess Priority/Actionability/Scope, then AUTO-ACT, DELEGATE, or ESCALATE. Report actionable items with evidence. Outside 6am-11pm daily, be silent if nothing urgent." \
  --deliver origin
```

This runs hourly 6am-11pm, uses the `inbox_watch` MCP tool, and delivers
results back to the agent's origin chat (Telegram DM).

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `inbox_watch` returns "Read failed (HTTP 401)" | Wrong auth in `moses-inbox.conf` | Check `MOSES_INBOX_AUTH` value |
| `inbox_watch` returns "Connection refused" | Inbox MCP server not running | Check `~/.hermes/config.yaml` for `agent-inbox` entry |
| No new messages found | Agent polling with wrong `AGENT_NAME` | Check `AGENT_NAME` in `moses-inbox.conf` matches the `to:` field of sent messages |
|| Old `agent-inbox-check.sh` not working | Script deprecated, MCP-only now | Remove old cron, create `process-mcp-agent-inbox-messages` cron instead |
| Messages addressed to `all` topic not seen | Agent reads only its own inbox | Orchestrator (moses) reads all; regular agents only see their own messages |

## Migration from Old Script-Based Inbox

If you were using the deprecated `agent-inbox-check.sh`:

```bash
# 1. Remove old cron
hermes cron remove --name agent-inbox-watchdog 2>/dev/null

# 2. Follow the 3-step setup above

# 3. Verify new cron works
hermes cron run --name process-mcp-agent-inbox-messages
```

# Agent Inbox Setup — MCP-Based Messaging + A2A Cross-Server Tasks

The agent inbox is a **single unified service** that handles both:
1. **Agent-to-agent messaging** (topic channels, threads, priority) via `inbox_send` / `inbox_read`
2. **A2A cross-server task delegation** (JSON-RPC task lifecycle) via `inbox_send_task` / `inbox_get_task`

Both use the **same backend server** (port 8903), the **same MCP server** (`inbox-mcp.py`), and the **same message store** (`~/hermes-cortex-private/messages/inbox/`).

---

## Architecture

```
┌──────────────────────────────────────────────┐
│        Agent Inbox Server (:8903)             │
│                                              │
│  /api/inbox/*   — REST (agent messages)      │
│  /a2a/*         — JSON-RPC (A2A tasks)       │
│  /a2a/agent-card— Agent card (discovery)     │
│  /.well-known/agent-card.json                │
│  /health        — health check               │
│  /              — HTML dashboard             │
│                                              │
│  Storage:                                     │
│  ├── ~/hermes-cortex-private/messages/inbox/ │
│  └── ~/.hermes-cortex/a2a/task-state.db      │
└──────────┬───────────────────────────────────┘
           │ HTTPS via nginx (port 13004)
           │ Basic Auth (all routes)
           │ mTLS optional (for A2A)
           ▼
     Remote agents via inbox_* MCP tools
```

**One port, one server, one MCP.** There is no separate A2A process.

---

## Complete Tool Reference

The `inbox-mcp.py` MCP server registers **10 tools**:

### Messaging (4 tools)

| Tool | Purpose | Key params |
|------|---------|------------|
| `inbox_send` | Send a message to another agent | `subject`, `body`, `to`, `topic`, `priority` |
| `inbox_read` | Read recent inbox messages | `limit`, `topic`, `unread_only` |
| `inbox_watch` | Check for new messages | `limit` |
| `inbox_delete` | Delete a message (to trash/) | `filename` |

### A2A Bridge (6 tools)

| Tool | Purpose | Key params |
|------|---------|------------|
| `inbox_list_agents` | List all known agents with URLs & roles | _(none)_ |
| `inbox_get_agent` | Get details for a specific agent | `name` |
| `inbox_discover` | Fetch a remote agent's Agent Card | `agent` |
| `inbox_send_task` | Submit a task to a remote agent | `agent`, `description`, `priority` |
| `inbox_get_task` | Poll task status on a remote agent | `agent`, `task_id` |
| `inbox_cancel_task` | Cancel a pending task | `agent`, `task_id` |

---

## Setup Overview — Are You a Server or a Client?

The inbox has two roles. **Most agents only need the client setup.**

| You are a... | If... | You need... |
|-------------|------|------------|
| **Server agent** | Your machine runs the inbox server process (port 8903) — typically Moses or Esther (backup) | Full server setup: MCP config + auth + server.py + nginx |
| **Client agent** | You connect to an existing inbox server — typically Titus, Gisu, Joseph, Kustos, or any new agent | **Only** MCP config + auth config (no server.py, no nginx) |

> ⚠️ **If in doubt, you're a client. Only Moses and Esther run the inbox server.**

---

## 1. Universal Setup (ALL agents — server AND client)

Every agent needs these two things to communicate via the inbox:

### 1a. MCP Server Config in `~/.hermes/config.yaml`

```yaml
agent-inbox:
  command: python3
  args:
    - ~/hermes-cortex/src/mcp-servers/inbox-mcp.py
  enabled: true
```

Verify:
```bash
hermes mcp list | grep agent-inbox
# → agent-inbox  python3 ...  all  ✓ enabled
```

If you previously had a separate `a2a-bridge` MCP server enabled, disable it:
```bash
# Edit ~/.hermes/config.yaml and set:
# a2a-bridge:
#   enabled: false  # DEPRECATED — merged into inbox-mcp
```

### 1b. Auth Config at `~/hermes-cortex/.env`

```bash
# Primary config: ~/hermes-cortex/.env (all env vars, single source of truth)
cat >> ~/hermes-cortex/.env << 'EOF'
CORTEX_INBOX_URL="https://your-domain.com:13004"
CORTEX_INBOX_AUTH="your-agent-name:your-password"
AGENT_NAME="your-agent-name"
EOF
chmod 600 ~/hermes-cortex/.env
```

> **Legacy fallback:** `~/.hermes/hermes-inbox.conf` still works if you prefer
> a separate file. Scripts check `.env` first, then fall back to `hermes-inbox.conf`.

Replace `your-agent-name` and `your-password` with credentials from Luke.

**Auth is shared** — the same `CORTEX_INBOX_AUTH` is used for:
- Reading/sending inbox messages (`inbox_read`, `inbox_send`)
- A2A cross-server task delegation (`inbox_send_task`, `inbox_get_task`)
- Fetching agent cards (`inbox_discover`)

Test it:
```bash
curl -sk -u "your-agent-name:your-password" \
  https://your-domain.com:13004/api/inbox?unread_only=true
```

**That's it for client agents.** If you're a client, stop here — you're done. The MCP tools connect to the remote server automatically via `CORTEX_INBOX_URL`. You do NOT need to run `server.py` or install nginx.

> ✅ **Client agents:** Just the MCP config + auth config above. No server, no systemd, no nginx.

---

## 2. Server-Only Setup (Moses / Esther / backup machines only)

Only run this if you are a **designated server machine** that hosts the inbox backend. Skip this section entirely for client-only agents.

### 2a. Deploy server.py

`cortex-update.sh` copies `src/agent-inbox/server.py` to `~/.hermes/agent-inbox/server.py`. Run:

```bash
bash ~/hermes-cortex/src/scripts/cortex-update.sh --force-all
```

### 2b. Run the server

**Linux (systemd):**
```bash
sudo systemctl enable --now hermes-agent-inbox
```

**macOS (launchd):**
```bash
launchctl load ~/Library/LaunchAgents/com.hermes.agent-inbox.plist
```

**Manual (for testing):**
```bash
cd ~/.hermes/agent-inbox
python3 -m uvicorn server:app --host 127.0.0.1 --port 8903
```

### 2c. Nginx config (Linux only)

Ensure the nginx site config at `/etc/nginx/sites-enabled/hermes-services.conf` proxies port 13004 to `agent_inbox_backend` (127.0.0.1:8903). Reload after any changes:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 2d. A2A Agent Registry

Keep `~/.hermes-cortex/a2a/agent-registry.json` on Moses' server up to date with all fleet agents so cross-server discovery works.

---

## A2A Cross-Server Flow (End-to-End)

### How It Works

When Agent A (e.g. Esther) on server A wants to delegate a task to Agent B (e.g. Moses) on server B:

```
Esther's Server                         Moses' Server
─────────────────                       ─────────────
1. inbox_discover(agent="moses")
   → GET https://your-domain.com:13004/.well-known/agent-card.json
   ← Returns Moses' capabilities (12 skills)

2. inbox_send_task(agent="moses",
     description="Check disk space")
   → POST https://your-domain.com:13004/a2a/task
     (with basic auth from hermes-inbox.conf)
   ← {id: "a2a-xxx", state: "submitted"}

3. [Moses' inbox cron picks up the task]        Moses' server creates:
                                                ├── inbox message with task-id in YAML frontmatter
                                                └── SQLite task row (state: submitted)

4. inbox_get_task(agent="moses", task_id="a2a-xxx")
   → GET https://your-domain.com:13004/a2a/task/a2a-xxx
   ← {state: "completed", artifacts: [{text: "Disk: 64G free"}]}
```

### Auth Flow for Cross-Server Requests

```
MCP server (Esther)                  nginx (Moses)                  Inbox Server (:8903)
───────────────────                  ─────────────                  ──────────────────
       │                                   │                              │
       │  POST /a2a/task                    │                              │
       │  Authorization: Basic <creds>      │                              │
       │─────────────────────────────────────→                              │
       │                                   │  Verify auth                  │
       │                                   │  ✓ agent:****                │
       │                                   │──────────────────────────────→│
       │                                   │                              │  Write inbox msg
       │                                   │                              │  Create task row
       │                                   │←──────────────────────────────│
       │←─────────────────────────────────────                              │
```

- All A2A endpoints go through nginx on port 13004, which requires Basic Auth
- The MCP server reads `CORTEX_INBOX_AUTH` from `hermes-inbox.conf` and includes it in every cross-server request
- mTLS client certs are also loaded if present (optional, for additional security)

---

## A2A Task Lifecycle

| State | Meaning | Who transitions |
|-------|---------|-----------------|
| `submitted` | Task created, waiting for agent | A2A endpoint (on task creation) |
| `working` | Agent picked up the task | `_mark_task_working()` (inbox processor) |
| `completed` | Task finished successfully | `_mark_task_completed(id, result)` |
| `failed` | Task ended with error | `_mark_task_failed(id, error)` |
| `canceled` | Task cancelled by requester | A2A cancel endpoint |
| `rejected` | Agent declined the task | `_mark_task_failed(id, "rejected")` |

State transitions on the server side happen via the Python functions in `server.py`:

```python
from server import _mark_task_working, _mark_task_completed

_mark_task_working("a2a-xxx")           # Agent picks it up
_mark_task_completed("a2a-xxx", result)  # Agent finishes
_mark_task_failed("a2a-xxx", error)      # Agent fails
```

These are typically called by the inbox processor cron when it detects an agent has read/replied to an A2A task message.

---

## Poll Cron (for inbox messages, not A2A)

For regular agent inbox polling (not A2A — A2A tasks are polled explicitly by the requesting agent):

```bash
hermes cron create --name process-mcp-agent-inbox-messages \
  --model "deepseek/deepseek-v4-flash" \
  --provider "openrouter" \
  --schedule "0 6-23 * * *" \
  --prompt "Check the agent inbox for new messages via inbox-watch MCP tool (mcp_agent_inbox_inbox_watch). If new messages are found, read (mcp_agent_inbox_inbox_read) and process using the Inbox Message Decision Framework: assess Priority/Actionability/Scope, then AUTO-ACT, DELEGATE, or ESCALATE. Report actionable items with evidence. Outside 6am-11pm daily, be silent if nothing urgent." \
  --deliver origin
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `inbox_watch` returns HTTP 401 | Wrong auth in `hermes-inbox.conf` | Check `CORTEX_INBOX_AUTH` value |
| `inbox_send_task` returns HTTP 401 | A2A cross-server request missing auth | Check `CORTEX_INBOX_AUTH` is set (A2A reuses same creds) |
| Agent card returns 404 | `.well-known/agent-card.json` route missing | Ensure server.py has the agent card routes (merged since 2026-07-05) |
| `inbox_watch` connection refused | MCP server not registered | Check `~/.hermes/config.yaml` for `agent-inbox` entry |
| A2A task stuck in `submitted` | No inbox processor marking it `working` | Agent needs to read the A2A inbox message, or manually call `_mark_task_working()` |
| Messages to `all` not seen | Agent reads only own inbox | Orchestrator (moses) sees all; regular agents only see messages addressed to them |
| Old `agent-inbox-check.sh` not working | Script deprecated, MCP-only now | Remove old cron, create `process-mcp-agent-inbox-messages` cron instead |

---

## Migration from Old Architecture

If upgrading from the standalone A2A server (pre-2026-07-05):

1. **Stop old A2A server** — `kill $(lsof -t -i:8906)`
2. **Remove old systemd service** — `sudo systemctl disable --now a2a-server; sudo rm /etc/systemd/system/a2a-server.service`
3. **Update inbox server.py** — `cp src/agent-inbox/server.py ~/.hermes/agent-inbox/server.py`
4. **Update inbox-mcp.py** — `cp src/mcp-servers/inbox-mcp.py ~/.hermes-cortex/scripts/inbox-mcp.py`
5. **Disable old a2a-bridge MCP** — set `enabled: false` in `~/.hermes/config.yaml`
6. **Restart inbox server** — `kill <pid>; cd ~/.hermes/agent-inbox && python3 -m uvicorn server:app --host 127.0.0.1 --port 8903`
7. **All A2A tools are now `inbox_*`** — use `inbox_list_agents`, `inbox_send_task`, etc. via the same MCP server

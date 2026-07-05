# A2A Agent-to-Agent Architecture

## Overview

The A2A architecture enables Hermes Cortex agents on **different servers** to discover each other, delegate tasks, and share results using the industry-standard [Agent2Agent Protocol v1.0](https://a2a-protocol.org) (Linux Foundation).

Rather than replacing the existing inbox system, this layers A2A **on top of it** — the inbox remains the durable message store, and A2A is the standardized HTTP envelope for cross-server delivery.

## Design Principles

| Principle | Why |
|-----------|-----|
| **Leverage existing infrastructure** | Inbox is already durable (files), proven (production), and agents know how to use it. A2A is a thin wrapper. |
| **Industry standard** | A2A v1.0 under Linux Foundation — 150+ orgs. Interoperable with non-Hermes agents. |
| **Zero third-party dependencies** | Self-hosted end-to-end. No broker, no cloud service. |
| **Private by default** | mTLS + IP allowlist. No agent topology leaked to DNS or third parties. |
| **Async-first** | Task state machine survives server restarts. No polling required. |

## Architecture

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│  Moses' Server                       │     │  Esther's Server                   │
│  bus.example.org:13004         │     │  esther.internal:13004             │
│                                     │     │                                    │
│  Hermes Agent                       │     │  Hermes Agent                      │
│    │                                │     │    │                               │
│    ├── MCP: agent-inbox             │     │    ├── MCP: agent-inbox            │
│    │     (local messages)           │     │    │     (local messages)          │
│    │                                │     │    │                               │
│    ├── MCP: a2a-bridge         ◄────┼─────┼────┤ MCP: a2a-bridge               │
│    │     (discover/send/get)  │     │     │    │     (discover/send/get)        │
│    │                          │     │     │    │                               │
│    │  ┌──────────────────┐    │     │     │    │  ┌──────────────────┐          │
│    │  │ FastAPI :8903    │    │     │     │    │  │ FastAPI :8903    │          │
│    │  │  ├─ /api/inbox   │    │     │     │    │  │  ├─ /api/inbox   │          │
│    │  │  ├─ /a2a/*       │◄───┘     │     │    │  │  ├─ /a2a/*       │◄─────────┘
│    │  │  └─ /health      │          │     │    │  │  └─ /health      │           │
│    │  └────────┬─────────┘          │     │    │  └────────┬─────────┘          │
│    │           │                    │     │    │           │                    │
│    │  nginx :13004                  │     │    │  nginx :13004                 │
│    │  ├─ /api/inbox → Basic Auth    │     │    │  ├─ /api/inbox → Basic Auth   │
│    │  ├─ /a2a/*     → Basic + mTLS  │     │    │  ├─ /a2a/*     → Basic + mTLS │
│    │  └─ /.well-known/agent-card    │     │    │  └─ /.well-known/agent-card   │
│    │           │                    │     │    │           │                    │
│    └───────────┼────────────────────┘     │    └───────────┼────────────────────┘
│               │                          │                 │
│    Storage:                              │      Storage:                        │
│    ├─ ~/hermes-cortex-private/inbox/     │      ├─ ~/hermes-cortex-private/inbox/
│    └─ ~/.hermes-cortex/a2a/             │      └─ ~/.hermes-cortex/a2a/
│       ├─ agent-registry.json            │         ├─ agent-registry.json
│       ├─ agent-card.json                │         ├─ agent-card.json
│       └─ task-state.db (SQLite)         │         └─ task-state.db (SQLite)
└─────────────────────────────────────────┘     └─────────────────────────────────────────┘
```

## Components

### 1. Agent Card (`src/a2a/agent-card.json`)

An A2A-standard JSON document declaring the agent's identity, capabilities, and skills.

**Schema (A2A v1.0):**
```json
{
  "name": "moses",
  "description": "Orchestrator agent — infrastructure, cron management, system health",
  "url": "https://bus.example.org:13004/a2a",
  "provider": { "name": "Hermes Cortex", "version": "1.0" },
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "stateTransitionHistory": true
  },
  "skills": [
    { "id": "cron.management", "name": "Cron Management", "description": "..." },
    { "id": "system.health", "name": "System Health", "description": "..." },
    { "id": "inbox.messaging", "name": "Inbox Messaging", "description": "..." }
  ],
  "authentication": { "type": "mTLS", "verify": "required" }
}
```

**Generation:** Automated from SOUL.md (role description) + `skills_list()` (available skills) + cron list (scheduled capabilities). Static JSON as fallback.

**Served at:**
- `/.well-known/agent-card.json` — public, unauthenticated, read-only
- `/a2a/agent-card` — authenticated, same data

### 2. Agent Registry (`~/.hermes-cortex/a2a/agent-registry.json`)

Static JSON deployed by `cortex-update.sh` to every agent server. Maps agent names → server URLs.

```json
{
  "version": 1,
  "agents": {
    "moses": {
      "name": "Moses",
      "role": "orchestrator",
      "url": "https://bus.example.org:13004",
      "auth_type": "mTLS",
      "agent_card_url": "https://bus.example.org:13004/.well-known/agent-card.json"
    },
    "esther": {
      "name": "Esther",
      "role": "manager",
      "url": "https://esther.internal:13004",
      "auth_type": "mTLS",
      "agent_card_url": "https://esther.internal:13004/.well-known/agent-card.json"
    }
  }
}
```

**Template** at `src/a2a/agent-registry.template.json` (already in repo from PII scrub). Real file is outside the repo.

### 3. A2A Server Extension (extend `src/agent-inbox/server.py`)

New routes on the existing FastAPI inbox server implementing JSON-RPC 2.0 over HTTP.

| JSON-RPC Method | HTTP Route | Purpose |
|---|---|---|
| `tasks/send` | `POST /a2a/task` | Submit a task to this agent |
| `tasks/get` | `GET /a2a/task/{id}` | Poll task status |
| `tasks/cancel` | `POST /a2a/task/{id}/cancel` | Cancel a running task |

**Data Flow — Task Submission:**

```
Remote Agent                    Our Server
    │                               │
    ├── HTTPS POST /a2a/task ──────►│
    │   {jsonrpc:"2.0",              │
    │    method:"tasks/send",        │
    │    params:{                    │
    │      id:"uuid-task-123",       │
    │      sessionId:"sess-1",       │
    │      task:{                    │
    │        state:"submitted",      │
    │        messages:[{             │
    │          role:"user",          │
    │          parts:[{              │
    │            type:"text",        │
    │            text:"Deploy v2.1"  │
    │          }]                    │
    │        }]                      │
    │      }                         │
    │    }}                           │
    │                               │
    │  1. mTLS validation           │
    │  2. IP whitelist check        │
    │  3. Agent Card capability     │
    │     validation                │
    │  4. Create SQLite row:        │
    │     task_id, state=submitted  │
    │  5. WRITE TO INBOX:           │
    │     ~/.../inbox/              │
    │      esther-task-uuid.md      │
    │     (same inbox format)       │
    │                               │
    ├── 200 OK ◄────────────────────┤
    │   {id:"uuid-task-123",        │
    │    result:{state:"submitted"}}│
```

**Key design:** The A2A endpoint writes to the **same inbox filesystem** as local messages. The target agent discovers it via `inbox_watch` — no new polling loop.

### 4. A2A Bridge MCP Server (`src/mcp-servers/a2a-mcp.py`)

New MCP server providing tools that Hermes agents use to interact with remote agents.

| MCP Tool | What It Does |
|---|---|
| `a2a_discover(agent_name)` | Fetch a remote agent's Agent Card |
| `a2a_send_task(agent, description)` | Submit a task to a remote agent |
| `a2a_get_task(task_id)` | Poll task status on origin server |
| `a2a_cancel_task(task_id)` | Cancel a pending task |
| `a2a_list_agents()` | List all known agents from registry |

**Agent UX:**
```
# Moses delegates to Esther on another server:
task_id = a2a_send_task("esther", "Check disk usage on server B")
# → "task-abc-123 submitted to Esther"

# Later:
status = a2a_get_task(task_id)
# → {"state": "completed", "result": "/dev/sda1: 45% used"}
```

### 5. Task State DB (`~/.hermes-cortex/a2a/task-state.db`)

SQLite database tracking task lifecycle.

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,              -- "task-<server>-<uuid>"
    source_agent TEXT NOT NULL,        -- who sent it
    target_agent TEXT NOT NULL,        -- who should handle it
    state TEXT NOT NULL DEFAULT 'submitted',
        -- submitted → working → completed | failed | canceled
    description TEXT,
    inbox_message_filename TEXT,       -- link to the inbox file
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    result_summary TEXT,
    error TEXT
);
```

**State transitions:**
```
submitted ──→ working ──→ completed
    │            │
    │            └──→ failed
    │
    └──→ canceled
```

**State detection** is passive — the A2A server observes inbox file changes:
- Inbox file created → `submitted`
- Target agent reads it (inbox_watch) → `working`
- Reply sent by target → `completed`
- Error reply → `failed`

### 6. mTLS Security Layer

Implemented at nginx level — no application code changes needed per-server.

```nginx
# Server block for A2A endpoint
location /a2a/ {
    # Layer 1: Mutual TLS
    ssl_verify_client on;
    ssl_client_certificate /etc/nginx/hermes-ca.crt;

    # Layer 2: IP allowlist
    allow 10.0.0.0/8;    # private subnet
    allow 192.168.0.0/16;
    deny all;

    # Layer 3: Rate limiting
    limit_req zone=a2a burst=20 nodelay;

    proxy_pass http://agent_inbox_backend;
}
```

**Certificate lifecycle:**
```
1. One CA key pair:  hermes-ca.crt + hermes-ca.key
2. Each server gets its own client cert signed by the CA:
     CN = moses.bus.example.org
     CN = esther.internal
3. Every nginx trusts the CA cert for client verification
4. Revocation: serial-based CRL distributed via cortex-update.sh
```

---

## Implementation Plan

### Slice 0 — Security Hardening ✅ DONE
- `chmod 600 /etc/nginx/.hermes-htpasswd`
- `chmod 700 ~/hermes-cortex-private/messages/inbox/`
- Add `client_max_body_size 10M` to inbox nginx block
- Clean: `src/agent-registry.template.json` exists, PII scrubbed

### Slice 1 — Agent Card ✅ DONE (2 hours)

**Files created:**
- `src/a2a/agent-card.json` — static card for this server
- `src/a2a/generate-agent-card.py` — script to regenerate from template

**Config changes:**
- nginx template: `location = /.well-known/agent-card.json` → public
- nginx template: `location /a2a/agent-card` → authenticated
- `__CORTEX_HOME__` placeholder substitution in cortex-update.sh

**Cron:**
- `agent-card-daily` (6am daily, no_agent, writes to ~/.hermes-cortex/a2a/agent-card.json)

**Dependencies:** None

### Slice 2 — Agent Registry ✅ DONE (30 min)

**Files created:**
- `src/mcp-servers/a2a-mcp.py` — MCP server with a2a_list_agents, a2a_get_agent

**Config changes:**
- Registered in ~/.hermes/config.yaml as MCP server (venv Python)
- Registered in cortex-update.sh MAP

**Dependencies:** Slice 1

### Slice 3 — A2A Server ✅ DONE (1 day)

**Files created:**
- `src/a2a/a2a-server.py` — standalone FastAPI app on port 8906

**Routes:**
- `POST /a2a/task` — receive task, create inbox msg, return task ID
- `GET /a2a/task/{id}` — return current task state with artifacts
- `POST /a2a/task/{id}/cancel` — cancel pending task
- `GET /health` — health check

**Integration:**
- Systemd service template at `docs/templates/a2a-server.service`
- SQLite task state DB at `~/.hermes-cortex/a2a/task-state.db`
- Inbox integration: writes to existing inbox filesystem

**Dependencies:** Slice 0 (mTLS certs), Slice 1 (Agent Card for capability validation)

### Slice 4 — A2A Bridge MCP ✅ DONE (4 hours)

**Files created:**
- `src/mcp-servers/a2a-mcp.py` (expanded from 2 → 6 tools)

**MCP Tools:**
- `a2a_discover(agent_name)` — GET Agent Card from registry URL
- `a2a_send_task(agent, description, priority)` — POST to remote A2A endpoint
- `a2a_get_task(agent, task_id)` — GET task status
- `a2a_cancel_task(agent, task_id)` — POST cancel
- `a2a_list_agents()` — read local registry
- `a2a_get_agent(name)` — detailed agent info

**Config:**
- Registered in ~/.hermes/config.yaml (venv Python)
- mTLS client cert loaded for outbound requests

**Dependencies:** Slice 3 (remote A2A server must exist to test against)

### Slice 5 — nginx A2A Block ✅ DONE (1 hour)

**Template changes:**
- `upstream a2a_backend` → 127.0.0.1:8906
- `location /a2a/` → proxy to a2a_backend
- Rate limiting applied (burst=40)

**Live deploy requires sudo — see docs/a2a-deploy-notes.md**

**Dependencies:** Slice 0 (CA certs exist for mTLS in cross-server setup)

### Slice 6 — Integration + E2E (remaining)

**Still needed:**
- Skills created for agents to use A2A tools
- `AGENTS.md` updated with A2A protocol summary
- E2E test when a second agent server is available

---

## Security Model (Defense in Depth)

| Layer | Mechanism | Stops |
|-------|-----------|-------|
| **Transport** | TLS 1.3 (LetsEncrypt) | Eavesdropping |
| **Identity** | mTLS (Hermes CA) | Impersonation |
| **Network** | IP allowlist | Unauthorized origins |
| **Rate** | nginx limit_req + fail2ban | Brute force / DDoS |
| **Auth** | Basic Auth (existing) | Plus layer for backward compat |
| **Application** | Capability validation | Irrelevant tasks |

## Migration Path

Existing agents on the same server continue to use the inbox as before — unaffected. The A2A layer only activates when an agent sends a task to a **remote** server. No existing workflows break.

For a new agent server joining the fleet:
1. Install hermes-cortex
2. Generate client cert from CA
3. Run `setup-agent-registry.sh` with their URLs
4. Copy CA cert to nginx
5. Add their IP to other servers' allowlists
6. Each server learns about the new one via git-pushed registry

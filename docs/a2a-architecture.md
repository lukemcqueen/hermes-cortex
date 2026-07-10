# A2A Agent-to-Agent Architecture

> **⚠️ DESIGN UPDATE (2026-07-05):** A2A is now fully merged into the Agent Inbox.
> There is ONE backend server on `:8903`, ONE MCP server (`inbox-mcp`), and ONE message store.
> The old standalone `a2a-server.py` (port 8906) and `a2a-mcp.py` are archived.

## Overview

The A2A protocol enables Hermes Cortex agents on **different servers** to discover each other, delegate tasks, and share results using the industry-standard [Agent2Agent Protocol v1.0](https://a2a-protocol.org) (Linux Foundation).

A2A is a **protocol layer** on top of the existing agent inbox — same message store, same API, same MCP tools. The only difference is the JSON-RPC envelope used for cross-server task delegation.

## Design Principles

| Principle | Why |
|-----------|-----|
| **ONE service** | Not two separate servers. A2A endpoints live on the inbox backend. |
| **ONE tool set** | Not two MCP servers. A2A bridge tools use the `inbox_` prefix. |
| **Leverage existing infrastructure** | Inbox is already durable (files), proven (production), and agents know how to use it. A2A is a thin wrapper. |
| **Industry standard** | A2A v1.0 under Linux Foundation — 150+ orgs. Interoperable with non-Hermes agents. |
| **Zero third-party dependencies** | Self-hosted end-to-end. No broker, no cloud service. |
| **Private by default** | mTLS + IP allowlist. No agent topology leaked to DNS or third parties. |
| **Async-first** | Task state machine (SQLite) survives server restarts. No polling required. |

## Architecture (Merged)

```
┌─────────────────────────────────────────────┐     ┌─────────────────────────────────────────────┐
│  Agent Inbox Server (:8903)                  │     │  Remote Agent Inbox Server (:8903)           │
│                                              │     │                                              │
│  FastAPI App                                 │     │  FastAPI App                                 │
│  ├── /api/inbox/*  — REST (agent messages)   │     │  ├── /api/inbox/*  — REST                   │
│  ├── /a2a/*        — JSON-RPC (task delegation)│   │  ├── /a2a/*        — JSON-RPC               │
│  ├── /health       — health check             │     │  ├── /health                               │
│  └── /             — HTML dashboard           │     │  └── /                                     │
│         │                                     │            │                                     │
│         │  nginx :13004                        │            │  nginx :13004                        │
│         │  ├── /api/inbox → Basic Auth         │            │  ├── /api/inbox → Basic Auth         │
│         │  ├── /a2a/*     → Basic + mTLS      │            │  ├── /a2a/*     → Basic + mTLS      │
│         │  └── /.well-known/agent-card         │            │  └── /.well-known/agent-card         │
│         │                                     │            │                                     │
│  Storage:                                     │     Storage:                                     │
│  ├── ~/hermes-cortex-private/messages/inbox/  │     ├── ~/hermes-cortex-private/messages/inbox/  │
│  └── ~/.hermes-cortex/a2a/                    │     └── ~/.hermes-cortex/a2a/                    │
│       ├── agent-registry.json                  │          ├── agent-registry.json                  │
│       ├── agent-card.json                     │          ├── agent-card.json                     │
│       └── task-state.db (SQLite)              │          └── task-state.db (SQLite)              │
└─────────────────────────────────────────────┘     └─────────────────────────────────────────────┘
        │                                                     │
        └────────────── HTTPS + mTLS ─────────────────────────┘
                         A2A protocol (JSON-RPC)
```

## Components

### 1. Agent Inbox Server (`src/agent-inbox/server.py`)

The single backend that serves everything:

- **`/api/inbox/*`** — REST endpoints for agent message CRUD (unchanged)
- **`/a2a/task`** — JSON-RPC endpoint for task submission (`tasks/send`)
- **`/a2a/task/{id}`** — Poll task state (`tasks/get`)
- **`/a2a/task/{id}/cancel`** — Cancel a task (`tasks/cancel`)
- **`/health`** — System health (now includes A2A task count)
- **`/`** — HTML dashboard UI (unchanged)

Runs on `127.0.0.1:8903`. Exposed externally via nginx on `:13004`.

### 2. A2A Task State Database (`~/.hermes-cortex/a2a/task-state.db`)

SQLite database tracking A2A task lifecycle:

- States: `submitted → working → completed / failed / canceled / rejected`
- Relates inbox messages to task IDs via `inbox_message_filename`
- Survives server restarts

### 3. Agent Card (`ops/services/a2a/agent-card.json`)

Static JSON file describing this agent's capabilities, published at:
- `https://domain.com:13004/.well-known/agent-card.json`
- `https://domain.com:13004/a2a/agent-card`

Agents fetch this via `inbox_discover` to learn what remote agents can do.

### 4. Agent Registry (`~/.hermes-cortex/a2a/agent-registry.json`)

Mapping of agent names → server URLs, roles, and accessibility flags.
Maintained manually or via the health monitoring system.

### 5. MCP Tools (all in `inbox-mcp.py`)

**Inbox messaging (existing):**
| Tool | Purpose |
|------|---------|
| `inbox_send` | Send a message |
| `inbox_read` | Read messages |
| `inbox_watch` | Check for new messages |
| `inbox_delete` | Delete a message |

**A2A bridge (merged, inbox_ prefix):**
| Tool | Purpose | Was called |
|------|---------|------------|
| `inbox_list_agents` | List all known agents | `a2a_list_agents` |
| `inbox_get_agent` | Get agent details | `a2a_get_agent` |
| `inbox_discover` | Fetch remote Agent Card | `a2a_discover` |
| `inbox_send_task` | Submit task to remote agent | `a2a_send_task` |
| `inbox_get_task` | Poll task status | `a2a_get_task` |
| `inbox_cancel_task` | Cancel pending task | `a2a_cancel_task` |

## Message Format (Unified)

All inbox messages (agent-to-agent AND A2A tasks) use the same YAML frontmatter format:

```yaml
---
from: moses
to: esther
cc: luke
subject: A2A Task: Process these logs
topic: a2a
priority: normal
thread: 20260705123456-moses
parent:
status: unread
read_by: moses
task-id: a2a-abc123def456   # ← A2A tasks have this field
---

Process the access logs and summarize errors.
```

- `task-id` is optional — only present on A2A task messages
- Topic `a2a` indicates A2A protocol traffic
- The inbox API (`/api/inbox/*`) can filter by topic

## Protocol Flow

```
Agent A                         Agent B (via inbox server :8903)
   │                                │
   │  POST /a2a/task                 │
   │  {jsonrpc, method:"tasks/send", │
   │   params:{task:{messages:[...]}}│
   │─────────────────────────────────→│
   │  {id:"a2a-xxx",                 │
   │   state:"submitted"}            │
   │←─────────────────────────────────│
   │                                │
   │  [A writes inbox message       │
   │   for B with task-id]          │
   │                                │
   │  GET /a2a/task/a2a-xxx         │
   │─────────────────────────────────→│
   │  {state:"working"}             │
   │←─────────────────────────────────│
   │                                │
   │  [B works on task...]          │
   │  [B writes result to inbox]    │
   │                                │
   │  GET /a2a/task/a2a-xxx         │
   │─────────────────────────────────→│
   │  {state:"completed",           │
   │   artifacts:[{text:...}]}      │
   │←─────────────────────────────────│
```

## Starting the Server

The inbox server is typically started via the Hermes agent-inbox script:
```bash
cd /home/moses/.hermes/agent-inbox
python3 -m uvicorn server:app --host 127.0.0.1 --port 8903
```

Or via systemd/supervisord if configured.

## Port Convention

| Port | Service | Purpose |
|------|---------|---------|
| 8903 | Inbox server | REST + A2A JSON-RPC + Dashboard UI |
| 8905 | Health server | Compact health checks |
| 13004 | nginx | External gateway for inbox + A2A |

## Migration from Standalone A2A

If you had the old standalone A2A server (port 8906):
1. Stop the old A2A server: `kill <pid>`
2. Update inbox server.py to the merged version (done in `src/agent-inbox/server.py`)
3. Update inbox-mcp.py to include A2A bridge tools (done in `src/mcp-servers/inbox-mcp.py`)
4. Disable old a2a-bridge MCP in `~/.hermes/config.yaml` (set `enabled: false`)
5. All A2A tools are now available as `inbox_*` tools via the same MCP server

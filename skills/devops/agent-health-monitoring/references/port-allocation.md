# Port Allocation — Hermes Cortex Services

Health endpoints use a **two-layer pattern**: nginx SSL termination on the
external port, health-vector process on an internal port (typically 8905)
bound to loopback only.

## Moses (orchestrator)

| Port | Service | Auth | Protocol | Layer |
|------|---------|------|----------|-------|
| 13001 | Cortex Dashboard | Basic Auth | HTTPS → nginx proxy | External |
| 13002 | Langfuse | Basic Auth | HTTPS → nginx proxy | External |
| 13003 | *(reserved)* | — | — | — |
| 13004 | Agent Inbox (MCP backend) | Basic Auth | HTTPS → nginx proxy | External |
| 13005 | *(reserved)* | — | — | — |
| 13006 | *(legacy health, migrated to 13007)* | — | — | — |
| 13007 | **Health vector (nginx SSL)** | **None** | **HTTPS → proxy to :8905** | **External** |
| 8905 | **Health vector (backend)** | **None** | **HTTP on 127.0.0.1** | **Internal (loopback)** |

## Joseph

| Port | Service | Auth | Protocol |
|------|---------|------|----------|
| 12004 | Agent Inbox | Basic Auth | HTTPS |
| 12007 | **Health vector (nginx SSL → proxy to :8905)** | **None** | **HTTPS** |

## Esther

| Port | Service | Auth | Protocol |
|------|---------|------|----------|
| 14004 | Agent Inbox | Basic Auth | HTTPS |
| 14007 | **Health vector (nginx SSL → proxy to :8905)** | **None** | **HTTPS** |

## Gisu

| Port | Service | Auth | Protocol |
|------|---------|------|----------|
| 13004 | Agent Inbox | Basic Auth | HTTPS |
| 13007 | **Health vector (nginx SSL → proxy to :8905)** | **None** | **HTTPS** |

## Kustos

| Port | Service | Auth | Protocol |
|------|---------|------|----------|
| 13004 | Agent Inbox | Basic Auth | HTTPS |
| 13007 | **Health vector (nginx SSL → proxy to :8905)** | **None** | **HTTPS** |

## Titus (macOS laptop) — no inbound

No exposed ports. Health data pushed to Moses inbox via inbox API.

## Evolution

- Previous design: health-vector bound to `0.0.0.0:<PORT>` directly (no nginx proxy).
  This caused port conflicts when nginx also needed to bind the same port for SSL.
- Current design: health-vector binds to `127.0.0.1:8905` (loopback, single port across all agents).
  nginx binds to `0.0.0.0:<EXTERNAL_PORT>` with SSL and proxies to the internal health-vector.
- Actual domain names are not listed here — see `~/.hermes/agent-registry.local.json`
  on the orchestrator for the real URLs (PII-safe pattern).
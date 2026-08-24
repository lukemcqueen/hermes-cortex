# ADR-0003: Agent Inbox v2 API Policy

- Status: accepted
- Date: 2026-08-24
- Author: Esther (verified from `~/.hermes-cortex/agent-inbox/server.py`)

## Context

The agent inbox has two generations of API surface. The legacy endpoints
(`POST /send`, `GET /read/{filename}`, `GET /delete/{filename}`) are
GET/stateful and predate the JSON convention. New agents and tools must
not learn the legacy surface — and existing callers must be migrated.

## Decision

**The v2 API is the canonical interface for the agent inbox (Agent Inbox
v2 — threaded messaging with topic channels):**

| Operation | v2 endpoint | Method |
|---|---|---|
| Send message | `/api/send` | POST (JSON body) |
| Delete/archive | `/api/delete/{filename}` | DELETE |
| Read inbox | `/api/inbox?unread_only=true` | GET (JSON) |
| Health | `/health` | GET |

- **Legacy endpoints are deprecated**: `/send` returns a warning
  ("Agents should use POST /api/send (JSON) instead"), `/read/{filename}`
  and `/delete/{filename}` exist only for backward compatibility.
- **New code targets v2 only.** The bus MCP tools (inbox_send,
  inbox_read, inbox_delete) wrap the v2 surface.
- **Auth**: the API is bearer-token gated (401 without valid token —
  verified by direct probe; the MCP server handles auth internally).

## Consequences

- **One canonical surface**: agents and tools don't need to know which
  inbox version a host runs — v2 is the contract.
- **Legacy endpoints stay until every fleet agent has migrated** — the
  `/send` warning is the migration beacon.
- **Breaking changes to v2 require a new ADR** (v3) — never a silent
  contract change.

## References

- `~/.hermes-cortex/agent-inbox/server.py` (implementation; legacy
  deprecation warnings at `/send`)
- Agent Bus MCP tools (`mcp__agent_bus__inbox_*`)

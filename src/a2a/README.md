# A2A — Agent-to-Agent Protocol for Hermes Cortex

This directory contains the A2A (Agent2Agent) v1.0 implementation.

## Contents

| Path | Purpose | Status |
|------|---------|--------|
| `agent-card.json` | Static Agent Card for this server | Not yet created (Slice 1) |
| `generate-agent-card.py` | Auto-generate Agent Card from SOUL.md + skills | Not yet created (Slice 1) |
| `agent-registry.template.json` | Template for agent server addresses | ✅ Created (PII scrub) |
| `a2a-server.py` | A2A-compliant HTTP server (JSON-RPC 2.0) | Not yet created (Slice 3) |
| `task-state-schema.sql` | SQLite schema for task state machine | Not yet created (Slice 3) |

## Architecture

See [`docs/a2a-architecture.md`](../../docs/a2a-architecture.md) for full design.

## Implementation Order

1. Agent Card (Slice 1)
2. Agent Registry MCP tool (Slice 2)
3. A2A Server (Slice 3)
4. A2A Bridge MCP (Slice 4)
5. nginx mTLS block (Slice 5)
6. Integration + E2E test (Slice 6)

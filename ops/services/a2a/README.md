# A2A — Agent-to-Agent Protocol for Hermes Cortex

This directory contains the A2A (Agent2Agent) v1.0 implementation.

## Contents

| Path | Purpose | Status |
|------|---------|--------|
| `agent-card.json` | Static Agent Card for this server (12 skills) | ✅ Done |
| `generate-agent-card.py` | no_agent generator for the Agent Card | ✅ Done |
| `a2a-server.py` | A2A-compliant HTTP server — **removed 2026-07-15** (merged into agent-bus server.py) | ❌ Removed |
| `agent-registry.template.json` | Template for agent server addresses | ✅ Done (in `src/`) |

## MCP Tools

The `a2a-bridge` MCP server (`src/mcp-servers/a2a-mcp.py`) provides 6 tools:

| Tool | What It Does |
|------|-------------|
| `a2a_list_agents` | List all known agents with URLs and roles |
| `a2a_get_agent` | Get details for a specific agent by name |
| `a2a_discover` | Fetch a remote agent's Agent Card |
| `a2a_send_task` | Submit a task to a remote agent |
| `a2a_get_task` | Poll task status on a remote agent |
| `a2a_cancel_task` | Cancel a pending task on a remote agent |

## Architecture

See [`docs/a2a-architecture.md`](../../docs/a2a-architecture.md) for full design.

## Remaining Work

- E2E test when a second agent server is available (Slice 6)

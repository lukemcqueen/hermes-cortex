# Cortex Runtime Adapter

Hermes Agent integration layer — plugins, MCP servers, hooks, and skill definitions. This layer bridges **Cortex Core** (schemas, policy, identity) with the **Hermes Agent execution runtime**.

## Contents

| Directory | Purpose | Status |
|-----------|---------|--------|
| `hermes/governance-enforcer/` | Pre-tool-call governance enforcement plugin | Populated (migrated from `plugins/governance-enforcer/`) |
| `hermes/hooks/` | Git hooks (pre-commit scoring, post-commit) | From `.hermes-cortex/hooks/` |
| `mcp-servers/` | MCP servers: inbox, loop-governance | Populated (migrated from `src/mcp-servers/`) |
|    `skills/` | Skill definitions loaded by Hermes Agent | From `skills/` |

## Design Rules

- **Runtime-agnostic interface** — The adapter layer should make it possible to swap in a different runtime (LangGraph, Temporal) without rewriting Cortex Core or Cortex Ops.
- **Thin bridge** — Minimise logic here. Policy decisions go in Core. Operational execution goes in Ops. This layer translates between them.

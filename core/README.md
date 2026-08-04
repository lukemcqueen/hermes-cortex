# Cortex Core

Canonical schemas, workflows, and policy contracts. This layer defines *what* the system knows and *how* it decides — without depending on any specific agent runtime.

## Contents

| Directory | Purpose | Status |
|-----------|---------|--------|
| `cortex_bus/` | Cortex Bus implementation — PGMQ-based queue server, auth, circuit breaker, workflow engine | Active |
| `cortex_bus/schema/` | Bus DDL (auth/queue/workflow/todos/command-verifications) | Active |
| `governance/` | Loop governance schemas (DEPRECATED — removed July 2026. Use MCP-based loop-governance tools instead) | Removed |

### cortex_bus/

| Module | Purpose |
|--------|---------|
| `server.py` | Agent Bus HTTP server — message send/read/archive/queue management over PGMQ |
| `queue.py` | PGMQ queue operations — enqueue, dequeue, archive, metrics |
| `auth.py` | Bus authentication — token validation, agent identity |
| `circuit_breaker.py` | Circuit breaker pattern for bus connections — failure tracking, state transitions |
| `workflow/` | Workflow orchestration: YAML-defined multi-step agent workflows (cross-agent-audit, fix-issue, research-then-write, etc.) |
| `workflows/` | YAML workflow definitions — 6 workflows for agent-to-agent orchestration |

## Design Rules

- **Zero runtime dependency** — Core types must not import Hermes Agent, LangGraph, or any execution runtime.
- **Pydantic-driven** — Data models use Pydantic for validation and serialization.
- **Pluggable** — Workflows, auth, and policy models define interfaces; concrete implementations live in the runtime adapter layer.

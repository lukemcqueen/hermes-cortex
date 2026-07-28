# Cortex Core

Canonical schemas, workflow state, policy, and identity contracts. This layer defines *what* the system knows and *how* it decides — without depending on any specific agent runtime.

## Contents

| Directory | Purpose | Status |
|-----------|---------|--------|
| `schemas/` | Canonical type definitions: WorkflowRun, Policy, KnowledgeRecord, Approval | Populated (KnowledgeRecord, WorkflowRun + state machine) |
|    `governance/` | Loop governance (DEPRECATED — removed July 2026. Use MCP-based loop-governance tools instead) | Removed |
| `identity/` | Agent identity contracts — workload identity, signed messages, credential model | Populated (AgentIdentity, IdentityRegistry, SignedMessage) |

## Design Rules

- **Zero runtime dependency** — Core types must not import Hermes Agent, LangGraph, or any execution runtime.
- **Pydantic-first** — All canonical schemas use Pydantic for validation and serialization.
- **Pluggable** — Policies and identity models define interfaces; concrete implementations live in the runtime adapter layer.

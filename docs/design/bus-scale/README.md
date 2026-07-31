# Bus Scale — Enterprise-Grade Hermes Agent Fleet Bus

> **Scaling the Hermes Cortex Agent Bus (PGMQ + FastAPI) from ~6 agents to 1000+ agents.**
> Design documents, user stories, and implementation plans for all identified gaps.

## Why This Exists

The Hermes Cortex Agent Bus was designed for a small fleet (~6 agents). A comprehensive
architecture review (HC-Party, July 2026) identified **15 distinct gaps** that must be
addressed to reach enterprise-grade scalability (1000+ agents). This directory contains
the design, decomposition, and implementation for closing those gaps.

## Gap Overview

| # | Gap | Priority | Effort | Status |
|---|-----|----------|--------|--------|
| 1 | **Credential provisioning API** (`hermes cortex agent add`) | 🔴 P0 | 1-2 days | Plan |
| 2 | **Inner body JSON auto-parse fix** | 🔴 P0 | 2 hours | Plan |
| 3 | **Agent labels + targeted fleet updates** | 🔴 P0 | 4 hours | Plan |
| 4 | **Queue sharding** (8 schemas, hash routing) | 🟡 P1 | 3-4 days | Plan |
| 5 | **VictoriaMetrics bus metrics** (push model) | 🟡 P1 | 2-3 days | Plan |
| 6 | **Long-poll read support** | 🟡 P1 | 2 days | Plan |
| 7 | **Per-queue circuit breaker + backpressure** | 🟡 P1 | 2 days | Plan |
| 8 | **`bus.audit_log`** (operations audit trail) | 🟢 P2 | 1 day | Plan |
| 9 | **Schema registry + schema_version** | 🟢 P2 | 3-5 days | Plan |
| 10 | **Auto-failover** (health → promote backup) | 🟢 P2 | 1 week | Plan |
| 11 | **Bus integration test harness** | 🟢 P2 | 3-5 days | Plan |
| 12 | **WebSocket push-based consumption** | 🔵 P3 | 1-2 weeks | Deferred |
| 13 | **Topic/subscription model** | 🔵 P3 | 2-3 weeks | Deferred |
| 14 | **Cross-region replication** | 🔵 P3 | 3-4 weeks | Deferred |
| 15 | **mTLS auto-renewal (step-ca)** | 🔵 P3 | 1 week | Deferred |

**P0** = Must have before adding agent #7  
**P1** = Must have before 50 agents  
**P2** = Needed for 100-500 agents  
**P3** = Needed for 500-1000 agents (deferred — pause before implementing)

> ⚠️ Items 12–15 (3rd-party / external integrations) are **paused** per user instruction.
> Designs exist conceptually but are not planned for implementation in this round.

## Architecture Principles

All designs in this directory follow these principles:

1. **Zero agent-side changes** — Where possible, all scaling work happens on the bus server. Agents should not need config changes or redeployment.
2. **Backward compatibility** — Existing message formats, consumption patterns, and ACLs must continue working. No breaking changes to the agent interface.
3. **Operational sanity** — Every new feature must be observable (metrics), debuggable (logs), and recoverable (timeouts, fallbacks, circuit breakers).
4. **Enterprise-grade** — Security (auth at every layer), auditability (every operation logged), reliability (no single points of failure), and scalability (horizontal sharding).
5. **Incremental deployment** — Each P0/P1/P2 item can be deployed independently, verified, and rolled back if needed.

## Design Documents

| Document | Covers |
|----------|--------|
| [User Stories](stories.md) | Full story decomposition — all stories sliced vertically by user value |
| [Credential Provisioning API](credential-provisioning-api.md) | `hermes cortex agent add` — automated agent onboarding |
| [Inner Body JSON Fix](inner-body-json-fix.md) | Auto-parse inner body in `bus_send`/`bus_read` |
| [Agent Labels + Targeted Updates](agent-labels.md) | Canary deployments via agent metadata |
| [Queue Sharding](queue-sharding.md) | Horizontal scale via Postgres hash sharding |
| [VictoriaMetrics Bus Metrics](prometheus-metrics.md) | Observable bus: latency, depth, error rates (push model) |
| [Long-Poll Read](long-poll-read.md) | Reduce PG load with HTTP long-poll |
| [Per-Queue Circuit Breaker](circuit-breaker.md) | Backpressure, inbox limits, per-agent isolation |
| [Bus Audit Log](audit-log.md) | Enterprise compliance — every operation logged |
| [Integration Test Harness](integration-test-harness.md) | Multi-agent bus testing for CI/CD |

## Related Documents

- [`docs/reference/cortex-bus-config.md`](../../reference/cortex-bus-config.md) — Current bus configuration guide
- [`docs/orch-bus-setup.md`](../../orch-bus-setup.md) — Bus setup and operation guide
- [`docs/fleet-update-protocol.md`](../../fleet-update-protocol.md) — Fleet update message schemas
- [`docs/agent-architecture.md`](../../agent-architecture.md) — Agent roles and capability matrix

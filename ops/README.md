# Cortex Operations

Installers, monitors, services, offline stack, and fleet management. This layer keeps the system running — health checks, recovery, cron orchestration, knowledge synchronization, and the offline-first infrastructure.

## Contents

| Directory | Purpose | Status |
|-----------|---------|--------|
| `install/` | Installer scripts and Docker deployments | From `install.sh`, `deploy/` |
| `scripts/` | Operational scripts: health, inbox, agent management | From `src/scripts/` |
| `services/` | Long-running services: dashboard, agent-inbox, A2A | From `src/dashboard/`, `src/agent-inbox/`, `src/a2a/` |
| `offline/` | Offline knowledge stack: Kiwix, code corpus, gbrain sync | From `src/offline/` |
| `web-cache/` | Local semantic web cache (sqlite-vec) | From `src/web-cache/` |
| `monitors/` | Watchdogs, cron quality gates, health probes | Planned |

## Design Rules

- **Self-healing** — Every service should have a monitor that detects failure and attempts recovery.
- **Silent when good** — No output on success; actionable output on failure.
- **Offline-first** — All ops must degrade gracefully when the network is unavailable.

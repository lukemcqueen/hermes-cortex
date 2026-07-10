# Cortex Operations

Installers, monitors, services, offline stack, and fleet management. This layer keeps the system running — health checks, recovery, cron orchestration, knowledge synchronization, and the offline-first infrastructure.

## Contents

| Directory | Purpose | Status |
|-----------|---------|--------|
| `install/` | Installer scripts and Docker deployments | Populated (install.sh, quick-start.sh, deploy/) |
| `scripts/` | Operational scripts: health, inbox, agent management | Populated (131 scripts from `src/scripts/`) |
| `services/` | Long-running services: dashboard, agent-inbox, A2A | Populated (dashboard, agent-inbox, a2a) |
| `offline/` | Offline knowledge stack: Kiwix, code corpus, gbrain sync | Populated (from `src/offline/`) |
| `web-cache/` | Local semantic web cache (sqlite-vec) | Populated (from `src/web-cache/`) |
| `monitors/` | Watchdogs, cron quality gates, health probes | Planned |

## Design Rules

- **Self-healing** — Every service should have a monitor that detects failure and attempts recovery.
- **Silent when good** — No output on success; actionable output on failure.
- **Offline-first** — All ops must degrade gracefully when the network is unavailable.

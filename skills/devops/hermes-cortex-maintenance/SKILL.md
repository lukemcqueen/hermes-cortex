--- Full content (truncated) ---
---
name: hermes-cortex-maintenance
version: 1.36.0
category: devops
description: >-
  Maintain an installed Hermes Cortex instance — update both the upstream
  Hermes Agent and the cortex repo layer, merge diverged histories, sync
  skills safely, and troubleshoot common issues. Covers the dual-update
  workflow (hermes update + cortex-update.sh), encrypted brain data backup,
  gbrain import, and recovery techniques.
---

# Hermes Cortex Maintenance v1.33.0

> **Maintaining your Hermes Cortex install** — pulling upstream changes,
> updating gbrain, syncing skills, and recovering when things go wrong.

## Prerequisites

- Hermes Cortex installed at `~/hermes-cortex/`
- Bun at `~/.bun/bin/bun`
- gbrain at `~/.bun/bin/gbrain`
- Ollama running as a systemd user service (or equivalent)

## Setup: Daily Auto-Update Timer (3am)

Since commit c4ff4e5, Hermes Cortex includes a **daily auto-update timer** that replaces all standalone maintenance cron jobs.

### Install the timer

```bash
# Copy
... [truncated]
--- End skill ---
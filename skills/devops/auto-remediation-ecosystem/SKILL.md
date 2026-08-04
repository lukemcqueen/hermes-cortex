---
name: auto-remediation-ecosystem
version: 1.0.0
author: Hermes Cortex
created: 2026-06-15
updated: 2026-06-15
tags:
- auto-remediation
- ecosystem
- setup
- troubleshooting
- monitoring
- server-administration
- automation
- production-operations

description: |
  Complete auto-remediation ecosystem setup, configuration, and maintenance
  for production systems. Covers deployment of all auto-remediation components,
  integration with existing server administration workflows, monitoring,
  troubleshooting, and production operations best practices.

syntax: |
  # Install the ecosystem setup
  hermes skills install auto-remediation-ecosystem

  # Verify complete system
  ecosystem-verify.sh

  # Setup reference
  cat .hermes/skills/auto-remediation-ecosystem/references/auto-remediation-ecosystem.md

references:
- references/auto-remediation-ecosystem.md
- templates/auto-remediation-full-setup.sh
- scripts/ecosystem-verify.sh
- scripts/auto-remediation-health-check.sh
- scripts/manual-triggers-guide.sh

examples:
- title: Verify a Fresh Ecosystem Install
  content: |
    ```bash
    ecosystem-verify.sh
    # Expect: all components present, services healthy, cron registered
    ```
- title: Run the Health Check
  content: |
    ```bash
    auto-remediation-health-check.sh
    # Reports per-component status: sensor, fixer, queue, delivery
    ```
---

# Auto-Remediation Ecosystem

## Overview

The auto-remediation ecosystem is the full production pipeline that detects
operational failures, remediates them automatically, and reports the outcome.
This skill covers **deployment, configuration, monitoring, and maintenance**
of the complete ecosystem — not just a single component.

## Components

| Component | Role | Entry point |
|-----------|------|-------------|
| **Sensor** | Detects failures (cron failures, service down, inbox drift) | `agent-remediation-sensor` cron |
| **Fixer** | Applies remediations autonomously | `agent-fixer-*` crons |
| **Queue / state** | Tracks what failed and what was attempted | PGMQ / state files |
| **Delivery** | Reports outcomes to the orchestrator / user | Agent bus + Telegram |
| **Verification** | Confirms the fix worked | re-run the failing check |

## Deployment

```bash
# 1. Deploy the full ecosystem from the template
bash templates/auto-remediation-full-setup.sh

# 2. Verify every component
bash scripts/ecosystem-verify.sh

# 3. Confirm the cron is registered with the right prefix
cronjob action=list | grep remediation
# Expected: agent-remediation-sensor, agent-fixer-*, orch-remediation-*
```

Deployment prerequisites (per component):
- **Passwordless sudo** for the fixer to act (documented in the setup skill)
- **Agent bus access** for delivery to the orchestrator
- **Cron scheduler healthy** — the doctor validates expected crons

## Monitoring

Run the health check on a schedule or on demand:

```bash
bash scripts/auto-remediation-health-check.sh
```

Watch for:
- **Sensor silence** — a sensor that stops firing means it stopped running,
  not that everything is fine (check the cron's `last_status`).
- **Fixer loops** — the same failure remediated repeatedly without resolution
  is a failed fix, not a healthy loop. Escalate after N retries.
- **Delivery gaps** — remediations applied but never reported = blind fixes.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Sensor never fires | Cron not running / status stale | `cronjob action=run` + doctor |
| Fixer applies but failure persists | Wrong remediation or missing root cause | Read the failure detail, fix the fixer |
| Health check reports component missing | Partial deploy | Re-run `auto-remediation-full-setup.sh` |
| Duplicate remediations | Two fixers watching the same failure | De-dup via `fix-cron-duplicates.py` |

## Production Operations Best Practices

1. **Remediation must be idempotent** — re-running a fix on an already-fixed
   state must be a no-op, never a destructive re-do.
2. **Every fix logs its outcome** — what failed, what was attempted, what the
   verification showed.
3. **Escalate after repeated failure** — a fix that fails 3× in a row becomes
   a human ticket; do not loop forever.
4. **Unattended destructive actions default to no-op** — when a cleanup or
   prune is ambiguous and no user can confirm, do nothing destructive
   (disk pressure can be remediated; deleted data cannot).
5. **The doctor is the source of truth** — run
   `cortex-doctor.py --quiet` after any ecosystem change.

## Related
- `auto-remediation-setup` — the focused setup/troubleshooting skill for a single machine
- `auto-remediation` — the fix patterns themselves
- `cortex-bus-automation` — delivery plumbing
- `sensor-false-positive-remediation` — handling false positives from the sensor

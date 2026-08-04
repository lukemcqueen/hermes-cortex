---
name: auto-remediation-setup
version: 1.0.0
author: Hermes Cortex
created: 2026-06-15
updated: 2026-06-15
tags:
- auto-remediation
- setup
- troubleshooting
- cron-jobs
- system-health

description: |
  Set up, configure, and troubleshoot the auto-remediation system.

  Covers passwordless sudo prerequisites, verification scripts,
  troubleshooting workflows, and best practices for deploying
  the auto-remediation pipeline across different environments.

syntax: |
  # Basic setup
  hermes skills install auto-remediation-setup

  # Quick verification
  verify-auto-remediation.sh

  # Setup reference
  cat .hermes/skills/auto-remediation-setup/references/auto-remediation-setup.md

references:
- references/auto-remediation-setup.md
- templates/auto-remediation-cron-setup.sh
- scripts/verify-auto-remediation.sh

examples:
- title: Quick Setup on New System
  content: |
    ```bash
    # 1. Install the skill
    hermes skills install auto-remediation-setup

    # 2. Verify prerequisites
    verify-auto-remediation.sh --prereqs

    # 3. Deploy the cron
    bash templates/auto-remediation-cron-setup.sh
    ```
---

# Auto-Remediation Setup

## Overview

Set up, configure, and troubleshoot the auto-remediation pipeline on a single
machine. This is the focused companion to `auto-remediation-ecosystem` — it
covers **prerequisites, cron deployment, and verification** for getting the
pipeline running.

## Prerequisites

1. **Hermes Agent installed** with the cron scheduler active
2. **Passwordless sudo** (NOPASSWD) for the fixing user — the fixer must be
   able to restart services and edit configs without a password prompt:
   ```bash
   sudo -n true && echo "NOPASSWD OK" || echo "NOPASSWD MISSING — fix sudoers first"
   ```
3. **Agent bus access** for reporting to the orchestrator
4. **Relevant agent skills deployed** (`agent-fundamentals`, monitoring skills)

## Setup Steps

```bash
# 1. Verify prerequisites
bash scripts/verify-auto-remediation.sh --prereqs

# 2. Deploy the remediation crons from the template
bash templates/auto-remediation-cron-setup.sh

# 3. Confirm the crons registered
cronjob action=list | grep remediation

# 4. Force a sensor run to validate the pipeline end-to-end
cronjob action=run <sensor-job-id>
```

## Cron Naming (fleet convention)

| Cron | Prefix | Install scope |
|------|--------|---------------|
| `agent-remediation-sensor` | `agent-` | All agents |
| `agent-fixer-*` | `agent-` | All agents |
| `orch-remediation-*` | `orch-` | Orchestrators only |

Every cron MUST be in the matching install script's uninstall array — the
doctor reads expected crons from those arrays.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `verify-auto-remediation.sh` fails prereq check | sudo not NOPASSWD | Configure sudoers (`sudoers-audit` skill) |
| Sensor cron missing from doctor | Not in uninstall array | Add to `install-crons.sh` uninstall array |
| Fixer can't act | Insufficient permissions | Grant the action in sudoers or adjust scope |
| Reports not reaching Moses | Bus access broken | Check `agent-bus-messaging` connectivity |

## Best Practices

- **Deploy from the repo, not by hand** — always run the setup template from
  `ops/scripts/`, never `cp` scripts manually (next cortex-update would drift).
- **Test the sensor end-to-end** after setup — `cronjob action=run` the sensor
  and confirm it delivers.
- **Remediations must be idempotent and non-destructive by default.**
- **Run the doctor** after any change:
  `python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet`

## Related
- `auto-remediation-ecosystem` — full-pipeline deployment + monitoring
- `auto-remediation` — remediation patterns themselves
- `sudoers-audit` — passwordless sudo configuration
- `cron-job-management` — cron naming and installer rules

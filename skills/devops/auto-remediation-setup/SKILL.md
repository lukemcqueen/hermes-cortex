--- Full content (truncated) ---
---
name: auto-remediation-setup
author: hermes
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
    verify-
... [truncated]
--- End skill ---
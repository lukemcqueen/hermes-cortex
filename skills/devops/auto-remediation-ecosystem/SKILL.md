--- Full content (truncated) ---
---
name: auto-remediation-ecosystem
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

... [truncated]
--- End skill ---
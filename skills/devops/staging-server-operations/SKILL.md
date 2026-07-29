--- Full content (truncated) ---
---
name: staging-server-operations
description: "Safe operational practices for Docker-based staging servers — volume management, change verification, and database recovery patterns."
version: 1.19.0
author: Hermes Cortex
license: MIT
platforms: [linux, darwin]
metadata:
  hermes:
    tags: [docker, staging, recovery, volumes, operations]
---

# Staging Server Operations

This skill covers the recurring maintenance operations for the KOSCAP staging
server: hermes-cortex pull-and-integrate, Docker volume management, cron
auditing, database recovery, and change verification.

## Principle: No Cutting Corners

The user has been emphatic: **implement everything from the repo — do not cut corners.**
A checklist item that says "skip if laborious" is permission to fail. When a task has 9
items and you do 7, the 2 you skipped will surface as drift, then as debt, then as fire.
Implement every step, verify every outcome. If a step can't be completed, escalate it —
don't silently skip it. 
... [truncated]
--- End skill ---
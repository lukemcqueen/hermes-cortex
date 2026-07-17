--- Full content (truncated) ---
---
name: governance-sentinel
version: 1.0.0
category: devops
description: >-
  Recurring governance introspection — scrape brain sync snapshots for codepath
  patterns, compile weekly insights, and store verdicts in dream.json for
  retrospection. Runs as a sentinel after gbrain-update-sync, before daily
  police logs.
---

# Governance Sentinel v1.0.0

> **Scraping brain sync state, extracting codepath patterns, and producing
> governance insights for weekly retrospection.** This is the sentinel that
> sits after gbrain-update-sync and before daily police logs in the pipeline.

## When to Use

Load this skill when the task involves:
- "sentinel" related to brain sync, governance, or reflection
- Scraping brain snapshots for patterns
- Writing or updating `dream.json`
- Weekly retrospection or governance insight compilation
- Pipeline-position-aware sentinel work (between gbrain update and police logs)

## Pipeline Position

```
gbrain-update-sync → GOVERNANCE-SENTINEL → daily police 
... [truncated]
--- End skill ---
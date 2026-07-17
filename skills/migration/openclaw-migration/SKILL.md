--- Full content (truncated) ---
---
name: openclaw-migration
description: Migrate a user's OpenClaw customization footprint into Hermes Agent. Imports Hermes-compatible memories, SOUL.md, command allowlists, user skills, and selected workspace assets from ~/.openclaw, then reports exactly what could not be migrated and why.
version: 1.0.0
author: Hermes Agent (Nous Research)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Migration, OpenClaw, Hermes, Memory, Persona, Import]
    related_skills: [hermes-agent]
---

# OpenClaw -> Hermes Migration

Use this skill when a user wants to move their OpenClaw setup into Hermes Agent with minimal manual cleanup.

## CLI Command

For a quick, non-interactive migration, use the built-in CLI command:

```bash
hermes claw migrate              # Full interactive migration
hermes claw migrate --dry-run    # Preview what would be migrated
hermes claw migrate --preset user-data   # Migrate without secrets
hermes claw migrate --overwrite  # Overwrite exis
... [truncated]
--- End skill ---
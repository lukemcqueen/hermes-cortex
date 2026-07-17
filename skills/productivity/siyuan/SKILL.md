--- Full content (truncated) ---
---
name: siyuan
description: SiYuan Note API for searching, reading, creating, and managing blocks and documents in a self-hosted knowledge base via curl.
version: 1.0.0
author: FEUAZUR
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [SiYuan, Notes, Knowledge Base, PKM, API]
    related_skills: [obsidian, notion]
    homepage: https://github.com/siyuan-note/siyuan
prerequisites:
  env_vars: [SIYUAN_TOKEN]
  commands: [curl, jq]
required_environment_variables:
  - name: SIYUAN_TOKEN
    prompt: SiYuan API token
    help: "Settings > About in SiYuan desktop app"
  - name: SIYUAN_URL
    prompt: SiYuan instance URL (default http://127.0.0.1:6806)
    required_for: remote instances
---

# SiYuan Note API

Use the [SiYuan](https://github.com/siyuan-note/siyuan) kernel API via curl to search, read, create, update, and delete blocks and documents in a self-hosted knowledge base. No extra tools needed -- just curl and an API token.

## Prerequisites

1. Install a
... [truncated]
--- End skill ---
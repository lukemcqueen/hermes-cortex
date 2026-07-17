--- Full content (truncated) ---
---
name: gitnexus-explorer
description: Index a codebase with GitNexus and serve an interactive knowledge graph via web UI + Cloudflare tunnel.
version: 1.0.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [gitnexus, code-intelligence, knowledge-graph, visualization]
    related_skills: [native-mcp, codebase-inspection]
---

# GitNexus Explorer

Index any codebase into a knowledge graph and serve an interactive web UI for exploring
symbols, call chains, clusters, and execution flows. Tunneled via Cloudflare for remote access.

## When to Use

- User wants to visually explore a codebase's architecture
- User asks for a knowledge graph / dependency graph of a repo
- User wants to share an interactive codebase explorer with someone

## Prerequisites

- **Node.js** (v18+) — required for GitNexus and the proxy
- **git** — repo must have a `.git` directory
- **cloudflared** — for tunneling (auto-installed to ~/.local/bin if missi
... [truncated]
--- End skill ---
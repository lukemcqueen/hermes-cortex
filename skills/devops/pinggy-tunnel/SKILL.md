--- Full content (truncated) ---
---
name: pinggy-tunnel
description: Zero-install localhost tunnels over SSH via Pinggy.
version: 0.1.0
author: Teknium (teknium1), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Pinggy, Tunnel, Networking, SSH, Webhook, Localhost]
    related_skills: [cloudflared-quick-tunnel, webhook-subscriptions]
---

# Pinggy Tunnel Skill

Expose a local service (dev server, webhook receiver, MCP endpoint, demo) to the public internet using a Pinggy SSH reverse tunnel. No daemon to install — the user's stock SSH client connects to `a.pinggy.io:443` and Pinggy hands back a public HTTP/HTTPS URL.

Free tier: 60-minute tunnels, random subdomain, no signup. Pro tier ($3/mo) is an opt-in with a token.

## When to Use

- User asks to "expose this locally", "share my dev server", "make this URL public", "tunnel port N", "get a public URL for a webhook"
- Need to receive a webhook callback during a local task (Stripe, GitHub, Discord, AgentMail)
- Sharing a one
... [truncated]
--- End skill ---
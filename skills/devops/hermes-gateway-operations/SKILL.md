--- Full content (truncated) ---
---
name: hermes-gateway-operations
description: >-
  Diagnose, configure, and maintain Hermes messaging gateway platforms
  (Telegram, Discord, WhatsApp, etc.). Covers connectivity troubleshooting,
  secret/token setup, gateway state inspection, and common failure patterns.
---

# Hermes Gateway Operations

Diagnostic and maintenance procedures for the Hermes messaging gateway.

## When to load

- User reports "messages not sending" on any platform
- Gateway is disconnected or repeatedly reconnecting
- Need to set up a new platform (Telegram bot token, Discord token, etc.)
- Debugging `.env` configuration for gateway platforms

## Diagnostic Path (Telegram example)

Always follow this sequence — each step feeds the next:

```
1. gateway_state.json    → platform state ("disconnected" / "connected")
2. gateway.log           → error message ("No bot token configured")
3. .env                  → check TELEGRAM_BOT_TOKEN exists
4. config.yaml           → check platform_plugins and telegram
... [truncated]
--- End skill ---
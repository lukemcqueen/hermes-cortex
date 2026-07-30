--- Full content (truncated) ---
---
name: macos-service-management
version: 1.0.0
description: Manage and troubleshoot macOS launchd services — plist authoring, exit code diagnosis, variable expansion rules, and service lifecycle
category: apple
---

# macOS Service Management (launchd)

Manage and debug launchd-based daemons and user agents on macOS. Launchd is macOS's system-wide service manager — analogous to systemd on Linux but with very different rules for paths, variables, and service configuration.

## Key Differences from systemd

| Concept | systemd (Linux) | launchd (macOS) |
|---------|----------------|-----------------|
| Unit file | `.service` | `.plist` (XML property list) |
| User services | `~/.config/systemd/user/` | `~/Library/LaunchAgents/` |
| System services | `/etc/systemd/system/` | `/Library/LaunchDaemons/` |
| User home variable | `%h` (expanded) | `$HOME` — **only in specific fields** |
| Shell variable expansion | Full (all env vars) | **None** — only `$HOME`, `$USER`, tilde `~` |
| Exit code 78 | N/A | 
... [truncated]
--- End skill ---
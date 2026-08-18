---
name: deploy-load-verification
version: 1.0.0
category: devops
description: "Use when a config change isn't live — verify what loaded."
platforms: [linux, macos]
author: Esther (Hermes Cortex)
license: MIT
metadata:
  hermes:
    tags: [deploy, verification, gateway, mcp, config, restart]
    related_skills: [hermes-gateway-operations, cortex-bus, change-checklist]
---

# Deploy ≠ Load Verification

## When to Use

- After changing `config.yaml` (MCP servers, plugins, enforcer) — is the change actually live?
- After renaming a service/package (e.g. `agent_bus` → `cortex_bus`) — do tool names match what skills/crons reference?
- Symptom: "tools still expose old names", "deployed but nothing changed", "restart needed"
- BEFORE claiming "everything renamed" — verify the config key AND the running process, not just the repo

## Core Principle

A file on disk is not a running process. The gateway (and any long-running
daemon) loads config/plugin/enforcer code at START and keeps it in memory.
**Deploy ≠ load.** Verification = compare when the process started vs when the
files changed, and inspect what the process ACTUALLY spawned.

## Verification Recipe

```bash
# 1. When did the process start vs when did the files change?
ps -eo pid,lstart,cmd | grep 'hermes_cli.main gateway' | grep -v grep
stat -c '%y %n' ~/.hermes/plugins/governance-enforcer/__init__.py ~/.hermes/config.yaml

# 2. What did the running process ACTUALLY spawn? (ground truth)
ps -eo pid,lstart,cmd | grep mcp_stdio_watchdog | grep -v grep

# 3. Bus/server daemon: exact module name in argv
ps -eo pid,lstart,cmd | grep uvicorn | grep -v grep
```

**Rule of thumb:** process start > file mtime → new code loaded. Start < mtime
→ old code still in memory; restart required.

**MCP children are ground truth:** each `mcp_stdio_watchdog` child carries the
exact script path the gateway spawned at startup. An old path in the child argv
(e.g. `agent-bus-mcp.py` while config now says `cortex-bus-mcp.py`) means the
gateway started before the config change — what config.yaml says on disk is
irrelevant until restart.

## MCP Config-Key → Tool-Namespace Coupling

- The `mcp_servers.<name>:` key in `config.yaml` determines the exposed tool
  namespace: key `agent-bus` → tools `mcp__agent_bus__*` (hyphen → underscore).
- Renaming the key (e.g. → `cortex-bus`) changes the tool namespace and breaks
  every skill/cron that references the old `mcp__<name>__*` tools — until the
  gateway restarts with the new key.
- A rename that sweeps packages/skills/crons but leaves the config key = tool
  names stay old while docs claim the new ones. **Search config keys with
  HYPHENS** (`grep -iE 'agent-bus|cortex-bus'`), never underscores — `agent_bus`
  matches the Python package, never the config key.

## Changing config.yaml

- `config.yaml` is **enforcer-blocked for direct agent patch** ("Agent cannot
  modify security-sensitive configuration"). Use `hermes config set <path>`
  / `hermes config unset <path>` (see `hermes config --help`), or have the
  user edit the file directly.
- Gateway restart is a lifecycle-guarded operator action on this fleet —
  prepare everything, verify on disk, then hand the restart to the host
  operator with the exact command. Don't loop-retry.

## Pitfalls

1. **Claiming "everything renamed" while the config key still has the old
   name.** Happened 2026-08-04: the migration summary said "one name" but
   `config.yaml` still had `mcp_servers.agent-bus:` — only the file-mutation
   verifier (refused patch) surfaced the overstatement. Always verify the
   config key + running children, not just the repo strings.
2. **Grepping config with underscore patterns.** `agent_bus` finds the Python
   package, not the config key `agent-bus`. Hyphens in config keys, underscores
   in code/package names.
3. **Trusting config.yaml on disk over the running process.** The running
   gateway may predate the edit; the child argv is the truth.
4. **Assuming a fresh gateway is automatically clean.** A gateway restarted
   AFTER the deploy is clean — verify with `lstart`, don't assume.

## Verification Checklist

- [ ] Gateway `lstart` > every changed file's mtime (or restart happened after deploy)
- [ ] `mcp_stdio_watchdog` children show the NEW script paths
- [ ] Config key name matches the tool namespace skills reference (`mcp__<key>__*`)
- [ ] Bus/daemon process argv shows the new module name
- [ ] Any required restarts handed to the operator with exact commands

## References

- `references/rename-verification-example.md` — worked example: the `agent_bus` → `cortex_bus` fleet rename (2026-08-04)

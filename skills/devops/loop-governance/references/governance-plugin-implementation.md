# Governance Plugin Implementation

## Overview

The Governance Enforcer is a **Hermes Plugin** that uses the `pre_tool_call` lifecycle hook to enforce loop governance at the Hermes runtime level. Unlike self-discipline (SOUL.md), pre-commit hooks (git), or reactive auditors (cron), this plugin blocks write tools **before they execute** — the agent cannot bypass it mid-session.

---

## The `pre_tool_call` Hook (Hermes Plugin API)

### What It Is

A lifecycle hook fired by `hermes_cli.plugins.get_pre_tool_call_block_message()` in `tool_executor.py` (and `agent_runtime_helpers.py`) before every Hermes tool execution. Plugins register callbacks via `ctx.register_hook("pre_tool_call", handler)`.

### Hook Handler Signature

```python
def handler(
    tool_name: str,
    args: dict,
    session_id: str,
    tool_call_id: str,
    turn_id: str,
    api_request_id: str,
    task_id: str,
    middleware_trace: list,
    **kwargs,
) -> dict | None:
```

### Return Values

| Return Value | Effect |
|---|---|
| `{"action": "block", "message": "Reason"}` | Tool is blocked — message shown to agent |
| `{"action": "block"}` (no message) | Ignored (message must be non-empty) |
| `None` or any non-matching dict | Pass — tool executes normally |

The **first** plugin to return a valid block wins. Subsequent return values are ignored. This means multiple plugins can coexist — an observer-only plugin returns `None`, while an enforcer plugin blocks.

### All Valid Lifecycle Hooks

Defined in `hermes_cli/plugins.py:VALID_HOOKS`:

| Hook | Fires | Return Shape |
|------|-------|-------------|
| `pre_tool_call` | Before every tool call | `{"action": "block", "message": "..."}` or `None` |
| `post_tool_call` | After every tool call | Observer-only |
| `pre_llm_call` | Before each LLM generation | `{"context": "... extra injection ..."}` |
| `post_llm_call` | After each LLM generation | Observer-only |
| `pre_verify` | Before verification stop | `{"action": "continue", "message": "..."}` |
| `transform_llm_output` | Before LLM output returned to user | String replacement |
| `transform_terminal_output` | Before terminal output returned | String replacement |
| `transform_tool_result` | Before tool result returned | String/structured replacement |
| `pre_api_request` | Before API request | Observer/modify |
| `post_api_request` | After API request | Observer-only |
| `api_request_error` | On API error | Observer-only |
| `on_session_start` | Session begins | Observer-only |
| `on_session_end` | Session ends | Observer-only |
| `on_session_finalize` | Session finalize | Observer-only |
| `on_session_reset` | Session reset | Observer-only |
| `subagent_start` / `subagent_stop` | Subagent lifecycle | Observer-only |
| `pre_gateway_dispatch` | Before message dispatch | `{"action": "skip"\|"rewrite"\|"allow"}` |

---

## Plugin System Architecture

### Discovery Sources (in priority order)

| Source | Path | Overrides |
|--------|------|-----------|
| Bundled | `<repo>/plugins/<name>/` | — |
| User | `~/.hermes/plugins/<name>/` | Bundled (same name) |
| Project | `./.hermes/plugins/<name>/` | User (same name) |
| Pip | `hermes_agent.plugins` entry point | All (same name) |

Later sources override earlier ones on name collision.

### Required Plugin Structure

```
<name>/
├── plugin.yaml         # Manifest (name, version, description)
└── __init__.py         # Must export register(ctx) function
```

### `plugin.yaml` Format

```yaml
name: governance-enforcer
description: "Enforces loop governance at the tool level"
version: "1.0.0"
author: Joseph (Hermes Cortex)
```

### `__init__.py` Contract

```python
def register(ctx: PluginContext) -> None:
    """Called by Hermes at startup. Register hooks, tools, and skills here."""
    ctx.register_hook("pre_tool_call", my_handler)
```

The `PluginContext` object provides:

| Method | Purpose |
|--------|---------|
| `register_hook(name, callback)` | Register a lifecycle hook |
| `register_tool(name, toolset, schema, handler, ...)` | Register a new tool |
| `register_middleware(kind, callback)` | Register middleware |
| `register_skill(name, path, description)` | Register a read-only skill |
| `llm` | Property — host-owned LLM access |
| `profile_name` | Property — active Hermes profile name |
| `manifest` | Property — the parsed plugin.yaml |

---

## How the Governance Enforcer Works

### Startup Flow

```
Hermes starts
  ├── PluginManager.discover_and_load()
  │     ├── Scans ~/.hermes/plugins/<name>/ for plugin.yaml + __init__.py
  │     ├── Calls plugin's register(ctx)
  │     │     └── ctx.register_hook("pre_tool_call", handler)  ← registered
  │     └── Plugin loaded
  └── Agent loop begins
```

### Tool Call Flow

```
Model requests tool call
  ├── tool_executor.py: execute_tool_call()
  │     └── get_pre_tool_call_block_message(tool_name, args)
  │           ├── Check thread-level tool whitelist (if set)
  │           ├── invoke_hook("pre_tool_call", tool_name, args, ...)
  │           │     ├── Plugin A handler returns None           → pass
  │           │     ├── Plugin B handler returns None           → pass
  │           │     └── Governance Enforcer returns block?     → STOP
  │           └── First block message wins → tool is blocked
  └── Tool executes (or blocked with message)
```

### Block Decision Matrix

| Tool | Governance Lock Present? | Result |
|------|------------------------|--------|
| `write_file` | No | 🔒 BLOCKED |
| `write_file` | Yes | ✅ Passes |
| `patch` | No | 🔒 BLOCKED |
| `patch` | Yes | ✅ Passes |
| `terminal("rm -rf /")` | No | 🔒 BLOCKED |
| `terminal("rm -rf /")` | Yes | ✅ Passes |
| `terminal("ls -la")` | Either | ✅ Passes (read-only) |
| `cronjob(action="create")` | No | 🔒 BLOCKED |
| `cronjob(action="list")` | Either | ✅ Passes |
| `skill_manage(action="create")` | No | 🔒 BLOCKED |
| `skill_manage(action="view")` | Either | ✅ Passes |

### Write Command Patterns (terminal)

The plugin blocks terminal commands matching these patterns:

```
(sudo)? rm|mv|cp|install|apt|apt-get|dpkg|pip|npm|brew|make|cmake
(sudo)? systemctl|service (start|stop|restart|reload|enable|disable)
(sudo)? chmod|chown|chattr|mkfs|fdisk|mount|umount|dd
(sudo)? sed|awk.*-i
(sudo)? git push|commit|merge|rebase|reset|cherry-pick|branch -d|-D
(sudo)? cronjob create|update|remove|delete
echo ... >|>>  (file redirection)
(sudo)? docker run|build|push|commit|tag|save|load|rmi|system prune
(sudo)? wget.*-O, curl.*-o, nohup, crontab, useradd, ufw, nginx -s reload
```

### Read Commands (always pass)

```
ls|cat|head|tail|less|more|grep|find|which|whoami|id|pwd|date|echo|printf
ps|top|htop|df|du|free|uptime|uname|hostname|dmesg|journalctl
git status|log|diff|show|branch|stash list
docker ps|images|logs|inspect|stats
pip|npm list|show|search
hermes --version|doctor|config get|config show|config path|config check
systemctl is-active|is-enabled|status|list-units
```

---

## Governance Lock File Protocol

### Location

Lock files are **session-scoped** — each governance session gets its own
file named by session ID:

```
~/.hermes-cortex/state/.governance-{session_id}.json
```

Example: `.governance-sess_abc123def456.json`

The repo slug is **stored in the lock file content**, not the filename.
This eliminates all cwd-dependency: the enforcer scans all `.governance-*.json`
files and matches by the `repo_slug` field. Multiple sessions in the same repo
each get their own file.

### Created By

`mcp_loop_governance_begin_change(task_id="...", description="...")`

The `loop-gov-mcp.py` MCP server writes the session-scoped lock file when
`begin_change` is called.

### Checked By

The governance enforcer plugin's `_has_governance_lock()` function
scans all `.governance-*.json` files, filters by `repo_slug` in content,
checks TTL staleness, and cleans stale/corrupt files automatically:

```python
GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"

def _has_governance_lock() -> bool:
    current_slug = _derive_slug()
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            state = json.loads(lock_file.read_text())
            # Legacy locks (no repo_slug) accepted for upgrade compat
            if state.get("repo_slug") is not None and state.get("repo_slug") != current_slug:
                continue
            if _is_lock_stale(state):
                lock_file.unlink()
                continue
            if state.get("task_id", ""):
                return True
        except (json.JSONDecodeError, OSError):
            try:
                lock_file.unlink()
            except OSError:
                log.warning("Cannot remove stale lock file: %s", lock_file)
                pass
    return False
```

### Format

```json
{
  "task_id": "fix-auth-403",
  "description": "Add rate limiting to auth endpoint",
  "repo_slug": "hermes-cortex",
  "started_at": "2026-07-04T00:00:00",
  "agent": "joseph",
  "session_id": "sess_abc123def456",
  "ttl_seconds": 3600,
  "heartbeat_at": "2026-07-04T00:00:00Z",
  "scored": false
}
```

### Released By

`mcp_loop_governance_end_change(task_id="...")` — deletes the session's
lock file.

### Critical: File Must Be Accessible

The plugin reads this file from the filesystem. On remote Hermes backends (Modal, Daytona, Docker) where `~/.hermes-cortex/` isn't mounted to the Hermes process's filesystem, the lock check always returns `False` and all write tools are blocked. This is **by design** — governance enforcement is stricter on remote backends where the lock file pattern can't work.

---

## Why Plugin, Not MCP Server

Before the plugin existed, a **loop-gov-mcp.py** script was written to provide `begin_change`/`end_change` MCP tools. This was mistakenly documented as the "enforcement layer."

**The problem:** MCP servers only **provide** tools — they do not intercept or block Hermes built-in tools. The MCP `begin_change`/`end_change` tools write and delete the governance lock file, but nothing checked that lock file when a write tool was called. The agent would call `begin_change`, make changes, call `end_change` — or skip all of them and the system had no way to block.

**The fix:** Move enforcement out of MCP (which can't intercept) into a plugin (which can). The plugin checks the lock file at `pre_tool_call` time — before the tool runs. The MCP tools continue to exist for creating and releasing locks, but the plugin is the actual enforcement actor.

---

## Installation (Single Agent)

```bash
# Create the plugins directory if it doesn't exist
mkdir -p ~/.hermes/plugins

# The plugin deploys as a COPY via cortex-update.sh (not symlink — enables chattr +i).
# cortex-update.sh is the ONLY sanctioned way to update the enforcement chain
# (hermes-plugin-lock unlock/update require the --cortex-update token or an
# orchestrator account since 2026-07-31):
bash ~/hermes-cortex/ops/scripts/cortex-update.sh

# Manual maintenance (ORCHESTRATOR ACCOUNT ONLY — moses|esther):
sudo hermes-plugin-lock unlock --orchestrator   # remove old immutability if set
sudo hermes-plugin-lock lock                    # set chattr +i (any agent may lock)

# Verify
ls -la ~/.hermes/plugins/governance-enforcer/
# Should show: __init__.py  plugin.yaml  README.md

# Restart Hermes for changes to take effect
/reset   # or start a new hermes process
```

### Debug Plugin Loading

```bash
HERMES_PLUGINS_DEBUG=1 hermes
# Check ~/.hermes/logs/agent.log for plugin discovery logs
```

---

## Fleet Installation (All Agents)

The plugin source lives in the Hermes Cortex repo. To deploy to all agents:

```bash
# Source of truth (commit and push first if modified)
ls ~/hermes-cortex/plugins/governance-enforcer/

# Deployed via cortex-update.sh as a copy (not symlink):
#   plugins/governance-enforcer/ → ~/.hermes/plugins/governance-enforcer/
# Run cortex-update to ensure repo is current:
cd ~/hermes-cortex && git pull origin main
bash ops/scripts/cortex-update.sh

# Then /reset the agent session
```

### Agent-Specific Paths

| Agent | Host | Repo Path |
|-------|------|-----------|
| Moses | Orchestrator | `~/hermes-cortex/plugins/governance-enforcer/` |
| Esther | Backup orchestrator | `~/hermes-cortex/plugins/governance-enforcer/` |
| Gisu | Work staging | `~/hermes-cortex/plugins/governance-enforcer/` |
| Kustos | Work production | `~/hermes-cortex/plugins/governance-enforcer/` |
| Joseph | Personal production | `~/hermes-cortex/plugins/governance-enforcer/` |

The pattern is the same for all: plugin source in the Cortex repo → copy into `~/.hermes/plugins/` via cortex-update.sh (not symlink — uses chattr +i for immutability). The old `plugins/governance-enforcer` symlink has been removed — always use `plugins/governance-enforcer/`.

### Deploy Script (automated)

For a clean install on any agent:

```bash
mkdir -p ~/.hermes/plugins
if [ -L ~/.hermes/plugins/governance-enforcer ] || [ -d ~/.hermes/plugins/governance-enforcer ]; then
  echo "Plugin exists, skipping symlink"
else
  ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/
  echo "Governance enforcer plugin installed. Restart Hermes to activate."
fi
```

---

## Verification

After restarting, this should be **blocked**:

```
write_file(path="/tmp/test.txt", content="hello")
```

Expected response:

```
GOVERNANCE LOCK REQUIRED

Tool 'write_file' modifies system state
...
```

After calling `begin_change()`, the same tool should **pass**.

---

## Writing Your Own pre_tool_call Plugin

To write a custom policy plugin (e.g. block all `docker run` commands):

```python
"""my-policy-plugin/__init__.py"""
import re

def register(ctx):
    if ctx is None:
        return
    def handler(tool_name, args, **kwargs):
        if not tool_name or not args:
            return None
        if tool_name == "terminal":
            command = args.get("command", "")
            if re.search(r"docker\s+run", command):
                return {
                    "action": "block",
                    "message": "Docker containers must be deployed via Docker Compose only. See ~/deploy/README.md",
                }
        return None  # everything else passes

    ctx.register_hook("pre_tool_call", handler)
```

```yaml
# my-policy-plugin/plugin.yaml
name: my-policy-plugin
description: "Blocks docker run commands"
version: "1.0.0"
```

This pattern works for any policy you want to enforce at the tool level — the plugin API is generic, not governance-specific.

---

## Key Lessons

1. **MCP servers cannot block built-in tools** — they only provide new tools. Enforcement must happen at the plugin level.
2. **Lock files are session-scoped** — each session gets its own `.governance-{session_id}.json`. The `repo_slug` is stored in the lock content, so the enforcer scans all locks and matches by content. This eliminates the cwd-mismatch problem entirely. Multiple sessions in the same repo can each hold a valid lock.
3. **The file system is the lock** — the governance lock is a file on disk. Any process on the same filesystem that reads it can enforce policy based on it. Processes on different filesystems can't — and that's a feature (remote backends block everything).
4. **Plugins compose** — multiple plugins can register `pre_tool_call` handlers. First block wins. This means you can layer security policies (Docker policy + governance + rate limiting) as independent plugins.
5. **Plugin changes require restart** — no hot-reload. Always `/reset` after installing or modifying a plugin.
6. **The agent cannot bypass this** — because the block comes from the Hermes runtime (Python process), not from the model's output or SOUL.md text, the agent cannot talk its way out of it.
7. **Every agent needs it** — if only one agent has the plugin, the others can freely skip governance. The source of truth is the repo; deploy the symlink to every agent.

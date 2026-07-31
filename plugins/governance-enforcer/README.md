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
├── plugin.yaml     # Manifest (name, version, description)
└── __init__.py     # Must export register(ctx) function
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
 │   ├── Scans ~/.hermes/plugins/<name>/ for plugin.yaml + __init__.py
 │   ├── Calls plugin's register(ctx)
 │   │   ├── ctx.register_hook("on_session_start", _on_session_start)
 │   │   │   └── Writes .hermes-session-{PID}.id with real session ID
 │   │   │     (MCP reads this via os.getppid() on begin_change)
 │   │   └── ctx.register_hook("pre_tool_call", handler) ← blocks writes
 │   └── Plugin loaded
 └── Agent loop begins
```

**Key security property:** The session marker is written at session start, *before* any
agent action. When the agent calls `begin_change` (an MCP tool), the MCP reads the
marker and finds the real Hermes session ID — so both sides create and check lock
files in the same namespace. Phase 1 exact match works on the first tool call.

If `_derive_repo_slug()` returns `""` (Hermes running outside a git repo), Phase 2
cannot match any lock. The enforcer blocks all writes. This is **correct behaviour** —
if the repo is unknown, no writes get through.

### Tool Call Flow

```
Model requests tool call
 ├── tool_executor.py: execute_tool_call()
 │   └── get_pre_tool_call_block_message(tool_name, args)
 │      ├── Check thread-level tool whitelist (if set)
 │      ├── invoke_hook("pre_tool_call", tool_name, args, ...)
 │      │   ├── Plugin A handler returns None      → pass
 │      │   ├── Plugin B handler returns None      → pass
 │      │   └── Governance Enforcer returns block?   → STOP
 │      └── First block message wins → tool is blocked
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
echo ... >|>> (file redirection)
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
hermes --version|doctor|config get|config show|config path|config check|env-path
systemctl is-active|is-enabled|status|list-units
```

---

## Skills-Loading Gate

The enforcer blocks ALL write tools (including terminal write commands, cronjob
creation, skill management) until all 8 always-section skills have been loaded
via actual `skill_view()` calls. This prevents agents from bypassing skill
loading by touching a file.

### How it works

The enforcer tracks every `skill_view(name=...)` call in the session. When all
8 required skills have been loaded, it **auto-creates a per-session marker**
with the session ID as proof:

```python
# Written by _auto_create_skills_marker() when _skills_loaded_in_session >= _REQUIRED_SKILLS
# Path:    ~/.hermes-cortex/state/skills-loaded/{session_id}
# Content: "session:{hermes_session_id}"
```

**Per-session files (since 2026-08-01):** each session owns its own marker
file under `state/skills-loaded/<session_id>`. The previous single shared
`state/.skills-loaded` file was the source of a multi-session race — on a
server with several sessions (telegram + cli 1 + cli 2), any session loading
skills overwrote the one file and blocked the other sessions' write tools
mid-task. With per-session files, concurrent sessions physically cannot stomp
each other. The old global `.skills-loaded` file is now inert (ignored).

The marker is **verified by content, not existence**. A bare `touch` creates
an empty file that is rejected:

| Marker state | Verdict | Why |
|-------------|---------|-----|
| No per-session file | 🔒 REJECTED | Skills not proven loaded |
| Empty (touch) | 🔒 REJECTED | No session proof |
| Whitespace only | 🔒 REJECTED | Same as empty |
| `session:correct-id` | ✅ ACCEPTED | Auto-created by enforcer after skill loading |
| `session:wrong-id` | 🔒 REJECTED | Session mismatch |
| Old global `.skills-loaded` | 🔒 IGNORED | Legacy file, superseded by per-session markers |

### The 8 required skills

```
task-start, agent-flow, reasoning-patterns, reflexion-check,
change-checklist, survey-before-action, cortex-preflight, agent-contract
```

### What this prevents

Previously, agents could bypass the skills gate by running:
```bash
touch ~/.hermes-cortex/state/.skills-loaded
```

This created an empty file that the enforcer accepted because it only checked
file existence. Now the enforcer verifies the content contains session proof
in a per-session file. The `touch` bypass is structurally closed. See also
`SOUL.md` Principle 23 for the agent-side discipline.

---

## Survey Gate for Cron Creation

The enforcer implements a **survey-before-action gate** specifically for cron creation.
Before `cronjob(action="create")` is allowed, the agent must demonstrate it has
surveyed existing resources by creating a marker file:

```bash
touch ~/.hermes-cortex/state/.cron-survey-done
```

This marker is created **after** running:
1. `cronjob(action='list')` — check existing crons for overlaps
2. `search_files(...)` — check for existing scripts
3. `skills_list()` — check for existing skills

The gate exists because agents historically created redundant cron jobs
and scripts instead of extending existing ones. The marker persists for the
session. Without it, all cron creation is blocked.

---

## Fail-Closed Safety

The enforcer wraps its entire `pre_tool_call` handler in a `try/except` block.
If any unhandled exception occurs (disk I/O error, corrupt lock file,
unexpected Python error), the handler **blocks all write operations**:

```
GOVERNANCE ENFORCER CRASHED — ALL WRITES BLOCKED
The enforcer plugin encountered an internal error and
cannot verify governance state.
All write operations are blocked until the enforcer
is reloaded or fixed.
```

This is a **fail-closed** design: uncertainty always defaults to blocking
writes rather than allowing ungoverned changes. Recovery requires checking
Hermes logs (`~/.hermes/logs/agent.log`) for the traceback, fixing the root
cause, and restarting the session.

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

#### Session ID alignment — Fixed-path marker (primary) + PID scan (fallback)

The enforcer plugin receives the Hermes session ID via the `pre_tool_call` hook's
`session_id` parameter. At each tool call, it writes this ID to **three** marker files:
1. **Fixed-path marker** (`.hermes-session-current.id`) — primary. The MCP server
  reads this by a known path, no PID arithmetic needed.
2. **PID-scoped marker** (`.hermes-session-{PID}.id`) — legacy fallback for MCP
  versions that predate the fixed path.
3. **`~/.hermes/session.id`** — Hermes config directory cache, final fallback
  for MCP when both state-directory markers are absent (e.g. on the very first
  tool call of a session before the enforcer has fired).

The fixed-path approach was introduced because the MCP server is NOT a direct child
of the Hermes process — there's a watchdog (`mcp_stdio_watchdog.py`) in between:
```
Hermes (PID=1001)
 └── watchdog (PID=1002, PPID=1001)
    └── MCP loop-gov (PID=1003, PPID=1002)
```
With the old PID-only handoff, `os.getppid()` inside the MCP returned the watchdog
PID (1002), not the Hermes PID (1001). The markers never matched, causing every
session's governance lock to be invisible to the enforcer.

The fixed-path marker eliminates this chain. Both sides agree on the same path
regardless of process ancestry:

```
pre_tool_call fires
 └── enforcer writes .hermes-session-current.id = "sess_abc123"
 └── enforcer writes .hermes-session-{PID}.id = "sess_abc123" (legacy)

begin_change fires (MCP, any depth)
 └── MCP reads .hermes-session-current.id → "sess_abc123"
 └── creates .governance-sess_abc123.json

next write tool fires
 └── enforcer Phase 1 looks for .governance-sess_abc123.json → FOUND
 └── pass through
```

If both markers are absent (e.g. no tool call has fired yet), the MCP falls back to
its cached `~/.hermes/session.id`, then generates a new UUID. Phase 2 (repo_slug
scan) covers any remaining mismatch for backward compat with old MCP locks.

### Checked By

The governance enforcer plugin's `_has_governance_lock()` function uses a
**three-phase approach** to find the active lock:

1. **Phase 1 — Exact match (primary):** Looks for `.governance-{hermes_session_id}.json`.
  The session ID is passed to the enforcer via the Hermes `pre_tool_call` hook's `session_id`
  parameter. The enforcer writes it to a fixed-path marker so the MCP server
  creates locks in the same namespace.

2. **Phase 2 — Scan by repo_slug (fallback):** If exact match fails (backward compat with
  old MCP locks that predate PID handoff, or when run outside a git repo), scans all
  `.governance-*.json` files and matches by `repo_slug` in content. **Cross-session
  protection:** when the current session and the lock both have a `session_id`, an
  exact match is required — Session B cannot write using Session A's lock.

3. **Phase 3 — Secondary lock marker (extra safety):** Checks the repo-located marker
  at `.hermes-cortex/.governance-lock` as a fallback when the primary state directory
  is inaccessible. The MCP server writes this alongside the primary lock during
  `begin_change()`.

On every call, the enforcer also **proactively purges stale locks** — any
`.governance-*.json` file whose `heartbeat_at` exceeds its TTL is removed
before the phase checks begin. This prevents lock accumulation and ensures
stale sessions don't accidentally block new ones.

```python
GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"

def _has_governance_lock(hermes_session_id: str = "") -> bool:
  current_slug = _derive_repo_slug()
  if not GOVERNANCE_STATE_DIR.exists():
    return False

  # ── Phase 1: Exact match by Hermes session ID ──
  if hermes_session_id:
    lock_path = GOVERNANCE_STATE_DIR / f".governance-{hermes_session_id}.json"
    if lock_path.exists():
      try:
        state = json.loads(lock_path.read_text())
        if state.get("task_id", "") and not _is_lock_stale(state):
          return True
        if state.get("task_id", ""):
          lock_path.unlink(missing_ok=True) # stale — clean
      except (json.JSONDecodeError, OSError):
        lock_path.unlink(missing_ok=True)

  # ── Phase 2: Scan by repo_slug (backward compat fallback) ──
  for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
    try:
      state = json.loads(lock_file.read_text())
      if state.get("repo_slug") is not None and state.get("repo_slug") != current_slug:
        continue
      if _is_lock_stale(state):
        lock_file.unlink(missing_ok=True)
        continue
      if state.get("task_id", ""):
        return True
    except (json.JSONDecodeError, OSError):
      lock_file.unlink(missing_ok=True)
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

# Symlink the plugin from the Hermes Cortex repo
ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/

# Verify
ls -la ~/.hermes/plugins/governance-enforcer/
# Should show: __init__.py plugin.yaml

# Restart Hermes for changes to take effect
/reset  # or start a new hermes process
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

# On each agent machine, symlink:
ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/

# Run cortex-update to ensure repo is current:
cd ~/hermes-cortex && git pull origin main
bash ops/scripts/cortex-update.sh

# Then /reset the agent session
```

### Common Path (All Agents)

All fleet agents use the same path pattern — plugin source in the Cortex repo
is symlinked into `~/.hermes/plugins/`:

| Location | Path |
|----------|------|
| Source (repo) | `~/hermes-cortex/plugins/governance-enforcer/` |
| Deployed (symlink) | `~/.hermes/plugins/governance-enforcer/` → source |

The pattern is the same for all agents: repo source → symlink into `~/.hermes/plugins/`.

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

## Cron / Cold-Session Bootstrap

Cron sessions (detected by `cron_` prefix in the session ID) start with no
per-session skills marker. The enforcer blocks all write tools until skills are
loaded — but cron agents may not have `skill_view()` in their tool registry,
creating a bootstrapping deadlock.

**Solution:** The `_on_session_start` hook auto-creates a per-session marker
(`state/skills-loaded/<cron-session-id>`) for cron sessions by:

1. Reading `~/.hermes-cortex/skills.yaml` for the `always` section
2. Verifying each of the 8 required skills has a `SKILL.md` on disk under
   `~/.hermes/skills/`
3. If all skills are present, calling `_auto_create_skills_marker()` with the
   session ID — same function used when all `skill_view()` calls succeed

This means the cron agent's first tool call is **not blocked** by the skills
gate, because the marker was created during session initialization (before
any tool call). The agent can then proceed to load skills for content.

**Security properties:**
- Only cron sessions (`cron_*` session IDs) get the bootstrap — interactive
  sessions still require `skill_view()` calls
- The bootstrap validates all 8 required skills exist on disk before creating
  the marker
- The marker content includes the session ID (same verification as interactive)
- Missing skills.yaml or missing SKILL.md files → bootstrap skipped → cron
  session is blocked (correct behavior for corrupted environments)

---

## Writing Your Own pre_tool_call Plugin

To write a custom policy plugin (e.g. block all `docker run` commands):

```python
"""my-policy-plugin/__init__.py"""
import re

def register(ctx):
  def handler(tool_name, args, **kwargs):
    if tool_name == "terminal":
      command = args.get("command", "")
      if re.search(r"docker\s+run", command):
        return {
          "action": "block",
          "message": "Docker containers must be deployed via Docker Compose only. See ~/deploy/README.md",
        }
    return None # everything else passes

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

## Coverage Table

The enforcer intercepts tools at the `pre_tool_call` hook. Every agent tool
is classified into one of three tiers:

| Tier | Tools | What's Blocked |
|------|-------|----------------|
| **WRITE_TOOLS** | `write_file`, `patch`, `execute_code`, `memory`, `text_to_speech` | Tool use at all — requires governance lock unconditionally. Note: `execute_code` may also be blocked by Hermes' `approvals.cron_mode` before the enforcer's check fires — the block message you see depends on which system intercepts it first. Either way, the tool is correctly blocked. |
| **CONDITIONAL** | `terminal`, `cronjob`, `skill_manage`, `process`, `computer_use` | Specific write-type actions (see tables below) |
| **READ-ONLY** | `read_file`, `search_files`, `session_search`, `skill_view`, `skills_list`, `clarify`, `vision_analyze`, `todo` | Nothing — always allowed |
| **DELEGATION** | `delegate_task` | Not blocked — subagents have their own enforcer instance |

### Conditional Tool Write Actions

| Tool | Write Actions (blocked without lock) | Read Actions (allowed) |
|------|--------------------------------------|----------------------|
| `terminal` | `rm`, `mv`, `cp`, `git push`, `bash -c`, `python3 -c`, etc. (see pattern list) | `ls`, `cat`, `git status`, `python3 --version`, etc. |
| `cronjob` | `create`, `update`, `remove` | `list`, `run` |
| `skill_manage` | `create`, `edit`, `delete`, `write_file`, `remove_file`, `patch` | `view` (via separate `skill_view` tool) |
| `process` | `write`, `submit`, `kill`, `close` | `list`, `poll`, `log`, `wait` |
| `computer_use` | `click`, `double_click`, `right_click`, `middle_click`, `drag`, `scroll`, `type`, `key`, `set_value`, `focus_app` | `capture`, `wait`, `list_apps`, `list_windows` |

### Write Command Patterns (terminal)

```
rm|mv|cp|install|apt|apt-get|dpkg|pip|npm|brew|make|cmake|docker compose|kubectl
systemctl|service  start|stop|restart|reload|enable|disable|daemon-reload
chmod|chown|chattr|mkfs|fdisk|mount|umount|dd
sed|awk|tee  -i
git  push|commit|merge|rebase|reset|cherry-pick|branch -d/-D|tag|stash|checkout|restore|clean|rm|mv|update-ref|config|submodule
cronjob  create|update|remove|delete
python|python3  -c (inline code)
bash|sh|zsh  -c (inline commands)
python3  -m pip install
wget -O, curl -o
nohup
docker  run|build|push|commit|tag|save|load|rmi|system prune
crontab
usermod|groupmod|useradd|groupadd|passwd
ufw  enable|disable|allow|deny|reject|delete|reset
nginx -s reload|stop|quit
journalctl --rotate
echo|printf|cat|tee  with > or >> redirect
printf|cat  with << heredoc
touch|mkdir|ln|rsync|unzip|tar|mkfifo
npx|yarn|go|cargo|flatpak|snap
python3 script.py, node app.js, bash setup.sh (interpreter + .py/.js/.rb/.pl/.sh file)
```

## Upgrade: v1 (slug-based locks) → v2 (session-scoped locks)

The upgrade is handled automatically by `cortex-update.sh`, but here's what
happens and how to verify a clean upgrade.

### What changed

| Aspect | v1 (old) | v2 (new) |
|--------|----------|----------|
| **Lock file name** | `.governance-{repo-slug}.json` (e.g. `.governance-hermes-cortex.json`) | `.governance-{session_id}.json` (e.g. `.governance-sess_abc123.json`) |
| **Repo identification** | CWD-dependent `git rev-parse` | Stored in lock content as `repo_slug` field |
| **Enforcer check** | Single file by path | Scan all `.governance-*.json`, match by content |
| **Multiple sessions** | Not supported (one lock per repo) | Each session gets its own file |
| **Generic fallback** | `.governance-generic.json` written alongside every lock | Eliminated — session-scoped locks (`.governance-{session_id}.json`) used instead. All code references removed. |

### Upgrade steps

1. `git pull && bash ~/hermes-cortex/ops/scripts/cortex-update.sh `
  - Cleans all stale slug-based lock files automatically
  - Ensures the new enforcer source is deployed
2. `/reset` (new Hermes session)
  - The new enforcer loads with scan-based lock checking
3. Verify:
  - `bash ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --once`
  - Should show: `Governance coverage — PASS — all bypass closures validated`
  - Should show: `Governance locks — PASS — no lock files`

### Mid-upgrade agents

If you were mid-task when upgrading, your old lock file (without `repo_slug`)
is accepted by the new enforcer as valid — you can finish your work and call
`end_change()`. On the next `cortex-update` run, the old lock is cleaned.

## Key Lessons

1. **MCP servers cannot block built-in tools** — they only provide new tools. Enforcement must happen at the plugin level.
2. **Lock files are session-scoped** — each session gets its own `.governance-{session_id}.json`. The `repo_slug` is stored in the lock content, so the enforcer scans all locks and matches by content. This eliminates the cwd-mismatch problem entirely. Multiple sessions in the same repo can each hold a valid lock.
3. **The file system is the lock** — the governance lock is a file on disk. Any process on the same filesystem that reads it can enforce policy based on it. Processes on different filesystems can't — and that's a feature (remote backends block everything).
4. **Plugins compose** — multiple plugins can register `pre_tool_call` handlers. First block wins. This means you can layer security policies (Docker policy + governance + rate limiting) as independent plugins.
5. **Plugin changes require restart** — no hot-reload. Always `/reset` after installing or modifying a plugin.
6. **The agent cannot bypass this** — because the block comes from the Hermes runtime (Python process), not from the model's output or SOUL.md text, the agent cannot talk its way out of it.
7. **Every agent needs it** — if only one agent has the plugin, the others can freely skip governance. The source of truth is the repo; deploy the symlink to every agent.
8. **Bypass coverage is structural, not complete** — the enforcer covers all built-in Hermes tools and common shell bypass patterns. It cannot intercept MCP tools (separate process), but no MCP tool currently allows arbitrary file writes.
9. **Known coverage gaps (by design)** — `delegate_task` spawns subagents that have their own enforcer. `todo` is in-memory only. MCP tools run in a separate process and aren't intercepted by the plugin.
10. **Survey gate prevents redundant cron creation** — cron creation is blocked until the agent demonstrates it has surveyed existing resources by creating `~/.hermes-cortex/state/.cron-survey-done`. This prevents duplicate cron jobs and scripts.
11. **Fail-closed design** — if the enforcer encounters an internal error, it blocks ALL writes. Uncertainty defaults to blocking, not allowing. Recovery requires checking logs and restarting the session.
12. **Three bridge files** — the enforcer writes the session ID to three locations for MCP discovery: fixed-path marker (primary), PID-scoped marker (legacy), and `~/.hermes/session.id` (cached fallback). This ensures lock discovery works even when the MCP server starts before the enforcer fires its first tool call.

## Session ID Handoff Architecture

The enforcer and the MCP loop-governance server must agree on the session ID
to discover lock files. They use a **bridge file** mechanism:

### Data flow

```
Hermes session starts
 → kwargs['session_id'] = 'sess_20260724_123456_abc123' (with 'sess_' prefix)
 → Enforcer pre_tool_call fires on every tool call
  → _write_session_marker(hermes_session_id) writes:
    1. ~/.hermes-cortex/state/.hermes-session-current.id (primary bridge)
    2. ~/.hermes-cortex/state/.hermes-session-{pid}.id   (PID fallback)
    3. ~/.hermes/session.id                (MCP cache fallback)
 → MCP get_session_id() reads Priority 1:
    1. .hermes-session-current.id  ← primary (written by enforcer)
    2. .hermes-session-{pid}.id   ← PID scan (legacy fallback)
    3. ~/.hermes/session.id     ← cached (final fallback)
    4. Generate new UUID       ← no enforcer present (first tool call?)
```

### Critical rules

1. **The session ID always has the `sess_` prefix** — kwargs delivers it as
  `sess_20260724_...`. The bridge files and lock files use this exact format.
2. **`$HERMES_SESSION_ID` env var should NOT be used** — its format has no
  `sess_` prefix, so using it would create lock files the enforcer can't find.
3. **The bridge file is written on EVERY pre_tool_call** — not just on write tools.
  This ensures the MCP can discover the session ID even on the first tool call.
4. **Stale `__pycache__` can hide old enforcer code** — after updating the enforcer
  source, run: `rm -rf plugins/governance-enforcer/__pycache__ && /reset`
  The doctor warns about this automatically via the "Plugin pycache" check.

### Diagnostic: session ID mismatch

If you see "No active governance session" when a lock file clearly exists:

```bash
# Check what session ID the enforcer is using
cat ~/.hermes-cortex/state/.hermes-session-current.id

# List all lock files
ls ~/.hermes-cortex/state/.governance-*.json

# If the filename (sess_<id>) doesn't match the bridge file content,
# the handoff is broken. Run cortex-update to clear pycache and fix.
bash ~/hermes-cortex/ops/scripts/cortex-update.sh
```

### Root causes of drift

| Cause | Symptom | Fix |
|-------|---------|-----|
| Stale .pyc cache | Old enforcer code runs with old session ID logic | `rm -rf __pycache__ && /reset` |
| Bridge file not written | MCP falls back to PID scan, finds wrong session | Check OSError logs in enforcer |
| `$HERMES_SESSION_ID` env var used as Priority 1 | Lock filename has no `sess_` prefix | Ensure bridge file is Priority 1 (committed in loop-gov-mcp.py) |

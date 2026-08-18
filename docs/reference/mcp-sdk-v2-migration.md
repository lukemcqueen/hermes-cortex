# mcp SDK 2.0 Migration — Cortex MCP Servers

> Status: APPLIED 2026-08-18 (commit `8b6e738e`) — fleet rollout in progress.
> Applies to: `mcp-servers/loop-gov-mcp.py`, `mcp-servers/task-mcp.py`,
> `mcp-servers/cortex-bus-mcp.py`, `ops/scripts/manage/loop-gov-mcp.sh`,
> and every host's `~/.hermes/config.yaml` `mcp_servers:` block.

## Why this document exists

On 2026-08-18 every Hermes session on this host lost ALL MCP tools
(governance, agent-bus, tasks) with:

```
AttributeError: 'Server' object has no attribute 'list_tools'
  File ".../mcp-servers/loop-gov-mcp.py", line 557, in <module>
    @server.list_tools()
```

Root cause: the cortex MCP servers were written against the **pre-1.0 mcp
Python SDK** decorator API. hermes-agent's venv now pins **`mcp==2.0.0`**
(`pyproject.toml`), which removed the `@server.list_tools()` /
`@server.call_tool()` decorators. The servers crashed at import, so no
session got MCP tools — including the loop-governance tools the enforcer
needs before it allows any write. That is a **write-deadlock**: every agent
session was blocked until the fix landed out-of-band.

## The API change (old → new)

Both styles are supported by `mcp.server.Server` (2.0):

| Concern | Old (≤0.x) | New (2.0) |
|---|---|---|
| Register tool list | `@server.list_tools()` decorator | `Server(name, on_list_tools=fn)` constructor kwarg |
| Register call handler | `@server.call_tool()` decorator | `Server(name, on_call_tool=fn)` constructor kwarg |
| list_tools handler | `async def list_tools() -> list[Tool]` | `async def list_tools(ctx, params=None) -> ListToolsResult` — return `ListToolsResult(tools=[...])` |
| call_tool handler | `async def call_tool(name, arguments) -> CallToolResult` | `async def call_tool(ctx, params=None) -> CallToolResult` — read `params.name`, `params.arguments` |
| Result types | `Tool`, `TextContent`, `CallToolResult` | Same (from `mcp.types`, which mirrors `mcp_types`) — add `ListToolsResult` |
| stdio + run | `stdio_server()` + `server.run(read, write, server.create_initialization_options())` | **UNCHANGED** |

The constructor kwargs are `on_list_tools` / `on_call_tool` (plus
`on_list_resources`, `on_read_resource`, etc.). Handlers take
`(ctx, params)` where `ctx` is a `ServerRequestContext` and `params` is the
request params model (`params.name`, `params.arguments` on a
`CallToolRequestParams`).

## How to update a cortex MCP server (recipe)

1. Import `ListToolsResult`:
   `from mcp.types import Tool, TextContent, CallToolResult, ListToolsResult`
2. Delete the module-level `server = Server("NAME")` line and BOTH decorator
   lines (`@server.list_tools()`, `@server.call_tool()`).
3. Change the list handler signature and return:
   ```python
   async def list_tools(ctx, params=None) -> ListToolsResult:
       return ListToolsResult(tools=[ Tool(...), ... ])   # was: return [ ... ]
   ```
   (close the list with `])` instead of `]`).
4. Change the call handler:
   ```python
   async def call_tool(ctx, params=None) -> CallToolResult:
       name = params.name if params else ""
       args = (params.arguments or {}) if params else {}
       ...existing dispatch unchanged...
   ```
5. Construct the server AFTER both handlers are defined (before `main()`):
   ```python
   server = Server("NAME", on_list_tools=list_tools, on_call_tool=call_tool)
   ```
6. `main()` stays as-is (`stdio_server()` + `server.run(...,
   server.create_initialization_options())`).

## Verification checklist (mandatory before commit)

```bash
# 1. Compile
/home/esther/.hermes/hermes-agent/venv/bin/python3 -m py_compile <script>

# 2. Import + dispatch smoke test (proves the crash path is gone)
/home/esther/.hermes/hermes-agent/venv/bin/python3 - <<'EOF'
import asyncio, importlib.util
from types import SimpleNamespace
async def main():
    spec = importlib.util.spec_from_file_location("m", "<script>")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    lt = await m.list_tools(None, None)
    ct = await m.call_tool(None, SimpleNamespace(name="<a-tool>", arguments={}))
    print("tools:", len(lt.tools), "| dispatch:", ct.content[0].text[:80])
asyncio.run(main())
EOF

# 3. Adversarial gate — A4 for mcp-servers/ (enforced at commit too)
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <script> --level A4 --gate
```

## Config requirements (per host)

`~/.hermes/config.yaml` `mcp_servers:` — all three servers must use the
hermes-agent venv python and the DEPLOYED script path (never the repo tree
for the enforcement server — P1-A hardening):

```yaml
mcp_servers:
  agent-bus:
    command: /home/esther/.hermes/hermes-agent/venv/bin/python3   # NOT python3 (system lacks mcp)
    args: [ /home/esther/.hermes-cortex/scripts/cortex-bus-mcp.py ]
  loop-governance:
    command: /home/esther/.hermes/hermes-agent/venv/bin/python3
    args: [ /home/esther/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py ]  # immutable deployed copy
  tasks:
    command: /home/esther/.hermes/hermes-agent/venv/bin/python3
    args: [ /home/esther/.hermes-cortex/scripts/task-mcp.py ]
```

Apply with `hermes config set mcp_servers.<name>.command <path>` and
`hermes config set mcp_servers.<name>.args '["<path>"]'` (config.yaml is
protected from direct agent edits).

## Fleet rollout checklist

On EVERY host (Moses, Esther, Joseph, Kustos, Gisu, Titus):

1. `cd ~/hermes-cortex && git pull --rebase` (picks up `8b6e738e`)
2. `bash ops/scripts/cortex-update.sh` (deploys the migrated servers)
3. Apply the config block above (venv python + deployed paths)
4. Restart the gateway OUTSIDE the agent (`systemctl --user restart
   hermes-gateway` or your service manager) — MCP servers spawn per gateway
5. Verify: `tail -50 ~/.hermes/logs/mcp-stderr.log` shows clean
   "starting MCP server ... Initializing server" with NO `AttributeError`;
   run `hermes doctor` / cortex-doctor and confirm the three
   `✅ MCP server (...)` checks

## Outage recovery: the write-deadlock (what to do when loop-gov MCP is down)

The enforcer blocks ALL writes without a governance lock, and the lock tool
(`begin_change`) lives in the dead server — a structural deadlock. The
sanctioned recovery:

1. **Diagnose with read-only tools only** — `pgrep`, `ls`, `grep`,
   `search_files`, `read_file` are lock-free; so is the exact command
   `bash ~/hermes-cortex/ops/scripts/cortex-update.sh`.
2. **The fix must be authored out-of-band or with a user-minted lock.** The
   user (fleet owner) can create the session lock directly:
   `python3 -c "import json,datetime,pathlib;s='<SESSION_ID>';..."`
   (see the enforcer README for the lock schema; find your session id via
   `~/.hermes-cortex/state/.hermes-session-<gateway-pid>.id` or the
   `skills-loaded/` marker mtimes — the mtime of YOUR marker tells which
   session id is yours; a stale marker file from a sibling session is the
   classic trap).
3. Then: fix repo source → commit (pre-commit hook scores + adversarial
   gate) → sanctioned `cortex-update.sh` → push (pre-push dogfood deploys
   again) → restart the gateway → verify spawn.
4. Score any leaked PENDING/LOOP cycles from sessions the outage killed
   (the doctor's own remediation; `feedback_accept` semantics: PENDING/LOOP
   → MOVE_ON, `user_overrode=0`).

## Guardrail for the future

- **Never downgrade mcp in the hermes-agent venv** — hermes-agent core
  requires 2.0.0. Cortex servers must track the constructor API.
- **New MCP servers** must be written against the 2.0 constructor API (see
  the `mcp-server-building` skill — updated 2026-08-18).
- If you see `AttributeError: 'Server' object has no attribute 'list_tools'`
  in `~/.hermes/logs/mcp-stderr.log`, the mcp SDK moved again — migrate the
  servers (this doc) before restarting the gateway.

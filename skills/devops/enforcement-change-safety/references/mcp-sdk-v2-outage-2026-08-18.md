# mcp SDK 2.0 Outage — 2026-08-18 (write-deadlock incident)

Session evidence for Rule 15 of enforcement-change-safety. Fix commit:
`8b6e738e` (fleet rollout in progress; doc:
`docs/reference/mcp-sdk-v2-migration.md`).

## Crash signature

Every session lost ALL MCP tools (governance, agent-bus, tasks):

```
AttributeError: 'Server' object has no attribute 'list_tools'
  File ".../mcp-servers/loop-gov-mcp.py", line 557, in <module>
    @server.list_tools()
```

`~/.hermes/logs/mcp-stderr.log` also showed agent-bus failing separately with
`Required 'mcp' Python package not found` (system `/usr/bin/python3` has no
mcp package; the gateway resolved `python3` to its venv only via PATH).

## Root cause chain

1. hermes-agent's venv upgraded to `mcp==2.0.0` (pinned in its pyproject —
   a CORE requirement; never downgrade it).
2. mcp 2.0 removed the pre-1.0 decorator API used by all three cortex MCP
   servers (`@server.list_tools()` / `@server.call_tool()`).
3. Servers crashed at import → no MCP tools → the enforcer's lock tool
   (`begin_change`) unavailable → every session write-deadlocked
   (Rule 15).

Timeline: last good loop-gov spawn 07-23 22:57; first crash 08-18 09:52
(gateway restart after the SDK landed). The `mcp_stdio_watchdog` respawned
the servers with the FIXED files at 11:06–11:11 after the deploy — verify
with `ps -o lstart,etime -p <pid>` (stable) + a clean mcp-stderr tail.

## Old → new API (mcp.server.Server)

| Concern | Old (≤0.x) | New (2.0) |
|---|---|---|
| register tool list | `@server.list_tools()` | `Server(name, on_list_tools=fn)` |
| register call | `@server.call_tool()` | `Server(name, on_call_tool=fn)` |
| list handler | `async def list_tools() -> list[Tool]` | `async def list_tools(ctx, params=None) -> ListToolsResult` — return `ListToolsResult(tools=[...])` |
| call handler | `async def call_tool(name, arguments)` | `async def call_tool(ctx, params=None)` — read `params.name`, `params.arguments` |
| types | `Tool, TextContent, CallToolResult` from `mcp.types` (mirrors `mcp_types`) | same + `ListToolsResult` |
| stdio/run | `stdio_server()` + `server.run(read, write, server.create_initialization_options())` | UNCHANGED |

Handlers must be defined BEFORE `Server(...)` construction (constructor
kwargs, not decorators). `mcp.types` is a wildcard mirror of the standalone
`mcp_types` package.

## Migration recipe (per server)

1. `from mcp.types import Tool, TextContent, CallToolResult, ListToolsResult`
2. Delete `server = Server("NAME")` and both decorator lines.
3. list handler: `async def list_tools(ctx, params=None) -> ListToolsResult:
   return ListToolsResult(tools=[ ... ])` (close `])`, not `]`).
4. call handler: `name = params.name if params else ""`,
   `args = (params.arguments or {}) if params else {}` — dispatch unchanged.
5. Before `main()`: `server = Server("NAME", on_list_tools=list_tools,
   on_call_tool=call_tool)`.
6. `main()` unchanged.

## Verification (before commit)

```bash
venv=$HOME/.hermes/hermes-agent/venv/bin/python3
$venv -m py_compile <script>
$venv - <<'EOF'
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
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <script> --level A4 --gate
```

## Config (per host, ~/.hermes/config.yaml via `hermes config set`)

All three servers: command = hermes venv python; args = DEPLOYED copies:
- agent-bus → `~/.hermes-cortex/scripts/cortex-bus-mcp.py`
- loop-governance → `~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py`
  (immutable, P1-A — never the repo tree)
- tasks → `~/.hermes-cortex/scripts/task-mcp.py`

`hermes config set mcp_servers.<name>.args '["<path>"]'` for list values.
Direct `patch`/`write_file` on config.yaml is refused by Hermes itself —
the CLI is the only path.

## Session-id forensics (the mint trap)

- `state/.hermes-session-<gateway-pid>.id` is rewritten by EVERY tool call
  from ANY session on the gateway → last-writer-wins, may show a SIBLING
  session's id. NOT trustworthy.
- Truth: `state/skills-loaded/<id>` markers — `stat` each candidate; the one
  whose mtime ≈ when YOU loaded the 8 always-skills is yours.
- A lock minted for the wrong id keeps blocking: Phase 1 exact-match misses,
  and Phase 2's session-match tightening
  (`if hermes_session_id and lock_session and lock_session != hermes_session_id: continue`)
  skips it. Gateway CWD is `/home/<user>` (not a repo) so the repo-slug
  fallback is a no-op.

## Cycle scoring with the tool down

`~/.hermes-cortex/data/loop-governance.db`, table `loop_cycles` (NOT
`cycles`; column is `timestamp`, not `created_at`):
PENDING/LOOP → `UPDATE loop_cycles SET user_overrode=0, decision='MOVE_ON',
outcome_note='...' WHERE id=?` (exact feedback_accept semantics). Only for
dead sessions (stale/absent lock). The pre-push dogfood counts leaked
PENDING cycles as a hard FAIL.

## Deploy-marker push pitfall (bit twice)

Doctor `Deploy sync` = HEAD vs the last-deploy commit marker. Committing
after a deploy without re-deploying → the push's dogfood reports
`❌ Deploy sync — HEAD ahead of last deploy — N commit(s) not deployed`
even when content is already deployed. Fix: run the sanctioned
`bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (prints
`State saved: <sha>`) immediately before pushing, then push.

## Fleet rollout (other hosts)

`git pull --rebase` → `bash ops/scripts/cortex-update.sh` → `hermes config
set mcp_servers.*` ×3 → restart gateway → verify mcp-stderr clean +
doctor `✅ MCP server (...)` ×3.

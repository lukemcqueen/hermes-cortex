# MCP Server Diagnostics — Orphaned Watchdog / Missing Script

## Error Signal

An MCP tool (e.g. `mcp__*__inbox_read`, `mcp__*__some_tool`) returns HTTP 4xx/5xx, but:

- The MCP server **process is alive** (`pgrep -af <script-name>` shows it running)
- The process was spawned by the `mcp_stdio_watchdog.py` (parent process)
- **The underlying script file does not exist** at the path configured in `config.yaml`

## Root Cause

The MCP server's wrapper/entry-point file was removed from the filesystem (repo reorg, intentional purge, never created) but the **config entry** in `config.yaml` still references it, and:

1. Hermes startup spawns `mcp_stdio_watchdog.py` with the non-existent path
2. The watchdog keeps the process alive (it waits for the child to exit, but the child may be a `fork+exec` that never fully initializes)
3. MCP tools attempt to connect via HTTP to the dead/non-functional server → 4xx/5xx

## Diagnosis

```bash
# 1. List all MCP servers defined in config
grep -A3 'mcp_servers:' ~/.hermes/config.yaml
# or find the specific server section
grep -B2 -A5 '<server-name>' ~/.hermes/config.yaml

# 2. Check if the underlying file exists
ls -la /path/from/config.yaml/to/script.py 2>&1

# 3. Find any orphaned watchdog processes
ps aux | grep mcp_stdio_watchdog | grep -v grep

# 4. For each watchdog, check what it's running
cat /proc/<watchdog-pid>/cmdline | tr '\0' ' '
# → the last args after '--' are the MCP server command

# 5. Verify the child process state
cat /proc/<child-pid>/status | grep -E '^(Name|State|Pid)'
# State 'Z' = zombie; 'S'/'D' = sleeping/waiting but functional
```

## Fix Options

### Option A — Recreate the missing script

If the MCP server is still needed (the function was valuable):

1. Check what the script was supposed to do — search for references in docs, other configs, git history
2. Create the file at the expected path
3. Verify end-to-end: kill the stale watchdog + children, then the next Hermes MCP init will re-spawn cleanly

### Option B — Remove stale config entry

If the MCP server was replaced by another system (e.g., legacy inbox → Agent Bus PGMQ):

1. Remove/comment out the server entry in `~/.hermes/config.yaml` under `mcp_servers:`
2. Kill the orphaned watchdog and child processes
3. Verify: `mcp__*__*` tools for that server should no longer appear in tool listings

## Key Difference From Cron Scripts

| Concern | Cron Script Missing | MCP Server Script Missing |
|---------|-------------------|---------------------------|
| Error surface | `last_status: error` in cron list | MCP tools return HTTP 4xx/5xx silently |
| Process state | Script just doesn't run | Watchdog keeps zombie/child alive |
| Discovery | Cron alert or scan | Tool invocation failure |
| Fix urgency | Next cron tick | Every MCP tool call fails |
| Side effect | None | Orphaned process consuming resources |

## Prevention

- When deprecating an MCP server: **delete the config entry** AND the script file, not just the file. Remove both ends of the reference.
- When renaming/relocating MCP scripts: update `config.yaml` path **before** deleting the old file — zero-downtime.
- Audit stale MCP servers periodically: check every server in `config.yaml` has a real, executable file at its configured path.

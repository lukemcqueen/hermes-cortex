# Troubleshooting: Stale `/api/inbox` References & MCP Server Path Issues

## Issue 1: Dead HTTP Inbox API References

**Symptom:** Scripts hitting `GET /api/inbox` on the old HTTP inbox endpoint (returning 404 / connection refused). Hundreds of 404 entries in the health server log.

**Root cause:** The v1 HTTP inbox API was retired in favor of the PGMQ Agent Bus (`lib.cortex_bus`). Multiple scripts still had hardcoded references to the dead endpoint:

- `bus/bus-sensor.py`, `agent/inbox-sensor.py`, `inbox/inbox-sensor.py` — duplicate sensors polling the dead API
- `bus/agent-bus-monitor.sh` — shell script polling `/api/inbox`
- `orch-bus/orch-bus-sensor.py` — same pattern on orchestrator side
- `cortex-bus-mcp.py` — had entire fallback block for `/api/inbox` in `_inbox_read()` and `_inbox_watch()`
- `inbox_watcher.py` — had dead `fetch_inbox_html()` function using HTTP inbox
- Various local-only scripts (`agent-inbox-processor.py`, `inbox-mcp-updated.py`, etc.)

**Fix:**

1. **Deleted** 6 dead sensor scripts from the repo
2. **Converted** `bus/bus-processor.py` to use `bus_list_queues()` (peek depth without consuming) + `bus_read()`/`bus_archive()` (read-archive cycle for inspection)
3. **Converted** `orch-bus/orch-bus-watch.sh` to query `/api/pgmq/queues` (depth API) instead of `/api/inbox`
4. **Converted** `orch-bus/orch-bus-mcp.py` to use `api/pgmq` regex instead of `api/inbox`
5. **Stripped fallback blocks** from `cortex-bus-mcp.py` — both `_inbox_read()` and `_inbox_watch()` now only use PGMQ
6. **Rewrote** `inbox_watcher.py` tool to use `bus_read()` primary, legacy file scan fallback

## Issue 2: Health Server Zombie

**Symptom:** The old `health-server.py` (FastAPI) was deleted from the repo but the process continued running from an in-memory binary because the source file didn't exist on disk anymore. The systemd service still pointed to the deleted file.

**Root cause:** `health-server.py` was replaced by `health-vector.py` (zero-dependency Python stdlib). The systemd unit `ExecStart=` was never updated, and `health-vector.py` requires `--serve <port>` to run as an HTTP server (it's a dual-mode script: standalone reporter or HTTP server).

**Fix:**

1. Updated both systemd units (`com.hermes.health-server.service` and `hermes-health-server.service`) to point to `health-vector.py --serve 8905`
2. The `--serve` flag and port argument are required — without them the script runs once and exits

## Issue 3: MCP Server Path Mismatch (Most Critical)

**Symptom:** `mcp_loop_governance_*` MCP tools never appeared in the agent's tool list. Agents fell back to manually creating `.governance-generic.json` lock files (the old format).

**Root cause:** `config.yaml` had:

```yaml
mcp_servers:
 loop-governance:
  args:
   - /home/user/hermes-cortex/runtime/mcp-servers/loop-gov-mcp.py  # ❌ doesn't exist
 agent-bus:
  args:
   - /home/user/hermes-cortex/runtime/mcp-servers/cortex-bus-mcp.py # ❌ doesn't exist
```

The actual files are at `mcp-servers/` (not `runtime/mcp-servers/`). The `runtime/` prefix was a leftover from a directory rename that was never propagated to config.yaml.

**Fix:**

```yaml
mcp_servers:
 loop-governance:
  args:
   - /home/user/hermes-cortex/mcp-servers/loop-gov-mcp.py  # ✅ correct path
 agent-bus:
  args:
   - /home/user/hermes-cortex/mcp-servers/cortex-bus-mcp.py  # ✅ correct path
```

**Verification:** The doctor checks `✅ MCP server (loop-governance) — configured in config.yaml` and `✅ MCP Python (loop-governance) — uses venv:` but does NOT verify the script file actually exists at the configured path. Consider adding a path-existence check to the doctor.

## Issue 4: cortex-update.sh Missing loop-gov-mcp Registration

**Symptom:** `cortex-update.sh ` does NOT deploy `loop-gov-mcp.py` anywhere.

**Check:** Search for `loop-gov-mcp.py` in `cortex-update.sh` — only `loop-gov-mcp.sh` (a shell wrapper) is registered, not the actual MCP server.

**Status:** Not critical — `config.yaml` points directly to the repo path, so the file lives at source. But if the repo is ever restructured, this will break silently.

## Cleanup Pattern: Removing Dead `/api/inbox` Scripts

When removing scripts that hit the old HTTP inbox API:

1. Check if the script is registered in `cortex-update.sh` (`register` lines)
2. If registered, remove the registration line AND delete the source file
3. `git rm` the source file from the repo
4. After push, run `cortex-update.sh ` to sync
5. Manually remove any orphaned local copies (cortex-update doesn't delete files that no longer have a source mapping)

The correct way to read the bus:

```python
# ✅ Modern: PGMQ bus
from lib.cortex_bus import bus_read, bus_send, bus_archive, bus_list_queues

# Check queue depth without consuming (peek)
queues = bus_list_queues()
inbox = next((q for q in queues if q["name"] == f"inbox_{agent}"), {})
depth = inbox.get("depth", 0)

# Read and process
msg = bus_read(f"inbox_{agent}", vt=60)
if msg:
  body = msg.get("body", {})
  bus_archive(f"inbox_{agent}", msg["msg_id"])
```

```python
# ❌ Dead: HTTP inbox API
requests.get(f"{url}/api/inbox?for={agent}&unread_only=true")
```

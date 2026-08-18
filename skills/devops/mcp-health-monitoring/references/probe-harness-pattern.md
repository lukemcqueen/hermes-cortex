# Watchdog Probe Test-Harness Pattern (fault injection, no test framework needed)

Discovered/validated 2026-08-18 while fixing the tirith false-positive
(`script not found: mcp-server` loop). This is the recipe for testing ANY
config-driven watchdog/probe script in-process, including against the
DEPLOYED copy — reusable for agent-langfuse-health-watchdog,
agent-model-health-watchdog, agent-service-recovery, etc.

Canonical example in the repo: `tests/test_mcp_health_watchdog.py` (7
scenarios). Run it against the deployed copy with
`WD_WATCHDOG_PATH=~/.hermes-cortex/scripts/agent-mcp-health-watchdog.py`.

## The recipe

1. **Load the watchdog module in-process and repoint its I/O constants:**
   ```python
   spec = importlib.util.spec_from_file_location("wd", WATCHDOG_PATH)
   wd = importlib.util.module_from_spec(spec)
   spec.loader.exec_module(wd)
   wd.CONFIG_PATH = tmp / "config.yaml"     # module globals are patchable
   wd.STATE_FILE = tmp / "state.json"
   wd.MCP_LOG_DIR = tmp / "logs"
   wd.PROBE_TIMEOUT = 3                      # fast tests
   ```
   No mocking framework, no pytest needed — the watchdog reads module-level
   constants at call time, so repointing them isolates it from the real
   `~/.hermes/config.yaml` and `mcp-health-state.json`.

2. **Fixture servers cover the failure-class matrix:**
   - `fakebin mcp-server` — healthy binary-CLI (args[0] is a SUBCOMMAND, not
     a file). Responds to `initialize` with serverInfo; rejects `tools/list`
     with -32601 (resource-only shape — must still PASS).
   - `crashbin` — exits 1 with a distinctive stderr line (real outage shape).
   - `hangbin` — sleeps forever (no initialize response).
   - `fakepyserver.py` — module-level `async def list_tools` (legacy .py
     import-probe shape).

3. **Assert on behavior, not internals:** run `wd.main()` with
   `contextlib.redirect_stdout`; assert on alert text ("MCP server down"),
   the REAL failure reason (stderr line / "timed out"), absence of the wrong
   reason, and silence when healthy.

4. **2-strike trap:** alert logic fires on the 2nd consecutive failure —
   a single-run assertion that an alert text appears will FAIL by design.
   Run `runs=2` for alert scenarios, `runs=1` for healthy/missing-config.

5. **Recovery test needs a CONSTANT server key:** state is keyed by the
   config server key, so the outage→recovery scenario must swap the binary
   under the SAME key (`target:` → crashbin, then `target:` → fakebin).
   Different keys = fresh state = no RECOVERED notice (test bug, not code).

6. **Prove deploy parity:** run the SAME suite against the deployed copy via
   an env override — it should FAIL there until `cortex-update.sh` runs.
   That green-on-deployed result is the evidence the cron actually runs the
   fixed code (the doctor's checksum check compares repo vs deployed, but a
   suite run against `~/.hermes-cortex/scripts/...` proves behavior).

## Pitfalls discovered while building it

- **`Path(os.environ.get("X", ""))` is truthy** — `Path("")` resolves to
  `Path(".")`, so `env or default` short-circuits to the WRONG path and
  `spec_from_file_location` returns None (crash: `'NoneType' object has no
  attribute 'loader'`). Guard with `_env = os.environ.get(...); Path(_env)
  if _env else default`.
- **The watchdog's own fixtures must be executable** (`chmod +x`) and the
  config's `command:` must be the ABSOLUTE fixture path (relative resolves
  against the watchdog's cwd, not the test's).
- **stdio probe deadline semantics:** reader thread + `join(timeout)`;
  `None` = timed out, `''` = EOF (process exited). EOF → read stderr for the
  real failure line; timeout → "timed out" message; always `proc.kill()` in
  finally.
- **`check_required` needs non-empty names for unmanaged servers** — the
  stdio probe returns `"name v version"` when tools/list is unsupported, so
  resource-only servers stay healthy instead of tripping "zero tools".

## Reference: the stdio initialize handshake (binary-CLI servers)

```python
init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "agent-mcp-health-watchdog",
                                  "version": "1.0"}}}
# serverInfo in the result = ALIVE. tools/list is opportunistic:
# -32601 (method not found) is NORMAL for resource-only servers — never
# fail on it; the handshake alone is the health signal.
```

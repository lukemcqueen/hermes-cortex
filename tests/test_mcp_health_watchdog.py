#!/usr/bin/env python3
"""Fault-injection suite for agent-mcp-health-watchdog probe logic.

Regression test for the 2026-08-18 false-positive loop: the probe treated
args[0] as a Python script file path, so binary-CLI servers (e.g.
`tirith mcp-server`, where args[0] is a subcommand) failed with
'script not found: mcp-server' every 5 minutes and alerted hourly while
perfectly healthy.

Scenarios:
  A: healthy binary-CLI server (the tirith class) -> MUST stay silent
  B: crashing binary-CLI server                   -> MUST fail with the REAL stderr reason
  C: hanging binary-CLI server                    -> MUST fail with timeout
  D: python-script server (legacy shape)          -> MUST stay healthy via import path
  F: no command configured                        -> fail fast
  G: no args configured                           -> fail fast
  R: outage -> recovery                           -> "MCP server recovered" notice

Run:  python3 tests/test_mcp_health_watchdog.py
Optional: WD_WATCHDOG_PATH=/path/to/agent-mcp-health-watchdog.py to test a
specific copy (e.g. the deployed one).
"""
import contextlib
import importlib.util
import io
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]  # repo root (tests/ is one level down)
_env = os.environ.get("WD_WATCHDOG_PATH")
WATCHDOG = Path(_env) if _env else (
    REPO / "ops" / "scripts" / "health" / "agent-mcp-health-watchdog.py"
)

FAKEBIN = r'''#!/usr/bin/env python3
"""Fake binary-CLI MCP server: invoked as `fakebin mcp-server`."""
import json, sys

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def main():
    if len(sys.argv) < 2 or sys.argv[1] != "mcp-server":
        print("usage: fakebin mcp-server", file=sys.stderr)
        return 1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg.get("id"),
                  "result": {"protocolVersion": "2024-11-05",
                             "capabilities": {"resources": {}},
                             "serverInfo": {"name": "faketirith", "version": "0.3.1"}}})
        elif method == "tools/list":
            # Resource-only server: tools/list unsupported — must still pass.
            send({"jsonrpc": "2.0", "id": msg.get("id"),
                  "error": {"code": -32601, "message": "Method not found"}})
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

CRASHBIN = r'''#!/usr/bin/env python3
import sys
print("fakebin: fatal: cannot connect to backend", file=sys.stderr)
sys.exit(1)
'''

HANGBIN = r'''#!/usr/bin/env python3
import time
time.sleep(3600)
'''

FAKE_PY_SERVER = '''"""Fake python-script MCP server (mcp 2.0 constructor-API import shape)."""
import sys
from types import SimpleNamespace


async def list_tools(ctx, params=None):
    return SimpleNamespace(tools=[SimpleNamespace(name="fake_tool_one")])


if __name__ == "__main__":
    sys.exit(0)
'''

OLDAPI_PY_SERVER = '''"""Fake OLD-API decorator python MCP server (mcp 1.x, list_tools() takes NO args).

The SDK-2.0 import probe calls list_tools(None, None), which this server
rejects with TypeError — the watchdog must fall back to a real stdio
handshake instead of reporting it down. (titus PROPOSAL follow-up
70cfc4f9, 2026-08-18)
"""
import json
import sys


async def list_tools():
    return [{"name": "oldapi_tool"}]


async def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        if method == "initialize":
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "oldapi-server", "version": "1.0.0"},
                },
            }) + "\\n")
            sys.stdout.flush()
        elif method == "tools/list":
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {"tools": [{"name": "oldapi_tool"}]},
            }) + "\\n")
            sys.stdout.flush()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''


def make_fixtures(tmp: Path) -> dict:
    """Write the fake servers; return {name: path}."""
    paths = {}
    for name, content, executable in (
        ("fakebin", FAKEBIN, True),
        ("crashbin", CRASHBIN, True),
        ("hangbin", HANGBIN, True),
        ("fakepyserver.py", FAKE_PY_SERVER, False),
        ("oldapiserver.py", OLDAPI_PY_SERVER, False),
    ):
        p = tmp / name
        p.write_text(content, encoding="utf-8")
        if executable:
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        paths[name] = p
    return paths


def load_wd(tmp: Path):
    spec = importlib.util.spec_from_file_location("wd", str(WATCHDOG))
    wd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wd)
    wd.CONFIG_PATH = tmp / "config.yaml"
    wd.STATE_FILE = tmp / "state.json"
    wd.MCP_LOG_DIR = tmp / "logs"
    wd.PROBE_TIMEOUT = 3  # fast tests
    return wd


def write_config(tmp: Path, config_text: str):
    (tmp / "config.yaml").write_text("mcp_servers:\n" + config_text, encoding="utf-8")


def fresh_state(tmp: Path):
    if (tmp / "state.json").exists():
        (tmp / "state.json").unlink()


def run_wd(wd, tmp: Path, config_text: str, runs: int = 1) -> str:
    write_config(tmp, config_text)
    fresh_state(tmp)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for _ in range(runs):
            wd.main()
    return buf.getvalue().strip()


def main() -> int:
    results: list[tuple[str, bool]] = []
    tmp = Path(tempfile.mkdtemp(prefix="wdtest-"))
    try:
        fx = make_fixtures(tmp)

        def check(name: str, passed: bool, out: str):
            results.append((name, passed))
            print(("PASS" if passed else "FAIL") + f"  {name}")
            if not passed:
                print("     out:", out[:500].replace("\n", " | "))

        # --- A: healthy binary-CLI (the tirith class) -> silent after 2 runs ---
        out = run_wd(
            load_wd(tmp), tmp,
            f"""  fakebin:
    command: {fx['fakebin']}
    args:
      - mcp-server
    enabled: true
""",
            runs=2,
        )
        check("A healthy binary-CLI stays silent (no 'script not found' loop)", out == "", out)

        # --- B: crashing binary-CLI -> real stderr reason, not 'script not found' ---
        out = run_wd(
            load_wd(tmp), tmp,
            f"""  crashbin:
    command: {fx['crashbin']}
    args:
      - mcp-server
    enabled: true
""",
            runs=2,
        )
        check(
            "B crashed binary fails loudly with real reason",
            "MCP server down (non-critical)" in out
            and "cannot connect to backend" in out
            and "script not found" not in out,
            out,
        )

        # --- C: hanging binary-CLI -> timeout ---
        out = run_wd(
            load_wd(tmp), tmp,
            f"""  hangbin:
    command: {fx['hangbin']}
    args:
      - mcp-server
    enabled: true
""",
            runs=2,
        )
        check("C hanging binary fails with timeout", "timed out" in out, out)

        # --- D: python-script server (legacy shape) -> healthy via import path ---
        out = run_wd(
            load_wd(tmp), tmp,
            f"""  fakepyserver:
    command: {sys.executable}
    args:
      - {fx['fakepyserver.py']}
    enabled: true
""",
            runs=1,
        )
        check("D python-script server stays healthy via import path", out == "", out)

        # --- E: OLD-API python server (list_tools() takes no args) ->
        # import probe TypeError must fall back to stdio handshake ---
        out = run_wd(
            load_wd(tmp), tmp,
            f"""  oldapiserver:
    command: {sys.executable}
    args:
      - {fx['oldapiserver.py']}
    enabled: true
""",
            runs=2,
        )
        check("E old-API python server healthy via stdio fallback (TypeError)", out == "", out)

        # --- P: phantom keys — platform_toolsets children must NOT become
        # servers when the regex parser is used (yaml-less host) ---
        wd = load_wd(tmp)
        write_config(
            tmp,
            f"""  realserver:
    command: {fx['fakebin']}
    args:
      - mcp-server
    enabled: true
""",
        )
        # Append a platform_toolsets section AFTER mcp_servers — the regex
        # parser previously treated its 2-space children as phantom servers.
        config_path = tmp / "config.yaml"
        config_path.write_text(
            config_path.read_text()
            + "platform_toolsets:\n  cli:\n    enabled: true\n  discord:\n    enabled: true\n",
            encoding="utf-8",
        )
        # Force the yaml-less regex path
        old_yaml = wd.yaml
        wd.yaml = None
        try:
            servers = wd.load_servers()
        finally:
            wd.yaml = old_yaml
        check(
            "P platform_toolsets children are NOT phantom servers",
            set(servers.keys()) == {"realserver"},
            f"parsed: {sorted(servers.keys())}",
        )

        # --- F: no command -> fail fast (after 2 strikes) ---
        out = run_wd(
            load_wd(tmp), tmp,
            """  badserver:
    command: ""
    args:
      - mcp-server
    enabled: true
""",
            runs=2,
        )
        check("F missing command fails fast", "no command configured" in out, out)

        # --- G: no args -> fail fast (not 'script not found: <none>') ---
        out = run_wd(
            load_wd(tmp), tmp,
            f"""  noargs:
    command: {sys.executable}
    args: []
    enabled: true
""",
            runs=2,
        )
        check("G missing args fails fast", "no script/args configured" in out, out)

        # --- R: outage -> recovered notice (same server key across configs) ---
        wd = load_wd(tmp)
        write_config(
            tmp,
            f"""  target:
    command: {fx['crashbin']}
    args:
      - mcp-server
    enabled: true
""",
        )
        fresh_state(tmp)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            wd.main()
            wd.main()  # 2 strikes -> alert
        write_config(
            tmp,
            f"""  target:
    command: {fx['fakebin']}
    args:
      - mcp-server
    enabled: true
""",
        )
        with contextlib.redirect_stdout(buf):
            wd.main()  # healthy again
        check("R outage->recovery emits RECOVERED notice", "MCP server recovered" in buf.getvalue(), buf.getvalue())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, p in results if not p]
    print(f"\n{len(results) - len(failed)}/{len(results)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

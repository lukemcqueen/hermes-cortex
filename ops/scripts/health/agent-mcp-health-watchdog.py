#!/usr/bin/env python3
"""agent-mcp-health-watchdog.py — Governance MCP health watchdog.

no_agent watchdog pattern:
  Empty stdout -> silent (all configured MCP servers healthy)
  Text output  -> delivered (CRITICAL/WARNING alert or recovery notice)

Probes every MCP server configured in ~/.hermes/config.yaml by spawning the
server's configured python to import the server script and call list_tools,
verifying required tool names are present. Also scans ~/.hermes/logs/
mcp-stderr*.log for import-crash signatures (the 2026-08-18 MCP SDK 2.0 class:
servers crashed at import, governance tools vanished, every session
write-deadlocked until an out-of-band fix).

Severity (M-001/M-002, docs/elicit/2026-08-18_governance-fail-loudly-party.md):
  loop-governance / tasks down -> CRITICAL (write-deadlock risk — ALL WRITES BLOCKED)
  agent-bus (cortex-bus) down   -> WARNING  (no deadlock)
  unknown configured server     -> WARNING  (probed generically)

Fires after 2 consecutive probe failures per server (transient tolerance),
re-alerts at most hourly, and emits a recovery notice when a server passes
again. A fresh import-crash signature in mcp-stderr.log fires immediately
(definitive evidence — see docs/reference/mcp-sdk-v2-migration.md).

Probes are read-only and need no governance lock: the watchdog runs fine even
while every agent session is deadlocked, which is exactly when it matters.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback path
    yaml = None

HOME = Path.home()
CONFIG_PATH = HOME / ".hermes" / "config.yaml"
STATE_FILE = HOME / ".hermes-cortex" / "state" / "mcp-health-state.json"
MCP_LOG_DIR = HOME / ".hermes" / "logs"

PROBE_TIMEOUT = 30          # seconds per server probe
STRIKES_TO_ALERT = 2        # consecutive probe failures before alerting
REALERT_COOLDOWN = 3600     # seconds between repeated alerts for one incident

CRITICAL = "CRITICAL"
WARNING = "WARNING"

# Live config server key -> (display name, severity, required tool names)
# Config uses `agent-bus`; the doctor's canonical name is `cortex-bus`.
EXPECTED_TOOLS = {
    "loop-governance": ("loop-governance", CRITICAL, ["begin_change", "end_change", "check_lock"]),
    "tasks": ("tasks", CRITICAL, ["task_add", "task_update"]),
    "agent-bus": ("agent-bus (cortex-bus)", WARNING, ["inbox_read", "inbox_send"]),
    "cortex-bus": ("agent-bus (cortex-bus)", WARNING, ["inbox_read", "inbox_send"]),
}

RECOVERY_HINT = (
    "Recovery: fix repo source -> bash ops/scripts/cortex-update.sh -> restart "
    "gateway. See docs/reference/mcp-sdk-v2-migration.md. Escalate to the "
    "orchestrator if needed."
)

# Import-crash signatures that prove an MCP server died at spawn. Kept narrow to
# avoid false positives from routine MCP churn.
CRASH_PATTERNS = [
    re.compile(r"AttributeError: 'Server' object has no attribute"),
    re.compile(r"ModuleNotFoundError: No module named"),
    re.compile(r"ImportError: cannot import name"),
    re.compile(r"mcp SDK \S+ requires constructor API"),
]

# Probe snippet: import the server script, call list_tools, print JSON tool
# names. Mirrors the migration doc verification recipe. Runs under the server's
# OWN configured python so SDK drift in that interpreter is caught.
PROBE_CODE = r"""
import asyncio, importlib.util, json, sys
spec = importlib.util.spec_from_file_location("_mcp_probe", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
async def _run():
    lt = await m.list_tools(None, None)
    tools = getattr(lt, "tools", lt)
    print(json.dumps([getattr(t, "name", str(t)) for t in tools]))
asyncio.run(_run())
"""


def kst_ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone(timedelta(hours=9))).strftime("%H:%M KST")


def now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def load_servers() -> dict:
    """Parse ~/.hermes/config.yaml -> {server_key: {command, args, enabled}}."""
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"config not found: {CONFIG_PATH}")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    if yaml is not None:
        try:
            data = yaml.safe_load(text) or {}
            raw = data.get("mcp_servers") or {}
            servers = {}
            for key, val in raw.items():
                if not isinstance(val, dict):
                    continue
                args = val.get("args") or []
                if isinstance(args, str):
                    args = [args]
                servers[str(key)] = {
                    "command": val.get("command") or "",
                    "args": [str(a) for a in args],
                    "enabled": bool(val.get("enabled", True)),
                }
            return servers
        except Exception:
            pass  # fall through to regex parser
    return _parse_without_yaml(text)


def _parse_without_yaml(text: str) -> dict:
    """Minimal fallback for hosts without PyYAML (config shape is regular)."""
    servers: dict = {}
    in_mcp = False
    cur: str | None = None
    for line in text.splitlines():
        if re.match(r"^mcp_servers:\s*$", line):
            in_mcp = True
            continue
        if not in_mcp:
            continue
        # Stop at the next top-level section (e.g. platform_toolsets:) —
        # its 2-space-indented children must not become phantom servers.
        # (titus PROPOSAL follow-up 70cfc4f9, 2026-08-18)
        if re.match(r"^\S", line):
            break
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
        if m:
            cur = m.group(1)
            servers[cur] = {"command": "", "args": [], "enabled": True}
            continue
        if cur is None:
            continue
        m = re.match(r"^    command:\s*(\S+)", line)
        if m:
            servers[cur]["command"] = m.group(1)
            continue
        m = re.match(r"^      -\s*(\S+)", line)
        if m:
            servers[cur]["args"].append(m.group(1))
            continue
        m = re.match(r"^    enabled:\s*(true|false)", line)
        if m:
            servers[cur]["enabled"] = m.group(1) == "true"
    return servers


def probe_server(command: str, args: list) -> tuple[bool, str]:
    """Probe one MCP server. Returns (ok, detail).

    Python-script servers (args[0] is an existing .py file) are probed by
    spawning the configured interpreter to import + list_tools — fast, and it
    catches import crashes (the 2026-08-18 MCP SDK class).

    Binary-CLI servers (args[0] is a subcommand, not a file — e.g.
    `tirith mcp-server`) get a REAL stdio initialize handshake instead.
    Treating a subcommand as a script path produced the 2026-08-18
    'script not found: mcp-server' false-positive loop (tirith, Gisu report).
    """
    if not command:
        return False, "no command configured"
    if not args:
        return False, "no script/args configured"
    first = args[0]
    if first.endswith(".py") and os.path.exists(first):
        ok, detail = _probe_python_script(command, first)
        if ok:
            return True, detail
        # Old-API decorator servers (async def list_tools() with no params)
        # reject the SDK-2.0 probe call shape list_tools(None, None) with
        # TypeError — the import probe is the wrong tool for them. Fall back
        # to the real stdio handshake, which is API-agnostic. (titus
        # PROPOSAL follow-up 70cfc4f9, 2026-08-18)
        if "TypeError" in detail:
            return _probe_stdio_handshake(command, args)
        return False, detail
    return _probe_stdio_handshake(command, args)


def _probe_python_script(command: str, script: str) -> tuple[bool, str]:
    """Spawn the server's python to import + list_tools. Returns (ok, detail)."""
    try:
        proc = subprocess.run(
            [command, "-c", PROBE_CODE, script],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            cwd=str(HOME),  # mirror the gateway's spawn env (servers resolve ~/ paths from HOME)
        )
    except subprocess.TimeoutExpired:
        return False, f"probe timed out after {PROBE_TIMEOUT}s"
    except OSError as exc:
        return False, f"cannot execute {command}: {exc}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = (err[-1] if err else "probe failed").strip()[:200]
        return False, detail
    try:
        names = json.loads(proc.stdout.strip() or "[]")
    except json.JSONDecodeError:
        return False, "probe returned unparsable output"
    return True, ",".join(str(n) for n in names)


def _readline_deadline(proc, timeout: float) -> str | None:
    """Read one stdout line with a deadline. None = timed out; '' = EOF."""
    box: dict = {}

    def reader():
        try:
            line = proc.stdout.readline()
            if line:
                box["line"] = line
            else:
                box["eof"] = True
        except Exception as exc:  # pragma: no cover - I/O edge
            box["err"] = exc

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None
    if "err" in box:
        raise box["err"]
    if "eof" in box:
        return ""
    return box.get("line", "")


def _stdio_failure_detail(proc, fallback: str) -> str:
    """Last stderr line (if any) with the given fallback message."""
    try:
        err = (proc.stderr.read() or "").strip().splitlines()
        if err:
            return (err[-1].strip()[:200]) or fallback
    except Exception:
        pass
    return fallback


def _probe_stdio_handshake(command: str, args: list) -> tuple[bool, str]:
    """Real MCP stdio handshake for binary-CLI servers.

    A successful initialize (serverInfo present) proves the server is alive.
    tools/list is probed opportunistically — resource-only servers legitimately
    reject it (-32601) and must still pass; the handshake alone is the health
    signal.
    """
    try:
        proc = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(HOME),
        )
    except OSError as exc:
        return False, f"cannot execute {command}: {exc}"
    if proc.stdin is None or proc.stdout is None or proc.stderr is None:
        try:
            proc.kill()
        except Exception:
            pass
        return False, "stdio pipe setup failed"
    try:
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-mcp-health-watchdog", "version": "1.0"},
            },
        }
        try:
            proc.stdin.write(json.dumps(init) + "\n")
            proc.stdin.flush()
        except OSError as exc:
            return False, f"stdio write failed: {exc}"
        line = _readline_deadline(proc, PROBE_TIMEOUT)
        if line is None:
            return False, f"stdio initialize timed out after {PROBE_TIMEOUT}s"
        if not line:
            return False, _stdio_failure_detail(proc, "stdio server exited before initialize response")
        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            return False, _stdio_failure_detail(proc, "unparsable initialize response")
        result = resp.get("result") or {}
        server_info = result.get("serverInfo")
        if not server_info:
            err = resp.get("error") or {}
            msg = err.get("message") or "no serverInfo in initialize response"
            return False, _stdio_failure_detail(proc, f"initialize failed: {msg}")
        name = str(server_info.get("name") or command)
        version = str(server_info.get("version") or "?")
        # tools/list — diagnostic only; resource-only servers may reject it.
        names: list = []
        try:
            req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            proc.stdin.write(json.dumps(req) + "\n")
            proc.stdin.flush()
            tline = _readline_deadline(proc, PROBE_TIMEOUT)
            if tline:
                tresp = json.loads(tline)
                tools = (tresp.get("result") or {}).get("tools") or []
                names = [str(t.get("name", "")) for t in tools if isinstance(t, dict)]
        except Exception:
            pass  # handshake already proved health
        detail = ",".join(names) if names else f"{name} v{version}"
        return True, detail
    finally:
        try:
            proc.kill()
        except Exception:
            pass


def check_required(names: list, required: list) -> str | None:
    """Return a problem description, or None when the tool list is acceptable."""
    if required:
        missing = [t for t in required if t not in names]
        if missing:
            return "missing tool(s): " + ", ".join(missing)
    elif not names:
        return "list_tools returned zero tools"
    return None


def scan_mcp_stderr(state: dict) -> tuple[bool, str]:
    """Scan newly-appended mcp-stderr bytes for import-crash signatures.

    Returns (found_new_crash, excerpt). Watermark per file: first run skips
    history, a rotated/missing log resets the watermark without alerting
    (the probes cover the gap).
    """
    offsets = state.setdefault("log_offsets", {})
    hits = []
    for log_path in sorted(str(p) for p in MCP_LOG_DIR.glob("mcp-stderr*.log")):
        p = Path(log_path)
        try:
            size = p.stat().st_size
        except OSError:
            continue
        offset = offsets.get(log_path)
        if offset is None:
            offsets[log_path] = size  # first run: skip history
            continue
        if size < offset:
            offsets[log_path] = size  # rotated -> fresh start, no scan
            continue
        if size == offset:
            continue
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(offset)
                chunk = fh.read()
            offsets[log_path] = size
        except OSError:
            continue
        for line in chunk.splitlines():
            for pat in CRASH_PATTERNS:
                if pat.search(line):
                    hits.append(line.strip()[:200])
                    break
    if hits:
        return True, " | ".join(hits[:3])
    return False, ""


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"servers": {}, "log_alerted": False, "log_last_alert": 0.0, "log_offsets": {}}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass  # state loss is not worth failing the watchdog over


def main() -> int:
    try:
        servers = load_servers()
    except RuntimeError as exc:
        print(f"❌ agent-mcp-health-watchdog internal error: {exc}")
        return 1

    state = load_state()
    now = now_epoch()
    sstate = state.setdefault("servers", {})
    messages: list[str] = []

    enabled = {k: v for k, v in servers.items() if v.get("enabled")}
    if not enabled:
        return 0  # nothing configured to watch -> silent

    for key, spec in enabled.items():
        display, severity, required = EXPECTED_TOOLS.get(
            key, (f"{key} (unmanaged)", WARNING, [])
        )
        command = spec.get("command", "")
        args: list = spec.get("args") or []
        ok, detail = probe_server(command, args)
        problem = None
        if ok:
            names = detail.split(",") if detail else []
            problem = check_required(names, required)
        cur = sstate.setdefault(
            key, {"fail": 0, "alerted": False, "since": 0.0, "last_alert": 0.0}
        )
        if ok and problem is None:
            if cur.get("alerted"):
                messages.append(
                    f"✅ MCP server recovered: {display} — back online "
                    f"(was down since {kst_ts(cur.get('since', now))})"
                )
            cur.update({"fail": 0, "alerted": False, "since": 0.0})
            continue
        fail_reason = problem or detail or "probe failed"
        cur["fail"] = cur.get("fail", 0) + 1
        if cur.get("since", 0.0) == 0.0:
            cur["since"] = now
        if cur["fail"] >= STRIKES_TO_ALERT:
            due = not cur.get("alerted") or (now - cur.get("last_alert", 0.0)) >= REALERT_COOLDOWN
            if due:
                cur["alerted"] = True
                cur["last_alert"] = now
                if severity == CRITICAL:
                    messages.append(
                        f"⚠️ GOVERNANCE OFFLINE — ALL WRITES BLOCKED\n"
                        f"MCP server down: {display}\n"
                        f"  {fail_reason}\n"
                        f"Since: {kst_ts(cur.get('since', now))} "
                        f"(consecutive fails: {cur['fail']})\n"
                        f"{RECOVERY_HINT}"
                    )
                else:
                    messages.append(
                        f"⚠️ MCP server down (non-critical): {display}\n"
                        f"  {fail_reason}\n"
                        f"Since: {kst_ts(cur.get('since', now))} "
                        f"(consecutive fails: {cur['fail']})\n"
                        f"No write-deadlock. {RECOVERY_HINT}"
                    )

    # mcp-stderr crash signature scan (definitive -> fires on first fresh hit)
    found_crash, excerpt = scan_mcp_stderr(state)
    if found_crash:
        due = (
            not state.get("log_alerted")
            or (now - state.get("log_last_alert", 0.0)) >= REALERT_COOLDOWN
        )
        if due:
            state["log_alerted"] = True
            state["log_last_alert"] = now
            messages.append(
                f"⚠️ GOVERNANCE OFFLINE — MCP server import crash in mcp-stderr log\n"
                f"  {excerpt}\n"
                f"Time: {kst_ts(now)}\n"
                f"{RECOVERY_HINT}"
            )
    elif not any(s.get("alerted") for s in sstate.values()):
        state["log_alerted"] = False  # everything healthy -> arm the log alarm again

    save_state(state)
    if messages:
        print("\n\n".join(messages))
    return 0


if __name__ == "__main__":
    sys.exit(main())

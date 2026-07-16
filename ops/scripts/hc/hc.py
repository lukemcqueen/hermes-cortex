#!/usr/bin/env python3
"""
hc — Hermes Cortex CLI for humans.

No curls, no API paths. Just:
  hc inbox             list your messages
  hc inbox joseph      list joseph's messages
  hc send joseph "Subject" "Body text"
  hc status            bus health + queue depths + fleet
  hc depth             all queue depths
  hc fleet             agent health statuses
  hc watch             poll inbox every 5s
  hc doctor            run cortex-doctor
  hc dashboard         open bus dashboard in browser
  hc env               show current config
  hc help              this message

Config: ~/.hermes-cortex/hc.env (copied from .env.example)
  HC_BUS_URL=https://your-domain.com:13004
  HC_BUS_AUTH=moses:your-password
  HC_AGENT=moses
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".hermes-cortex" / "hc.env"
DEFAULT_AGENT = "moses"


def load_config() -> dict:
    """Load config from hc.env (env vars override)."""
    config = {
        "bus_url": os.environ.get("HC_BUS_URL", ""),
        "bus_auth": os.environ.get("HC_BUS_AUTH", ""),
        "agent": os.environ.get("HC_AGENT", ""),
    }

    if CONFIG_FILE.exists():
        try:
            for line in CONFIG_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (x.strip().strip("'\"").strip() for x in line.split("=", 1))
                v = v.split("#")[0].strip()
                if k == "HC_BUS_URL" and not config["bus_url"]:
                    config["bus_url"] = v
                elif k == "HC_BUS_AUTH" and not config["bus_auth"]:
                    config["bus_auth"] = v
                elif k == "HC_AGENT" and not config["agent"]:
                    config["agent"] = v
        except Exception:
            pass

    if not config["agent"]:
        config["agent"] = DEFAULT_AGENT
    if not config["bus_url"]:
        config["bus_url"] = "http://127.0.0.1:8903"
    return config


# ── HTTP helpers ────────────────────────────────────────────────

def _request(cfg: dict, method: str, path: str, body: dict = None) -> tuple[int, str]:
    """Make an HTTP request to the bus API."""
    import urllib.error
    import urllib.request

    url = f"{cfg['bus_url'].rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    if cfg["bus_auth"]:
        encoded = base64.b64encode(cfg["bus_auth"].encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:1000]
    except Exception as e:
        return 0, str(e)


def _get_json(cfg: dict, path: str):
    status, body = _request(cfg, "GET", path)
    if status != 200:
        return None, status, body
    try:
        return json.loads(body), status, body
    except json.JSONDecodeError:
        return None, status, body


def _post_json(cfg: dict, path: str, body: dict):
    status, resp_body = _request(cfg, "POST", path, body)
    if status != 200:
        return None, status, resp_body
    try:
        return json.loads(resp_body), status, resp_body
    except json.JSONDecodeError:
        return None, status, resp_body


# ── Formatting ──────────────────────────────────────────────────

def _fmt_ts(ts_str: str) -> str:
    """Format ISO timestamp to human-readable."""
    if not ts_str:
        return "?"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%H:%M:%S")
    except Exception:
        return ts_str[:19]


def _msg_preview(msg: dict) -> str:
    """Format a single message for display."""
    msg_body = msg.get("message", {})
    if isinstance(msg_body, str):
        try:
            msg_body = json.loads(msg_body)
        except json.JSONDecodeError:
            msg_body = {"body": msg_body}

    pri = msg_body.get("priority", "normal")
    icon = "🔴" if pri == "critical" else ("🟡" if pri == "urgent" else "📩")
    frm = msg_body.get("from", "?")
    subj = msg_body.get("subject", "(no subject)")
    body = msg_body.get("body", "")
    ts = _fmt_ts(msg.get("enqueued_at", ""))

    # Try to detect structured task body
    if isinstance(body, str) and body.startswith("{"):
        try:
            task = json.loads(body)
            if task.get("type") == "task_delegation":
                body = f"[Task: {task.get('description','')[:100]}]"
            elif task.get("type") == "task_cancel":
                body = f"[Cancel request for task: {task.get('task_id','')[:12]}...]"
        except json.JSONDecodeError:
            pass

    if len(str(body)) > 150:
        body = str(body)[:150] + "..."

    lines = [f"  {icon} [{ts}] {frm} → {subj}"]
    if body:
        for line in str(body).split("\\n"):
            lines.append(f"     {line}")
    return "\n".join(lines)


# ── Commands ────────────────────────────────────────────────────

def cmd_inbox(cfg: dict, args: list):
    """Read messages from an agent's inbox."""
    agent = args[0] if args else cfg["agent"]

    result = _post_json(cfg, "/api/pgmq/read", {
        "queue": f"inbox_{agent}",
        "vt": 60,
        "batch_size": 20,
    })
    if result[0] is None:
        print(f"❌ Could not read inbox: HTTP {result[1]} — {result[2][:100]}")
        return

    data = result[0]
    msgs = data if isinstance(data, list) else data.get("data", [])
    if isinstance(msgs, dict):
        msgs = [msgs]

    if not msgs:
        print(f"📬 No unread messages in inbox_{agent}.")
        return

    print(f"📬 {len(msgs)} unread message(s) in inbox_{agent}:")
    print()
    for m in msgs:
        print(_msg_preview(m))
        print()


def cmd_send(cfg: dict, args: list):
    """Send a message to an agent's inbox."""
    if len(args) < 2:
        print("Usage: hc send <agent> <subject> [body]")
        return

    agent = args[0]
    subject = args[1]
    body = " ".join(args[2:]) if len(args) > 2 else ""

    result = _post_json(cfg, "/api/pgmq/send", {
        "queue": f"inbox_{agent}",
        "message": {
            "from": cfg["agent"],
            "to": agent,
            "topic": "general",
            "subject": subject,
            "body": body or subject,
            "priority": "normal",
        },
        "priority": 0,
    })
    if result[0] is None:
        print(f"❌ Send failed: HTTP {result[1]} — {result[2][:200]}")
        return

    msg_id = result[0].get("msg_id", result[0])
    print(f"✅ Sent to {agent}. msg_id={msg_id}")


def cmd_status(cfg: dict, args: list):
    """Show bus health + queue depths + fleet."""
    # Health
    health, status_code, _ = _get_json(cfg, "/health")
    if health:
        status_icon = "✅" if health.get("status") == "ok" else "⚠️"
        print(f"{status_icon} Bus: {health.get('status', 'unknown')} ({health.get('backend', '?')})")
        print(f"   Queues: {health.get('queues', '?')}")
    else:
        print(f"❌ Bus health: HTTP {status_code}")

    # Queue depths
    queues, _, _ = _get_json(cfg, "/api/pgmq/queues")
    print()
    if queues:
        qlist = queues if isinstance(queues, list) else queues.get("queues", [])
        if qlist and isinstance(qlist[0], dict):
            # [{"name": "...", "depth": N}, ...]
            inbox_qs = [q for q in qlist if q["name"].startswith("inbox_") and not q.get("dlq")]
            print(f"📊 {len(inbox_qs)} inbox queue(s):")
            for q in sorted(inbox_qs, key=lambda x: x["name"]):
                d = q.get("depth", "?")
                print(f"   {q['name']:30s}  depth={d}")
        elif qlist and isinstance(qlist[0], str):
            # ["queue_1", "queue_2"]
            inbox_qs = sorted([q for q in qlist if q.startswith("inbox_") and "_dlq" not in q])
            print(f"📊 {len(inbox_qs)} inbox queue(s):")
            for q in inbox_qs:
                depth, _, _ = _get_json(cfg, f"/api/pgmq/depth/{q}")
                d = depth if isinstance(depth, int) else (depth.get("depth", "?") if isinstance(depth, dict) else "?")
                print(f"   {q:30s}  depth={d}")
        else:
            print(f"📊 Queues: {len(qlist)} total")

    # Fleet
    fleet = Path.home() / ".hermes" / "state" / "fleet-status.state"
    if fleet.exists():
        print()
        try:
            data = json.loads(fleet.read_text())
            agents = data.get("a", {})
            print("🚩 Fleet:")
            for name, status in sorted(agents.items()):
                icon = "✅" if status == "✅" else ("⚠️" if status == "⚠️" else "❌")
                print(f"   {icon} {name:12s}  {status}")
            print(f"\n   Workflows: {data.get('wf', '?')}")
        except Exception:
            pass


def cmd_depth(cfg: dict, args: list):
    """Show depth of a specific queue or all inbox queues."""
    if args:
        agent = args[0]
        result = _get_json(cfg, f"/api/pgmq/depth/inbox_{agent}")
        print(f"📊 inbox_{agent} depth: {result[0] if result[0] is not None else result[1]}")
        return

    # Show all inbox queues
    queues, _, _ = _get_json(cfg, "/api/pgmq/queues")
    if not queues:
        print("❌ Could not list queues")
        return

    qlist = queues if isinstance(queues, list) else queues.get("queues", [])
    if qlist and isinstance(qlist[0], dict):
        inbox_qs = sorted([q for q in qlist if q["name"].startswith("inbox_") and not q.get("dlq")], key=lambda x: x["name"])
        print("📊 Queue depths:")
        for q in inbox_qs:
            print(f"   {q['name']:30s}  {q.get('depth', '?')}")
    elif qlist and isinstance(qlist[0], str):
        inbox_qs = sorted([q for q in qlist if q.startswith("inbox_") and "_dlq" not in q])
        print("📊 Queue depths:")
        for q in inbox_qs:
            d, _, _ = _get_json(cfg, f"/api/pgmq/depth/{q}")
            depth = d if isinstance(d, int) else (d.get("depth", "?") if isinstance(d, dict) else "?")
            print(f"   {q:30s}  {depth}")
    else:
        print(f"📊 {len(qlist)} queue(s)")


def cmd_fleet(cfg: dict, args: list):
    """Show fleet health status."""
    fleet = Path.home() / ".hermes" / "state" / "fleet-status.state"
    if not fleet.exists():
        print("❌ Fleet state not found (only available on orchestrator)")
        return

    try:
        data = json.loads(fleet.read_text())
        agents = data.get("a", {})
        print("🚩 Fleet Health:")
        print()
        for name, status in sorted(agents.items()):
            icon = "✅" if status == "✅" else ("⚠️" if status == "⚠️" else "❌")
            print(f"   {icon} {name:12s}  {status}")
        issues = data.get("i", [])
        if issues:
            print(f"\n⚠️  Issues ({len(issues)}):")
            for issue in issues:
                print(f"   • {issue}")
        stalled = data.get("s", [])
        if stalled:
            print(f"\n⏸️  Stalled ({len(stalled)}):")
            for s in stalled:
                print(f"   • {s}")
        print(f"\n📊 Workflows: {data.get('wf', 0)}")
    except Exception as e:
        print(f"❌ Error reading fleet state: {e}")


def cmd_watch(cfg: dict, args: list):
    """Poll inbox continuously."""
    agent = args[0] if args else cfg["agent"]
    seen_ids = set()
    interval = 5

    print(f"👀 Watching inbox_{agent} (poll every {interval}s, Ctrl+C to stop)...")
    print()
    try:
        while True:
            result = _post_json(cfg, "/api/pgmq/read", {
                "queue": f"inbox_{agent}",
                "vt": 30,
                "batch_size": 5,
            })
            if result[0] is not None:
                data = result[0]
                msgs = data if isinstance(data, list) else data.get("data", [])
                if isinstance(msgs, dict):
                    msgs = [msgs]
                new = [m for m in msgs if m.get("msg_id") not in seen_ids]
                for m in new:
                    seen_ids.add(m.get("msg_id"))
                    print(_msg_preview(m))
                    print()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n👋 Stopped.")


def cmd_doctor(cfg: dict, args: list):
    """Run cortex-doctor."""
    script = Path.home() / "hermes-cortex" / "ops" / "scripts" / "manage" / "cortex-doctor.py"
    if not script.exists():
        script = Path.home() / ".hermes-cortex" / "scripts" / "cortex-doctor.py"
    if script.exists():
        subprocess.run([sys.executable, str(script), "--quiet"])
    else:
        print("❌ cortex-doctor.py not found")


def cmd_dashboard(cfg: dict, args: list):
    """Open bus dashboard in browser."""
    url = f"{cfg['bus_url'].rstrip('/')}/"
    print(f"🌐 Opening {url} ...")
    try:
        webbrowser.open(url)
    except Exception:
        print(f"   Open manually: {url}")


def cmd_env(cfg: dict, args: list):
    """Show current config."""
    print("📋 hc Configuration:")
    print(f"   HC_BUS_URL   = {cfg['bus_url']}")
    auth_masked = cfg["bus_auth"][:cfg["bus_auth"].find(":") + 1] + "****" if ":" in cfg["bus_auth"] else "****"
    print(f"   HC_BUS_AUTH  = {auth_masked}")
    print(f"   HC_AGENT     = {cfg['agent']}")
    print(f"   Config file  = {CONFIG_FILE}")
    print(f"   File exists  = {CONFIG_FILE.exists()}")


def cmd_help(cfg: dict, args: list):
    """Show this help."""
    print(__doc__.strip())
    print()
    print("Quick reference:")
    print(f"  hc inbox              — read your inbox ({cfg['agent']})")
    print("  hc inbox <agent>      — read another agent's inbox")
    print("  hc send <a> <subj>    — send a message")
    print("  hc status             — bus health + queue depths + fleet")
    print("  hc depth [agent]      — queue depth (all or specific)")
    print("  hc fleet              — agent health statuses")
    print("  hc watch [agent]      — continuously poll inbox")
    print("  hc doctor             — run cortex-doctor")
    print("  hc dashboard          — open bus dashboard")
    print("  hc env                — show config")
    print("  hc help               — this message")


# ── Main ────────────────────────────────────────────────────────

COMMANDS = {
    "inbox": cmd_inbox,
    "send": cmd_send,
    "status": cmd_status,
    "depth": cmd_depth,
    "fleet": cmd_fleet,
    "watch": cmd_watch,
    "doctor": cmd_doctor,
    "dashboard": cmd_dashboard,
    "env": cmd_env,
    "help": cmd_help,
}


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Hermes Cortex CLI", add_help=False)
    parser.add_argument("command", nargs="?", default="help", help="Command to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Command arguments")
    parsed = parser.parse_args()

    cmd = parsed.command
    cmd_args = parsed.args

    if cmd in COMMANDS:
        COMMANDS[cmd](cfg, cmd_args)
    else:
        print(f"Unknown command: {cmd}\n")
        cmd_help(cfg, [])


if __name__ == "__main__":
    main()

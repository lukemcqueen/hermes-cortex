#!/usr/bin/env python3
"""
hc — Hermes Cortex CLI for humans. Runs direct against Postgres (docker exec).
No curls, no API paths, no ACLs. Read any queue, see everything.

  hc inbox             list your messages (non-destructive read)
  hc inbox joseph      list joseph's messages
  hc send <a> <subj>   send a message (via POST to bus API)
  hc status            bus health + queue depths + fleet
  hc depth             all queue depths
  hc fleet             agent health statuses
  hc watch             watch ALL inbox queues (default)
  hc watch moses       watch only moses' inbox (non-destructive)
  hc doctor            run cortex-doctor
  hc dashboard         open bus dashboard in browser
  hc env               show current config
  hc help              this message

Config: ~/.hermes-cortex/hc.env
  HC_AGENT=moses                          # your agent name (default)
"""

import argparse
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
                if k == "HC_AGENT" and not config["agent"]:
                    config["agent"] = v
        except Exception:
            pass

    if not config["agent"]:
        config["agent"] = DEFAULT_AGENT
    return config


# ── Database helpers ────────────────────────────────────────────

def _psql(query: str) -> str:
    """Run a SQL query against the bus Postgres via docker exec."""
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql",
             "-U", "gbrain", "-d", "gbrain", "-t", "-c", query],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else f"ERROR: {r.stderr[:200]}"
    except FileNotFoundError:
        return "ERROR: docker not found"
    except subprocess.TimeoutExpired:
        return "ERROR: query timed out"
    except Exception as e:
        return f"ERROR: {e}"


def _psql_json(query: str):
    """Run SQL and parse JSON result."""
    raw = _psql(query)
    if raw.startswith("ERROR"):
        return None, raw
    if not raw:
        return None, "empty"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return None, raw[:200]


def _get_messages(queue: str, limit: int = 20) -> list[dict]:
    """Get pending messages from a queue (non-destructive read)."""
    raw = _psql(f"""
        SELECT row_to_json(m) FROM (
            SELECT msg_id::text, queue_name, body, priority,
                   retry_count, max_retries,
                   enqueued_at::text, timeout_at::text, state
            FROM bus.messages
            WHERE queue_name = '{queue}'
              AND state = 'pending'
              AND visible_after <= now()
            ORDER BY priority DESC, enqueued_at ASC
            LIMIT {limit}
        ) m;
    """)
    if not raw:
        return []
    results = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return results


def _get_queue_depths() -> list[dict]:
    """Get depth of all inbox queues via SQL."""
    raw = _psql("""
        SELECT row_to_json(d) FROM (
            SELECT q.name,
                   (SELECT count(*) FROM bus.messages
                    WHERE queue_name = q.name
                      AND state = 'pending'
                      AND visible_after <= now()) AS depth
            FROM bus.queues q
            WHERE q.name LIKE 'inbox_%' AND q.is_dlq = false
            ORDER BY q.name
        ) d;
    """)
    if not raw:
        return []
    results = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return results


def _send_message(queue: str, body: dict) -> str:
    """Send a message via bus.send() SQL function."""
    body_json = json.dumps(body).replace("'", "''")
    result = _psql(f"SELECT bus.send('{queue}', '{body_json}'::jsonb, 0)")
    if result and not result.startswith("ERROR"):
        return f"✅ Sent to {queue[6:]}. msg_id={result}"
    return f"❌ Send failed: {result}"


# ── Formatting ──────────────────────────────────────────────────

def _fmt_ts(ts_str: str) -> str:
    if not ts_str:
        return "?"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M:%S")
    except Exception:
        return ts_str[:19]


def _msg_preview(msg: dict) -> str:
    """Format a message for display."""
    body_raw = msg.get("body", {})
    if isinstance(body_raw, str):
        try:
            body_raw = json.loads(body_raw)
        except json.JSONDecodeError:
            body_raw = {"body": body_raw}

    pri = body_raw.get("priority", "normal")
    icon = "🔴" if pri == "critical" else ("🟡" if pri == "urgent" else "📩")
    frm = body_raw.get("from", "?")
    subj = body_raw.get("subject", "(no subject)")

    body_text = body_raw.get("body", "")
    if isinstance(body_text, str) and body_text.startswith("{"):
        try:
            task = json.loads(body_text)
            if task.get("type") == "task_delegation":
                body_text = f"[Task: {task.get('description','')[:100]}]"
            elif task.get("type") == "task_cancel":
                body_text = f"[Cancel: {task.get('task_id','')[:12]}...]"
        except json.JSONDecodeError:
            pass

    if len(str(body_text)) > 150:
        body_text = str(body_text)[:150] + "..."

    ts = _fmt_ts(msg.get("enqueued_at", ""))
    lines = [f"  {icon} [{ts}] {frm} → {subj}"]
    if body_text:
        for line in str(body_text).split("\\n"):
            lines.append(f"     {line}")
    return "\n".join(lines)


# ── Commands ────────────────────────────────────────────────────

def cmd_inbox(cfg: dict, args: list):
    """Read messages from an agent's inbox (non-destructive)."""
    agent = args[0] if args else cfg["agent"]
    queue = f"inbox_{agent}"

    msgs = _get_messages(queue)
    if not msgs:
        print(f"📬 No pending messages in {queue}.")
        return

    print(f"📬 {len(msgs)} pending message(s) in {queue}:")
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
    body_text = " ".join(args[2:]) if len(args) > 2 else subject

    body = {
        "from": cfg["agent"],
        "to": agent,
        "topic": "general",
        "subject": subject,
        "body": body_text,
        "priority": "normal",
    }
    result = _send_message(f"inbox_{agent}", body)
    print(result)


def cmd_status(cfg: dict, args: list):
    """Show bus health + queue depths + fleet."""
    # Health via localhost API (no auth for health)
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://127.0.0.1:8903/health", timeout=5)
        health = json.loads(resp.read().decode())
        status_icon = "✅" if health.get("status") == "ok" else "⚠️"
        print(f"{status_icon} Bus: {health.get('status', 'unknown')} ({health.get('backend', '?')})")
    except Exception:
        print("❌ Bus health: unreachable")

    # Queue depths
    print()
    queues = _get_queue_depths()
    if queues:
        print(f"📊 {len(queues)} inbox queue(s):")
        for q in queues:
            print(f"   {q['name']:30s}  depth={q['depth']}")
    else:
        print("📊 No inbox queues found.")

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
    """Show depth of all inbox queues."""
    if args:
        agent = args[0]
        msgs = _get_messages(f"inbox_{agent}")
        print(f"📊 inbox_{agent}: {len(msgs)} pending message(s)")
        return

    queues = _get_queue_depths()
    if queues:
        print("📊 Queue depths:")
        for q in queues:
            print(f"   {q['name']:30s}  {q['depth']}")
    else:
        print("📊 No inbox queues found.")


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


def _get_all_messages(limit_per_queue: int = 5) -> list[tuple[str, dict]]:
    """Get pending messages from ALL inbox queues. Returns [(queue_name, msg), ...]."""
    queues = _get_queue_depths()
    results = []
    for q in queues:
        if q["depth"] > 0:
            for m in _get_messages(q["name"], limit=limit_per_queue):
                results.append((q["name"], m))
    return results


def cmd_watch(cfg: dict, args: list):
    """Poll inbox continuously (non-destructive). Default: all queues."""
    interval = 5
    seen = set()

    if args:
        # Single agent watch
        queue = f"inbox_{args[0]}"
        print(f"👀 Watching {queue} (poll every {interval}s, Ctrl+C to stop)...")
        print()
        try:
            while True:
                for m in _get_messages(queue):
                    mid = m.get("msg_id", "")
                    if mid not in seen:
                        seen.add(mid)
                        print(_msg_preview(m))
                        print()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 Stopped.")
        return

    # All queues watch
    print(f"👀 Watching ALL inbox queues (poll every {interval}s, Ctrl+C to stop)...")
    print()
    try:
        while True:
            for queue_name, m in _get_all_messages():
                mid = m.get("msg_id", "")
                if mid not in seen:
                    seen.add(mid)
                    agent = queue_name.replace("inbox_", "")
                    agent_label = f"📬 [{agent}]" if agent else ""
                    preview = _msg_preview(m)
                    print(f"  {agent_label}")
                    for line in preview.split("\n"):
                        print(f"   {line}")
                    print()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n👋 Stopped.")


def cmd_doctor(cfg: dict, args: list):
    """Run cortex-doctor."""
    for path in [
        Path.home() / "hermes-cortex" / "ops" / "scripts" / "manage" / "cortex-doctor.py",
        Path.home() / ".hermes-cortex" / "scripts" / "cortex-doctor.py",
    ]:
        if path.exists():
            subprocess.run([sys.executable, str(path), "--quiet"])
            return
    print("❌ cortex-doctor.py not found")


def cmd_dashboard(cfg: dict, args: list):
    """Open bus dashboard in browser."""
    url = "http://127.0.0.1:8903/"
    print(f"🌐 Opening {url} ...")
    try:
        webbrowser.open(url)
    except Exception:
        print(f"   Open manually: {url}")


def cmd_env(cfg: dict, args: list):
    """Show current config."""
    print("📋 hc Configuration:")
    print(f"   HC_AGENT     = {cfg['agent']}")
    print(f"   Config file  = {CONFIG_FILE}")
    print(f"   File exists  = {CONFIG_FILE.exists()}")
    print(f"   Backend      = Postgres (direct via docker exec)")
    print(f"   Auth         = None (admin-level access)")
    print(f"\nTip: Any agent's inbox is readable:")
    print(f"  hc inbox moses    hc inbox joseph    hc inbox esther")


def cmd_help(cfg: dict, args: list):
    """Show this help."""
    print(__doc__.strip())
    print()
    print("Quick reference:")
    print(f"  hc inbox              — read your inbox ({cfg['agent']})")
    print("  hc inbox <agent>      — read any agent's inbox")
    print("  hc send <a> <subj>    — send a message")
    print("  hc status             — bus health + queue depths + fleet")
    print("  hc depth [agent]      — queue depth (all or specific)")
    print("  hc fleet              — agent health statuses")
    print("  hc watch              — watch ALL inbox queues (default)")
    print("  hc watch moses        — watch only moses' inbox")
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

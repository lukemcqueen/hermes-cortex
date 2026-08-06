#!/usr/bin/env python3
"""
hc — Hermes Cortex CLI for humans. Talks to the Agent Bus over HTTP.
Host-independent: reads CORTEX_BUS_URL / CORTEX_BUS_FALLBACK_URL from
cortex-bus.conf (same as every fleet script), so it works identically on
moses and esther hosts. No docker exec, no local-Postgres assumption.

  hc inbox             list your messages (non-destructive read)
  hc inbox joseph      list joseph's messages
  hc send <a> <subj>   send a message (via POST to bus API)
  hc exec <a> <cmd>    execute a script on a remote agent, wait for result
  hc status            bus health + queue depths + fleet
  hc depth             all queue depths
  hc fleet             agent health statuses
  hc bus               full bus dashboard (queue states, processing, stuck, DLQ)
  hc bus --all         include archived activity
  hc watch             watch ALL inbox queues (default)
  hc watch moses       watch only moses' inbox (non-destructive)
  hc kill <agent>    send KILL signal to a fleet agent (emergency stop)
  hc doctor            run cortex-doctor
  hc dashboard         open bus dashboard in browser
  hc env               show current config
  hc help              this message

Config: ~/.hermes-cortex/hc.env (optional; every field falls back)
  HC_AGENT=esther                          # your agent name (default)
Bus config comes from ~/.hermes-cortex/cortex-bus.conf:
  CORTEX_BUS_URL=https://…:13004           # active bus (Moses)
  CORTEX_BUS_FALLBACK_URL=https://…:14004  # fallback bus (Esther)
  CORTEX_BASIC_AUTH=user:pass              # nginx Basic auth
  CORTEX_BUS_TOKEN=hbus_…                  # direct Bearer token
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".hermes-cortex" / "hc.env"
BUS_CONF_FILE = Path.home() / ".hermes-cortex" / "cortex-bus.conf"
DEFAULT_AGENT = ""

# Make the shared bus client importable from both the repo and the
# deployed layout (repo: ops/scripts/lib; deployed: scripts/lib).
# `from lib.cortex_bus import …` needs the PARENT of lib/ on sys.path.
# Insert only the FIRST existing candidate (priority order) so the repo
# copy isn't shadowed by a stale deployed copy missing new functions.
_LIB_CANDIDATES = [
    Path(__file__).resolve().parent.parent,          # repo: ops/scripts
    Path.home() / ".hermes-cortex" / "scripts",      # deployed: scripts
    Path.home() / "hermes-cortex" / "ops" / "scripts",
]
for _lib in _LIB_CANDIDATES:
    if _lib.is_dir() and str(_lib) not in sys.path:
        sys.path.insert(0, str(_lib))
        break

try:
    from lib.cortex_bus import (  # type: ignore
        bus_archives,
        bus_health,
        bus_list_queues,
        bus_peek,
        bus_send,
        BUS_URL,
        BUS_FALLBACK_URL,
    )
    _HAS_LIB = True
except Exception:
    # ImportError (module missing) OR RuntimeError (BUS_URL unset on this
    # host — e.g. a bare machine without cortex-bus.conf). Both degrade to
    # a clear message; hc must never crash at import.
    _HAS_LIB = False
    BUS_URL = ""
    BUS_FALLBACK_URL = ""

    def bus_archives(queue: str, limit: int = 20, since_minutes: int = 60) -> list[dict]:
        """Stub — lib.cortex_bus unavailable; _get_archives guards on _HAS_LIB."""
        return []


def _read_bus_conf(key: str) -> str:
    """Read a value from cortex-bus.conf (fallback for env)."""
    if BUS_CONF_FILE.exists():
        try:
            for line in BUS_CONF_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (x.strip().strip("'\"") for x in line.split("=", 1))
                if k == key:
                    return v
        except Exception:
            pass
    return ""


def load_config() -> dict:
    """Load config from hc.env + cortex-bus.conf (env vars override).

    Agent resolution order:
      1. HC_AGENT env var
      2. HC_AGENT in hc.env
      3. AGENT_NAME in cortex-bus.conf (canonical per-host identity)
      4. hostname-based guess (never a hardcoded other agent)
    """
    config = {
        "agent": os.environ.get("HC_AGENT", ""),
    }

    if CONFIG_FILE.exists():
        try:
            for line in CONFIG_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (x.strip().strip("'\"") for x in line.split("=", 1))
                if k == "HC_AGENT" and not config["agent"]:
                    config["agent"] = v
        except Exception:
            print("expected — silently handled", file=sys.stderr)

    if not config["agent"]:
        config["agent"] = os.environ.get("AGENT_NAME", "") or _read_bus_conf("AGENT_NAME")

    if not config["agent"]:
        # Never impersonate another agent: derive from hostname, or refuse.
        import socket
        hostname = socket.gethostname().split(".")[0].lower()
        # Known fleet hostname→agent map (PII-safe: no real hostnames here)
        _HOST_MAP = {
            "luke-server": "joseph",
            "cisnet03": "gisu",
            "cisnet02": "kustos",
            "lam2": "titus",
        }
        config["agent"] = _HOST_MAP.get(hostname, hostname)
        if config["agent"]:
            print(f"ℹ️  HC_AGENT unset — derived agent '{config['agent']}' from hostname", file=sys.stderr)
    return config


# ── Database helpers ────────────────────────────────────────────

def _psql(query: str) -> str:
    """Run a SQL query against the bus Postgres via docker exec."""
    try:
        r = subprocess.run(
            ["docker", "exec", "mycortex-postgres", "psql",
             "-U", "mycortex", "-d", "mycortex", "-t", "-c", query],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else f"ERROR: {r.stderr[:200]}"
    except FileNotFoundError:
        return "ERROR: docker not found"
    except subprocess.TimeoutExpired:
        return "ERROR: query timed out"
    except Exception as e:
        return f"ERROR: {e}"


def _psql_json(query: str | None) -> tuple:
    """Run a SQL query and parse the result as JSON."""
    if query is None:
        return None, "Query is None"
    raw = _psql(query)
    if raw.startswith("ERROR"):
        return None, raw
    if not raw:
        return None, "empty"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return None, raw[:200]


# ── Command Verification ────────────────────────────────────

_EXPECTED_RESPONSE_MAP = {
    "UPDATE_REQUEST": "UPDATE_RESULT",
    "ROLLBACK_REQUEST": "ROLLBACK_RESULT",
    "GIT_AUTH_CHECK": "GIT_AUTH_RESULT",
    "DIAGNOSTIC_REQUEST": "DIAGNOSTIC_RESULT",
    "EXEC": "EXEC_RESULT",
}


def _subject_to_expected_response(subject: str) -> str | None:
    """Map a subject to its expected response, or None if fire-and-forget."""
    return _EXPECTED_RESPONSE_MAP.get(subject, None)


def _record_verification(
    correlation_id: str,
    agent: str,
    command_type: str,
    subject: str,
    timeout_seconds: int = 600,
) -> bool:
    """Record a command dispatch in bus.command_verifications.

    Returns True on success, False on DB error (send proceeds regardless).
    """
    expected = _subject_to_expected_response(subject)
    expected_str = "NULL" if expected is None else f"'{expected}'"
    q = f"SELECT bus.record_dispatch('{correlation_id}', '{agent}', " \
        f"'{command_type}', '{subject}', {expected_str}, NULL, {timeout_seconds})"
    result = _psql(q)
    if result.startswith("ERROR") or not result:
        print(f"  ⚠️  Verification recording failed (send still succeeded): {result[:100]}", file=sys.stderr)
        return False
    return True


def _get_messages(queue: str, limit: int = 20) -> list[dict]:
    """Get pending messages from a queue (non-destructive read via HTTP peek)."""
    if not _HAS_LIB:
        print("❌ lib.cortex_bus not importable — run cortex-update.sh to deploy.", file=sys.stderr)
        return []
    try:
        return bus_peek(queue, limit=limit)
    except Exception as e:
        print(f"  ⚠️  peek {queue} failed: {e}", file=sys.stderr)
        return []


def _get_archives(queue: str, limit: int = 50, since_minutes: int = 60) -> list[dict]:
    """Get recently archived messages from a queue (non-destructive read).

    The live peek only returns 'pending' messages — a result the handler
    already archived is invisible to it. hc exec polls archives too so a
    fast-archived EXEC_RESULT is found instead of hanging (2026-08-06).
    """
    if not _HAS_LIB:
        print("❌ lib.cortex_bus not importable — run cortex-update.sh to deploy.", file=sys.stderr)
        return []
    try:
        return bus_archives(queue, limit=limit, since_minutes=since_minutes)
    except Exception as e:
        print(f"  ⚠️  archives {queue} failed: {e}", file=sys.stderr)
        return []


def _get_queue_depths() -> list[dict]:
    """Get depth of all inbox queues via HTTP (name + depth)."""
    if not _HAS_LIB:
        print("❌ lib.cortex_bus not importable — run cortex-update.sh to deploy.", file=sys.stderr)
        return []
    try:
        queues = bus_list_queues()
        return [
            {"name": q["name"], "depth": q.get("depth", 0)}
            for q in queues
            if q.get("name", "").startswith("inbox_") and not q.get("dlq")
        ]
    except Exception as e:
        print(f"  ⚠️  list_queues failed: {e}", file=sys.stderr)
        return []


def _send_message(queue: str, body: dict) -> str:
    """Send a message via the bus HTTP API (active bus, fallback on failure)."""
    if not _HAS_LIB:
        return "❌ lib.cortex_bus not importable — run cortex-update.sh to deploy."
    try:
        result = bus_send(queue, body)
        if result is None:
            return "❌ Send failed: bus_send returned None (see logs)"
        msg_id = result.get("msg_id") if isinstance(result, dict) else result
        if msg_id is None:
            return f"❌ Send failed: {result}"
        return f"✅ Sent to {queue[6:]}. msg_id={msg_id}"
    except Exception as e:
        return f"❌ Send failed: {e}"


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
            pass  # expected — silently handled

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
    """Send a message to an agent's inbox.
    
    HARD RULE: Sending to a fleet agent (not self) requires --self-tested
    to prove the identical flow was tested on yourself first.
    """
    # Check for --self-tested flag
    self_tested = "--self-tested" in args
    args = [a for a in args if a != "--self-tested"]
    
    if len(args) < 2:
        print("Usage: hc send <agent> <subject> [body] [--self-tested]")
        return

    agent = args[0]
    subject = args[1]
    body_text = " ".join(args[2:]) if len(args) > 2 else subject
    
    # SELF-TEST ENFORCEMENT: Sending to a fleet agent requires --self-tested
    my_name = cfg.get("agent", "")
    if agent != my_name and not self_tested:
        print(f"❌ REFUSED: Sending to '{agent}' requires --self-tested.")
        print()
        print("   Fleet-commands hard rule: Never send a command to a fleet agent")
        print("   until you've proven the identical flow works on yourself.")
        print()
        print(f"   To self-test first:")
        print(f"     1. hc send {my_name} \"{subject}\" '<identical-body>'")
        print(f"     2. Verify the handler processes it (run handler --once)")
        print(f"     3. Check inbox for UPDATE_RESULT / EXEC_RESULT")
        print(f"     4. Then re-run: hc send {agent} \"{subject}\" '<body>' --self-tested")
        print()
        print("   Use --self-tested only AFTER the self-test is verified.")
        return

    body = {
        "from": cfg["agent"],
        "to": agent,
        "topic": "general",
        "subject": subject,
        "body": body_text,
        "priority": "normal",
    }

    # Add correlation_id for verifiability
    corr_id = f"send-{uuid.uuid4().hex[:12]}"
    body["correlation_id"] = corr_id

    result = _send_message(f"inbox_{agent}", body)
    print(result)

    # Record verification (non-blocking — send succeeded regardless)
    if not result.startswith("❌"):
        msg_id = result.split("msg_id=")[-1].strip() if "msg_id=" in result else None
        _record_verification(corr_id, agent, "SEND", subject)


def cmd_status(cfg: dict, args: list):
    """Show bus health + queue depths + fleet."""
    # Health via the shared bus client (active bus, fallback, Bearer→Basic)
    if _HAS_LIB:
        try:
            health = bus_health()
            status_icon = "✅" if health.get("status") == "ok" else "⚠️"
            print(f"{status_icon} Bus: {health.get('status', 'unknown')} ({health.get('backend', '?')}) — {BUS_URL}")
        except Exception as e:
            print(f"❌ Bus health: unreachable ({e})")
    else:
        print("❌ lib.cortex_bus not importable — run cortex-update.sh to deploy.")

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
            print("expected — silently handled", file=sys.stderr)


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


def cmd_bus(cfg: dict, args: list):
    """Show full bus dashboard: queue states, processing, stuck, DLQ, activity.

    NOTE: this deep-dive reads the LOCAL Postgres (docker exec mycortex-postgres).
    On moses' host that is the ACTIVE bus; on esther's host it shows her own
    (fallback) bus. For the fleet-wide view use: hc status / hc depth / hc inbox.
    """
    show_all = "--all" in args or "-a" in args
    show_archived = "--archived" in args

    # ── Queue summary ────────────────────────────────────────
    print("🚌 Agent Bus Dashboard")
    print(f"   source: local Postgres (docker exec) — {Path.home()}/.hermes-cortex (agent {cfg['agent']})")
    print()

    raw = _psql("""
        SELECT row_to_json(q) FROM (
            SELECT
                q.name,
                (SELECT count(*) FROM bus.messages WHERE queue_name = q.name AND state = 'pending' AND visible_after <= now()) AS pending,
                (SELECT count(*) FROM bus.messages WHERE queue_name = q.name AND state = 'processing') AS processing,
                0::bigint AS archived
            FROM bus.queues q
            WHERE q.name LIKE 'inbox_%' AND q.is_dlq = false
            ORDER BY q.name
        ) q;
    """)
    if raw and not raw.startswith("ERROR"):
        queues = []
        for line in raw.split("\n"):
            line = line.strip()
            if line:
                try: queues.append(json.loads(line))
                except Exception: continue
        print(f"📊 Queue Summary ({len(queues)} queues):")
        print(f"   {'Queue':30s} {'Pending':>8s} {'Processing':>11s}")
        print(f"   {'─'*30} {'─'*8} {'─'*11}")
        total_pending = total_proc = 0
        for q in queues:
            total_pending += q["pending"]
            total_proc += q["processing"]
            name = q["name"].replace("inbox_", "")
            icon = "⚠️" if q["processing"] > 0 else ("📬" if q["pending"] > 0 else "  ")
            print(f"   {icon} {name:28s} {q['pending']:>8d} {q['processing']:>11d}")
        print(f"   {'─'*30} {'─'*8} {'─'*11}")
        print(f"   {'TOTAL':30s} {total_pending:>8d} {total_proc:>11d}")
    print()

    # ── Processing / In-flight ───────────────────────────────
    raw = _psql("""
        SELECT row_to_json(m) FROM (
            SELECT msg_id::text, queue_name, body,
                   enqueued_at::text, timeout_at::text,
                   retry_count, max_retries, error
            FROM bus.messages
            WHERE state = 'processing'
              AND queue_name LIKE 'inbox_%'
            ORDER BY enqueued_at ASC
            LIMIT 20
        ) m;
    """)
    if raw and not raw.startswith("ERROR") and raw != "empty":
        procs = []
        for line in raw.split("\n"):
            line = line.strip()
            if line:
                try: procs.append(json.loads(line))
                except Exception: continue
        if procs:
            print(f"⚙️  Processing ({len(procs)} message(s)):")
            now_ts = datetime.now(timezone.utc)
            for m in procs:
                body = m.get("body", {})
                if isinstance(body, str):
                    try: body = json.loads(body)
                    except: body = {}
                frm = body.get("from", "?")
                subj = body.get("subject", "(no subject)")[:40]
                enq = m.get("enqueued_at", "")
                tout = m.get("timeout_at", "")
                elapsed = ""
                overdue = ""
                if tout:
                    try:
                        tout_dt = datetime.fromisoformat(tout.replace("Z", "+00:00"))
                        remaining = (tout_dt - now_ts).total_seconds()
                        if remaining > 0:
                            elapsed = f"⏳ {remaining:.0f}s remaining"
                        else:
                            elapsed = f"⏰ {abs(remaining):.0f}s overdue"
                            overdue = " ⚠️"
                    except Exception: continue
                if enq:
                    try:
                        enq_dt = datetime.fromisoformat(enq.replace("Z", "+00:00"))
                        age = (now_ts - enq_dt).total_seconds()
                    except: age = 0
                agent = m["queue_name"].replace("inbox_", "")
                retry_info = f" (retry {m.get('retry_count',0)}/{m.get('max_retries',3)})" if m.get("retry_count", 0) > 0 else ""
                print(f"   {agent:10s} ← {frm:10s} \"{subj}\"  {elapsed}{retry_info}{overdue}")
            print()
        else:
            print(f"⚙️  No messages currently processing.")
            print()

    # ── Stuck / Timed out ────────────────────────────────────
    raw = _psql("""
        SELECT row_to_json(m) FROM (
            SELECT msg_id::text, queue_name, body,
                   enqueued_at::text, timeout_at::text,
                   retry_count, max_retries, error
            FROM bus.messages
            WHERE state = 'processing'
              AND timeout_at < now()
              AND queue_name LIKE 'inbox_%'
            ORDER BY timeout_at ASC
            LIMIT 10
        ) m;
    """)
    if raw and not raw.startswith("ERROR") and raw != "empty":
        stuck = []
        for line in raw.split("\n"):
            line = line.strip()
            if line:
                try: stuck.append(json.loads(line))
                except Exception: continue
        if stuck:
            print(f"⏰  STUCK — Past Timeout ({len(stuck)}):")
            now_ts = datetime.now(timezone.utc)
            for m in stuck:
                body = m.get("body", {})
                if isinstance(body, str):
                    try: body = json.loads(body)
                    except: body = {}
                subj = body.get("subject", "(no subject)")[:40]
                tout = m.get("timeout_at", "")
                overdue = "?"
                if tout:
                    try:
                        tout_dt = datetime.fromisoformat(tout.replace("Z", "+00:00"))
                        overdue = f"{(now_ts - tout_dt).total_seconds():.0f}s overdue"
                    except Exception: continue
                agent = m["queue_name"].replace("inbox_", "")
                retry = f" (retry {m.get('retry_count',0)}/{m.get('max_retries',3)})"
                err = f" — {m.get('error', '')[:60]}" if m.get("error") else ""
                print(f"   ⏰ {agent:10s} \"{subj}\"  {overdue}{retry}{err}")
            print()

    # ── DLQ ──────────────────────────────────────────────────
    raw = _psql("""
        SELECT row_to_json(d) FROM (
            SELECT q.name,
                   (SELECT count(*) FROM bus.messages
                    WHERE queue_name = q.name AND state = 'pending') AS depth
            FROM bus.queues q
            WHERE q.name LIKE 'inbox_%_dlq' AND q.is_dlq = true
              AND (SELECT count(*) FROM bus.messages
                   WHERE queue_name = q.name AND state = 'pending') > 0
            ORDER BY q.name
        ) d;
    """)
    if raw and not raw.startswith("ERROR") and raw != "empty":
        dlqs = []
        for line in raw.split("\n"):
            line = line.strip()
            if line:
                try: dlqs.append(json.loads(line))
                except Exception: continue
        if dlqs:
            print(f"🚫  Dead Letter Queues ({len(dlqs)}):")
            for d in dlqs:
                name = d["name"].replace("inbox_", "").replace("_dlq", "")
                print(f"   🚫 {name:10s} {d['depth']} message(s) — max retries exceeded")
            print()

    # ── Recent activity (archived) ────────────────────────────
    if show_all or show_archived:
        raw = _psql("""
            SELECT row_to_json(a) FROM (
                SELECT msg_id, queue_name, body,
                       archived_at, error
                FROM bus.messages_archive
                WHERE queue_name LIKE 'inbox_%'
                ORDER BY archived_at DESC
                LIMIT 15
            ) a;
        """)
        if raw and not raw.startswith("ERROR") and raw != "empty":
            archs = []
            for line in raw.split("\n"):
                line = line.strip()
                if line:
                    try: archs.append(json.loads(line))
                    except Exception: continue
            if archs:
                print(f"📜 Recent Activity (last {len(archs)} archived):")
                for a in archs:
                    body = a.get("body", {})
                    if isinstance(body, str):
                        try: body = json.loads(body)
                        except: body = {}
                    frm = body.get("from", "?")
                    to = body.get("to", "?")
                    subj = body.get("subject", "(no subject)")[:35]
                    ts = a.get("archived_at", "")[:19] if a.get("archived_at") else ""
                    err = f" ❌ {a.get('error','')[:40]}" if a.get("error") else " ✅"
                    print(f"   [{ts}] {frm} → {to:10s} \"{subj}\"{err}")
                print()
        else:
            if show_archived:
                print("📜 No archived messages found.")
                print()
    elif total_pending == 0 and total_proc == 0:
        print("📭 No activity. All queues idle.")
        print()
    else:
        print("💡 Tip: use 'hc bus --all' or 'hc bus --archived' to see archived messages.")
        print()


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
    if _HAS_LIB:
        print(f"   Bus URL      = {BUS_URL or '(unset)'}")
        print(f"   Fallback URL = {BUS_FALLBACK_URL or '(unset)'}")
        print(f"   Backend      = HTTP (active bus, fallback on failure)")
        print(f"   Auth         = Bearer → Basic fallback (via lib.cortex_bus)")
    else:
        print(f"   Backend      = ❌ lib.cortex_bus not importable (run cortex-update.sh)")
    print(f"\nTip: Any agent's inbox is readable:")
    print(f"  hc inbox moses    hc inbox joseph    hc inbox esther")


def cmd_kill(cfg: dict, args: list):
    """Kill a fleet agent — emergency stop.

    Usage: hc kill <agent> [--reason <why>] [--no-rollback] [--dry-run]

    If no reason given, prompts for one. Sends KILL via bus + records
    outerloop evidence + creates HITL escalation.
    """
    if not args:
        print("Usage: hc kill <agent> [--reason <why>] [--no-rollback] [--dry-run]")
        print("       hc kill all         # Kill every agent in the fleet")
        print("       hc kill esther --reason 'Security breach'")
        print("       hc kill esther --no-rollback --dry-run")
        return

    # Parse args
    clean_args = list(args)
    target = clean_args[0]
    extra_args = []

    reason = None
    no_rollback = False
    dry_run = False

    i = 1
    while i < len(clean_args):
        if clean_args[i] == "--reason" and i + 1 < len(clean_args):
            reason = clean_args[i + 1]
            i += 2
        elif clean_args[i] == "--no-rollback":
            no_rollback = True
            i += 1
        elif clean_args[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            extra_args.append(clean_args[i])
            i += 1

    if not reason:
        print("⚠️  Kill requires a reason. Provide one with --reason")
        print("   Example: hc kill esther --reason 'Emergency maintenance'")
        return

    # Build fleet-kill-switch args
    ks_script = str(Path.home() / "hermes-cortex" / "ops" / "scripts" / "manage" / "fleet-kill-switch.py")
    ks_args = [sys.executable, ks_script, "--reason", reason]
    if target != "all":
        ks_args.extend(["--agent", target])
    if no_rollback:
        ks_args.append("--no-rollback")
    if dry_run:
        ks_args.append("--dry-run")

    result = subprocess.run(ks_args, timeout=60, text=True)
    sys.exit(result.returncode)


def cmd_exec(cfg: dict, args: list):
    """Execute a command on a remote agent via the bus.

    Usage: hc exec <agent> <command> [args...] [--output-schema <name>]
           hc exec <agent> -- <command with args>
           hc exec <agent> <command> --timeout <seconds>

    Validates the EXEC payload against handoff_schema before sending
    and validates the EXEC_RESULT against the specified output schema.

    Schemas: EXEC, EXEC_RESULT, WAVE_RESULT, UPDATE_REQUEST, UPDATE_RESULT
    """
    # Parse --output-schema and --timeout from args
    output_schema = "EXEC_RESULT"
    timeout_seconds = 120  # default: quick command + one handler tick
    clean_args = list(args)
    for i in range(len(clean_args) - 1, -1, -1):
        if clean_args[i] == "--output-schema" and i + 1 < len(clean_args):
            output_schema = clean_args[i + 1]
            clean_args.pop(i + 1)
            clean_args.pop(i)
            break
    for i in range(len(clean_args) - 1, -1, -1):
        if clean_args[i] == "--timeout" and i + 1 < len(clean_args):
            try:
                timeout_seconds = max(10, int(clean_args[i + 1]))
            except ValueError:
                print(f"⚠️  Invalid --timeout '{clean_args[i + 1]}' — using {timeout_seconds}s")
            clean_args.pop(i + 1)
            clean_args.pop(i)
            break

    if len(clean_args) < 2:
        print("Usage: hc exec <agent> <command> [args...] [--output-schema <name>]")
        print("       hc exec <agent> <command> [--timeout <seconds>]")
        print()
        print("Examples:")
        print("  hc exec esther manage/cortex-doctor.py --json")
        print("  hc exec gisu manage/cortex-doctor.py --quiet")
        print("  hc exec joseph -- df -h /")
        print("  hc exec kustos manage/cortex-doctor.py --json --output-schema WAVE_RESULT")
        print("  hc exec kustos install-provider-timeouts.sh --timeout 60")
        print()
        print(f"Available schemas: EXEC, EXEC_RESULT, WAVE_RESULT, UPDATE_REQUEST, UPDATE_RESULT")
        print()
        print("Note: command resolves relative to ~/.hermes-cortex/scripts/ on target.")
        print("      Use absolute paths with caution.")
        return

    agent = clean_args[0]
    command = clean_args[1]
    params = clean_args[2:]

    # Import handoff_schema (available after deployment)
    _validate = lambda _p, _s: (True, [])  # no-op fallback (schema-less)
    try:
        sys.path.insert(0, str(Path.home() / ".hermes-cortex" / "scripts" / "lib"))
        from handoff_schema import validate_payload as _validate
        _HAS_SCHEMA = True
    except ImportError:
        try:
            sys.path.insert(0, str(Path.home() / "hermes-cortex" / "ops" / "scripts" / "lib"))
            from handoff_schema import validate_payload as _validate
            _HAS_SCHEMA = True
        except ImportError:
            _HAS_SCHEMA = False

    # Generate unique correlation ID
    corr_id = f"exec-{uuid.uuid4().hex[:12]}"

    exec_payload = {
        "command": command,
        "params": params,
        "timeout": 120,
        "output_schema": output_schema,
    }

    # Validate EXEC payload before sending
    if _HAS_SCHEMA:
        valid, errs = _validate(exec_payload, "EXEC")
        if not valid:
            print("❌ EXEC payload validation failed:")
            for e in errs:
                print(f"   - {e}")
            print()
            print("Fix the command and retry.")
            return
        print(f"✅ EXEC payload validated against schema")

    body = {
        "from": cfg["agent"],
        "to": agent,
        "topic": "command",
        "subject": "EXEC",
        "correlation_id": corr_id,
        "body": json.dumps(exec_payload),
    }

    queue = f"inbox_{agent}"
    print(f"📤 Sending EXEC to {agent} (corr={corr_id})...")
    result = _send_message(queue, body)
    print(f"   {result}")
    print()

    # Record verification (non-blocking — send succeeded regardless)
    if not result.startswith("❌"):
        _record_verification(corr_id, agent, "EXEC", "EXEC", timeout_seconds)

    # Poll for the result. The handler ALWAYS sends *_RESULT to inbox_moses,
    # but the result may be ARCHIVED by the receiving handler before the
    # live-queue poll sees it — the live peek only returns 'pending'
    # messages. So poll BOTH the live queue AND bus.archives each cycle
    # (the archive-blindness hang, 2026-08-06).
    moses_queue = "inbox_moses"
    deadline = time.time() + timeout_seconds
    poll_interval = 10  # every 10 seconds
    print(f"⏳ Waiting for EXEC_RESULT from {agent} (live + archives, max {timeout_seconds}s)...")
    print()

    while time.time() < deadline:
        time.sleep(poll_interval)
        found = _match_result_msg(moses_queue, corr_id, agent, command,
                                  output_schema, _HAS_SCHEMA, _validate)
        if found:
            return
        print(f"   ⏳ still waiting... ({(deadline - time.time()):.0f}s remaining)")

    print("❌ Timed out waiting for EXEC_RESULT.")
    print(f"   Checked live queue AND archives for {timeout_seconds}s and found no result.")
    print(f"   The agent may not have agent-message-handler running, the command may")
    print(f"   have taken longer than {timeout_seconds}s, or the result never arrived.")
    print(f"   Re-run with --timeout <longer> for long commands, or check:")
    print(f"     hc bus --all   (recent archived activity)")


def _match_result_msg(queue: str, corr_id: str, agent: str, command: str,
                      output_schema: str, has_schema, validate) -> bool:
    """Check live queue + archives for the matching EXEC_RESULT.

    Returns True when found (and prints the result); False to keep polling.
    """
    candidates = list(_get_messages(queue))
    # Also check archives — results archived by the handler before the
    # live poll saw them would otherwise be missed forever.
    try:
        candidates.extend(_get_archives(queue))
    except Exception as e:
        print(f"  ⚠️  archive check failed: {e}", file=sys.stderr)

    for msg in candidates:
        body_raw = msg.get("body", {})
        if isinstance(body_raw, str):
            try:
                body_raw = json.loads(body_raw)
            except json.JSONDecodeError:
                continue
        msg_corr = body_raw.get("correlation_id", "")
        msg_subj = body_raw.get("subject", "")
        if msg_corr == corr_id and msg_subj == "EXEC_RESULT":
            # Found our result
            inner = body_raw.get("body", {})
            if isinstance(inner, str):
                try:
                    inner = json.loads(inner)
                except json.JSONDecodeError:
                    inner = {"raw": inner}

            # Validate result against schema
            if has_schema and output_schema != "RAW":
                svalid, serrs = validate(inner, output_schema)
                if svalid:
                    print(f"✅ EXEC_RESULT validated against '{output_schema}' schema")
                else:
                    print(f"⚠️  EXEC_RESULT schema violations ({output_schema}):")
                    for e in serrs:
                        print(f"   - {e}")

            success = inner.get("success", False)
            stdout = inner.get("stdout", "")
            stderr = inner.get("stderr", "")
            exit_code = inner.get("exit_code", -1)
            cmd_run = inner.get("command", command)
            duration = inner.get("duration_ms", None)

            icon = "✅" if success else "❌"
            print(f"{icon} EXEC_RESULT from {agent}:")
            print(f"   Command: {cmd_run}")
            print(f"   Exit:    {exit_code}")
            if duration is not None:
                print(f"   Duration: {duration}ms")
            if stdout:
                print(f"   stdout:  {stdout[:2000]}")
                if len(stdout) > 2000:
                    print(f"            ... ({len(stdout)} chars total)")
            if stderr:
                print(f"   stderr:  {stderr[:500]}")
                if len(stderr) > 500:
                    print(f"            ... ({len(stderr)} chars total)")
            print()
            if not success:
                print("⚠️  Command failed (non-zero exit).")
            return True
    return False


def cmd_help(cfg: dict, args: list):
    """Show this help."""
    print(__doc__.strip())
    print()
    print("Quick reference:")
    print(f"  hc inbox              — read your inbox ({cfg['agent']})")
    print("  hc inbox <agent>      — read any agent's inbox")
    print("  hc send <a> <subj>    — send a message")
    print("  hc exec <a> <cmd>    — execute a script on remote agent")
    print("  hc status             — bus health + queue depths + fleet")
    print("  hc depth [agent]      — queue depth (all or specific)")
    print("  hc fleet              — agent health statuses")
    print("  hc bus                — full bus dashboard (queues, processing, stuck, DLQ)")
    print("  hc bus --all          — include archived activity")
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
    "exec": cmd_exec,
    "status": cmd_status,
    "depth": cmd_depth,
    "fleet": cmd_fleet,
    "bus": cmd_bus,
    "watch": cmd_watch,
    "doctor": cmd_doctor,
    "dashboard": cmd_dashboard,
    "kill": cmd_kill,
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

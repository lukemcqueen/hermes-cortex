#!/usr/bin/env python3
"""
orch-bus-confirmation-poller.py — Track sent bus messages, collect confirmations, alert on failures.

Three modes:
  1. send     — Send a message via bus, record in tracker, return job_id
  2. poll     — Read inbox_moses for confirmations, update tracker
  3. status   — Show pending / failed confirmations
  4. alert    — List messages past deadline with no confirmation

Usage:
  python3 orch-bus-confirmation-poller.py send <queue> <message> [--deadline <minutes>] [--correlation-id <uuid>]
  python3 orch-bus-confirmation-poller.py poll
  python3 orch-bus-confirmation-poller.py status
  python3 orch-bus-confirmation-poller.py alert [--deadline <minutes>]
"""
import json, os, sys, time, uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

CORTEX_HOME = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex"))
TRACKER_DB = CORTEX_HOME / "data" / "message-tracker.json"
BUS_URL = os.environ.get("CORTEX_BUS_URL", "http://127.0.0.1:8903")
BUS_FALLBACK_URL = os.environ.get(
    "CORTEX_BUS_FALLBACK_URL",
    os.environ.get("CORTEX_BUS_FALLBACK_URL", ""),
)
CONFIG_FILE = CORTEX_HOME / "cortex-bus.conf"


def _read_config(key: str) -> str:
    """Read a value from config file. Returns empty string if not found."""
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return ""


def _get_auth_header() -> tuple[str, str]:
    """Return (scheme, credentials) for bus auth.
    
    Tries in order:
      1. Bearer token from CORTEX_BUS_TOKEN (env or config)
      2. Basic auth from CORTEX_BASIC_AUTH (env or config)
    
    Returns (scheme, value) where scheme is 'Bearer' or 'Basic'.
    Falls back to ('Basic', '') if nothing configured.
    """
    import base64
    
    token = os.environ.get("CORTEX_BUS_TOKEN", "") or _read_config("CORTEX_BUS_TOKEN")
    if token:
        return ("Bearer", token)
    
    basic = os.environ.get("CORTEX_BASIC_AUTH", "") or _read_config("CORTEX_BASIC_AUTH")
    if basic:
        encoded = base64.b64encode(basic.encode()).decode()
        return ("Basic", encoded)
    
    return ("Basic", "")


def _bus_post(endpoint: str, payload: dict, fallback: bool = False) -> dict:
    """POST to bus API with retry and exponential backoff.
    
    Args:
        endpoint: API path (e.g. /api/pgmq/send)
        payload: JSON-serializable dict
        fallback: If True, use BUS_FALLBACK_URL instead of BUS_URL
    """
    scheme, creds = _get_auth_header()
    base_url = BUS_FALLBACK_URL if (fallback and BUS_FALLBACK_URL) else BUS_URL
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode()
    last_error = ""
    for attempt in range(3):
        try:
            req = Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"{scheme} {creds}")
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except (URLError, OSError, TimeoutError) as e:
            body = e.read().decode() if hasattr(e, 'read') else str(e)[:200]
            last_error = body
            if attempt < 2:
                delay = (2 ** attempt) * 2  # 2s, 4s
                time.sleep(delay)
    return {"error": last_error}


def _tracker_load() -> dict:
    """Load the tracker database."""
    if TRACKER_DB.exists():
        try:
            return json.loads(TRACKER_DB.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled
    return {"messages": []}


def _tracker_save(data: dict):
    """Save the tracker database."""
    TRACKER_DB.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_DB.write_text(json.dumps(data, indent=2))


def cmd_send(args):
    """Send a message, record in tracker."""
    if len(args) < 2:
        print("Usage: send <queue> <message> [--deadline <min>] [--correlation-id <uuid>]", file=sys.stderr)
        sys.exit(1)

    queue = args[0]
    message_text = args[1]
    deadline_min = 15  # default 15 minutes — agents should complete tasks in minutes
    correlation_id = str(uuid_mod.uuid4())

    # Parse optional args
    rest = args[2:]
    for i, a in enumerate(rest):
        if a == "--deadline" and i + 1 < len(rest):
            deadline_min = int(rest[i + 1])
        elif a == "--correlation-id" and i + 1 < len(rest):
            correlation_id = rest[i + 1]

    # Send via bus
    payload = {
        "queue": queue,
        "message": message_text,
        "correlation_id": correlation_id,
    }
    result = _bus_post("/api/pgmq/send", payload)

    if "msg_id" in result:
        msg_id = result["msg_id"]
        now = datetime.now(timezone.utc).isoformat()
        deadline = (datetime.now(timezone.utc) + timedelta(minutes=deadline_min)).isoformat()

        tracker = _tracker_load()
        tracker["messages"].append({
            "msg_id": msg_id,
            "correlation_id": correlation_id,
            "queue": queue,
            "message_preview": message_text[:100],
            "sent_at": now,
            "deadline": deadline,
            "confirmed": False,
            "confirmed_at": None,
            "action_taken": None,
            "details": None,
            "escalated": False,
        })
        _tracker_save(tracker)
        print(f"SENT msg_id={msg_id} correlation_id={correlation_id} queue={queue} deadline={deadline_min}m")
    else:
        print(f"FAILED to send: {result}", file=sys.stderr)
        sys.exit(1)


def cmd_poll(args):
    """Read inbox_moses for confirmation messages, update tracker."""
    result = _bus_post("/api/pgmq/read", {"queue": "inbox_moses", "vt": 30})

    if result.get("msg_id") is None:
        print("No confirmations pending")
        return

    msg = result.get("body", {})
    msg_id = result["msg_id"]
    correlation_id = result.get("correlation_id", "")

    if not isinstance(msg, dict):
        msg = {"raw": str(msg)[:200]}

    if not correlation_id:
        # Fallback: check inside body
        correlation_id = msg.get("correlation_id", "")

    action_taken = msg.get("action_taken", "")
    status = msg.get("status", "")
    details = msg.get("details", "")

    # Also check at root level for metadata fields
    if not action_taken:
        action_taken = result.get("action_taken", "")
    if not status:
        status = result.get("status", "")

    if not correlation_id:
        _bus_post("/api/pgmq/archive", {"queue": "inbox_moses", "msg_id": msg_id})
        print(f"Archived message without correlation_id msg_id={msg_id}")
        cmd_poll(args)
        return

    # Update tracker
    tracker = _tracker_load()
    found = False
    for m in tracker["messages"]:
        if m["correlation_id"] == correlation_id:
            m["confirmed"] = True
            m["confirmed_at"] = datetime.now(timezone.utc).isoformat()
            m["action_taken"] = action_taken
            m["details"] = details
            m["status"] = status
            found = True
            break

    # Archive the confirmation
    _bus_post("/api/pgmq/archive", {"queue": "inbox_moses", "msg_id": msg_id})

    if found:
        print(f"CONFIRMED correlation_id={correlation_id} action={action_taken} status={status}")
    else:
        print(f"WARN: Confirmation for unknown correlation_id={correlation_id} (archived)")

    _tracker_save(tracker)
    # Try next message
    cmd_poll(args)


def cmd_status(args):
    """Show pending / confirmed message status."""
    tracker = _tracker_load()
    msgs = tracker.get("messages", [])

    if not msgs:
        print("No tracked messages")
        return

    pending = [m for m in msgs if not m["confirmed"]]
    confirmed = [m for m in msgs if m["confirmed"]]

    print(f"Total: {len(msgs)} | Confirmed: {len(confirmed)} | Pending: {len(pending)}")
    print()

    if pending:
        print("─── PENDING ───")
        for m in sorted(pending, key=lambda x: x["sent_at"]):
            deadline = m.get("deadline", "?")
            overdue = ""
            if deadline != "?":
                try:
                    dt = datetime.fromisoformat(deadline)
                    if dt < datetime.now(timezone.utc):
                        overdue = " ⏰ OVERDUE"
                    else:
                        remaining = (dt - datetime.now(timezone.utc)).total_seconds()
                        overdue = f" ({int(remaining/60)}m remaining)"
                except (ValueError, TypeError):
                    pass  # expected — silently handled
            print(f"  {m['correlation_id'][:8]} → {m['queue']:20s} | {m['message_preview'][:50]:50s} | sent={m['sent_at'][:19]}{overdue}")

    if confirmed:
        print()
        print("─── CONFIRMED ───")
        for m in sorted(confirmed, key=lambda x: x["confirmed_at"]):
            print(f"  {m['correlation_id'][:8]} → {m['queue']:20s} | ✓ {m.get('action_taken','?')} | at={m['confirmed_at'][:19]}")


def cmd_alert(args):
    """List pending messages past deadline."""
    deadline_min = 60
    if args and args[0] == "--deadline" and len(args) > 1:
        deadline_min = int(args[1])

    tracker = _tracker_load()
    now = datetime.now(timezone.utc)

    overdue = []
    for m in tracker.get("messages", []):
        if m["confirmed"]:
            continue
        deadline = m.get("deadline")
        if deadline:
            try:
                dt = datetime.fromisoformat(deadline)
                if dt < now:
                    overdue.append(m)
            except (ValueError, TypeError):
                pass  # expected — silently handled

    if not overdue:
        print("No overdue messages")
        return

    print(f"⚠️  {len(overdue)} message(s) past deadline:")
    for m in sorted(overdue, key=lambda x: x["deadline"]):
        mins_over = int((now - datetime.fromisoformat(m["deadline"])).total_seconds() / 60)
        print(f"  {m['correlation_id'][:8]} → {m['queue']:20s} | {m['message_preview'][:50]} | {mins_over}m overdue")


def cmd_report(args):
    """Combined bus health report: tracker status + queue depths + DLQ health.
    Silent when everything is healthy — only outputs on issues."""
    
    tracker = _tracker_load()
    msgs = tracker.get("messages", [])
    pending = [m for m in msgs if not m["confirmed"]]
    overdue = []
    now = datetime.now(timezone.utc)
    for m in pending:
        deadline = m.get("deadline")
        if deadline:
            try:
                if datetime.fromisoformat(deadline) < now:
                    overdue.append(m)
            except (ValueError, TypeError):
                pass  # expected — silently handled
    scheme, creds = _get_auth_header()
    dlq_issues = []
    queue_lines = []
    try:
        req = Request(f"{BUS_URL}/api/pgmq/queues",
                      headers={"Authorization": f"{scheme} {creds}"},
                      method="GET")
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        queues = data.get("queues", []) if isinstance(data, dict) else data
        inbox_queues = [q for q in queues if q.get("name", "").startswith("inbox_")]
        for q in sorted(inbox_queues, key=lambda x: x["name"]):
            name = q["name"]
            depth = q.get("depth", 0)
            processing = q.get("processing", 0)
            is_dlq = q.get("dlq", False)
            marker = " ⚠️ DLQ" if is_dlq and (depth > 0 or processing > 0) else ""
            if is_dlq and (depth > 0 or processing > 0):
                dlq_issues.append(f"{name}(depth={depth}, processing={processing})")
            queue_lines.append(f"   {name:35s} depth={depth} processing={processing}{marker}")
    except Exception as e:
        queue_lines.append(f"  ⚠️ Could not query queues: {str(e)[:100]}")

    # Silent exit if nothing to report
    if not overdue and not dlq_issues and not pending:
        return

    print("📊 Bus Message Health Report")
    print()

    # Tracker status
    confirmed_count = len([m for m in msgs if m["confirmed"]])
    print(f"📬 Messages tracked: {len(msgs)}")
    print(f"   ✅ Confirmed: {confirmed_count}")
    print(f"   ⏳ Pending:   {len(pending)}")
    if overdue:
        print(f"   ⏰ Overdue:   {len(overdue)}")
        for m in overdue:
            mins = int((now - datetime.fromisoformat(m["deadline"])).total_seconds() / 60)
            print(f"      {m['correlation_id'][:8]} → {m['queue']} ({mins}m overdue)")
    print()

    # Queue depths
    print(f"📨 Inbox queues ({len(queue_lines)}):")
    for line in queue_lines:
        print(line)
    if dlq_issues:
        print(f"\n⚠️  DLQ backlog: {', '.join(dlq_issues)}")
    print()

    # Summary line
    total = len(msgs)
    if overdue:
        print(f"Summary: {total} tracked | {confirmed_count} confirmed | {len(overdue)} overdue ⚠️")
    elif pending:
        print(f"Summary: {total} tracked | {confirmed_count} confirmed | {len(pending)} pending ✓")
    else:
        print(f"Summary: {total} tracked | All confirmed ✓")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: poll mode (for cron usage with no_agent=True)
        cmd_poll([])
        sys.exit(0)

    command = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "send": cmd_send,
        "poll": cmd_poll,
        "status": cmd_status,
        "alert": cmd_alert,
        "report": cmd_report,
    }

    if command not in commands:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(f"Known: {', '.join(commands.keys())}", file=sys.stderr)
        sys.exit(1)

    commands[command](args)

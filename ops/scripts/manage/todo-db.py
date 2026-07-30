#!/usr/bin/env python3
"""
Todo DB — persistent cross-session todo storage for Hermes Cortex agents.

Uses the shared gbrain Postgres (bus.todos table) so items survive
session boundaries and are fleet-visible.

Usage:
    todo-db.py list [--agent <name>] [--status <status>]
    todo-db.py add <content> [--agent <name>] [--priority <n>]
    todo-db.py update <id> --status <new-status>
    todo-db.py pending          # print pending items as JSON (for session start)
    todo-db.py restore <json>   # bulk restore from JSON file (session start)
    todo-db.py save-end         # archive completed, save pending (session end)
"""

import functools
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────

GBRAIN_CONFIG = os.path.expanduser("~/.gbrain/config.json")

@functools.lru_cache(maxsize=1)
def _get_db_query() -> list[str]:
    """Return platform-appropriate psql invocation.

    macOS → reads ~/.gbrain/config.json, builds a direct psql call.
    Linux  → uses sg docker ... (unchanged).
    """
    if platform.system() == "Darwin":
        if os.path.exists(GBRAIN_CONFIG):
            with open(GBRAIN_CONFIG) as f:
                cfg = json.load(f)
            url = cfg.get("database_url", "postgresql://gbrain:@127.0.0.1:15432/gbrain")
        else:
            url = "postgresql://gbrain:@127.0.0.1:15432/gbrain"
        # postgresql://user:***@host:port/dbname → psql -h host -p port -U user -d dbname
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return [
            shutil.which("psql") or "/opt/homebrew/bin/psql",
            "-h", parsed.hostname or "127.0.0.1",
            "-p", str(parsed.port or 15432),
            "-U", parsed.username or "gbrain",
            "-d", parsed.path.lstrip("/") if parsed.path else "gbrain",
            "-t", "-A", "-F", "||",
        ]
    # Linux — unchanged sg docker invocation
    return [
        "sg", "docker", "-c",
        "docker exec -i gbrain-postgres psql -U gbrain -d gbrain -t -A -F '||'"
    ]

AGENT_NAME = os.environ.get("AGENT_NAME") or subprocess.run(
    ["python3", "-c", "import socket; print(socket.gethostname())"],
    capture_output=True, text=True, timeout=5
).stdout.strip()


# ── Helpers ───────────────────────────────────────────────────

def psql(query: str, params: list | None = None) -> str:
    """Run a SQL query via psql and return raw output."""
    full_query = query
    if params:
        # Safe parameter interpolation for UUIDs and simple types
        for p in params:
            # Replace first ? with properly escaped value
            idx = full_query.find("?")
            if idx >= 0:
                if p is None:
                    replacement = "NULL"
                elif p in ("pending", "in_progress", "completed", "cancelled"):
                    replacement = f"'{p}'"
                else:
                    replacement = f"'{p.replace(chr(39), chr(39)+chr(39))}'"
                full_query = full_query[:idx] + replacement + full_query[idx+1:]
    result = subprocess.run(
        _get_db_query(), input=full_query, capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def parse_row(line: str) -> dict:
    """Parse a ||-delimited psql output line into a dict."""
    parts = [p.strip() for p in line.split("||")]
    if len(parts) < 8:
        return {}
    return {
        "id": parts[0],
        "agent_name": parts[1],
        "content": parts[2],
        "status": parts[3],
        "session_id": parts[4],
        "priority": int(parts[5]) if parts[5] else 0,
        "created_at": parts[6],
        "updated_at": parts[7],
    }


# ── Commands ──────────────────────────────────────────────────

def cmd_list(agent: str | None, status: str | None):
    """List todos for an agent, optionally filtered by status."""
    conditions = []
    if agent:
        conditions.append(f"t.agent_name = '{agent}'")
    if status:
        conditions.append(f"t.status = '{status}'")
    where = " AND ".join(conditions) if conditions else "TRUE"

    raw = psql(
        f"SELECT t.id, t.agent_name, t.content, t.status, t.session_id, "
        f"t.priority, t.created_at, t.updated_at "
        f"FROM bus.todos t WHERE {where} ORDER BY t.priority DESC, t.created_at ASC;"
    )
    if not raw:
        print("No todos found.")
        return

    print(f"{'ID':<38} {'Agent':<12} {'Status':<14} {'Priority':<9} {'Content'}")
    print("-" * 100)
    for line in raw.split("\n"):
        if not line.strip():
            continue
        row = parse_row(line)
        if not row:
            continue
        print(f"{row['id']:<38} {row['agent_name']:<12} {row['status']:<14} "
              f"{row['priority']:<9} {row['content']}")


def cmd_add(content: str, agent: str | None, priority: int):
    """Add a new todo item."""
    agent = agent or AGENT_NAME
    new_id = str(uuid.uuid4())
    session_id = os.environ.get("HERMES_SESSION_ID", "")
    psql(
        "SELECT bus.todo_upsert(?::uuid, ?, ?, 'pending', ?, ?);",
        [new_id, agent, content, session_id or None, str(priority)]
    )
    print(f"✅ Todo added: {new_id[:8]}... — {content}")


def cmd_update(todo_id: str, new_status: str):
    """Update a todo item's status."""
    if new_status not in ("pending", "in_progress", "completed", "cancelled"):
        print(f"ERROR: Invalid status '{new_status}'. Must be one of: pending, in_progress, completed, cancelled.", file=sys.stderr)
        sys.exit(1)
    psql(
        "UPDATE bus.todos SET status = ?, updated_at = now() WHERE id = ?::uuid;",
        [new_status, todo_id]
    )
    print(f"✅ Todo {todo_id[:8]}... → {new_status}")


def cmd_pending():
    """Print pending/in_progress todos as JSON for session restore."""
    raw = psql(
        f"SELECT t.id, t.agent_name, t.content, t.status, t.session_id, "
        f"t.priority, t.created_at, t.updated_at "
        f"FROM bus.todos t "
        f"WHERE t.agent_name = '{AGENT_NAME}' AND t.status IN ('pending', 'in_progress') "
        f"ORDER BY t.priority DESC, t.created_at ASC;"
    )
    items = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        row = parse_row(line)
        if row:
            items.append({
                "id": row["id"],
                "agent_name": row["agent_name"],
                "content": row["content"],
                "status": row["status"],
                "session_id": row["session_id"],
                "priority": row["priority"],
            })
    print(json.dumps(items, indent=2))


def cmd_restore(json_file: str):
    """Bulk-restore todos from a JSON file (session start)."""
    if not os.path.exists(json_file):
        print(f"No restore file: {json_file} — starting fresh.")
        return
    with open(json_file) as f:
        items = json.load(f)
    if not items:
        print("No pending todos to restore.")
        return

    count = 0
    for item in items:
        psql(
            "SELECT bus.todo_upsert(?::uuid, ?, ?, ?, ?, ?);",
            [item["id"], item.get("agent_name", AGENT_NAME),
             item["content"], item.get("status", "pending"),
             item.get("session_id"), str(item.get("priority", 0))]
        )
        count += 1
    print(f"✅ Restored {count} pending todo(s) from {json_file}")


def cmd_save_end():
    """Session-end: archive completed/cancelled items, keep pending."""
    result = psql("SELECT bus.todo_archive_old(?);", [AGENT_NAME])
    archived = result.strip()
    print(f"Archived {archived} completed/cancelled todos for {AGENT_NAME}.")

    # Print remaining pending for the next session
    pending_result = psql(
        f"SELECT COUNT(*) FROM bus.todos "
        f"WHERE agent_name = '{AGENT_NAME}' AND status IN ('pending', 'in_progress');"
    )
    pending = pending_result.strip()
    if pending and int(pending) > 0:
        print(f"⚠️  {pending} pending todo(s) remain for next session.")


# ── CLI ───────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        agent = None
        status = None
        for i in range(2, len(sys.argv)):
            if sys.argv[i] == "--agent" and i + 1 < len(sys.argv):
                agent = sys.argv[i + 1]
            if sys.argv[i] == "--status" and i + 1 < len(sys.argv):
                status = sys.argv[i + 1]
        cmd_list(agent, status)

    elif command == "add":
        content = None
        agent = None
        priority = 0
        for i in range(2, len(sys.argv)):
            if i == 2 and not sys.argv[i].startswith("--"):
                content = sys.argv[i]
            elif sys.argv[i] == "--agent" and i + 1 < len(sys.argv):
                agent = sys.argv[i + 1]
            elif sys.argv[i] == "--priority" and i + 1 < len(sys.argv):
                priority = int(sys.argv[i + 1])
        if not content:
            print("ERROR: content required. Usage: todo-db.py add <content>", file=sys.stderr)
            sys.exit(1)
        cmd_add(content, agent, priority)

    elif command == "update":
        if len(sys.argv) < 5 or "--status" not in sys.argv:
            print("ERROR: Usage: todo-db.py update <id> --status <new-status>", file=sys.stderr)
            sys.exit(1)
        todo_id = sys.argv[2]
        new_status = sys.argv[sys.argv.index("--status") + 1]
        cmd_update(todo_id, new_status)

    elif command == "pending":
        cmd_pending()

    elif command == "restore":
        json_file = sys.argv[2] if len(sys.argv) > 2 else "/dev/stdin"
        cmd_restore(json_file)

    elif command == "save-end":
        cmd_save_end()

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

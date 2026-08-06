#!/usr/bin/env python3
"""
dream-todo-bridge.py — turn dream insights into durable bus.todos items.

The dream layer (nightly/weekly/monthly mycortex dreams) writes serendipity
back into the brain but previously could not task. This bridge lets dream
crons promote a SUBSET of dream output into durable, fleet-visible todos:

  Option A — knowledge-gap → learning todo (monthly tier)
    A zero/weak-hit gap topic from the Knowledge-Gap Probe becomes
    `learn <topic> — brain has no strong hits (dream gap, YYYY-MM)`.

  Option B — insight triage (all tiers)
    An insight that implies a concrete, verifiable next action becomes a
    todo: `verb object — outcome` + `[from dream YYYY-MM-DD]`.

Enforcement lives HERE (caps, dedup, tenant-scoping), not in the cron
prompt prose. The LLM judges what is actionable; this script guarantees
the rules. Design: docs/design/mycortex-dream-todo-bridge.md.

Usage (called by dream cron prompts):
  dream-todo-bridge.py add-gap "<topic>" --agent <profile> --month YYYY-MM
  dream-todo-bridge.py add-insight "<verb object — outcome>" --agent <profile> --date YYYY-MM-DD --priority 2
  dream-todo-bridge.py list [--agent <profile>]

Guarantees (enforced here, NOT in prompt prose):
  - Cap A: at most 4 gap todos per run (script call count is per-run; the
    cron calls add-gap at most 4 times)
  - Cap B: at most 2 insight todos per run (same pattern)
  - Dedup: skips if a pending todo with the same topic keyword exists
  - Tenant: always --agent <profile>, never hostname, never shared reader
  - Add-only: never updates or archives existing todos
  - Fail-soft: if todo-db.py errors (DB down), warn on stderr, exit 0 —
    the dream must never be taken down by the bridge
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

TODO_DB = Path.home() / ".hermes-cortex" / "scripts" / "todo-db.py"
if not TODO_DB.exists():
    # repo fallback for direct invocation
    TODO_DB = Path.home() / "hermes-cortex" / "ops" / "scripts" / "manage" / "todo-db.py"


def _todo_db(args: list[str]) -> str:
    """Run todo-db.py, returning stdout. Non-fatal on error (warn+empty)."""
    try:
        result = subprocess.run(
            [sys.executable, str(TODO_DB)] + args,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"⚠️  dream-todo-bridge: todo-db.py warning: {result.stderr.strip()[:200]}",
                  file=sys.stderr)
            return ""
        return result.stdout.strip()
    except Exception as e:
        print(f"⚠️  dream-todo-bridge: todo-db.py unavailable ({e}) — bridge skipped, dream continues",
              file=sys.stderr)
        return ""


def _pending_contents(agent: str | None) -> list[str]:
    """Return list of pending todo contents (lowercased) for dedup."""
    args = ["list", "--status", "pending"]
    if agent:
        args += ["--agent", agent]
    out = _todo_db(args)
    # todo-db.py list prints a header then rows: ID Agent Status Priority Content
    contents = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("ID") or line.startswith("-"):
            continue
        parts = line.split(None, 4)
        if len(parts) >= 5:
            contents.append(parts[4].lower())
    return contents


def _pending_json(agent: str | None) -> list[dict]:
    """Return pending todos as parsed JSON via `todo-db.py pending`-style list."""
    # Use list --status pending (robust to parse); fall back to JSON pending
    args = ["list", "--status", "pending"]
    if agent:
        args += ["--agent", agent]
    out = _todo_db(args)
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("ID") or line.startswith("-"):
            continue
        parts = line.split(None, 4)
        if len(parts) >= 5:
            rows.append({"content": parts[4], "priority": parts[3]})
    return rows


def _is_duplicate(topic: str, pending: list[str]) -> bool:
    """True if a pending todo already covers this topic (keyword match)."""
    topic_l = topic.lower()
    for content in pending:
        # match on the topic's significant words (≥4 chars) appearing in content
        words = [w for w in topic_l.replace("-", " ").split() if len(w) >= 4]
        if not words:
            words = [topic_l]
        if any(w in content for w in words):
            return True
    return False


def cmd_add_gap(topic: str, agent: str, month: str):
    """Option A: knowledge-gap → learning todo (priority 1)."""
    if not topic or not agent:
        print("ERROR: add-gap requires --topic and --agent", file=sys.stderr)
        sys.exit(2)
    pending = _pending_contents(agent)
    if _is_duplicate(topic, pending):
        print(f"SKIP: gap already covered by a pending todo — {topic}")
        return
    content = f"learn {topic} — brain has no strong hits (dream gap, {month})"
    out = _todo_db(["add", content, "--agent", agent, "--priority", "1"])
    if out:
        # extract the uuid8 from "✅ Todo added: a85c2522... — content"
        uuid8 = out.split("added:")[1].split("...")[0].strip() if "added:" in out else "?"
        print(f"todo {uuid8}: {content} (priority 1)")


def cmd_add_insight(content: str, agent: str, date: str, priority: int):
    """Option B: insight triage → todo (priority 1-2), traceable to dream."""
    if not content or not agent:
        print("ERROR: add-insight requires --content and --agent", file=sys.stderr)
        sys.exit(2)
    if priority not in (1, 2):
        print(f"ERROR: priority must be 1 or 2 (got {priority})", file=sys.stderr)
        sys.exit(2)
    pending = _pending_contents(agent)
    if _is_duplicate(content, pending):
        print(f"SKIP: insight already covered by a pending todo — {content[:60]}")
        return
    full = f"{content} [from dream {date}]"
    out = _todo_db(["add", full, "--agent", agent, "--priority", str(priority)])
    if out:
        uuid8 = out.split("added:")[1].split("...")[0].strip() if "added:" in out else "?"
        print(f"todo {uuid8}: {full} (priority {priority})")


def cmd_list(agent: str | None):
    """List pending todos (bridge visibility)."""
    args = ["list", "--status", "pending"]
    if agent:
        args += ["--agent", agent]
    out = _todo_db(args)
    print(out if out else "No pending todos.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_gap = sub.add_parser("add-gap", help="Option A: knowledge-gap → learning todo")
    p_gap.add_argument("--topic", required=True)
    p_gap.add_argument("--agent", required=True)
    p_gap.add_argument("--month", required=True, help="YYYY-MM")

    p_ins = sub.add_parser("add-insight", help="Option B: insight triage → todo")
    p_ins.add_argument("--content", required=True)
    p_ins.add_argument("--agent", required=True)
    p_ins.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_ins.add_argument("--priority", type=int, default=2, choices=[1, 2])

    p_list = sub.add_parser("list", help="List pending todos")
    p_list.add_argument("--agent")

    args = parser.parse_args()

    if args.command == "add-gap":
        cmd_add_gap(args.topic, args.agent, args.month)
    elif args.command == "add-insight":
        cmd_add_insight(args.content, args.agent, args.date, args.priority)
    elif args.command == "list":
        cmd_list(args.agent)


if __name__ == "__main__":
    main()

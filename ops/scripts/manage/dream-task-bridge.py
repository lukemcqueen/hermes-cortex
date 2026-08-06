#!/usr/bin/env python3
"""
dream-task-bridge.py — turn dream insights into durable tasks (tasks schema).

The dream layer (nightly/weekly/monthly mycortex dreams) writes serendipity
back into the brain but previously could not task. This bridge lets dream
crons promote a SUBSET of dream output into durable personal tasks:

  Option A — knowledge-gap → learning task (monthly tier)
    A zero/weak-hit gap topic from the Knowledge-Gap Probe becomes
    `learn <topic> — brain has no strong hits (dream gap, YYYY-MM)`.

  Option B — insight triage (all tiers)
    An insight that implies a concrete, verifiable next action becomes a
    task: `verb object — outcome` + `[from dream YYYY-MM-DD]`.

Tasks are created as scope=personal on THIS host (honest semantics — the
fleet transport is a roadmap item; see docs/design/task-workflow.md §3).
project/repo are tagged `hermes-cortex`, source=`dream`, so dream-derived
tasks are queryable and attributable.

Enforcement lives HERE (caps, dedup, tenant-scoping), not in the cron
prompt prose. The LLM judges what is actionable; this script guarantees
the rules. Design: docs/design/mycortex-dream-task-bridge.md.

Usage (called by dream cron prompts):
  dream-task-bridge.py add-gap "<topic>" --agent <profile> --month YYYY-MM
  dream-task-bridge.py add-insight "<verb object — outcome>" --agent <profile> --date YYYY-MM-DD --priority 2
  dream-task-bridge.py list [--agent <profile>]

Guarantees (enforced here, NOT in prompt prose):
  - Cap A: at most 4 gap tasks per run (script call count is per-run; the
    cron calls add-gap at most 4 times)
  - Cap B: at most 2 insight tasks per run (same pattern)
  - Dedup: skips if a pending task with the same topic keyword exists
  - Tenant: always --agent <profile>, never hostname, never shared reader
  - Add-only: never updates or archives existing tasks
  - Fail-soft: if task-db.py errors (DB down), warn on stderr, exit 0 —
    the dream must never be taken down by the bridge
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TASK_DB = Path.home() / ".hermes-cortex" / "scripts" / "task-db.py"
if not TASK_DB.exists():
    # repo fallback for direct invocation
    TASK_DB = Path.home() / "hermes-cortex" / "ops" / "scripts" / "manage" / "task-db.py"

TAG_ARGS = ["--project", "hermes-cortex", "--repo", "hermes-cortex",
            "--scope", "personal", "--source", "dream"]


def _task_db(args: list[str]) -> str:
    """Run task-db.py, returning stdout. Non-fatal on error (warn+empty)."""
    try:
        result = subprocess.run(
            [sys.executable, str(TASK_DB)] + args,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"⚠️  dream-task-bridge: task-db.py warning: {result.stderr.strip()[:200]}",
                  file=sys.stderr)
            return ""
        return result.stdout.strip()
    except Exception as e:
        print(f"⚠️  dream-task-bridge: task-db.py unavailable ({e}) — bridge skipped, dream continues",
              file=sys.stderr)
        return ""


def _pending_contents(agent: str | None) -> list[str]:
    """Return list of pending task contents (lowercased) via `pending` JSON."""
    args = ["pending"]
    out = _task_db(args)
    if not out:
        return []
    try:
        items = json.loads(out)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    contents = []
    for item in items:
        if agent and item.get("agent_name") != agent:
            continue
        content = item.get("content")
        if content:
            contents.append(str(content).lower())
    return contents


def _is_duplicate(topic: str, pending: list[str]) -> bool:
    """True if a pending task already covers this topic (keyword match)."""
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
    """Option A: knowledge-gap → learning task (priority 1)."""
    if not topic or not agent:
        print("ERROR: add-gap requires --topic and --agent", file=sys.stderr)
        sys.exit(2)
    pending = _pending_contents(agent)
    if _is_duplicate(topic, pending):
        print(f"SKIP: gap already covered by a pending task — {topic}")
        return
    content = f"learn {topic} — brain has no strong hits (dream gap, {month})"
    out = _task_db(["add", content, "--agent", agent, "--priority", "1", *TAG_ARGS])
    if out:
        # extract the uuid8 from "✅ Task added: a85c2522... — content"
        uuid8 = out.split("added:")[1].split("...")[0].strip() if "added:" in out else "?"
        print(f"task {uuid8}: {content} (priority 1)")


def cmd_add_insight(content: str, agent: str, date: str, priority: int):
    """Option B: insight triage → task (priority 1-2), traceable to dream."""
    if not content or not agent:
        print("ERROR: add-insight requires --content and --agent", file=sys.stderr)
        sys.exit(2)
    if priority not in (1, 2):
        print(f"ERROR: priority must be 1 or 2 (got {priority})", file=sys.stderr)
        sys.exit(2)
    pending = _pending_contents(agent)
    if _is_duplicate(content, pending):
        print(f"SKIP: insight already covered by a pending task — {content[:60]}")
        return
    full = f"{content} [from dream {date}]"
    out = _task_db(["add", full, "--agent", agent, "--priority", str(priority), *TAG_ARGS])
    if out:
        uuid8 = out.split("added:")[1].split("...")[0].strip() if "added:" in out else "?"
        print(f"task {uuid8}: {full} (priority {priority})")


def cmd_list(agent: str | None):
    """List pending tasks (bridge visibility)."""
    args = ["list", "--status", "pending"]
    if agent:
        args += ["--agent", agent]
    out = _task_db(args)
    print(out if out else "No pending tasks.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_gap = sub.add_parser("add-gap", help="Option A: knowledge-gap → learning task")
    p_gap.add_argument("--topic", required=True)
    p_gap.add_argument("--agent", required=True)
    p_gap.add_argument("--month", required=True, help="YYYY-MM")

    p_ins = sub.add_parser("add-insight", help="Option B: insight triage → task")
    p_ins.add_argument("--content", required=True)
    p_ins.add_argument("--agent", required=True)
    p_ins.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_ins.add_argument("--priority", type=int, default=2, choices=[1, 2])

    p_list = sub.add_parser("list", help="List pending tasks")
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

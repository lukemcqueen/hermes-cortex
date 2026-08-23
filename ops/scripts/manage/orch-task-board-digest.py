#!/usr/bin/env python3
"""orch-task-board-digest.py — daily task board digest for Telegram (T4).

Zero-token no_agent cron: reads the task DB and renders the board —
open counts, per-agent in_progress, review queue (awaiting verify),
claimable slices. Delivered by the scheduler to Telegram (Luke + Amy).

Design: docs/design/task-model-v3.md §4.2. Coverage-aware: missing
agents show as gaps, never zeros (same rule as the cost digest).
Silent on empty board? No — always deliver (the board IS the daily
status; "nothing open" is useful signal).
"""

import json
import os
import sys
from pathlib import Path

HOME = Path.home()
TASK_DB = HOME / "hermes-cortex" / "ops" / "scripts" / "manage" / "task-db.py"


def q(query: str, params: list | None = None) -> str:
    """Run a query through task-db.py's psql bridge (same RLS identity)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("task_db_bridge", TASK_DB)
    if spec is None or spec.loader is None:
        return ""
    tdb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tdb)
    return tdb.psql(tdb.build_query(query, params or []))


def main() -> int:
    try:
        counts_raw = q(
            "SELECT status, count(*) FROM tasks.tasks "
            "WHERE status IN ('pending','in_progress','review') "
            "GROUP BY status ORDER BY status;"
        )
        counts: dict[str, int] = {}
        for line in counts_raw.splitlines():
            parts = line.split("||")
            if len(parts) == 2:
                counts[parts[0]] = int(parts[1])

        inprog_raw = q(
            "SELECT COALESCE(assignee, created_by), count(*) "
            "FROM tasks.tasks WHERE status = 'in_progress' "
            "GROUP BY 1 ORDER BY 2 DESC;"
        )
        by_agent = []
        for line in inprog_raw.splitlines():
            parts = line.split("||")
            if len(parts) == 2:
                by_agent.append((parts[0], int(parts[1])))

        review_raw = q(
            "SELECT t.id, t.created_by, t.content FROM tasks.tasks t "
            "WHERE t.status = 'review' ORDER BY t.status_changed_at ASC LIMIT 10;"
        )
        review = []
        for line in review_raw.splitlines():
            parts = line.split("||")
            if len(parts) >= 3:
                review.append((parts[0][:8], parts[1], parts[2][:70]))

        claimable_raw = q(
            "SELECT t.id, t.priority, t.project, t.content FROM tasks.tasks t "
            "WHERE t.status = 'pending' AND t.kind = 'slice' "
            "AND t.assignee IS NULL "
            "ORDER BY t.priority DESC, t.status_changed_at ASC LIMIT 5;"
        )
        claimable = []
        for line in claimable_raw.splitlines():
            parts = line.split("||")
            if len(parts) >= 4:
                claimable.append((parts[0][:8], parts[1], parts[2][:16],
                                  parts[3][:60]))

        open_total = sum(counts.values())
        lines = [
            "📋 *Task Board — Daily Digest*",
            f"Open: **{open_total}** "
            f"({counts.get('pending', 0)} pending · "
            f"{counts.get('in_progress', 0)} in_progress · "
            f"{counts.get('review', 0)} review)",
        ]
        if by_agent:
            lines.append("")
            lines.append("In progress:")
            for agent, n in by_agent:
                lines.append(f"  • {agent}: {n}")
        if review:
            lines.append("")
            lines.append("In review (awaiting verify):")
            for tid, agent, content in review:
                lines.append(f"  • `{tid}` ({agent}): {content}")
        if claimable:
            lines.append("")
            lines.append("Claimable (pending, no assignee):")
            for tid, pr, proj, content in claimable:
                lines.append(f"  • [{pr}] `{tid}` {proj}: {content}")
        if not counts and not by_agent and not review and not claimable:
            lines.append("")
            lines.append("_No open tasks — queue is clear._")

        print("\n".join(lines))
        return 0
    except Exception as e:
        print(f"❌ board digest error: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

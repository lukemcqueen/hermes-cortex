#!/usr/bin/env python3
"""
Loop Feedback CLI — collect user feedback on STOP/LOOP/MOVE ON decisions.

The system generates decisions autonomously, but only user feedback provides
the ground-truth labels needed for meta-learning. This tool lets you mark a
decision as correct (accepted) or incorrect (overrode), with an optional note.

Usage:
    # List cycles that need feedback
    python3 loop_feedback.py list

    # List recent cycles (with or without feedback)
    python3 loop_feedback.py list --all
    python3 loop_feedback.py list --limit 20

    # Accept a decision (it was correct)
    python3 loop_feedback.py accept <cycle_id>
    python3 loop_feedback.py accept <cycle_id> --note "Good stop, all tests passed"

    # Override a decision (it was wrong)
    python3 loop_feedback.py override <cycle_id>
    python3 loop_feedback.py override <cycle_id> --note "Should have kept looping, more edge cases"

    # Show feedback statistics
    python3 loop_feedback.py stats

    # JSON output (for programmatic use)
    python3 loop_feedback.py list --json
    python3 loop_feedback.py stats --json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loop_db import LoopDB


def format_cycle(c, detail=False):
    """Format a single cycle row for human display."""
    decision_icon = {
        "STOP ✓": "✅",
        "LOOP": "🔄",
        "LOOP 🔄": "🔄",
        "MOVE ON": "→",
        "MOVE ON →": "→",
        "STOP ✗": "❌",
        "STOP ✗ (hard fail)": "❌",
    }.get(c.get("decision", ""), "❓")

    overrode = c.get("user_overrode")
    if overrode is None:
        status = "⏳ needs feedback"
        icon = "?"
    elif overrode == 0:
        status = "✅ accepted"
        icon = "✓"
    else:
        status = "✋ overridden"
        icon = "!"

    line = (
        f"  #{c['id']:>4}  {icon}  {decision_icon} {c.get('decision', '?'):<20}  "
        f"composite={c.get('composite', '?'):>5.1f}  "
        f"task={c.get('task_id', '?'):<16}  "
        f"cycle={c.get('cycle_num', '?')}  "
        f"{c.get('timestamp', '?')[:19]}  "
        f"{status}"
    )

    if detail and c.get("outcome_note"):
        line += f"\n         └─ note: {c['outcome_note']}"

    return line


def cmd_list(args):
    """List cycles, defaulting to those needing feedback."""
    db = LoopDB(args.db or None)
    try:
        if args.all:
            rows = db.conn.execute(
                "SELECT * FROM loop_cycles ORDER BY id DESC LIMIT ?",
                (args.limit,),
            ).fetchall()
        else:
            rows = db.conn.execute(
                "SELECT * FROM loop_cycles WHERE user_overrode IS NULL ORDER BY id DESC LIMIT ?",
                (args.limit,),
            ).fetchall()

        if not rows:
            if args.all:
                print("📭 No cycles in the database yet.")
            else:
                print("✅ All cycles have feedback! Use --all to see everything.")
            return

        # Count feedback status
        total = len(rows)
        pending = sum(1 for r in rows if r["user_overrode"] is None)
        accepted = sum(1 for r in rows if r["user_overrode"] == 0)
        overridden = sum(1 for r in rows if r["user_overrode"] == 1)

        if args.json:
            print(json.dumps([dict(r) for r in rows], indent=2, default=str))
            return

        print(f"📊 Showing {total} cycles ({pending} need feedback, {accepted} accepted, {overridden} overridden)")
        print()
        for r in rows:
            print(format_cycle(dict(r), detail=True))
        print()
        if pending > 0:
            print(f"💡 Tip: use `loop_feedback.py accept <id>` or `loop_feedback.py override <id>`")
    finally:
        db.close()


def cmd_accept(args):
    """Record that a decision was correct."""
    db = LoopDB(args.db or None)
    try:
        cycle = db.get_cycle(args.cycle_id)
        if not cycle:
            print(f"❌ Cycle #{args.cycle_id} not found.")
            sys.exit(1)

        # Already recorded?
        if cycle["user_overrode"] is not None:
            current = "accepted" if cycle["user_overrode"] == 0 else "overridden"
            print(f"⚠️  Cycle #{args.cycle_id} already has feedback ({current}). Use --force to overwrite.")
            if not args.force:
                return

        db.record_user_outcome(args.cycle_id, accepted=True, note=args.note or "")
        cycle = db.get_cycle(args.cycle_id)

        if args.json:
            print(json.dumps({"cycle_id": args.cycle_id, "action": "accepted", "status": "ok"}, indent=2))
            return

        print(f"✅ Recorded: cycle #{args.cycle_id} — ACCEPTED (user agrees with decision)")
        print()
        print(f"  Decision:   {cycle['decision']}")
        print(f"  Composite:  {cycle['composite']}/10")
        print(f"  Task:       {cycle['task_id']} (cycle {cycle['cycle_num']})")
        print(f"  Timestamp:  {cycle['timestamp'][:19]}")
        if args.note:
            print(f"  Note:       {args.note}")
    finally:
        db.close()


def cmd_override(args):
    """Record that a decision was wrong."""
    db = LoopDB(args.db or None)
    try:
        cycle = db.get_cycle(args.cycle_id)
        if not cycle:
            print(f"❌ Cycle #{args.cycle_id} not found.")
            sys.exit(1)

        if cycle["user_overrode"] is not None:
            current = "accepted" if cycle["user_overrode"] == 0 else "overridden"
            print(f"⚠️  Cycle #{args.cycle_id} already has feedback ({current}). Use --force to overwrite.")
            if not args.force:
                return

        db.record_user_outcome(args.cycle_id, accepted=False, note=args.note or "")
        cycle = db.get_cycle(args.cycle_id)

        if args.json:
            print(json.dumps({"cycle_id": args.cycle_id, "action": "overridden", "status": "ok"}, indent=2))
            return

        print(f"✋ Recorded: cycle #{args.cycle_id} — OVERRIDDEN (user disagrees with decision)")
        print()
        print(f"  Decision:   {cycle['decision']}")
        print(f"  Composite:  {cycle['composite']}/10")
        print(f"  Task:       {cycle['task_id']} (cycle {cycle['cycle_num']})")
        print(f"  Timestamp:  {cycle['timestamp'][:19]}")
        if args.note:
            print(f"  Note:       {args.note}")
    finally:
        db.close()


def cmd_stats(args):
    """Show feedback statistics."""
    db = LoopDB(args.db or None)
    try:
        # Overall stats
        total = db.conn.execute("SELECT COUNT(*) AS c FROM loop_cycles").fetchone()["c"]
        with_feedback = db.conn.execute(
            "SELECT COUNT(*) AS c FROM loop_cycles WHERE user_overrode IS NOT NULL"
        ).fetchone()["c"]
        accepted = db.conn.execute(
            "SELECT COUNT(*) AS c FROM loop_cycles WHERE user_overrode = 0"
        ).fetchone()["c"]
        overridden = db.conn.execute(
            "SELECT COUNT(*) AS c FROM loop_cycles WHERE user_overrode = 1"
        ).fetchone()["c"]

        accuracy = db.get_decision_accuracy()

        # Per-decision breakdown
        dec_rows = db.conn.execute("""
            SELECT decision,
                   COUNT(*) AS total,
                   SUM(CASE WHEN user_overrode = 0 THEN 1 ELSE 0 END) AS accepted,
                   SUM(CASE WHEN user_overrode = 1 THEN 1 ELSE 0 END) AS overridden
            FROM loop_cycles
            WHERE user_overrode IS NOT NULL
            GROUP BY decision
            ORDER BY total DESC
        """).fetchall()

        # Recent feedback
        recent = db.conn.execute("""
            SELECT * FROM loop_cycles
            WHERE user_overrode IS NOT NULL
            ORDER BY id DESC
            LIMIT 5
        """).fetchall()

        if args.json:
            print(json.dumps({
                "total_cycles": total,
                "with_feedback": with_feedback,
                "accepted": accepted,
                "overridden": overridden,
                "accuracy": accuracy,
                "per_decision": [dict(r) for r in dec_rows],
            }, indent=2, default=str))
            return

        print("📊 Feedback Statistics")
        print("=" * 55)
        print()
        print(f"  Total cycles logged:    {total}")
        print(f"  With user feedback:     {with_feedback}")
        print(f"  Accepted (correct):     {accepted}")
        print(f"  Overridden (incorrect): {overridden}")
        print()

        if with_feedback > 0:
            acc_pct = round(accepted / with_feedback * 100, 1)
            print(f"  Decision accuracy:      {acc_pct}% ({accepted}/{with_feedback})")
            print()
            print("  Per-decision breakdown:")
            for r in dec_rows:
                dr = dict(r)
                acc = dr.get("accepted", 0) or 0
                ovr = dr.get("overridden", 0) or 0
                print(f"    {dr['decision'][:20]:<22}  {dr['total']} decisions  ({acc} accepted, {ovr} overridden)")
            print()

            print("  Most recent feedback:")
            for r in recent:
                dr = dict(r)
                label = "✅ accepted" if dr["user_overrode"] == 0 else "✋ overridden"
                note = f" — {dr['outcome_note']}" if dr.get("outcome_note") else ""
                print(f"    #{dr['id']} {dr['decision'][:20]:<22}  composite={dr['composite']:.1f}  {label}{note}")
        else:
            print("  No feedback collected yet.")
            print("  💡 Use `loop_feedback.py list` to see cycles needing feedback.")

        print()
        print("=" * 55)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Loop Feedback CLI — ground-truth labels for meta-learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 loop_feedback.py list
  python3 loop_feedback.py accept 42 --note "perfect stop, all edge cases covered"
  python3 loop_feedback.py override 7 --note "should have looped, missed null case"
  python3 loop_feedback.py stats
  python3 loop_feedback.py list --json
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Global --db flag
    parser.add_argument("--db", default=None, help="Custom DB path (default: ~/.hermes/data/loop-governance.db)")

    # list
    list_p = subparsers.add_parser("list", help="List cycles needing feedback")
    list_p.add_argument("--all", action="store_true", help="Show all cycles, not just pending")
    list_p.add_argument("--limit", type=int, default=20, help="Max cycles to show (default: 20)")
    list_p.add_argument("--json", action="store_true", help="JSON output")
    list_p.set_defaults(func=cmd_list)

    # accept
    accept_p = subparsers.add_parser("accept", help="Mark a decision as correct")
    accept_p.add_argument("cycle_id", type=int, help="Cycle ID to accept")
    accept_p.add_argument("--note", "-n", help="Optional note about why")
    accept_p.add_argument("--force", "-f", action="store_true", help="Overwrite existing feedback")
    accept_p.add_argument("--json", action="store_true", help="JSON output")
    accept_p.set_defaults(func=cmd_accept)

    # override
    override_p = subparsers.add_parser("override", help="Mark a decision as incorrect")
    override_p.add_argument("cycle_id", type=int, help="Cycle ID to override")
    override_p.add_argument("--note", "-n", help="Optional note about why")
    override_p.add_argument("--force", "-f", action="store_true", help="Overwrite existing feedback")
    override_p.add_argument("--json", action="store_true", help="JSON output")
    override_p.set_defaults(func=cmd_override)

    # stats
    stats_p = subparsers.add_parser("stats", help="Show feedback statistics")
    stats_p.add_argument("--json", action="store_true", help="JSON output")
    stats_p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

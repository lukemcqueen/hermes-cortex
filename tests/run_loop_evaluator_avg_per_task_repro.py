#!/usr/bin/env python3
"""Runnable regression for the loop_evaluator 'Avg cycles per task' metric.

Why this exists: the weekly report printed `AVG(cycle_num)` — the mean cycle
INDEX of a cycle — under the label "Avg cycles per task", so a week with 1592
cycles over 545 tasks claimed 24.5 while its own Total/Unique lines implied 2.9.
An adversarial review filed the contradiction as fabrication (ADV-12197-1). The
label promises cycles-per-task, so the metric must EQUAL total/unique — this
script asserts exactly that, and fails on the pre-fix SQL.

Hermetic: builds a throwaway SQLite fixture; never touches the live DB.

Usage:  python3 tests/run_loop_evaluator_avg_per_task_repro.py
Exit 0 = the metric is consistent with its label. Non-zero = regression.
"""
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "core/governance/loop_evaluator.py"

FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _fixture():
    """Two tasks: one with 5 cycles, one with 1. True avg/task = 3.0.
    AVG(cycle_num) over 6 rows = (1+2+3+4+5+1)/6 = 2.67 — a different number,
    so the fixture can tell the two formulas apart."""
    db = str(Path(tempfile.mkdtemp(prefix="lg-eval-")) / "lg.db")
    c = sqlite3.connect(db)
    c.execute(
        "CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY, timestamp TEXT, "
        "task_id TEXT, cycle_num INTEGER, completeness REAL, quality REAL, "
        "progress REAL, composite REAL, no_progress INTEGER, decision TEXT, "
        "user_overrode INTEGER)"
    )
    rows = [(1, "2026-10-10 00:00:00", "task-a", 1, 8, 7, 9, 8, 0, "LOOP", None),
            (2, "2026-10-10 01:00:00", "task-a", 2, 8, 7, 9, 8, 0, "LOOP", None),
            (3, "2026-10-10 02:00:00", "task-a", 3, 8, 7, 9, 8, 0, "LOOP", None),
            (4, "2026-10-10 03:00:00", "task-a", 4, 8, 7, 9, 8, 0, "LOOP", None),
            (5, "2026-10-10 04:00:00", "task-a", 5, 8, 7, 9, 8, 0, "STOP ✓", None),
            (6, "2026-10-10 05:00:00", "task-b", 1, 6, 5, 7, 6, 0, "STOP ✓", None)]
    c.executemany("INSERT INTO loop_cycles VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()
    return db


def _metric_fixed(db_path):
    """The FIXED formula: average over TASKS."""
    c = sqlite3.connect(db_path)
    row = c.execute("""
        SELECT COUNT(*) AS total, COUNT(DISTINCT task_id) AS uniq,
               ROUND(1.0 * COUNT(*) / MAX(COUNT(DISTINCT task_id), 1), 1) AS v
        FROM loop_cycles WHERE timestamp >= datetime('now','-30 days')
    """).fetchone()
    c.close()
    return row


def _metric_old(db_path):
    """The DEFECTIVE formula, kept only to prove the fixture can tell the two
    apart. Constant SQL — no caller-supplied fragment is ever interpolated."""
    c = sqlite3.connect(db_path)
    row = c.execute("""
        SELECT COUNT(*) AS total, COUNT(DISTINCT task_id) AS uniq,
               ROUND(AVG(cycle_num), 1) AS v
        FROM loop_cycles WHERE timestamp >= datetime('now','-30 days')
    """).fetchone()
    c.close()
    return row


def main() -> int:
    print("== loop_evaluator avg-cycles-per-task regression ==")
    print(f"   source: {SRC.relative_to(REPO)}")
    check("source exists", SRC.is_file())
    if not SRC.is_file():
        return 1

    text = SRC.read_text()
    # The defective expression must be gone from the metric slot.
    check("no AVG(cycle_num) AS avg_cycles_per_task",
          not re.search(r"AVG\(cycle_num\)\s+AS\s+avg_cycles_per_task", text))
    check("uses COUNT(*)/COUNT(DISTINCT task_id)",
          "COUNT(*) / MAX(COUNT(DISTINCT task_id), 1)" in text)
    # The report line still names the metric (label preserved).
    check("report still prints 'Avg cycles per task'",
          "Avg cycles per task" in text)

    db = _fixture()
    total, uniq, fixed = _metric_fixed(db)
    old_total, old_uniq, old = _metric_old(db)
    print(f"   fixture: total={total} uniq={uniq}  fixed={fixed}  old(AVG(cycle_num))={old}")

    check("label matches arithmetic (fixed == total/unique)",
          abs(fixed - round(total / uniq, 1)) < 0.05,
          f"{fixed} vs {total}/{uniq}={round(total/uniq,1)}")
    check("fixture distinguishes the two formulas", old != fixed,
          f"AVG(cycle_num)={old} would differ from {fixed}")

    print()
    if FAILURES:
        print(f"RESULT: FAIL ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("RESULT: PASS — metric is consistent with its label")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Runnable regression for loop_evaluator window scoping + recommendation direction.

Why this exists (2026-10-19 weekly eval run): two defects in the same report.

1. WINDOW: `get_decision_accuracy()` and `get_threshold_recommendations()` had no
   `timestamp` filter, so a `--days 7` report printed ALL-TIME accuracy —
   measured 38.7% over 11,037 labelled rows when the 7-day figure was 55.3%
   over 642. The header said "last 7 days" while the number described 3 months,
   and that stale mass drove the threshold recommendation.

2. DIRECTION: the STOP recommendation text hardcoded "raising ... to {proposed}"
   with `proposed = min(9.0, avg+0.5)`. With all-time avg 6.0 that yields 6.5,
   i.e. it proposed LOWERING the threshold while telling the reader to raise it,
   and it quoted "composite >= 8.0" when the live config carried 8.2.

Both are asserted here against a throwaway fixture whose in-window and
out-of-window feedback deliberately disagree, so a re-introduced missing WHERE
clause or a hardcoded direction word fails the check.

Hermetic: builds a temp SQLite DB; never touches the live DB.

Usage:  python3 tests/run_loop_evaluator_accuracy_window_repro.py
Exit 0 = window scoping and recommendation direction are correct.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "core/governance/loop_evaluator.py"

FAILURES: list = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


SCHEMA = """
CREATE TABLE loop_cycles (
  id INTEGER PRIMARY KEY, timestamp TEXT, task_id TEXT, cycle_num INTEGER,
  completeness REAL, quality REAL, progress REAL, composite REAL,
  no_progress INTEGER DEFAULT 0, decision TEXT,
  user_overrode INTEGER, spec_hash TEXT, code_hash TEXT, test_output_hash TEXT
);
"""


def build_fixture(path):
    """7-day window: 3 accepted / 1 overridden (75%).
    All-time adds 10 overridden STOPs at composite 5.0 -> 13.3% overall.
    The two differ hugely, so an unscoped query cannot pass the accuracy check.
    """
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    rows = []
    # in-window
    rows += [("datetime('now','-1 days')", "STOP ✓", 0, 8.5)]
    rows += [("datetime('now','-2 days')", "STOP ✓", 0, 8.6)]
    rows += [("datetime('now','-3 days')", "MOVE_ON", 0, 4.0)]
    rows += [("datetime('now','-4 days')", "STOP ✓", 1, 7.0)]
    # out-of-window: pulled the all-time figure to 13.3% from 75%
    for i in range(10):
        rows.append(("datetime('now','-200 days')", "STOP ✓", 1, 5.0))
    for ts_expr, decision, overrode, comp in rows:
        conn.execute(
            f"INSERT INTO loop_cycles (timestamp, task_id, cycle_num, completeness,"
            f" quality, progress, composite, decision, user_overrode)"
            f" VALUES ({ts_expr}, 'fixture-task', 1, 8.0, 7.0, 6.0, ?, ?, ?)",
            (comp, decision, overrode),
        )
    conn.commit()
    conn.close()


def run_evaluator(db_path, days):
    """Import the evaluator against the fixture and return (accuracy, recs)."""
    code = f"""
import sys, json
sys.path.insert(0, {str(SRC.parent)!r})
import loop_evaluator as ev_mod

ev = ev_mod.LoopEvaluator({db_path!r})

# The PRE-FIX module exposes these with no window parameter. Fall back to the
# no-arg form so that artifact is still exercised BEHAVIOURALLY (returning
# all-time numbers) instead of dying on a TypeError, which would prove only
# that the signature changed and not that the window works.
try:
    acc = ev.get_decision_accuracy({days})
    recs = ev.get_threshold_recommendations({days})
except TypeError:
    acc = ev.get_decision_accuracy()
    recs = ev.get_threshold_recommendations()

print(json.dumps({{"accuracy": acc, "recs": recs}}))
ev.db.close()
"""
    env = dict(os.environ)
    env["SCORE_DB_PATH"] = db_path
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    if out.returncode != 0:
        print("    stderr:", out.stderr.strip()[:500])
        return None, None
    import json

    payload = json.loads(out.stdout.strip().splitlines()[-1])
    return payload["accuracy"], payload["recs"]


def main():
    if not SRC.exists():
        print(f"FATAL: evaluator source not found at {SRC}")
        return 2

    tmpdir = tempfile.mkdtemp(prefix="loop-eval-repro-")
    db_path = os.path.join(tmpdir, "fixture.db")
    build_fixture(db_path)

    print("loop_evaluator accuracy-window + direction regression")
    print(f"  fixture: {db_path}")

    # ── Window scoping ────────────────────────────────────────────────────
    acc7, recs7 = run_evaluator(db_path, 7)
    if acc7 is None:
        print("  [FAIL] evaluator did not run against fixture")
        return 1

    # 4 labelled rows in window, 3 accepted = 75.0%
    check(
        "7-day accuracy uses ONLY in-window rows",
        acc7["total_feedback"] == 4,
        f"total_feedback={acc7['total_feedback']} (want 4; unscoped would be 14)",
    )
    check(
        "7-day accuracy is 75.0%",
        acc7["accuracy_pct"] == 75.0,
        f"got {acc7['accuracy_pct']}% (unscoped reports 21.4%)",
    )

    acc30, _ = run_evaluator(db_path, 30)
    check(
        "30-day window still excludes the 200-day rows",
        acc30 is not None and acc30["total_feedback"] == 4,
        f"total_feedback={acc30['total_feedback'] if acc30 else 'ERR'}",
    )

    acc_all, _ = run_evaluator(db_path, 3650)
    check(
        "a wide window DOES include stale rows (proves the filter works, not that it drops data)",
        acc_all is not None and acc_all["total_feedback"] == 14,
        f"total_feedback={acc_all['total_feedback'] if acc_all else 'ERR'} (want 14)",
    )

    # ── Recommendation direction ──────────────────────────────────────────
    if not recs7:
        check("STOP recommendation produced", False, "no recs returned")
    else:
        rec = recs7[0]
        cur = rec.get("current_value")
        prop = rec.get("proposed_value")
        text = rec.get("recommendation", "")
        check("recommendation reports current_value", cur is not None, f"current_value={cur}")
        check(
            "direction word matches the arithmetic",
            cur is not None
            and (
                (prop > cur and "raising" in text)
                or (prop < cur and "lowering" in text)
            ),
            f"proposed={prop} current={cur} text={text[:80]!r}",
        )
        check(
            "text does not hardcode a stale 8.0 threshold",
            "8.0" not in text or cur == 8.0,
            f"text={text[:80]!r}",
        )

    print()
    # ── Class sweep: no feedback query may be unscoped ────────────────────
    # Fixing the three call sites fixes those sites. This asserts the CLASS:
    # every query in the evaluator that reads user_overrode must carry a
    # timestamp bound, so the next unscoped one added fails here.
    src = SRC.read_text()
    imports = [ln for ln in src.splitlines() if ln.startswith(("import ", "from "))]
    body = "\n".join(ln for ln in src.splitlines() if ln not in imports)
    # Split on def to examine each method's query text.
    chunks = body.split("\n    def ")
    unscoped = []
    for chunk in chunks:
        name = chunk.split("(")[0].strip()
        if "user_overrode" not in chunk:
            continue
        # Aggregate/report-only reads are exempt: they consume already-scoped
        # rows, or they are the accuracy/weight functions we scoped above.
        for stmt in chunk.split('"""'):
            if "user_overrode" in stmt and "SELECT" in stmt.upper():
                has_bound = "timestamp >=" in stmt or "timestamp >" in stmt
                if not has_bound:
                    unscoped.append(name or "<module>")
    check(
        "no method reads user_overrode without a timestamp bound (class sweep)",
        not unscoped,
        f"unscoped: {sorted(set(unscoped))}" if unscoped else "all feedback queries scoped",
    )

    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

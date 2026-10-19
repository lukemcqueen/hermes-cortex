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
    """Import the evaluator against the fixture and return (accuracy, recs).

    The windowed call is made DIRECTLY: a module without the `days` parameter
    raises TypeError here and the caller records that as a hard failure. It
    must not fall back to the no-argument form, because that fallback would
    let this regression adapt to the exact pre-fix signature it exists to
    catch (an adapted run returns all-time numbers and can drift through the
    remaining checks).
    """
    code = f"""
import sys, json
sys.path.insert(0, {str(SRC.parent)!r})
import loop_evaluator as ev_mod

ev = ev_mod.LoopEvaluator({db_path!r})
acc = ev.get_decision_accuracy({days})
recs = ev.get_threshold_recommendations({days})
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
    # Fixing the three call sites fixes those sites. This asserts the CLASS by
    # PARSING the module: every `.execute(<sql>, <params>)` whose SQL reads
    # user_overrode must bind a timestamp predicate. An AST walk is used rather
    # than a text search so a name in a docstring/comment cannot create a false
    # positive, a wrapped call cannot be missed, and the params tuple is
    # inspected (a `%s`/`?` placeholder in the SQL with no matching parameter is
    # reported as unbound rather than assumed correct).
    import ast

    tree = ast.parse(SRC.read_text())
    unscoped, unbound = [], []

    def _sql_and_params(node):
        """Return (sql, params_node) for an .execute(...) call, else (None, None)."""
        if not isinstance(node, ast.Call):
            return None, None
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "execute"):
            return None, None
        if not node.args:
            return None, None
        sql_node = node.args[0]
        if isinstance(sql_node, ast.Constant) and isinstance(sql_node.value, str):
            params = node.args[1] if len(node.args) > 1 else None
            return sql_node.value, params
        return None, None

    class MethodVisitor(ast.NodeVisitor):
        def __init__(self):
            self.current = "<module>"

        def visit_FunctionDef(self, node):
            prev, self.current = self.current, node.name
            self.generic_visit(node)
            self.current = prev

        def visit_Call(self, node):
            sql, params = _sql_and_params(node)
            if sql and "user_overrode" in sql:
                has_bound = "timestamp >=" in sql or "timestamp >" in sql
                if not has_bound:
                    unscoped.append(self.current)
                elif "?" in sql and params is None:
                    # Bound in text but no parameter supplied -> the predicate
                    # cannot actually constrain anything.
                    unbound.append(self.current)
            self.generic_visit(node)

    MethodVisitor().visit(tree)

    check(
        "no method reads user_overrode without a timestamp predicate (AST sweep)",
        not unscoped,
        f"unscoped: {sorted(set(unscoped))}" if unscoped else "all feedback queries scoped",
    )
    check(
        "every timestamp predicate also binds its parameter",
        not unbound,
        f"placeholder without params: {sorted(set(unbound))}" if unbound else "all bound",
    )

    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

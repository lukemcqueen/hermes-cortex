#!/usr/bin/env python3
"""Runnable regression for the config-patch window binding (2026-10-26 weekly run).

Why this exists: commit 83575b31 scoped the evaluator's recommendation queries to
the report window but left `generate_config_patch()` without a `days` parameter
while its body called `self.get_threshold_recommendations(days)` and
`self.get_weight_recommendations(days)`. `days` was then an unbound name, so
EVERY config-patch path raised NameError:

    python3 loop_evaluator.py --config-patch   -> NameError: name 'days' is not defined
    python3 auto_apply.py                      -> NameError: name 'days' is not defined

i.e. the self-tuning half of the pipeline was dead in production, while the
plain report still worked because `generate_report(days)` passes the window.

This test pins BOTH halves of the class:
  1. `generate_config_patch` accepts and BINDS a window (calling it must not raise),
     and the window it is given reaches the recommendation queries it delegates to.
  2. No method in loop_evaluator binds a bare `days` name it does not own
     (AST sweep -- the general shape, so the next such edit is caught).

Hermetic: builds a temp SQLite DB; never touches the live DB.

Usage:  python3 tests/run_loop_evaluator_config_patch_window_repro.py
Exit 0 = config-patch generation is wired to the window.
"""
import ast
import importlib.util
import re
import sqlite3
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
CREATE TABLE content_assets (
  hash TEXT PRIMARY KEY, kind TEXT, text TEXT, created TEXT
);
"""


def build_fixture(path):
    """In-window rows only; enough labelled feedback to exercise both
    recommendation paths (threshold recs need STOP overrides)."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    rows = [
        ("datetime('now','-1 days')", "STOP ✓", 1, 9.0, 8.0, 7.0, 8.0),
        ("datetime('now','-2 days')", "STOP ✓", 1, 8.8, 7.5, 6.0, 7.5),
        ("datetime('now','-3 days')", "LOOP", 0, 5.0, 5.0, 4.0, 4.6),
        ("datetime('now','-4 days')", "MOVE_ON", 0, 3.0, 4.0, 3.0, 3.3),
    ]
    for ts, decision, overrode, c, q, p, comp in rows:
        conn.execute(
            f"INSERT INTO loop_cycles (timestamp, task_id, cycle_num, completeness,"
            f" quality, progress, composite, decision, user_overrode)"
            f" VALUES ({ts}, 'cfg-fixture', 1, ?, ?, ?, ?, ?, ?)",
            (c, q, p, comp, decision, overrode),
        )
    conn.commit()
    conn.close()


def load_module():
    spec = importlib.util.spec_from_file_location("loop_evaluator_under_test", SRC)
    assert spec is not None and spec.loader is not None, f"cannot load {SRC}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loop_evaluator_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    print("loop_evaluator config-patch window repro")
    print(f"  source: {SRC}")

    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "fixture.db")
        build_fixture(db)
        mod = load_module()

        ev = mod.LoopEvaluator(db)

        # ── 1. generate_config_patch must accept a window and not raise ──────
        # (Before the fix this raised NameError: name 'days' is not defined.)
        try:
            patch = ev.generate_config_patch(days=7)
            raised = None
        except Exception as exc:  # noqa: BLE001
            patch, raised = None, exc
        check(
            "generate_config_patch(days=7) does not raise",
            raised is None,
            "" if raised is None else f"{type(raised).__name__}: {raised}",
        )
        check(
            "returns a patch dict with 'changes'",
            isinstance(patch, dict) and "changes" in patch,
        )

        # ── 2. the window actually REACHES the delegated queries ────────────
        # Record the `days` argument each recommendation query is called with;
        # an ignored window (or a hardcoded default) fails this.
        seen = {}

        orig_t = mod.LoopEvaluator.get_threshold_recommendations
        orig_w = mod.LoopEvaluator.get_weight_recommendations

        def spy_t(self, days=7):
            seen["threshold"] = days
            return orig_t(self, days)

        def spy_w(self, days=7):
            seen["weight"] = days
            return orig_w(self, days)

        mod.LoopEvaluator.get_threshold_recommendations = spy_t
        mod.LoopEvaluator.get_weight_recommendations = spy_w
        try:
            try:
                ev.generate_config_patch(days=30)
            except Exception:  # noqa: BLE001 — pre-fix shape is reported below, not traced
                pass
        finally:
            mod.LoopEvaluator.get_threshold_recommendations = orig_t
            mod.LoopEvaluator.get_weight_recommendations = orig_w

        check(
            "days reaches get_threshold_recommendations",
            seen.get("threshold") == 30,
            f"got {seen.get('threshold')!r}",
        )
        check(
            "days reaches get_weight_recommendations",
            seen.get("weight") == 30,
            f"got {seen.get('weight')!r}",
        )

        # ── 3. the CLI path must also not raise ─────────────────────────────
        import subprocess
        for flag in ("--config-patch", "--json"):
            r = subprocess.run(
                [sys.executable, str(SRC), flag, "--days", "7", "--db", db],
                capture_output=True, text=True, timeout=60,
            )
            combined = (r.stdout or "") + (r.stderr or "")
            check(
                f"CLI {flag} exits 0 without NameError",
                r.returncode == 0 and "NameError" not in combined,
                f"rc={r.returncode}" + (f" :: {r.stderr.strip().splitlines()[-1]}" if r.returncode else ""),
            )

        ev.close()

    # ── 4. AST sweep: no method binds a bare `days` it does not own ─────────
    # This is the CLASS check -- it fails on the next edit of the same shape,
    # not just on this one call site.
    tree = ast.parse(SRC.read_text())
    unbound = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = {a.arg for a in node.args.args + node.args.kwonlyargs}
            if node.args.vararg:
                params.add(node.args.vararg.arg)
            if node.args.kwarg:
                params.add(node.args.kwarg.arg)
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and n.id == "days" and isinstance(n.ctx, ast.Load) and "days" not in params:
                    unbound.append(f"{node.name}() line {n.lineno}")
    check(
        "no method loads an unbound `days` name",
        not unbound,
        "; ".join(unbound),
    )

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
        return 1
    print("ALL PASS — config-patch generation is window-bound")
    return 0


if __name__ == "__main__":
    sys.exit(main())
